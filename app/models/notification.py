"""Fila persistente e auditavel de notificacoes externas."""
from datetime import datetime, timezone

from app.extensions import db


def _now():
    return datetime.now(timezone.utc)


class Notification(db.Model):
    __tablename__ = "notifications"
    __table_args__ = (
        db.UniqueConstraint("organization_id", "idempotency_key", name="uq_notification_org_key"),
    )

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    channel = db.Column(db.String(30), nullable=False, default="whatsapp")
    recipient = db.Column(db.String(80), nullable=False)
    event_type = db.Column(db.String(80), nullable=False)
    idempotency_key = db.Column(db.String(160), nullable=False)
    payload = db.Column(db.JSON, nullable=False)
    status = db.Column(db.String(30), nullable=False, default="pending", index=True)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    max_attempts = db.Column(db.Integer, nullable=False, default=3)
    next_attempt_at = db.Column(db.DateTime, nullable=False, default=_now, index=True)
    last_error = db.Column(db.Text)
    sent_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=_now, onupdate=_now)
