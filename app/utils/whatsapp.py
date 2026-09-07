"""Envio de WhatsApp pela Meta Cloud API com fallback manual seguro."""
import logging
import os
import re
import urllib.parse

import requests
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)

_META_GRAPH_URL = "https://graph.facebook.com"


def _normalizar_numero(numero: str) -> str:
    digits = re.sub(r"\D", "", numero)
    if not digits.startswith("55"):
        digits = "55" + digits
    return digits


def _wa_me_link(numero: str, mensagem: str) -> str:
    return f"https://wa.me/{_normalizar_numero(numero)}?text={urllib.parse.quote(mensagem)}"


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
    return {
        "modo": "simulacao",
        "sucesso": False,
        "link": link,
        "aviso": "Meta WhatsApp Cloud API não configurada. Use o link para envio manual.",
    }


def status_wpp() -> dict:
    if _cloud_config():
        return {"status": "configurado", "modo": "whatsapp_cloud"}
    return {"status": "desconectado", "modo": "simulacao"}


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
