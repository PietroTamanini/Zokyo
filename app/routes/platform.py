"""Rotas do admin global, webhooks de billing e assinatura do tenant."""

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, session, url_for

from app.admin.dashboard import admin_dashboard_context
from app.admin.organizations import (
    create_organization_from_form,
    create_tenant_admin_from_form,
    reset_tenant_admin_password,
    sync_organization_dns,
    update_organization_from_form,
)
from app.admin.plans import assign_subscription_from_form, create_plan_from_form, plan_json
from app.admin.security import global_admin_required
from app.extensions import db
from app.models import OrganizationSubscription, Plan, Usuario
from app.services.billing import process_asaas_event, process_sandbox_event

platform_bp = Blueprint("platform", __name__, url_prefix="/platform")


@platform_bp.route("")
@global_admin_required
def index():
    context = admin_dashboard_context()
    view = request.args.get("view", "overview")
    if view not in {"overview", "organizations", "plans", "domains", "new-company", "company"}:
        view = "overview"
    context["admin_view"] = view
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


@platform_bp.route("/organizations", methods=["POST"])
@global_admin_required
def create_organization():
    ok, message = create_organization_from_form(request.form)
    flash(message, "success" if ok else "error")
    return redirect(url_for("platform.index", view="organizations" if ok else "new-company"))


@platform_bp.route("/organizations/<int:organization_id>", methods=["POST"])
@global_admin_required
def update_organization(organization_id):
    update_organization_from_form(organization_id, request.form)
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


@platform_bp.route("/plans", methods=["POST"])
@global_admin_required
def create_plan():
    create_plan_from_form(request.form)
    return redirect(url_for("platform.index", view="plans"))


@platform_bp.route("/subscriptions", methods=["POST"])
@global_admin_required
def assign_subscription():
    assign_subscription_from_form(request.form)
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
