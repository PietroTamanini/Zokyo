"""Painel global separado e webhook do provider sandbox."""
import os
from functools import wraps

from flask import Blueprint, abort, jsonify, redirect, render_template, request, session, url_for
from sqlalchemy import func

from app.extensions import db
from app.models import (
    Cliente,
    EventoLog,
    LaudoFoto,
    OrdemServico,
    Organization,
    OrganizationSubscription,
    OSFoto,
    Plan,
    Usuario,
)
from app.services.billing import process_sandbox_event
from app.utils.sanitizers import sanitize_text

platform_bp = Blueprint("platform", __name__, url_prefix="/platform")


def global_admin_required(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        user = db.session.get(Usuario, session.get("usuario_id")) if session.get("usuario_id") else None
        allowed = {item.strip().lower() for item in os.environ.get("PLATFORM_ADMIN_EMAILS", "").split(",") if item.strip()}
        if not user:
            return redirect(url_for("auth.login_page"))
        if user.nivel != "admin" or user.email.lower() not in allowed:
            abort(403)
        return function(*args, **kwargs)
    return wrapped


@platform_bp.route("")
@global_admin_required
def index():
    organizations = db.session.execute(
        db.select(Organization).order_by(Organization.nome).execution_options(include_all_tenants=True)
    ).scalars().all()
    usage = {}
    for organization in organizations:
        options = {"include_all_tenants": True}
        usage[organization.id] = {
            "users": db.session.execute(db.select(func.count(Usuario.id)).where(Usuario.organization_id == organization.id).execution_options(**options)).scalar_one(),
            "clients": db.session.execute(db.select(func.count(Cliente.id)).where(Cliente.organization_id == organization.id).execution_options(**options)).scalar_one(),
            "orders": db.session.execute(db.select(func.count(OrdemServico.id)).where(OrdemServico.organization_id == organization.id).execution_options(**options)).scalar_one(),
            "last_activity": db.session.execute(db.select(func.max(EventoLog.criado_em)).where(EventoLog.organization_id == organization.id).execution_options(**options)).scalar_one_or_none(),
            "storage_bytes": int(
                (db.session.execute(db.select(func.coalesce(func.sum(OSFoto.tamanho_bytes), 0)).where(OSFoto.organization_id == organization.id).execution_options(**options)).scalar_one() or 0)
                + (db.session.execute(db.select(func.coalesce(func.sum(LaudoFoto.tamanho_bytes), 0)).where(LaudoFoto.organization_id == organization.id).execution_options(**options)).scalar_one() or 0)
            ),
        }
    return render_template(
        "pages/platform.html", organizations=organizations,
        plans=Plan.query.order_by(Plan.nome).all(), subscriptions=OrganizationSubscription.query.all(), usage=usage,
    )


@platform_bp.route("/plans", methods=["POST"])
@global_admin_required
def create_plan():
    code = sanitize_text(request.form.get("code"), max_length=50).lower().replace(" ", "-")
    name = sanitize_text(request.form.get("nome"), max_length=100)
    if not code or not name or Plan.query.filter_by(code=code).first():
        abort(400)
    limits = {}
    for key in ("max_users", "max_clients", "max_open_orders", "max_storage_mb"):
        value = request.form.get(key, type=int)
        if value is not None and value >= 0:
            limits[key] = value
    db.session.add(Plan(code=code, nome=name, limites=limits))
    db.session.commit()
    return redirect(url_for("platform.index"))


@platform_bp.route("/subscriptions", methods=["POST"])
@global_admin_required
def assign_subscription():
    organization_id = request.form.get("organization_id", type=int)
    plan_id = request.form.get("plan_id", type=int)
    organization = db.session.execute(
        db.select(Organization).where(Organization.id == organization_id).execution_options(include_all_tenants=True)
    ).scalar_one_or_none()
    plan = db.session.get(Plan, plan_id)
    if not organization or not plan or not plan.ativo:
        abort(400)
    subscription = OrganizationSubscription.query.filter_by(organization_id=organization.id).first()
    if subscription:
        subscription.plan_id = plan.id
        subscription.status = "trialing"
        subscription.provider = "sandbox"
    else:
        db.session.add(OrganizationSubscription(
            organization_id=organization.id, plan_id=plan.id, provider="sandbox", status="trialing",
        ))
    db.session.commit()
    return redirect(url_for("platform.index"))


@platform_bp.route("/webhooks/sandbox", methods=["POST"])
def sandbox_webhook():
    try:
        event, processed = process_sandbox_event(request.get_data(cache=True), request.headers.get("X-Zokyo-Signature", ""))
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"ok": False, "erro": str(exc)}), 400
    return jsonify({"ok": True, "processed": processed, "event_id": event.external_event_id})
