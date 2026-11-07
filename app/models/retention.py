"""Politicas de retencao aprovadas por organizacao."""
from datetime import datetime, timezone

from app.extensions import db


def _now():
    return datetime.now(timezone.utc)


class RetentionPolicy(db.Model):
    __tablename__ = "retention_policies"
    __table_args__ = (
        db.UniqueConstraint("organization_id", "category", name="uq_retention_org_category"),
    )

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    category = db.Column(db.String(60), nullable=False)
    retention_days = db.Column(db.Integer, nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=False)
    approved_by_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    approved_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=_now, onupdate=_now)


class PlatformRetentionPolicy(db.Model):
    """Regra global separada das políticas pertencentes às assistências."""

    __tablename__ = "platform_retention_policies"

    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(60), nullable=False, unique=True)
    retention_days = db.Column(db.Integer, nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=False)
    approval_reference = db.Column(db.String(40))
    approved_by_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    approved_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=_now, onupdate=_now)
