"""Rotas do admin global, webhooks de billing e assinatura do tenant."""

import re
from datetime import datetime, timezone

from flask import Blueprint, abort, current_app, flash, g, jsonify, redirect, render_template, request, send_file, session, url_for
from sqlalchemy import func

from app.admin.dashboard import admin_dashboard_context
from app.admin.organizations import (
    create_organization_from_form,
    create_tenant_admin_from_form,
    get_organization_or_404,
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
from app.models import Cliente, Configuracao, ConsentRecord, DataSubjectRequest, EventoLog, Organization, OrganizationSubscription, Plan, PlatformSetting, PrivacyIncident, Usuario, registrar
from app.services.billing import process_asaas_event, process_sandbox_event
from app.services.tenant_site_service import TenantSiteError, verify_custom_domain
from app.services.tenant_site_bundle import SiteBundleError, publish_bundle, unpublish_bundle
from app.services.privacy import anonymize_client, export_subject_data

platform_bp = Blueprint("platform", __name__, url_prefix="/platform")

_AUDITED_READS = {
    "platform.index": "Painel global",
    "platform.dashboard": "Visão global",
    "platform.companies": "Lista de empresas",
    "platform.subscriptions": "Assinaturas",
    "platform.company_settings": "Configurações da empresa",
    "platform.company_settings_importacao": "Importação da empresa",
    "platform.company_privacy_clients": "Lista de clientes para privacidade",
    "platform.company_client_privacy": "Privacidade de cliente",
    "platform.audit": "Auditoria global",
    "platform.operations": "Operações globais",
}


@platform_bp.after_request
def audit_privileged_read(response):
    """Registra leituras administrativas concluídas sem persistir query strings ou PII."""
    label = _AUDITED_READS.get(request.endpoint)
    user = getattr(g, "current_user", None)
    if (request.method != "GET" or response.status_code != 200 or not label
            or not user or not user.is_platform_admin or user.organization_id):
        return response
    organization_id = (request.view_args or {}).get("organization_id")
    if request.endpoint == "platform.index" and request.args.get("view") == "company":
        organization_id = request.args.get("organization_id", type=int)
    if request.endpoint == "platform.audit":
        organization_id = request.args.get("organization_id", type=int)
    registrar(
        "acesso", "platform_access", label,
        f"organization_id={organization_id}" if organization_id else "escopo=global",
        organization_id=organization_id,
    )
    db.session.commit()
    return response


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


@platform_bp.route("/companies/<int:organization_id>/settings")
@global_admin_required
def company_settings(organization_id):
    organization = get_organization_or_404(organization_id)
    g.organization_id = organization.id
    g.platform_settings_organization_id = organization.id
    g.cfg = Configuracao.get(organization.id)
    return render_template(
        "pages/configuracoes.html",
        active="configuracoes",
        cfg=g.cfg,
        platform_mode=True,
        platform_org=organization,
        platform_workspace=True,
        current_platform_view="organizations",
    )


def _platform_company_settings_action(organization_id, handler_name):
    organization = get_organization_or_404(organization_id)
    g.organization_id = organization.id
    g.platform_settings_organization_id = organization.id
    g.cfg = Configuracao.get(organization.id)
    from app.routes import configuracoes as configuracoes_routes
    return getattr(configuracoes_routes, handler_name)()


@platform_bp.route("/companies/<int:organization_id>/settings/save", methods=["POST"])
@global_admin_required
def company_settings_save(organization_id):
    return _platform_company_settings_action(organization_id, "salvar")


@platform_bp.route("/companies/<int:organization_id>/settings/dashboard", methods=["POST"])
@global_admin_required
def company_settings_dashboard(organization_id):
    return _platform_company_settings_action(organization_id, "salvar_dashboard")


@platform_bp.route("/companies/<int:organization_id>/settings/os-options", methods=["POST"])
@global_admin_required
def company_settings_os_options(organization_id):
    return _platform_company_settings_action(organization_id, "salvar_os_opcoes")


@platform_bp.route("/companies/<int:organization_id>/settings/importacao")
@global_admin_required
def company_settings_importacao(organization_id):
    organization = get_organization_or_404(organization_id)
    g.organization_id = organization.id
    g.platform_settings_organization_id = organization.id
    g.cfg = Configuracao.get(organization.id)
    return render_template(
        "pages/importacao_bancos.html",
        active="importacao_bancos",
        platform_mode=True,
        platform_org=organization,
        platform_workspace=True,
        current_platform_view="organizations",
    )


@platform_bp.route("/companies/<int:organization_id>/settings/privacy/clients")
@global_admin_required
def company_privacy_clients(organization_id):
    organization = get_organization_or_404(organization_id)
    g.organization_id = organization.id
    query = Cliente.query.filter_by(organization_id=organization.id)
    search = request.args.get("q", "").strip()[:100]
    if search.isdecimal():
        query = query.filter(Cliente.id == int(search))
    elif search:
        query = query.filter(Cliente.nome.contains(search, autoescape=True))
    page = max(1, request.args.get("page", 1, type=int))
    pagination = query.order_by(Cliente.id.desc()).paginate(page=page, per_page=30, error_out=False)
    return render_template(
        "admin/company_privacy_clients.html", active="privacidade",
        platform_mode=True, platform_org=organization, platform_workspace=True,
        current_platform_view="organizations", clients=pagination.items,
        pagination=pagination, search=search,
    )


def _company_privacy_client(organization_id, client_id):
    organization = get_organization_or_404(organization_id)
    g.organization_id = organization.id
    client = Cliente.query.filter_by(id=client_id, organization_id=organization.id).first_or_404()
    return organization, client


@platform_bp.route("/companies/<int:organization_id>/settings/privacy/clients/<int:client_id>")
@global_admin_required
def company_client_privacy(organization_id, client_id):
    organization, client = _company_privacy_client(organization_id, client_id)
    linked_requests = DataSubjectRequest.query.filter_by(
        organization_id=organization.id, cliente_id=client.id,
    ).order_by(DataSubjectRequest.solicitado_em.desc()).all()
    return render_template(
        "pages/client_privacy.html", active="privacidade", cliente=client,
        consents=ConsentRecord.query.filter_by(organization_id=organization.id, cliente_id=client.id)
        .order_by(ConsentRecord.registrado_em.desc()).all(),
        requests=linked_requests,
        export_requests=[item for item in linked_requests if item.identity_verified and item.status != "rejected"],
        removal_requests=[item for item in linked_requests if item.identity_verified
                          and item.status in {"open", "in_progress"}
                          and item.request_type in {"deletion", "anonymization"}],
        incidents=PrivacyIncident.query.filter_by(organization_id=organization.id)
        .order_by(PrivacyIncident.id.desc()).limit(100).all(),
        platform_mode=True, platform_org=organization, platform_workspace=True,
        current_platform_view="organizations",
    )


_EXPORT_REASONS = {"subject_request", "support_request", "incident_investigation"}
_REMOVAL_REASONS = {"subject_request", "duplicate_record", "data_minimization"}


def _privacy_action_reference(organization_id, client_id, reason, *, removal=False):
    if reason == "subject_request":
        request_id = request.form.get("request_id", type=int)
        linked = DataSubjectRequest.query.filter_by(
            id=request_id, organization_id=organization_id, cliente_id=client_id,
            identity_verified=True,
        ).first() if request_id else None
        if (not linked or linked.status == "rejected"
                or (removal and (linked.status not in {"open", "in_progress"}
                                 or linked.request_type not in {"deletion", "anonymization"}))):
            abort(400, description="Selecione uma solicitação verificada e vinculada a este cliente.")
        return f"solicitacao_id={linked.id}"
    if reason == "incident_investigation":
        incident_id = request.form.get("incident_id", type=int)
        linked = PrivacyIncident.query.filter_by(
            id=incident_id, organization_id=organization_id,
        ).first() if incident_id else None
        if not linked:
            abort(400, description="Selecione um incidente desta empresa.")
        return f"incidente_id={linked.id}"
    protocol = request.form.get("protocol", "").strip()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9-]{3,39}", protocol):
        abort(400, description="Informe o código do protocolo externo, com 4 a 40 letras maiúsculas, números ou hífens.")
    return f"protocolo={protocol}"


@platform_bp.route("/companies/<int:organization_id>/settings/privacy/clients/<int:client_id>/export", methods=["POST"])
@global_admin_required
def company_client_export(organization_id, client_id):
    reason = request.form.get("reason", "")
    if reason not in _EXPORT_REASONS:
        abort(400, description="Selecione o motivo da exportação.")
    organization, client = _company_privacy_client(organization_id, client_id)
    reference = _privacy_action_reference(organization.id, client.id, reason)
    user = g.current_user
    archive = export_subject_data(client, user, target_organization_id=organization.id,
                                  access_reason=reason, access_reference=reference)
    if reason == "subject_request":
        record = DataSubjectRequest.query.filter_by(
            id=request.form.get("request_id", type=int),
            organization_id=organization.id, cliente_id=client.id,
        ).one()
        record.prepared_export_sha256 = archive.export_sha256
        record.prepared_export_at = datetime.now(timezone.utc)
        record._revision_actor_id = user.id
    db.session.commit()
    response = send_file(archive, mimetype="application/zip", as_attachment=True,
                         download_name=f"cliente-{client.id}-dados.zip")
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["X-Export-SHA256"] = archive.export_sha256
    return response


@platform_bp.route("/companies/<int:organization_id>/settings/privacy/clients/<int:client_id>/remove-registration", methods=["POST"])
@global_admin_required
def company_client_remove_registration(organization_id, client_id):
    reason = request.form.get("reason", "")
    if reason not in _REMOVAL_REASONS:
        abort(400, description="Selecione o motivo da remoção cadastral.")
    organization, client = _company_privacy_client(organization_id, client_id)
    reference = _privacy_action_reference(organization.id, client.id, reason, removal=True)
    try:
        anonymize_client(client, g.current_user, target_organization_id=organization.id,
                         access_reason=reason, access_reference=reference)
        db.session.commit()
        flash("Dados cadastrais removidos. Históricos e registros de auditoria permanecem sujeitos à retenção.", "success")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "error")
    return redirect(url_for("platform.company_client_privacy", organization_id=organization.id, client_id=client.id))


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
        f"status={subscription.status}; plan_id={subscription.plan_id}"
        + ("; site_hospedado=true" if subscription.site_hospedado else ""),
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
        "site_hospedado": subscription.site_hospedado,
        "preco_mensal": float(subscription.preco_mensal_cobrado),
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
