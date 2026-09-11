"""Abstração de billing; somente provider sandbox, sem cobrança real."""
import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta, timezone

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


def process_asaas_event(payload: dict) -> tuple[BillingEvent, bool]:
    event_id = str(payload.get("id", ""))[:160]
    event_type = str(payload.get("event", ""))[:80]
    payment = payload.get("payment") or {}
    external_subscription = payment.get("subscription") or (payload.get("subscription") or {}).get("id")
    if not event_id or not event_type or not external_subscription:
        raise ValueError("Evento Asaas inválido.")
    existing = BillingEvent.query.filter_by(provider="asaas", external_event_id=event_id).first()
    if existing:
        return existing, False
    subscription = OrganizationSubscription.query.execution_options(include_all_tenants=True).filter_by(
        provider="asaas", external_id=str(external_subscription),
    ).first()
    if not subscription:
        raise ValueError("Assinatura Asaas não reconhecida.")
    if event_type in {"PAYMENT_RECEIVED", "PAYMENT_CONFIRMED"}:
        subscription.status = "active"
    elif event_type in {"PAYMENT_OVERDUE", "PAYMENT_DUNNING_REQUESTED"}:
        subscription.status = "past_due"
    elif event_type in {"SUBSCRIPTION_DELETED", "SUBSCRIPTION_INACTIVATED"}:
        subscription.status = "cancelled"
        subscription.cancelado_em = _now()
    event = BillingEvent(
        provider="asaas", external_event_id=event_id, event_type=event_type,
        organization_id=subscription.organization_id, payload=payload,
    )
    db.session.add(event)
    return event, True


def subscription_for(organization_id: int) -> OrganizationSubscription | None:
    return OrganizationSubscription.query.filter_by(organization_id=organization_id).first()


def ensure_trial_subscription(organization_id: int, trial_days: int = 14) -> OrganizationSubscription:
    existing = subscription_for(organization_id)
    if existing:
        return existing
    plan = Plan.query.filter_by(code="starter", ativo=True).first()
    if not plan:
        plan = Plan(
            code="starter", nome="Starter",
            limites={"max_users": 3, "max_clients": 500, "max_open_orders": 100, "max_storage_mb": 1024},
        )
        db.session.add(plan)
        db.session.flush()
    subscription = OrganizationSubscription(
        organization_id=organization_id, plan_id=plan.id, provider="sandbox",
        status="trialing", trial_fim=_now() + timedelta(days=max(1, min(trial_days, 90))),
    )
    db.session.add(subscription)
    return subscription


def assert_write_allowed(organization_id: int):
    subscription = subscription_for(organization_id)
    if subscription and subscription.status == "trialing" and subscription.trial_fim:
        trial_end = subscription.trial_fim
        if trial_end.tzinfo is None:
            trial_end = trial_end.replace(tzinfo=timezone.utc)
        if trial_end <= _now():
            subscription.status = "past_due"
            db.session.commit()
    if subscription and subscription.status in {"past_due", "cancelled", "suspended"}:
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


def assert_storage_limit(organization_id: int, incoming_bytes: int):
    from sqlalchemy import func

    from app.models import LaudoFoto, OSFoto

    used = int(
        (db.session.query(func.coalesce(func.sum(OSFoto.tamanho_bytes), 0)).filter_by(organization_id=organization_id).scalar() or 0)
        + (db.session.query(func.coalesce(func.sum(LaudoFoto.tamanho_bytes), 0)).filter_by(organization_id=organization_id).scalar() or 0)
    )
    subscription = subscription_for(organization_id)
    raw_limit = (subscription.plan.limites or {}).get("max_storage_mb") if subscription and subscription.plan else None
    if raw_limit is not None and used + max(0, int(incoming_bytes)) > int(raw_limit) * 1024 * 1024:
        raise PermissionError(f"Limite de armazenamento do plano atingido ({raw_limit} MB).")
