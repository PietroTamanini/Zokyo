"""Rotas do admin global, webhooks de billing e assinatura do tenant."""

import re

from flask import Blueprint, abort, current_app, flash, g, jsonify, redirect, render_template, request, session, url_for
from sqlalchemy import func

from app.admin.dashboard import admin_dashboard_context
from app.admin.organizations import (
    create_organization_from_form,
    create_tenant_admin_from_form,
    reset_tenant_admin_password,
    sync_organization_dns,
    update_organization_from_form,
)
from app.admin.plans import (
    assign_subscription_from_form,
    create_plan_from_form,
    delete_plan_by_id,
    plan_json,
    update_plan_from_form,
)
from app.admin.operations import operations_context
from app.admin.security import global_admin_required
from app.extensions import db
from app.models import EventoLog, Organization, OrganizationSubscription, Plan, PlatformSetting, Usuario, registrar
from app.services.billing import process_asaas_event, process_sandbox_event
from app.services.tenant_site_service import TenantSiteError, verify_custom_domain
from app.services.tenant_site_bundle import SiteBundleError, publish_bundle, unpublish_bundle

platform_bp = Blueprint("platform", __name__, url_prefix="/platform")


@platform_bp.route("")
@global_admin_required
def index():
    context = admin_dashboard_context()
    view = request.args.get("view") or getattr(g, "platform_view", "overview")
    if view not in {"overview", "organizations", "plans", "domains", "new-company", "company"}:
        view = "overview"
    context["admin_view"] = view
    context["plan_subscription_counts"] = dict(
        db.session.query(OrganizationSubscription.plan_id, func.count(OrganizationSubscription.id))
        .group_by(OrganizationSubscription.plan_id)
        .all()
    )
    if view == "company":
        organization_id = request.args.get("organization_id", type=int)
        context["org"] = next((org for org in context["organizations"] if org.id == organization_id), None)
        if context["org"] is None:
            abort(404)
    query = request.args.get("q", "").strip()[:200]
    status = request.args.get("status", "")
    organizations = context["organizations"]
    if query:
        organizations = [org for org in organizations if query.casefold() in
                         f"{org.nome} {org.slug} {org.custom_domain or ''}".casefold()]
    if status in {"active_company", "inactive_company"}:
        organizations = [org for org in organizations if org.ativo == (status == "active_company")]
    elif status in {"active", "past_due", "suspended", "trialing", "cancelled"}:
        organizations = [org for org in organizations if
                         context["subscriptions_by_org"].get(org.id) and
                         context["subscriptions_by_org"][org.id].status == status]
    elif status == "dns_pending":
        organizations = [org for org in organizations if org.dns_status != "active"]
    else:
        status = ""
    page_count = max(1, (len(organizations) + 19) // 20)
    page = min(max(request.args.get("page", 1, type=int), 1), page_count)
    context.update(
        filtered_organizations=organizations[(page - 1) * 20:page * 20],
        result_count=len(organizations), search_query=query, status_filter=status,
        page=page, page_count=page_count,
    )
    return render_template("admin/platform.html", **context)


@platform_bp.route("/dashboard")
@global_admin_required
def dashboard():
    g.platform_view = "overview"
    return index()


@platform_bp.route("/companies")
@global_admin_required
def companies():
    g.platform_view = "organizations"
    return index()


@platform_bp.route("/subscriptions")
@global_admin_required
def subscriptions():
    g.platform_view = "organizations"
    return index()


@platform_bp.route("/audit")
@global_admin_required
def audit():
    from app.routes.logs import _build_query

    data_ini = request.args.get("data_ini", "")
    data_fim = request.args.get("data_fim", "")
    usuario_id = request.args.get("usuario_id", "")
    tipo = request.args.get("tipo", "")
    modulo = request.args.get("modulo", "")
    organization_id = request.args.get("organization_id", "")
    page = request.args.get("page", 1, type=int)
    pag = _build_query(data_ini, data_fim, usuario_id, tipo, modulo, organization_id, include_all_tenants=True).order_by(
        EventoLog.criado_em.desc()
    ).paginate(page=page, per_page=50, error_out=False)
    usuarios = Usuario.query.execution_options(include_all_tenants=True).order_by(Usuario.nome).all()
    organizations = Organization.query.execution_options(include_all_tenants=True).order_by(Organization.nome).all()
    modulos = [row[0] for row in db.session.query(EventoLog.modulo).distinct().all() if row[0]]
    return render_template(
        "pages/logs.html",
        active="logs",
        eventos=pag.items,
        paginacao=pag,
        usuarios=usuarios,
        organizations=organizations,
        modulos=modulos,
        filtros={"data_ini": data_ini, "data_fim": data_fim, "usuario_id": usuario_id, "tipo": tipo, "modulo": modulo, "organization_id": organization_id},
    )


@platform_bp.route("/operations")
@global_admin_required
def operations():
    return render_template("admin/operations.html", operations=operations_context())


@platform_bp.route("/organizations", methods=["POST"])
@global_admin_required
def create_organization():
    ok, message = create_organization_from_form(request.form)
    flash(message, "success" if ok else "error")
    return redirect(url_for("platform.index", view="organizations" if ok else "new-company"))


@platform_bp.route("/organizations/<int:organization_id>", methods=["POST"])
@global_admin_required
def update_organization(organization_id):
    try:
        update_organization_from_form(organization_id, request.form)
    except TenantSiteError as exc:
        db.session.rollback()
        flash(str(exc), "error")
    else:
        flash("Empresa e assinatura atualizadas.", "success")
    return redirect(url_for("platform.index", view="company", organization_id=organization_id))


@platform_bp.route("/organizations/<int:organization_id>/admins", methods=["POST"])
@global_admin_required
def create_tenant_admin(organization_id):
    create_tenant_admin_from_form(organization_id, request.form)
    return redirect(url_for("platform.index", view="company", organization_id=organization_id))


@platform_bp.route("/users/<int:user_id>/reset-password", methods=["POST"], endpoint="reset_tenant_admin_password")
@global_admin_required
def reset_tenant_admin_password_route(user_id):
    user = reset_tenant_admin_password(user_id)
    return redirect(url_for("platform.index", view="company", organization_id=user.organization_id))


@platform_bp.route("/organizations/<int:organization_id>/dns", methods=["POST"])
@global_admin_required
def sync_dns(organization_id):
    sync_organization_dns(organization_id)
    return redirect(url_for("platform.index", view="domains"))


@platform_bp.route("/organizations/<int:organization_id>/site-domain/verify", methods=["POST"])
@global_admin_required
def verify_site_domain(organization_id):
    ok = verify_custom_domain(organization_id)
    registrar("status", "site_publico", "Verificacao de dominio executada pelo super admin", f"validated={ok}", organization_id=organization_id)
    db.session.commit()
    flash(
        "Domínio verificado. A landing page está liberada."
        if ok
        else "Domínio ainda não aponta para o servidor configurado.",
        "success" if ok else "warning",
    )
    return redirect(url_for("platform.index", view="company", organization_id=organization_id))


@platform_bp.route("/organizations/<int:organization_id>/site/upload", methods=["POST"])
@global_admin_required
def upload_site(organization_id):
    organization = db.session.get(Organization, organization_id)
    if not organization or not organization.ativo:
        abort(404)
    from app.services.tenant_site_service import get_or_create_site
    site = get_or_create_site(organization.id)
    try:
        result = publish_bundle(site, request.files.get("site_bundle"))
        registrar(
            "edicao", "site_publico", "Site publicado pelo super admin",
            f"files={result['files']};size_bytes={result['size_bytes']};version={result['version']}",
            organization_id=organization.id,
        )
        db.session.commit()
        flash("Site da empresa publicado com sucesso.", "success")
    except SiteBundleError as exc:
        db.session.rollback()
        flash(str(exc), "error")
    except Exception:
        db.session.rollback()
        flash("Nao foi possivel publicar o site desta empresa.", "error")
    return redirect(url_for("platform.index", view="company", organization_id=organization.id))


@platform_bp.route("/organizations/<int:organization_id>/site/unpublish", methods=["POST"])
@global_admin_required
def unpublish_site(organization_id):
    from app.models import Organization
    from app.services.tenant_site_service import get_or_create_site
    organization = db.session.get(Organization, organization_id)
    if not organization:
        abort(404)
    site = get_or_create_site(organization.id)
    had_bundle = unpublish_bundle(site)
    registrar("exclusao", "site_publico", "Site despublicado pelo super admin", f"had_bundle={had_bundle}", organization_id=organization.id)
    db.session.commit()
    flash("Site da empresa despublicado.", "success")
    return redirect(url_for("platform.index", view="company", organization_id=organization.id))


@platform_bp.route("/settings/domain", methods=["GET", "POST"], strict_slashes=False)
@global_admin_required
def update_base_domain():
    if request.method == "GET":
        return redirect(url_for("platform.index", view="domains"))

    value = (request.form.get("base_domain") or "").strip().lower().strip(".")
    if not value or len(value) > 253 or not re.fullmatch(
        r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*",
        value,
    ):
        flash("Domínio base inválido. Use somente domínio sem http://, porta ou caminho.", "error")
        return redirect(url_for("platform.index", view="domains"))
    PlatformSetting.set_value("tenant_base_domain", value)
    current_app.config["TENANT_BASE_DOMAIN"] = value
    registrar("edicao", "dns", "Dominio base da plataforma alterado", "base_domain_updated=true", organization_id=None)
    db.session.commit()
    flash(f"Domínio base atualizado para {value}.", "success")
    return redirect(url_for("platform.index", view="domains"))


@platform_bp.route("/plans", methods=["POST"])
@global_admin_required
def create_plan():
    plan = create_plan_from_form(request.form)
    registrar("criacao", "platform", f"Plano #{plan.id} criado", f"code={plan.code}")
    db.session.commit()
    return redirect(url_for("platform.index", view="plans"))


@platform_bp.route("/plans/<int:plan_id>", methods=["POST"])
@global_admin_required
def update_plan(plan_id):
    try:
        plan = update_plan_from_form(plan_id, request.form)
    except LookupError as exc:
        db.session.rollback()
        flash(str(exc), "error")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "error")
    else:
        registrar("edicao", "platform", f"Plano #{plan.id} atualizado", f"code={plan.code};active={plan.ativo}")
        db.session.commit()
        flash("Plano atualizado com sucesso.", "success")
    return redirect(url_for("platform.index", view="plans"))


@platform_bp.route("/plans/<int:plan_id>/delete", methods=["POST"])
@global_admin_required
def delete_plan(plan_id):
    try:
        plan = delete_plan_by_id(plan_id)
    except LookupError as exc:
        db.session.rollback()
        flash(str(exc), "error")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "error")
    else:
        registrar("exclusao", "platform", f"Plano #{plan.id} excluído", f"code={plan.code}")
        db.session.commit()
        flash("Plano excluído com sucesso.", "success")
    return redirect(url_for("platform.index", view="plans"))


@platform_bp.route("/subscriptions", methods=["POST"])
@global_admin_required
def assign_subscription():
    subscription = assign_subscription_from_form(request.form)
    registrar(
        "assinatura",
        "platform",
        f"Assinatura da organizacao #{subscription.organization_id} atualizada",
        f"status={subscription.status}; plan_id={subscription.plan_id}",
        organization_id=subscription.organization_id,
    )
    db.session.commit()
    return redirect(url_for("platform.index", view="organizations"))


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
        return jsonify({"erro": "Autenticacao necessaria."}), 401
    subscription = OrganizationSubscription.query.filter_by(organization_id=user.organization_id).first()
    if not subscription:
        return jsonify({"subscription": None, "plans": [plan_json(item) for item in Plan.query.filter_by(ativo=True).all()]})
    return jsonify({"subscription": {
        "status": subscription.status,
        "provider": subscription.provider,
        "plan": plan_json(subscription.plan),
        "periodo_fim": subscription.periodo_fim.isoformat() if subscription.periodo_fim else None,
        "trial_fim": subscription.trial_fim.isoformat() if subscription.trial_fim else None,
        "cancelar_no_fim": subscription.cancelar_no_fim,
    }})


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
        return jsonify({"erro": "CPF/CNPJ do assinante e obrigatorio."}), 400
    subscription = OrganizationSubscription.query.filter_by(organization_id=user.organization_id).first()
    if not subscription:
        subscription = OrganizationSubscription(organization_id=user.organization_id, plan_id=plan.id)
        db.session.add(subscription)
    subscription.plan = plan
    try:
        result = create_subscription(
            subscription,
            user.organization,
            user,
            document,
            request.form.get("billing_type", "UNDEFINED"),
            request.form.get("trial_days", 7, type=int),
        )
        registrar(
            "assinatura",
            "platform",
            f"Checkout Asaas criado para organizacao #{user.organization_id}",
            f"plan_id={plan.id}; status={subscription.status}",
            organization_id=user.organization_id,
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
        registrar(
            "cancelamento",
            "platform",
            f"Assinatura da organizacao #{user.organization_id} cancelada",
            f"provider={subscription.provider}",
            organization_id=user.organization_id,
        )
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
