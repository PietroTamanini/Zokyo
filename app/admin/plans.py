"""Planos e assinaturas no admin global."""

from flask import abort

from app.admin.constants import SUBSCRIPTION_STATUSES
from app.extensions import db
from app.models import Organization, OrganizationSubscription, Plan
from app.utils.sanitizers import sanitize_text


def create_plan_from_form(form) -> None:
    code = sanitize_text(form.get("code"), max_length=50).lower().replace(" ", "-")
    name = sanitize_text(form.get("nome"), max_length=100)
    if not code or not name or Plan.query.filter_by(code=code).first():
        abort(400)
    limits = {}
    for key in ("max_users", "max_clients", "max_open_orders", "max_storage_mb"):
        value = form.get(key, type=int)
        if value is not None and value >= 0:
            limits[key] = value
    price = form.get("preco_mensal", type=float) or 0
    if price < 0:
        abort(400)
    db.session.add(Plan(code=code, nome=name, limites=limits, preco_mensal=price))
    db.session.commit()


def assign_subscription_from_form(form) -> None:
    organization_id = form.get("organization_id", type=int)
    plan_id = form.get("plan_id", type=int)
    status = sanitize_text(form.get("status") or "trialing", max_length=30)
    if status not in SUBSCRIPTION_STATUSES:
        abort(400)
    organization = db.session.execute(
        db.select(Organization).where(Organization.id == organization_id).execution_options(include_all_tenants=True)
    ).scalar_one_or_none()
    plan = db.session.get(Plan, plan_id)
    if not organization or not plan or not plan.ativo:
        abort(400)
    subscription = OrganizationSubscription.query.filter_by(organization_id=organization.id).first()
    if subscription:
        subscription.plan_id = plan.id
        subscription.status = status
        subscription.provider = "sandbox"
    else:
        db.session.add(OrganizationSubscription(
            organization_id=organization.id,
            plan_id=plan.id,
            provider="sandbox",
            status=status,
        ))
    db.session.commit()


def plan_json(plan: Plan) -> dict:
    return {
        "id": plan.id,
        "code": plan.code,
        "nome": plan.nome,
        "preco_mensal": float(plan.preco_mensal or 0),
        "ciclo": plan.ciclo,
        "limites": plan.limites or {},
    }
