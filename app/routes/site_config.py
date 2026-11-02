"""Blueprint de configuracao de sites publicos (painel administrativo)."""
from __future__ import annotations

from flask import Blueprint, abort, flash, g, redirect, render_template, request, session, url_for

from app.extensions import db
from app.models import Organization
from app.services.domain_resolution import DomainResolutionError
from app.services.tenant_site_service import (
    TenantSiteError,
    get_domain_status,
    get_or_create_site,
    get_site_content,
    update_site_config,
    update_tenant_subdomain,
    verify_custom_domain,
)
from app.utils.auth import page_nivel_required

site_config_bp = Blueprint("site_config", __name__, url_prefix="/configuracoes/site")


def _get_org_or_404(organization_id: int) -> Organization:
    organization = (
        Organization.query.execution_options(include_all_tenants=True)
        .filter_by(id=organization_id, ativo=True)
        .first()
    )
    if not organization:
        abort(404)
    return organization


def _site_context():
    organization_id = getattr(g, "organization_id", None)
    if not organization_id:
        abort(403, description="Contexto de empresa necessario.")
    organization = _get_org_or_404(organization_id)
    site = get_or_create_site(organization.id)
    content = get_site_content(organization, site)
    return organization, site, content


@site_config_bp.route("/", methods=["GET"])
@page_nivel_required("admin")
def index():
    organization, site, content = _site_context()
    return render_template(
        "pages/site_config.html",
        active="site_config",
        organization=organization,
        site=site,
        content=content,
        domain_status=get_domain_status(organization.id),
    )


@site_config_bp.route("/", methods=["POST"])
@page_nivel_required("admin")
def salvar():
    organization_id = getattr(g, "organization_id", None)
    if not organization_id:
        abort(403, description="Contexto de empresa necessario.")
    organization = _get_org_or_404(organization_id)

    data = request.form.to_dict()
    try:
        update_site_config(
            organization.id,
            data,
            current_user_id=session.get("usuario_id", 0),
        )
        db.session.commit()
        flash("Configuracao do site publico atualizada com sucesso.", "success")
    except TenantSiteError as exc:
        db.session.rollback()
        flash(str(exc), "error")
        return redirect(url_for("site_config.index"))
    return redirect(url_for("site_config.index"))


@site_config_bp.route("/toggle", methods=["POST"])
@page_nivel_required("admin")
def toggle():
    organization_id = getattr(g, "organization_id", None)
    if not organization_id:
        abort(403, description="Contexto de empresa necessario.")
    organization = _get_org_or_404(organization_id)
    site = get_or_create_site(organization.id)
    site.site_enabled = not site.site_enabled
    db.session.commit()
    status = "ativado" if site.site_enabled else "desativado"
    flash(f"Site publico {status}.", "success")
    return redirect(url_for("site_config.index"))


@site_config_bp.route("/subdomain", methods=["POST"])
@page_nivel_required("admin")
def subdomain():
    organization_id = getattr(g, "organization_id", None)
    if not organization_id:
        abort(403, description="Contexto de empresa necessario.")
    organization = _get_org_or_404(organization_id)
    subdomain = (request.form.get("subdomain") or "").strip()
    try:
        update_tenant_subdomain(organization.id, subdomain)
        db.session.commit()
        flash("Subdominio atualizado com sucesso.", "success")
    except (TenantSiteError, DomainResolutionError) as exc:
        db.session.rollback()
        flash(str(exc), "error")
    return redirect(url_for("site_config.index"))


@site_config_bp.route("/verify", methods=["POST"])
@page_nivel_required("admin")
def verify():
    organization_id = getattr(g, "organization_id", None)
    if not organization_id:
        abort(403, description="Contexto de empresa necessario.")
    organization = _get_org_or_404(organization_id)
    ok = verify_custom_domain(organization.id)
    db.session.commit()
    if ok:
        flash("Dominio verificado com sucesso. Site liberado.", "success")
    else:
        flash("Dominio ainda nao validado. Configure o registro DNS e tente novamente.", "error")
    return redirect(url_for("site_config.index"))


@site_config_bp.route("/preview", methods=["GET"])
@page_nivel_required("admin")
def preview():
    organization, site, content = _site_context()
    return render_template(
        "pages/public_site.html",
        organization=organization,
        site=site,
        content=content,
        preview=True,
    )
