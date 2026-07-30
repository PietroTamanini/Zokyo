"""
utils/whatsapp.py
-----------------
Fix H05: validação de SSRF em wpp_server_url.
  - Aceita apenas URLs HTTP/HTTPS.
  - Bloqueia IPs privados, loopback e link-local exceto localhost explícito.
  - Usa allowlist de hosts configurável.
  - Timeout curto; sem redirect.
"""
import ipaddress
import logging
import os
import re
import socket
import urllib.parse

import requests
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)

_WPP_ALLOWED_HOSTS = {"localhost", "127.0.0.1"}
_META_GRAPH_URL = "https://graph.facebook.com"


def _allowed_hosts() -> set[str]:
    configured = {
        item.strip().lower()
        for item in os.environ.get("WPP_ALLOWED_HOSTS", "").split(",")
        if item.strip()
    }
    return _WPP_ALLOWED_HOSTS | configured


def _is_safe_wpp_url(url: str) -> bool:
    """
    Valida um gateway externo contra SSRF e configuracoes ambiguas.
    """
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return False

    if parsed.scheme not in ("http", "https") or parsed.username or parsed.password:
        return False

    hostname = (parsed.hostname or "").lower()
    if not hostname or parsed.query or parsed.fragment:
        return False

    allowed_hosts = _allowed_hosts()
    if hostname not in allowed_hosts:
        logger.warning("[WhatsApp] Host não permitido: %s", hostname)
        return False

    is_localhost = hostname in _WPP_ALLOWED_HOSTS
    if parsed.scheme != "https" and not is_localhost:
        logger.warning("[WhatsApp] HTTPS obrigatório para gateway remoto: %s", hostname)
        return False

    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(hostname, parsed.port)}
        for addr in addresses:
            ip = ipaddress.ip_address(addr)
            blocked = ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast
            if blocked and not is_localhost:
                logger.warning("[WhatsApp] Endereço bloqueado para %s: %s", hostname, addr)
                return False
    except (socket.gaierror, ValueError):
        logger.warning("[WhatsApp] Host não resolvido: %s", hostname)
        return False

    return True


def _normalizar_numero(numero: str) -> str:
    digits = re.sub(r"\D", "", numero)
    if not digits.startswith("55"):
        digits = "55" + digits
    return digits


def _wa_me_link(numero: str, mensagem: str) -> str:
    return f"https://wa.me/{_normalizar_numero(numero)}?text={urllib.parse.quote(mensagem)}"


def _wpp_url() -> str | None:
    try:
        from app.models import Configuracao
        cfg = Configuracao.get()
        url = (cfg.wpp_server_url or "").strip()
        if url:
            return url.rstrip("/")
    except Exception:
        logger.debug("[WhatsApp] Configuração do gateway indisponível no banco.", exc_info=True)
    env_url = os.environ.get("WPP_SERVER_URL", "").strip()
    return env_url.rstrip("/") if env_url else None


def _wpp_headers() -> dict:
    secret  = os.environ.get("WPP_SECRET", "").strip()
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["X-Wpp-Token"] = secret
    return headers


def _cloud_config() -> tuple[str, str, str] | None:
    token = os.environ.get("WHATSAPP_CLOUD_API_TOKEN", "").strip()
    phone_id = os.environ.get("WHATSAPP_CLOUD_PHONE_NUMBER_ID", "").strip()
    version = os.environ.get("WHATSAPP_CLOUD_API_VERSION", "").strip()
    if not token or not phone_id or not re.fullmatch(r"v\d+\.\d+", version):
        return None
    if not phone_id.isdigit():
        return None
    return token, phone_id, version


def _send_cloud_api(numero: str, mensagem: str, link: str) -> dict:
    token, phone_id, version = _cloud_config()
    try:
        response = requests.post(
            f"{_META_GRAPH_URL}/{version}/{phone_id}/messages",
            json={
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": _normalizar_numero(numero),
                "type": "text",
                "text": {"preview_url": False, "body": mensagem},
            },
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=10,
            allow_redirects=False,
        )
        if response.status_code in (200, 201):
            payload = response.json()
            message_id = ((payload.get("messages") or [{}])[0]).get("id")
            return {"modo": "whatsapp_cloud", "sucesso": True, "link": link, "message_id": message_id}
        logger.error("[WhatsApp Cloud] Falha HTTP %s", response.status_code)
        return {
            "modo": "whatsapp_cloud", "sucesso": False, "link": link,
            "erro": f"WhatsApp Cloud API retornou HTTP {response.status_code}.",
        }
    except (RequestException, ValueError, TypeError) as exc:
        logger.warning("[WhatsApp Cloud] Envio indisponivel: %s", type(exc).__name__)
        return {
            "modo": "fallback", "sucesso": False, "link": link,
            "aviso": "WhatsApp Cloud API indisponivel. Use o link para envio manual.",
        }


def enviar_whatsapp(numero: str, mensagem: str) -> dict:
    link    = _wa_me_link(numero, mensagem)
    if _cloud_config():
        return _send_cloud_api(numero, mensagem, link)
    srv_url = _wpp_url()

    if not srv_url or not os.environ.get("WPP_SECRET", "").strip():
        return {
            "modo":    "simulacao",
            "sucesso": False,
            "link":    link,
            "aviso":   "Gateway seguro não configurado. Use o link para envio manual.",
        }

    # H05: valida a URL antes de fazer a requisição
    if not _is_safe_wpp_url(srv_url):
        logger.error("[WPP] URL rejeitada por política SSRF: %s", srv_url)
        return {
            "modo":    "simulacao",
            "sucesso": False,
            "link":    link,
            "erro":    "URL do servidor WhatsApp inválida ou bloqueada por política de segurança.",
        }

    try:
        resp = requests.post(
            f"{srv_url}/send",
            json={"number": _normalizar_numero(numero), "message": mensagem},
            headers=_wpp_headers(),
            timeout=10,
            allow_redirects=False,   # Nunca seguir redirects (anti-SSRF)
        )
        data = resp.json()

        if resp.status_code == 200 and data.get("ok"):
            return {"modo": "gateway", "sucesso": True, "link": link}

        logger.error("[WPP] Erro do servidor: %s", data)
        return {
            "modo":    "gateway",
            "sucesso": False,
            "link":    link,
            "erro":    data.get("erro", str(data)),
        }

    except RequestException as exc:
        logger.warning("[WhatsApp] Gateway offline (%s)", exc)
        return {
            "modo":    "fallback",
            "sucesso": False,
            "link":    link,
            "aviso":   "Servidor WhatsApp offline. Use o link para envio manual.",
        }
    except Exception as exc:
        logger.error("[WPP] Erro inesperado: %s", exc)
        return {"modo": "fallback", "sucesso": False, "link": link, "erro": str(exc)}


def status_wpp() -> dict:
    if _cloud_config():
        return {"status": "configurado", "modo": "whatsapp_cloud"}
    srv_url = _wpp_url()
    if not srv_url or not os.environ.get("WPP_SECRET", "").strip():
        return {"status": "desconectado", "modo": "simulacao"}

    if not _is_safe_wpp_url(srv_url):
        return {"status": "erro", "modo": "gateway",
                "erro": "URL bloqueada por política de segurança."}

    try:
        resp = requests.get(
            f"{srv_url}/status",
            headers=_wpp_headers(),
            timeout=5,
            allow_redirects=False,
        )
        data = resp.json()
        return {"status": data.get("status", "desconhecido"), "modo": "gateway"}
    except RequestException:
        return {"status": "offline", "modo": "gateway",
                "erro": f"Servidor não responde em {srv_url}"}
    except Exception as exc:
        return {"status": "erro", "modo": "gateway", "erro": str(exc)}


def mensagem_os_pronta(os) -> str:
    total        = float(os.valor_total or 0)
    aparelho     = f"{os.marca or ''} {os.modelo or ''}".strip() or "Aparelho"
    solucao      = os.solucao or "Reparo concluído"
    cliente_nome = os.cliente.nome if os.cliente else "Cliente"
    codigo_os = getattr(os, "codigo_os", f"{os.id:04d}")

    try:
        from app.models import Configuracao
        cfg = Configuracao.get()
    except Exception:
        cfg = None

    return (
        f"Olá, *{cliente_nome}*! 👋\n\n"
        f"Seu aparelho está *pronto* para retirada! ✅\n\n"
        f"📋 OS *#{codigo_os}*\n"
        f"📱 {aparelho}\n"
        f"🔧 {solucao}\n"
        f"💰 Total: *R$ {total:.2f}*\n\n"
        f"*{cfg.nome_empresa if cfg else 'Zokyo Platform'} — Joinville SC*\n"
        f"Seg–Sex 9h–18h | Sáb 9h–13h"
    )
