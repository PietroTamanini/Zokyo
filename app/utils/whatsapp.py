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

# Hosts permitidos para o wpp-server (além de localhost/127.0.0.1)
# Adicione entradas se seu servidor WPP estiver em outra máquina da rede interna.
_WPP_ALLOWED_HOSTS = {"localhost", "127.0.0.1"}


def _is_safe_wpp_url(url: str) -> bool:
    """
    H05: Valida que a URL do wpp-server é segura.
    Rejeita URLs que apontem para serviços internos inesperados.
    """
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return False

    if parsed.scheme not in ("http", "https"):
        return False

    hostname = parsed.hostname or ""
    if not hostname:
        return False

    # Permite hosts explicitamente whitelistados
    if hostname.lower() in _WPP_ALLOWED_HOSTS:
        return True

    # Resolve o hostname e rejeita IPs privados/reservados
    try:
        addr = socket.getaddrinfo(hostname, None)[0][4][0]
        ip   = ipaddress.ip_address(addr)
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast):
            logger.warning("[WPP] URL rejeitada (IP privado/reservado): %s → %s", url, addr)
            return False
    except (socket.gaierror, ValueError):
        # Não conseguiu resolver → rejeita por segurança
        logger.warning("[WPP] URL rejeitada (não resolveu): %s", url)
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
        pass
    env_url = os.environ.get("WPP_SERVER_URL", "").strip()
    return env_url.rstrip("/") if env_url else None


def _wpp_headers() -> dict:
    secret  = os.environ.get("WPP_SECRET", "").strip()
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["X-Wpp-Token"] = secret
    else:
        logger.warning("[WPP] WPP_SECRET não configurado.")
    return headers


def enviar_whatsapp(numero: str, mensagem: str) -> dict:
    link    = _wa_me_link(numero, mensagem)
    srv_url = _wpp_url()

    if not srv_url:
        return {
            "modo":    "simulacao",
            "sucesso": False,
            "link":    link,
            "aviso":   "Servidor WhatsApp não configurado. Use o link para envio manual.",
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
            return {"modo": "wpp-server", "sucesso": True, "link": link}

        logger.error("[WPP] Erro do servidor: %s", data)
        return {
            "modo":    "wpp-server",
            "sucesso": False,
            "link":    link,
            "erro":    data.get("erro", str(data)),
        }

    except RequestException as exc:
        logger.warning("[WPP] wpp-server offline (%s)", exc)
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
    srv_url = _wpp_url()
    if not srv_url:
        return {"status": "desconectado", "modo": "simulacao"}

    if not _is_safe_wpp_url(srv_url):
        return {"status": "erro", "modo": "wpp-server",
                "erro": "URL bloqueada por política de segurança."}

    try:
        resp = requests.get(
            f"{srv_url}/status",
            headers=_wpp_headers(),
            timeout=5,
            allow_redirects=False,
        )
        data = resp.json()
        return {"status": data.get("status", "desconhecido"), "modo": "wpp-server"}
    except RequestException:
        return {"status": "offline", "modo": "wpp-server",
                "erro": f"Servidor não responde em {srv_url}"}
    except Exception as exc:
        return {"status": "erro", "modo": "wpp-server", "erro": str(exc)}


def mensagem_os_pronta(os) -> str:
    total        = float(os.valor_total or 0)
    aparelho     = f"{os.marca or ''} {os.modelo or ''}".strip() or "Aparelho"
    solucao      = os.solucao or "Reparo concluído"
    cliente_nome = os.cliente.nome if os.cliente else "Cliente"

    return (
        f"Olá, *{cliente_nome}*! 👋\n\n"
        f"Seu aparelho está *pronto* para retirada! ✅\n\n"
        f"📋 OS *#{os.id:04d}*\n"
        f"📱 {aparelho}\n"
        f"🔧 {solucao}\n"
        f"💰 Total: *R$ {total:.2f}*\n\n"
        f"*{cfg.nome_empresa if cfg else 'Zokyo Platform'} — Joinville SC*\n"
        f"Seg–Sex 9h–18h | Sáb 9h–13h"
    )
