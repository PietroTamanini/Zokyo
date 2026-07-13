"""Entrega confiavel de notificacoes com idempotencia e retentativas."""
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Notification
from app.utils.email_delivery import send_email
from app.utils.whatsapp import enviar_whatsapp


def _now():
    return datetime.now(timezone.utc)


def enqueue_notification(organization_id, channel, recipient, payload, event_type, idempotency_key):
    existing = Notification.query.execution_options(include_all_tenants=True).filter_by(
        organization_id=organization_id, idempotency_key=idempotency_key
    ).first()
    if existing:
        return existing, False
    item = Notification(
        organization_id=organization_id,
        channel=channel,
        recipient=recipient,
        event_type=event_type,
        idempotency_key=idempotency_key,
        payload=payload,
    )
    db.session.add(item)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return Notification.query.execution_options(include_all_tenants=True).filter_by(
            organization_id=organization_id, idempotency_key=idempotency_key
        ).one(), False
    return item, True


def enqueue_whatsapp(organization_id, recipient, message, event_type, idempotency_key):
    return enqueue_notification(
        organization_id, "whatsapp", recipient, {"message": message}, event_type, idempotency_key,
    )


def enqueue_email(organization_id, recipient, subject, message, event_type, idempotency_key):
    return enqueue_notification(
        organization_id, "email", recipient, {"subject": subject, "message": message}, event_type, idempotency_key,
    )


def process_notification(notification_id):
    item = Notification.query.execution_options(include_all_tenants=True).filter_by(id=notification_id).first()
    if not item or item.status in {"sent", "manual_required", "failed"}:
        return item

    if item.channel == "email":
        result = send_email(item.recipient, item.payload.get("subject", "Zokyo"), item.payload.get("message", ""))
    else:
        result = enviar_whatsapp(item.recipient, item.payload.get("message", ""))
    item.attempts += 1
    payload = dict(item.payload)
    payload["last_result"] = result
    item.payload = payload
    item.updated_at = _now()

    if result.get("sucesso"):
        item.status = "sent"
        item.sent_at = _now()
        item.last_error = None
    elif result.get("modo") == "simulacao":
        item.status = "manual_required"
        item.last_error = result.get("erro") or result.get("aviso")
    elif item.attempts >= item.max_attempts:
        item.status = "failed"
        item.last_error = result.get("erro") or result.get("aviso") or "Falha de entrega"
    else:
        delays = (1, 5, 15)
        item.status = "retry"
        item.next_attempt_at = _now() + timedelta(minutes=delays[min(item.attempts - 1, len(delays) - 1)])
        item.last_error = result.get("erro") or result.get("aviso") or "Falha temporaria"

    db.session.commit()
    if item.status == "failed":
        from app.services.operational_alerts import emit_alert
        emit_alert("critical", "notifications", f"Notificacao #{item.id} falhou apos {item.attempts} tentativas")
    return item


def process_pending_notifications(limit=50):
    now = _now()
    items = (Notification.query.execution_options(include_all_tenants=True)
             .filter(Notification.status.in_(("pending", "retry")), Notification.next_attempt_at <= now)
             .order_by(Notification.next_attempt_at, Notification.id).limit(limit).all())
    for item in items:
        process_notification(item.id)
    return len(items)


def retry_notification(notification_id, organization_id):
    item = Notification.query.filter_by(id=notification_id, organization_id=organization_id).first()
    if not item:
        raise LookupError("Notificacao nao encontrada.")
    if item.status == "sent":
        raise ValueError("Notificacao ja entregue.")
    item.status = "pending"
    item.attempts = 0
    item.next_attempt_at = _now()
    item.last_error = None
    db.session.commit()
    return item
