"""Painel global separado e webhook do provider sandbox."""
import os
import secrets
import string
from collections import defaultdict
from functools import wraps

from flask import Blueprint, abort, current_app, flash, g, jsonify, redirect, render_template, request, session, url_for
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
from app.services.billing import process_asaas_event, process_sandbox_event
from app.services.tenant_provisioning import TenantProvisioningError, provision_tenant, sync_tenant_dns, tenant_hostname
from app.utils.sanitizers import sanitize_text
from app.utils.validators import validar_email

platform_bp = Blueprint("platform", __name__, url_prefix="/platform")
SUBSCRIPTION_STATUSES = ("trialing", "active", "past_due", "suspended", "cancelled")


def _temporary_password() -> str:
    alphabet = string.ascii_letters + string.digits
    return "Zk!" + "".join(secrets.choice(alphabet) for _ in range(13)) + "9"


def global_admin_required(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        user = getattr(g, "current_user", None)
        if user is None and session.get("usuario_id"):
            user = db.session.get(Usuario, session.get("usuario_id"))
        allowed = {item.strip().lower() for item in os.environ.get("PLATFORM_ADMIN_EMAILS", "").split(",") if item.strip()}
        if not user:
            return redirect(url_for("auth.login_page"))
        if user.nivel != "admin" or (not user.is_platform_admin and user.email.lower() not in allowed):
            abort(403)
        return function(*args, **kwargs)
    return wrapped


@platform_bp.route("")
@global_admin_required
def index():
    organizations = db.session.execute(
        db.select(Organization).order_by(Organization.nome).execution_options(include_all_tenants=True)
    ).scalars().all()
    options = {"include_all_tenants": True}
    user_counts = dict(db.session.execute(
        db.select(Usuario.organization_id, func.count(Usuario.id))
        .group_by(Usuario.organization_id)
        .execution_options(**options)
    ).all())
    client_counts = dict(db.session.execute(
        db.select(Cliente.organization_id, func.count(Cliente.id))
        .group_by(Cliente.organization_id)
        .execution_options(**options)
    ).all())
    order_counts = dict(db.session.execute(
        db.select(OrdemServico.organization_id, func.count(OrdemServico.id))
        .group_by(OrdemServico.organization_id)
        .execution_options(**options)
    ).all())
    last_activity = dict(db.session.execute(
        db.select(EventoLog.organization_id, func.max(EventoLog.criado_em))
        .group_by(EventoLog.organization_id)
        .execution_options(**options)
    ).all())
    os_storage = dict(db.session.execute(
        db.select(OSFoto.organization_id, func.coalesce(func.sum(OSFoto.tamanho_bytes), 0))
        .group_by(OSFoto.organization_id)
        .execution_options(**options)
    ).all())
    report_storage = dict(db.session.execute(
        db.select(LaudoFoto.organization_id, func.coalesce(func.sum(LaudoFoto.tamanho_bytes), 0))
        .group_by(LaudoFoto.organization_id)
        .execution_options(**options)
    ).all())
    usage = {}
    for organization in organizations:
        usage[organization.id] = {
            "users": int(user_counts.get(organization.id, 0) or 0),
            "clients": int(client_counts.get(organization.id, 0) or 0),
            "orders": int(order_counts.get(organization.id, 0) or 0),
            "last_activity": last_activity.get(organization.id),
            "storage_bytes": int(os_storage.get(organization.id, 0) or 0) + int(report_storage.get(organization.id, 0) or 0),
        }
    owners = defaultdict(list)
    owner_rows = db.session.execute(
        db.select(Usuario.organization_id, Usuario.id, Usuario.nome, Usuario.email)
        .where(Usuario.nivel == "admin", Usuario.organization_id.is_not(None))
        .order_by(Usuario.nome)
        .execution_options(**options)
    ).all()
    for organization_id, user_id, name, email in owner_rows:
        owners[organization_id].append({"id": user_id, "name": name, "email": email})
    subscriptions = OrganizationSubscription.query.all()
    subscriptions_by_org = {item.organization_id: item for item in subscriptions}
    summary = {
        "organizations": len(organizations),
        "active_organizations": sum(1 for item in organizations if item.ativo),
        "total_users": sum(item["users"] for item in usage.values()),
        "total_clients": sum(item["clients"] for item in usage.values()),
        "total_orders": sum(item["orders"] for item in usage.values()),
        "past_due": sum(1 for item in subscriptions if item.status == "past_due"),
        "suspended": sum(1 for item in subscriptions if item.status == "suspended"),
    }
    dns_mode = (current_app.config.get("TENANT_DNS_MODE") or "manual").lower()
    dns_target = current_app.config.get("TENANT_DNS_TARGET") or ""
    dns_ready = dns_mode == "wildcard" or (
        dns_mode in {"cloudflare", "api"}
        and bool(current_app.config.get("CLOUDFLARE_API_TOKEN"))
        and bool(current_app.config.get("CLOUDFLARE_ZONE_ID"))
        and bool(dns_target)
    )
    return render_template(
        "pages/platform.html", organizations=organizations,
        plans=Plan.query.order_by(Plan.nome).all(), subscriptions=subscriptions, subscriptions_by_org=subscriptions_by_org,
        usage=usage, summary=summary, owners=dict(owners), dns_mode=dns_mode, dns_target=dns_target, dns_ready=dns_ready,
        subscription_statuses=SUBSCRIPTION_STATUSES,
        base_domain=current_app.config.get("TENANT_BASE_DOMAIN", "tamanini.dev.br"),
    )


@platform_bp.route("/organizations", methods=["POST"])
@global_admin_required
def create_organization():
    plan_id = request.form.get("plan_id", type=int)
    if plan_id and not db.session.get(Plan, plan_id):
        abort(400)
    try:
        organization, _owner = provision_tenant(
            name=request.form.get("name", ""),
            slug=request.form.get("slug", ""),
            owner_name=request.form.get("owner_name", ""),
            owner_email=request.form.get("owner_email", ""),
            owner_password=request.form.get("owner_password", ""),
            plan_id=plan_id,
            trial_days=request.form.get("trial_days", 14, type=int) or 14,
            active=request.form.get("active") == "on",
            provision_dns=bool(request.form.get("provision_dns")),
        )
        db.session.commit()
        flash(f"Empresa criada: {organization.custom_domain}", "success")
    except TenantProvisioningError as exc:
        db.session.rollback()
        flash(str(exc), "error")
    return redirect(url_for("platform.index"))


@platform_bp.route("/organizations/<int:organization_id>", methods=["POST"])
@global_admin_required
def update_organization(organization_id):
    organization = db.session.execute(
        db.select(Organization).where(Organization.id == organization_id).execution_options(include_all_tenants=True)
    ).scalar_one_or_none()
    if not organization:
        abort(404)
    name = sanitize_text(request.form.get("name", ""), max_length=200)
    if name:
        organization.nome = name
    organization.ativo = request.form.get("active") == "on"
    plan_id = request.form.get("plan_id", type=int)
    status = sanitize_text(request.form.get("status") or "", max_length=30)
    if plan_id:
        if status not in SUBSCRIPTION_STATUSES:
            abort(400)
        plan = db.session.get(Plan, plan_id)
        if not plan or not plan.ativo:
            abort(400)
        subscription = OrganizationSubscription.query.filter_by(organization_id=organization.id).first()
        if subscription:
            subscription.plan_id = plan.id
            subscription.status = status
            subscription.provider = subscription.provider or "sandbox"
        else:
            db.session.add(OrganizationSubscription(
                organization_id=organization.id, plan_id=plan.id, provider="sandbox", status=status,
            ))
    if request.form.get("sync_dns") == "on":
        if not organization.custom_domain and organization.subdomain:
            organization.custom_domain = tenant_hostname(organization.subdomain)
        sync_tenant_dns(organization)
    db.session.commit()
    return redirect(url_for("platform.index"))


@platform_bp.route("/organizations/<int:organization_id>/admins", methods=["POST"])
@global_admin_required
def create_tenant_admin(organization_id):
    organization = db.session.execute(
        db.select(Organization).where(Organization.id == organization_id).execution_options(include_all_tenants=True)
    ).scalar_one_or_none()
    if not organization:
        abort(404)
    name = sanitize_text(request.form.get("owner_name", ""), max_length=120)
    email = (request.form.get("owner_email") or "").strip().lower()
    password = request.form.get("owner_password") or _temporary_password()
    if len(name) < 2 or not validar_email(email):
        flash("Nome ou e-mail do admin invalido.", "error")
        return redirect(url_for("platform.index"))
    if Usuario.query.execution_options(include_all_tenants=True).filter_by(email=email).first():
        flash("E-mail ja cadastrado.", "error")
        return redirect(url_for("platform.index"))
    user = Usuario(
        organization_id=organization.id,
        nome=name,
        email=email,
        nivel="admin",
        ativo=True,
        onboarding_completed=False,
    )
    user.set_senha(password)
    db.session.add(user)
    db.session.commit()
    flash(f"Admin criado para {organization.nome}. Senha temporaria: {password}", "success")
    return redirect(url_for("platform.index"))


@platform_bp.route("/users/<int:user_id>/reset-password", methods=["POST"])
@global_admin_required
def reset_tenant_admin_password(user_id):
    user = db.session.execute(
        db.select(Usuario)
        .where(Usuario.id == user_id, Usuario.organization_id.is_not(None))
        .execution_options(include_all_tenants=True)
    ).scalar_one_or_none()
    if not user:
        abort(404)
    password = _temporary_password()
    user.set_senha(password)
    user.security_version += 1
    from app.services.user_sessions import revoke_all

    revoke_all(user.id, "reset pelo admin global")
    db.session.commit()
    flash(f"Senha temporaria de {user.nome}: {password}", "success")
    return redirect(url_for("platform.index"))


@platform_bp.route("/organizations/<int:organization_id>/dns", methods=["POST"])
@global_admin_required
def sync_dns(organization_id):
    organization = db.session.execute(
        db.select(Organization).where(Organization.id == organization_id).execution_options(include_all_tenants=True)
    ).scalar_one_or_none()
    if not organization:
        abort(404)
    if not organization.custom_domain and organization.subdomain:
        organization.custom_domain = tenant_hostname(organization.subdomain)
    sync_tenant_dns(organization)
    db.session.commit()
    return redirect(url_for("platform.index"))


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
    price = request.form.get("preco_mensal", type=float) or 0
    if price < 0:
        abort(400)
    db.session.add(Plan(code=code, nome=name, limites=limits, preco_mensal=price))
    db.session.commit()
    return redirect(url_for("platform.index"))


@platform_bp.route("/subscriptions", methods=["POST"])
@global_admin_required
def assign_subscription():
    organization_id = request.form.get("organization_id", type=int)
    plan_id = request.form.get("plan_id", type=int)
    status = sanitize_text(request.form.get("status") or "trialing", max_length=30)
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
            organization_id=organization.id, plan_id=plan.id, provider="sandbox", status=status,
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


@platform_bp.route("/subscription")
def tenant_subscription():
    user = db.session.get(Usuario, session.get("usuario_id")) if session.get("usuario_id") else None
    if not user:
        return jsonify({"erro": "Autenticação necessária."}), 401
    subscription = OrganizationSubscription.query.filter_by(organization_id=user.organization_id).first()
    if not subscription:
        return jsonify({"subscription": None, "plans": [_plan_json(item) for item in Plan.query.filter_by(ativo=True).all()]})
    return jsonify({"subscription": {
        "status": subscription.status, "provider": subscription.provider,
        "plan": _plan_json(subscription.plan), "periodo_fim": subscription.periodo_fim.isoformat() if subscription.periodo_fim else None,
        "trial_fim": subscription.trial_fim.isoformat() if subscription.trial_fim else None,
        "cancelar_no_fim": subscription.cancelar_no_fim,
    }})


def _plan_json(plan):
    return {"id": plan.id, "code": plan.code, "nome": plan.nome, "preco_mensal": float(plan.preco_mensal or 0), "ciclo": plan.ciclo, "limites": plan.limites or {}}


@platform_bp.route("/subscription/checkout", methods=["POST"])
def subscription_checkout():
    from app.services.asaas_subscriptions import AsaasSubscriptionError, create_subscription
    user = db.session.get(Usuario, session.get("usuario_id")) if session.get("usuario_id") else None
    if not user or user.nivel != "admin":
        abort(403)
    plan = db.session.get(Plan, request.form.get("plan_id", type=int))
    if not plan or not plan.ativo:
        abort(400)
    document = request.form.get("cpf_cnpj", "")
    if len("".join(character for character in document if character.isdigit())) not in {11, 14}:
        return jsonify({"erro": "CPF/CNPJ do assinante é obrigatório."}), 400
    subscription = OrganizationSubscription.query.filter_by(organization_id=user.organization_id).first()
    if not subscription:
        subscription = OrganizationSubscription(organization_id=user.organization_id, plan_id=plan.id)
        db.session.add(subscription)
    subscription.plan = plan
    try:
        result = create_subscription(
            subscription, user.organization, user, document,
            request.form.get("billing_type", "UNDEFINED"), request.form.get("trial_days", 7, type=int),
        )
        db.session.commit()
    except AsaasSubscriptionError as exc:
        db.session.rollback()
        return jsonify({"erro": str(exc)}), 502
    return jsonify({"ok": True, "subscription_id": result.get("id"), "status": subscription.status}), 201


@platform_bp.route("/subscription/cancel", methods=["POST"])
def subscription_cancel():
    from app.services.asaas_subscriptions import AsaasSubscriptionError, cancel_subscription
    user = db.session.get(Usuario, session.get("usuario_id")) if session.get("usuario_id") else None
    if not user or user.nivel != "admin":
        abort(403)
    subscription = OrganizationSubscription.query.filter_by(organization_id=user.organization_id).first_or_404()
    try:
        cancel_subscription(subscription)
        db.session.commit()
    except AsaasSubscriptionError as exc:
        db.session.rollback()
        return jsonify({"erro": str(exc)}), 502
    return jsonify({"ok": True, "status": subscription.status})


@platform_bp.route("/webhooks/asaas", methods=["POST"])
def asaas_webhook():
    from app.services.asaas_subscriptions import verify_webhook_token
    if not verify_webhook_token(request.headers.get("asaas-access-token", "")):
        return jsonify({"ok": False}), 401
    try:
        event, processed = process_asaas_event(request.get_json(silent=True) or {})
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"ok": False, "erro": str(exc)}), 400
    return jsonify({"ok": True, "processed": processed, "event_id": event.external_event_id}), 200
