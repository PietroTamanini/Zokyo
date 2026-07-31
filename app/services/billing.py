"""Abstração de billing; somente provider sandbox, sem cobrança real."""
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone

from app.extensions import db
from app.models import BillingEvent, OrganizationSubscription, Plan

EVENT_STATUS = {
    "subscription.activated": "active",
    "subscription.past_due": "past_due",
    "subscription.cancelled": "cancelled",
}


def _now():
    return datetime.now(timezone.utc)


def verify_sandbox_signature(raw_body: bytes, signature: str) -> bool:
    secret = os.environ.get("BILLING_SANDBOX_SECRET", "").encode()
    if not secret or not signature.startswith("sha256="):
        return False
    expected = hmac.new(secret, raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature[7:], expected)


def process_sandbox_event(raw_body: bytes, signature: str) -> tuple[BillingEvent, bool]:
    if not verify_sandbox_signature(raw_body, signature):
        raise ValueError("Assinatura do webhook invalida.")
    try:
        payload = json.loads(raw_body)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Payload JSON inválido.") from exc
    event_id = str(payload.get("event_id", ""))[:160]
    event_type = str(payload.get("type", ""))[:80]
    organization_id = payload.get("organization_id")
    if not event_id or event_type not in set(EVENT_STATUS) | {"subscription.plan_changed"}:
        raise ValueError("Evento sandbox inválido.")
    if not isinstance(organization_id, int):
        raise ValueError("organization_id inválido.")
    existing = BillingEvent.query.filter_by(provider="sandbox", external_event_id=event_id).first()
    if existing:
        return existing, False
    subscription = OrganizationSubscription.query.filter_by(organization_id=organization_id).first()
    if not subscription:
        raise ValueError("Assinatura da organização não encontrada.")
    if event_type == "subscription.plan_changed":
        plan = Plan.query.filter_by(code=str(payload.get("plan_code", "")), ativo=True).first()
        if not plan:
            raise ValueError("Plano informado não encontrado.")
        subscription.plan_id = plan.id
    else:
        subscription.status = EVENT_STATUS[event_type]
        if subscription.status == "cancelled":
            subscription.cancelado_em = _now()
    event = BillingEvent(
        provider="sandbox", external_event_id=event_id, event_type=event_type,
        organization_id=organization_id, payload=payload,
    )
    db.session.add(event)
    return event, True


def subscription_for(organization_id: int) -> OrganizationSubscription | None:
    return OrganizationSubscription.query.filter_by(organization_id=organization_id).first()


def assert_write_allowed(organization_id: int):
    subscription = subscription_for(organization_id)
    if subscription and subscription.status in {"past_due", "cancelled"}:
        raise PermissionError("Assinatura indisponivel para novas operacoes. Contate o administrador da plataforma.")


def assert_limit(organization_id: int, key: str, current_count: int):
    subscription = subscription_for(organization_id)
    if not subscription or not subscription.plan or subscription.status not in {"trialing", "active"}:
        return
    raw_limit = (subscription.plan.limites or {}).get(key)
    if raw_limit is None:
        return
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        return
    if limit >= 0 and current_count >= limit:
        raise PermissionError(f"Limite do plano atingido: {key} ({limit}).")
