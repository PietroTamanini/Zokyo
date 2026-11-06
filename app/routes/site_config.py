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
from app.services.tenant_site_bundle import SiteBundleError, publish_bundle, unpublish_bundle
from app.services.tenant_provisioning import tenant_hostname
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


def _public_site_url(organization, site):
    hostname = site.custom_domain if site.custom_domain_validated and site.custom_domain else tenant_hostname(organization.subdomain)
    port = request.host.rsplit(":", 1)[1] if ":" in request.host else ""
    suffix = f":{port}" if port and port.isdigit() and port not in {"80", "443"} else ""
    return f"{request.scheme}://{hostname}{suffix}/"


@site_config_bp.route("/", methods=["GET"], strict_slashes=False)
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
        public_site_url=_public_site_url(organization, site),
    )


@site_config_bp.route("/", methods=["POST"], strict_slashes=False)
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
        from app.models import registrar
        registrar("edicao", "site_publico", "Configuracao de dominio do site alterada", "domain_settings_updated=true", organization_id=organization.id)
        db.session.commit()
        flash("Configuracao do site publico atualizada com sucesso.", "success")
    except TenantSiteError as exc:
        db.session.rollback()
        flash(str(exc), "error")
        return redirect(url_for("site_config.index"))
    return redirect(url_for("site_config.index"))


@site_config_bp.route("/upload", methods=["POST"], strict_slashes=False)
@page_nivel_required("admin")
def upload():
    """Publica um ZIP estatico pertencente exclusivamente ao tenant atual."""
    organization, site, _content = _site_context()
    try:
        result = publish_bundle(site, request.files.get("site_bundle"))
        from app.models import registrar
        registrar(
            "edicao", "site_publico", "Site publicado pela empresa",
            f"files={result['files']};size_bytes={result['size_bytes']};version={result['version']}",
            organization_id=organization.id,
        )
        db.session.commit()
        flash(f"Site publicado: {result['files']} arquivos enviados com sucesso.", "success")
    except SiteBundleError as exc:
        db.session.rollback()
        flash(str(exc), "error")
    except Exception:
        db.session.rollback()
        flash("Nao foi possivel publicar o site. Verifique o ZIP e tente novamente.", "error")
    return redirect(url_for("site_config.index"))


@site_config_bp.route("/unpublish", methods=["POST"], strict_slashes=False)
@page_nivel_required("admin")
def unpublish():
    organization, site, _content = _site_context()
    had_bundle = unpublish_bundle(site)
    from app.models import registrar
    registrar(
        "exclusao", "site_publico", "Site despublicado pela empresa",
        f"had_bundle={had_bundle}", organization_id=organization.id,
    )
    db.session.commit()
    flash("Site despublicado. Publique outro ZIP para voltar a exibir um site.", "success")
    return redirect(url_for("site_config.index"))


@site_config_bp.route("/toggle", methods=["POST"], strict_slashes=False)
@page_nivel_required("admin")
def toggle():
    organization_id = getattr(g, "organization_id", None)
    if not organization_id:
        abort(403, description="Contexto de empresa necessario.")
    organization = _get_org_or_404(organization_id)
    site = get_or_create_site(organization.id)
    site.site_enabled = not site.site_enabled
    from app.models import registrar
    registrar("status", "site_publico", "Visibilidade do site alterada", f"enabled={site.site_enabled}", organization_id=organization.id)
    db.session.commit()
    status = "ativado" if site.site_enabled else "desativado"
    flash(f"Site publico {status}.", "success")
    return redirect(url_for("site_config.index"))


@site_config_bp.route("/subdomain", methods=["POST"], strict_slashes=False)
@page_nivel_required("admin")
def subdomain():
    organization_id = getattr(g, "organization_id", None)
    if not organization_id:
        abort(403, description="Contexto de empresa necessario.")
    organization = _get_org_or_404(organization_id)
    subdomain = (request.form.get("subdomain") or "").strip()
    try:
        update_tenant_subdomain(organization.id, subdomain)
        from app.models import registrar
        registrar("edicao", "site_publico", "Subdominio do site alterado", "subdomain_configured=true", organization_id=organization.id)
        db.session.commit()
        flash("Subdominio atualizado com sucesso.", "success")
    except (TenantSiteError, DomainResolutionError) as exc:
        db.session.rollback()
        flash(str(exc), "error")
    return redirect(url_for("site_config.index"))


@site_config_bp.route("/verify", methods=["POST"], strict_slashes=False)
@page_nivel_required("admin")
def verify():
    organization_id = getattr(g, "organization_id", None)
    if not organization_id:
        abort(403, description="Contexto de empresa necessario.")
    organization = _get_org_or_404(organization_id)
    ok = verify_custom_domain(organization.id)
    from app.models import registrar
    registrar("status", "site_publico", "Verificacao de dominio executada", f"validated={ok}", organization_id=organization.id)
    db.session.commit()
    if ok:
        flash("Dominio verificado com sucesso. Site liberado.", "success")
    else:
        flash("Dominio ainda nao validado. Configure o registro DNS e tente novamente.", "error")
    return redirect(url_for("site_config.index"))


@site_config_bp.route("/preview", methods=["GET"], strict_slashes=False)
@page_nivel_required("admin")
def preview():
    organization, site, _content = _site_context()
    if site.site_mode != "upload" or not site.site_bundle_version:
        flash("Publique um ZIP antes de abrir a previa do site.", "error")
        return redirect(url_for("site_config.index"))
    return redirect(_public_site_url(organization, site))
