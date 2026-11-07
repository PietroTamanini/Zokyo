"""Planos e assinaturas no admin global."""

from flask import abort

from app.admin.constants import SUBSCRIPTION_STATUSES
from app.extensions import db
from app.models import Organization, OrganizationSubscription, Plan
from app.utils.sanitizers import sanitize_text

PLAN_BILLING_CYCLES = {
    "MONTHLY": "Mensal",
    "QUARTERLY": "Trimestral",
    "SEMIANNUALLY": "Semestral",
    "YEARLY": "Anual",
}


def _hosting_percentage(form, current: Plan | None = None) -> float:
    value = form.get("hospedagem_percentual", type=float)
    if value is None:
        value = float(current.hospedagem_percentual or 0) if current else 0
    if value is None or value < 0 or value > 1000:
        raise ValueError("Informe um percentual de hospedagem entre 0 e 1000.")
    return value


def _billing_cycle(form, current: Plan | None = None) -> str:
    value = sanitize_text(form.get("ciclo") or (current.ciclo if current else "MONTHLY"), max_length=20).upper()
    if value not in PLAN_BILLING_CYCLES:
        raise ValueError("Selecione um ciclo de cobrança válido.")
    return value


def create_plan_from_form(form) -> Plan:
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
    try:
        hosting_percentage = _hosting_percentage(form)
        cycle = _billing_cycle(form)
    except ValueError:
        abort(400)
    plan = Plan(
        code=code,
        nome=name,
        limites=limits,
        preco_mensal=price,
        hospedagem_percentual=hosting_percentage,
        ciclo=cycle,
    )
    db.session.add(plan)
    db.session.commit()
    return plan


def _plan_values_from_form(form, current: Plan | None = None) -> tuple[str, str, float, float, str, dict, bool]:
    code = sanitize_text(form.get("code"), max_length=50).lower().replace(" ", "-")
    name = sanitize_text(form.get("nome"), max_length=100)
    query = Plan.query.filter_by(code=code)
    if current is not None:
        query = query.filter(Plan.id != current.id)
    if not code or not name or query.first():
        raise ValueError("Informe um código e um nome únicos para o plano.")
    limits = {}
    for key in ("max_users", "max_clients", "max_open_orders", "max_storage_mb"):
        value = form.get(key, type=int)
        if value is not None and value >= 0:
            limits[key] = value
    price = form.get("preco_mensal", type=float)
    if price is None or price < 0:
        raise ValueError("Informe uma mensalidade válida.")
    hosting_percentage = _hosting_percentage(form, current)
    cycle = _billing_cycle(form, current)
    active = form.get("ativo") == "on"
    return code, name, price, hosting_percentage, cycle, limits, active


def update_plan_from_form(plan_id: int, form) -> Plan:
    plan = db.session.get(Plan, plan_id)
    if not plan:
        raise LookupError("Plano não encontrado.")
    code, name, price, hosting_percentage, cycle, limits, active = _plan_values_from_form(form, plan)
    plan.code = code
    plan.nome = name
    plan.preco_mensal = price
    plan.hospedagem_percentual = hosting_percentage
    plan.ciclo = cycle
    plan.limites = limits
    plan.ativo = active
    return plan


def delete_plan_by_id(plan_id: int) -> Plan:
    plan = db.session.get(Plan, plan_id)
    if not plan:
        raise LookupError("Plano não encontrado.")
    if OrganizationSubscription.query.filter_by(plan_id=plan.id).first():
        raise ValueError("Este plano está vinculado a uma assinatura e não pode ser excluído. Desative-o para impedir novas assinaturas.")
    db.session.delete(plan)
    return plan


def assign_subscription_from_form(form) -> OrganizationSubscription:
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
    site_hospedado = form.get("site_hospedado") == "on"
    if subscription:
        subscription.plan_id = plan.id
        subscription.status = status
        subscription.site_hospedado = site_hospedado
        subscription.provider = "sandbox"
    else:
        subscription = OrganizationSubscription(
            organization_id=organization.id,
            plan_id=plan.id,
            provider="sandbox",
            status=status,
            site_hospedado=site_hospedado,
        )
        db.session.add(subscription)
    db.session.commit()
    return subscription


def plan_json(plan: Plan) -> dict:
    return {
        "id": plan.id,
        "code": plan.code,
        "nome": plan.nome,
        "preco_mensal": float(plan.preco_mensal or 0),
        "hospedagem_percentual": float(plan.hospedagem_percentual or 0),
        "ciclo": plan.ciclo,
        "limites": plan.limites or {},
    }
