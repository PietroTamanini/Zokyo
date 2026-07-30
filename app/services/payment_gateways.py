"""Cobranças com Asaas real, provedores compatíveis e fallback seguro."""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from urllib.parse import urlencode

import requests
from flask import current_app, url_for

from app.models import Configuracao, OrdemServico, Transacao

SUPPORTED_GATEWAYS = {"manual", "pix", "sandbox", "asaas", "mercadopago", "gerencianet"}
SUPPORTED_METHODS = {"pix", "boleto", "link"}
ASAAS_METHODS = {"pix": "PIX", "boleto": "BOLETO", "link": "UNDEFINED"}


@dataclass(frozen=True)
class PaymentResult:
    gateway: str
    method: str
    provider_id: str
    status: str
    payment_url: str | None = None
    link: str | None = None
    barcode: str | None = None
    payload: str | None = None
    expires_at: datetime | None = None
    raw: dict | None = None

    def to_dict(self) -> dict:
        return {
            "payment_gateway": self.gateway,
            "payment_method": self.method,
            "payment_provider_id": self.provider_id,
            "payment_status": self.status,
            "payment_url": self.payment_url,
            "link": self.link,
            "barcode": self.barcode,
            "payload": self.payload,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


class PaymentGatewayError(RuntimeError):
    """Erro controlado de gateway de pagamento."""


def _digits(value: str | None, limit: int | None = None) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    return digits[:limit] if limit else digits


def _clean_emv(value: str | None, limit: int) -> str:
    cleaned = re.sub(r"[^A-Z0-9 .,\-_/]", "", str(value or "").upper())
    return cleaned[:limit] or "ZOKYO"


def _emv(tag: str, value: str) -> str:
    return f"{tag}{len(value):02d}{value}"


def _crc16(payload: str) -> str:
    poly = 0x1021
    crc = 0xFFFF
    for byte in payload.encode("ascii", errors="ignore"):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ poly) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def _pix_payload(transacao: Transacao, cfg: Configuracao) -> str | None:
    key = (cfg.pix_chave or "").strip()
    if not key:
        return None
    merchant_account = _emv("00", "br.gov.bcb.pix") + _emv("01", key[:77])
    amount = f"{Decimal(transacao.valor or 0):.2f}"
    reference = f"ZOKYO{transacao.id:04d}"
    payload = (
        _emv("00", "01")
        + _emv("26", merchant_account)
        + _emv("52", "0000")
        + _emv("53", "986")
        + _emv("54", amount)
        + _emv("58", "BR")
        + _emv("59", _clean_emv(cfg.nome_empresa, 25))
        + _emv("60", _clean_emv(cfg.cidade or "BRASIL", 15))
        + _emv("62", _emv("05", reference[:25]))
    )
    partial = payload + "6304"
    return partial + _crc16(partial)


def _provider_configured(gateway: str) -> bool:
    prefix = {
        "asaas": "ASAAS",
        "mercadopago": "MERCADOPAGO",
        "gerencianet": "GERENCIANET",
    }.get(gateway)
    if not prefix:
        return True
    token = current_app.config.get(f"{prefix}_API_KEY") or current_app.config.get(f"{prefix}_TOKEN")
    return bool(token)


def _asaas_token() -> str | None:
    return (
        current_app.config.get("ASAAS_API_KEY")
        or current_app.config.get("ASAAS_TOKEN")
        or current_app.config.get("ASAAS_ACCESS_TOKEN")
    )


def _asaas_base_url() -> str:
    explicit = (current_app.config.get("ASAAS_BASE_URL") or "").strip().rstrip("/")
    if explicit:
        return explicit
    sandbox = bool(current_app.config.get("ASAAS_SANDBOX", True))
    return "https://api-sandbox.asaas.com/v3" if sandbox else "https://api.asaas.com/v3"


def _asaas_timeout() -> float:
    return float(current_app.config.get("ASAAS_TIMEOUT", 15))


def _asaas_headers() -> dict[str, str]:
    token = _asaas_token()
    if not token:
        raise PaymentGatewayError("ASAAS_API_KEY não configurado.")
    return {
        "accept": "application/json",
        "content-type": "application/json",
        "access_token": token,
        "user-agent": current_app.config.get("ASAAS_USER_AGENT") or "Zokyo/1.0 (Flask)",
    }


def _asaas_request(method: str, path: str, **kwargs) -> dict:
    try:
        response = requests.request(
            method,
            f"{_asaas_base_url()}{path}",
            headers=_asaas_headers(),
            timeout=_asaas_timeout(),
            **kwargs,
        )
    except requests.RequestException as exc:
        raise PaymentGatewayError("Falha de comunicação com o Asaas.") from exc

    if response.status_code >= 400:
        try:
            payload = response.json()
        except ValueError:
            payload = {"message": response.text[:300]}
        errors = payload.get("errors") if isinstance(payload, dict) else None
        message = "; ".join(item.get("description", "") for item in errors or [] if isinstance(item, dict))
        raise PaymentGatewayError(message or payload.get("message") or "Asaas recusou a cobrança.")
    try:
        return response.json()
    except ValueError as exc:
        raise PaymentGatewayError("Asaas retornou uma resposta inválida.") from exc


def _billing_customer(transacao: Transacao):
    if not transacao.os_id:
        return None
    order = OrdemServico.query.filter_by(id=transacao.os_id).first()
    return order.cliente if order and order.cliente else None


def _asaas_customer_payload(transacao: Transacao) -> dict:
    cliente = _billing_customer(transacao)
    document = _digits(getattr(cliente, "cpf", None) or getattr(cliente, "cnpj", None)) if cliente else ""
    phone = _digits(getattr(cliente, "telefone", None), 20) if cliente else ""
    payload = {
        "name": (getattr(cliente, "nome", None) or f"Cliente cobrança {transacao.id:04d}")[:120],
        "externalReference": f"zokyo_cliente_{cliente.id}" if cliente else f"zokyo_transacao_{transacao.id}",
        "notificationDisabled": True,
    }
    if document:
        payload["cpfCnpj"] = document
    if phone:
        payload["mobilePhone"] = phone
    if cliente and cliente.email:
        payload["email"] = cliente.email[:254]
    if cliente and cliente.cep:
        payload["postalCode"] = cliente.cep
    if cliente and cliente.endereco:
        payload["address"] = cliente.endereco[:255]
    if cliente and cliente.numero_casa:
        payload["addressNumber"] = cliente.numero_casa[:20]
    return payload


def _asaas_find_customer(external_reference: str) -> str | None:
    result = _asaas_request("GET", "/customers", params={"externalReference": external_reference, "limit": 1})
    data = result.get("data") or []
    return data[0].get("id") if data and isinstance(data[0], dict) else None


def _asaas_customer_id(transacao: Transacao) -> str:
    payload = _asaas_customer_payload(transacao)
    existing = _asaas_find_customer(payload["externalReference"])
    if existing:
        return existing
    created = _asaas_request("POST", "/customers", data=json.dumps(payload))
    customer_id = created.get("id")
    if not customer_id:
        raise PaymentGatewayError("Asaas não retornou o ID do cliente.")
    return customer_id


def _parse_due_date(expires_at: datetime) -> str:
    return expires_at.date().isoformat() if isinstance(expires_at, datetime) else date.today().isoformat()


def _asaas_status(status: str | None) -> str:
    status_map = {
        "PENDING": "pending",
        "CONFIRMED": "confirmed",
        "RECEIVED": "received",
        "RECEIVED_IN_CASH": "received",
        "OVERDUE": "overdue",
        "REFUNDED": "refunded",
        "CANCELED": "cancelled",
        "DELETED": "cancelled",
    }
    return status_map.get(str(status or "").upper(), "pending")


def _generate_asaas_payment(transacao: Transacao, method: str, expires_at: datetime) -> PaymentResult:
    billing_type = ASAAS_METHODS.get(method)
    if not billing_type:
        raise ValueError("Forma de pagamento inválida para Asaas.")
    customer_id = _asaas_customer_id(transacao)
    payload = {
        "customer": customer_id,
        "billingType": billing_type,
        "value": float(Decimal(transacao.valor or 0)),
        "dueDate": _parse_due_date(expires_at),
        "description": (transacao.descricao or f"Cobrança Zokyo #{transacao.id:04d}")[:500],
        "externalReference": f"zokyo_transacao_{transacao.id}",
    }
    payment = _asaas_request("POST", "/payments", data=json.dumps(payload))
    provider_id = payment.get("id")
    if not provider_id:
        raise PaymentGatewayError("Asaas não retornou o ID da cobrança.")

    pix_payload = None
    if method == "pix":
        try:
            qr_code = _asaas_request("GET", f"/payments/{provider_id}/pixQrCode")
            pix_payload = qr_code.get("payload")
        except PaymentGatewayError:
            current_app.logger.warning("Asaas criou cobrança, mas não retornou QR Code Pix.", exc_info=True)

    return PaymentResult(
        gateway="asaas",
        method=method,
        provider_id=provider_id,
        status=_asaas_status(payment.get("status")),
        payment_url=payment.get("invoiceUrl") or payment.get("bankSlipUrl"),
        link=payment.get("invoiceUrl") or payment.get("bankSlipUrl"),
        barcode=payment.get("identificationField") or payment.get("nossoNumero"),
        payload=pix_payload,
        expires_at=expires_at,
        raw=payment,
    )


def generate_payment(transacao: Transacao, gateway: str = "pix", method: str = "pix", days: int = 7) -> PaymentResult:
    gateway = (gateway or "pix").strip().lower()
    method = (method or "pix").strip().lower()
    if gateway not in SUPPORTED_GATEWAYS:
        raise ValueError("Gateway de pagamento inválido.")
    if method not in SUPPORTED_METHODS:
        raise ValueError("Forma de pagamento inválida.")
    if transacao.tipo != "receita":
        raise ValueError("Somente receitas podem gerar cobrança.")
    if transacao.status == "cancelado":
        raise ValueError("Cobrança cancelada não pode gerar pagamento.")

    cfg = Configuracao.get()
    expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=max(1, min(int(days or 7), 90)))
    if gateway == "asaas" and _provider_configured(gateway):
        return _generate_asaas_payment(transacao, method, expires_at)

    provider_id = f"{gateway}_{uuid.uuid4().hex[:20]}"
    payload = _pix_payload(transacao, cfg) if method == "pix" else None
    base_link = url_for("pages.cobrancas_visualizar_alias", id=transacao.id, _external=True)

    if gateway in {"asaas", "mercadopago", "gerencianet"} and not _provider_configured(gateway):
        gateway = "pix" if payload else "manual"
        provider_id = f"{gateway}_{uuid.uuid4().hex[:20]}"

    query = {
        "cobranca": f"{transacao.id:04d}",
        "valor": f"{Decimal(transacao.valor or 0):.2f}",
        "gateway": gateway,
        "metodo": method,
    }
    payment_url = f"{base_link}?{urlencode(query)}"
    barcode_source = payload or f"{transacao.id}:{transacao.valor}:{provider_id}"
    barcode = hashlib.sha256(barcode_source.encode("utf-8")).hexdigest()[:44].upper()

    return PaymentResult(
        gateway=gateway,
        method=method,
        provider_id=provider_id,
        status="pending",
        payment_url=payment_url,
        link=payment_url,
        barcode=barcode,
        payload=payload,
        expires_at=expires_at,
    )


def apply_payment(transacao: Transacao, result: PaymentResult) -> Transacao:
    transacao.payment_gateway = result.gateway
    transacao.payment_method = result.method
    transacao.payment_provider_id = result.provider_id
    transacao.payment_status = result.status
    transacao.payment_url = result.payment_url
    transacao.payment_link = result.link
    transacao.payment_barcode = result.barcode
    transacao.payment_payload = result.payload
    transacao.payment_expires_at = result.expires_at
    if result.raw:
        transacao.payment_payload = result.payload
    if result.method:
        transacao.forma_pagamento = result.method
    return transacao
