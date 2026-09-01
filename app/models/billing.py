"""Planos e assinaturas sem acoplamento a gateway comercial."""
from datetime import datetime, timezone

from app.extensions import db


def _now():
    return datetime.now(timezone.utc)


class Plan(db.Model):
    __tablename__ = "plans"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), nullable=False, unique=True)
    nome = db.Column(db.String(100), nullable=False)
    limites = db.Column(db.JSON, nullable=False, default=dict)
    preco_mensal = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    ciclo = db.Column(db.String(20), nullable=False, default="MONTHLY")
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    criado_em = db.Column(db.DateTime, nullable=False, default=_now)
    atualizado_em = db.Column(db.DateTime, nullable=False, default=_now, onupdate=_now)


class OrganizationSubscription(db.Model):
    __tablename__ = "organization_subscriptions"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, unique=True)
    plan_id = db.Column(db.Integer, db.ForeignKey("plans.id"), nullable=False)
    provider = db.Column(db.String(30), nullable=False, default="sandbox")
    external_id = db.Column(db.String(120))
    external_customer_id = db.Column(db.String(120))
    checkout_url = db.Column(db.String(600))
    status = db.Column(db.String(30), nullable=False, default="trialing")
    trial_fim = db.Column(db.DateTime)
    cancelar_no_fim = db.Column(db.Boolean, nullable=False, default=False)
    periodo_fim = db.Column(db.DateTime)
    cancelado_em = db.Column(db.DateTime)
    criado_em = db.Column(db.DateTime, nullable=False, default=_now)
    atualizado_em = db.Column(db.DateTime, nullable=False, default=_now, onupdate=_now)

    organization = db.relationship("Organization")
    plan = db.relationship("Plan")


class BillingEvent(db.Model):
    __tablename__ = "billing_events"
    __table_args__ = (
        db.UniqueConstraint("provider", "external_event_id", name="uq_billing_provider_event"),
    )

    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(30), nullable=False)
    external_event_id = db.Column(db.String(160), nullable=False)
    event_type = db.Column(db.String(80), nullable=False)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False)
    payload = db.Column(db.JSON, nullable=False)
    processado_em = db.Column(db.DateTime, nullable=False, default=_now)
