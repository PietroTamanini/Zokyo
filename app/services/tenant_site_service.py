"""Servico de configuracao de sites publicos por tenant."""
from __future__ import annotations

from app.extensions import db
from app.models import Configuracao, Organization, TenantSite
from app.services.domain_resolution import (
    DomainResolutionError,
    validate_unique_domain,
    validate_unique_subdomain,
)
from app.services.tenant_provisioning import verify_tenant_domain


class TenantSiteError(ValueError):
    pass


def get_or_create_site(organization_id: int) -> TenantSite:
    """Retorna a configuracao de site da organizacao, criando se necessario."""
    site = TenantSite.query.filter_by(organization_id=organization_id).first()
    if not site:
        site = TenantSite(organization_id=organization_id, site_enabled=True)
        db.session.add(site)
        db.session.flush()
    return site


def _clean(value, max_length: int = 600) -> str | None:
    text = str(value if value is not None else "" or "").strip()
    return text[:max_length] or None


def update_site_config(
    organization_id: int,
    data: dict,
    current_user_id: int,
) -> TenantSite:
    """Atualiza configuracao de site publico da organizacao."""
    site = get_or_create_site(organization_id)

    site_enabled = data.get("site_enabled", site.site_enabled)
    site.site_enabled = bool(site_enabled)

    if "site_title" in data:
        site.site_title = _clean(data["site_title"], 200)
    if "site_subtitle" in data:
        site.site_subtitle = _clean(data["site_subtitle"], 300)
    if "site_description" in data:
        site.site_description = _clean(data["site_description"], 600)
    if "primary_color" in data:
        site.primary_color = _clean(data["primary_color"], 7)
    if "accent_color" in data:
        site.accent_color = _clean(data["accent_color"], 7)
    if "logo_url" in data:
        site.logo_url = _clean(data["logo_url"], 600)
    if "favicon_url" in data:
        site.favicon_url = _clean(data["favicon_url"], 600)
    if "cover_image" in data:
        site.cover_image = _clean(data["cover_image"], 600)
    if "secondary_color" in data:
        site.secondary_color = _clean(data["secondary_color"], 7)

    if "site_name" in data:
        site.site_name = _clean(data["site_name"], 200)
    if "tagline" in data:
        site.tagline = _clean(data["tagline"], 300)
    if "description" in data:
        site.description = _clean(data["description"], 1000)
    if "story" in data:
        site.story = _clean(data["story"], 4000)
    if "phone" in data:
        site.phone = _clean(data["phone"], 20)
    if "whatsapp" in data:
        site.whatsapp = _clean(data["whatsapp"], 20)
    if "address" in data:
        site.address = _clean(data["address"], 500)
    if "hours" in data:
        site.hours = _clean(data["hours"], 1000)
    if "services_json" in data:
        site.services_json = _json_or_none(data.get("services_json"))
    if "socials_json" in data:
        site.socials_json = _json_or_none(data.get("socials_json"))
    if "diferencias_json" in data:
        site.diferencias_json = _json_or_none(data.get("diferencias_json"))

    if "seo_title" in data:
        site.seo_title = _clean(data["seo_title"], 200)
    if "seo_description" in data:
        site.seo_description = _clean(data["seo_description"], 500)
    if "seo_image" in data:
        site.seo_image = _clean(data["seo_image"], 600)

    # Dominio customizado do site publico
    new_domain = data.get("custom_domain")
    if new_domain is not None:
        new_domain = str(new_domain or "").strip().lower() or None
        if new_domain and new_domain != site.custom_domain:
            try:
                validate_unique_domain(
                    new_domain,
                    organization_id=organization_id,
                    base_domain=_base_domain(),
                )
            except DomainResolutionError as exc:
                raise TenantSiteError(str(exc)) from exc
            site.custom_domain = new_domain
            site.custom_domain_validated = False  # revalidar apos mudanca
        elif new_domain is None and site.custom_domain is not None:
            site.custom_domain = None
            site.custom_domain_validated = False

    db.session.flush()
    return site


def _json_or_none(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        import json

        return json.dumps(value, ensure_ascii=False)
    text = str(value).strip()
    if not text:
        return None
    return text


def get_site_content(organization: Organization, site: TenantSite) -> dict:
    """Retorna conteudo publico do site com fallbacks para dados da organizacao."""
    cfg = None
    try:
        cfg = Configuracao.get(organization.id)
    except Exception:
        cfg = None

    return {
        "organization": organization,
        "site": site,
        "name": site.site_name or organization.nome or "",
        "tagline": site.tagline or organization.slug or (cfg.subtitulo_empresa if cfg else None) or "",
        "description": site.description or site.site_description or "",
        "story": site.story or "",
        "services": _parse_json(site.services_json) or [],
        "diferenciais": _parse_json(site.diferencias_json) or [],
        "socials": _parse_json(site.socials_json) or {},
        "phone": site.phone or (cfg.telefone if cfg else None) or "",
        "whatsapp": site.whatsapp or (cfg.whatsapp_publico if cfg else None) or "",
        "address": site.address or (cfg.endereco if cfg else None) or "",
        "hours": site.hours or "",
        "colors": {
            "primary": site.primary_color or "#2563eb",
            "secondary": site.secondary_color or "#6b7280",
            "accent": site.accent_color or "#6366f1",
        },
        "seo": {
            "title": site.seo_title or f"{site.site_title or organization.nome} - {site.tagline or 'Assistência Técnica'}",
            "description": site.seo_description or site.description or "",
            "image": site.seo_image or site.cover_image or "",
        },
    }


def _parse_json(value):
    if not value:
        return None
    import json

    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(str(value))
        return parsed if isinstance(parsed, (dict, list)) else None
    except Exception:
        return None


def set_custom_domain(organization_id: int, domain: str) -> TenantSite:
    """Cadastra ou substitui o dominio customizado do site com validacao de unicidade."""
    site = get_or_create_site(organization_id)
    clean = str(domain or "").strip().lower()
    if clean:
        if clean != site.custom_domain:
            try:
                validate_unique_domain(
                    clean,
                    organization_id=organization_id,
                    base_domain=_base_domain(),
                )
            except DomainResolutionError as exc:
                raise TenantSiteError(str(exc)) from exc
            site.custom_domain = clean
            site.custom_domain_validated = False
        organization = (
            Organization.query.execution_options(include_all_tenants=True)
            .filter_by(id=organization_id, ativo=True)
            .first()
        )
        if organization:
            organization.dns_status = "pending"
            organization.dns_last_error = None
    else:
        site.custom_domain = None
        site.custom_domain_validated = False
    db.session.flush()
    return site


def get_domain_status(organization_id: int) -> str:
    """Retorna o indicador do dominio customizado: none/pending/active/error."""
    site = TenantSite.query.filter_by(organization_id=organization_id).first()
    if not site or not site.custom_domain:
        return "none"
    if not site.custom_domain_validated:
        return "pending"
    organization = (
        Organization.query.execution_options(include_all_tenants=True)
        .filter_by(id=organization_id, ativo=True)
        .first()
    )
    dns_status = (organization.dns_status or "pending") if organization else "pending"
    if dns_status == "active":
        return "active"
    if dns_status == "error":
        return "error"
    return "pending"


def _base_domain() -> str:
    from app.services.platform_settings import get_base_domain

    return get_base_domain()


def verify_custom_domain(organization_id: int) -> bool:
    """Dispara verificacao de DNS do dominio customizado e atualiza estado."""
    organization = (
        Organization.query.execution_options(include_all_tenants=True)
        .filter_by(id=organization_id, ativo=True)
        .first()
    )
    site = get_or_create_site(organization_id)
    if not organization or not site.custom_domain:
        return False
    ok = verify_tenant_domain(organization, hostname=site.custom_domain)
    site.custom_domain_validated = bool(ok)
    if ok:
        organization.dns_status = "active"
        organization.dns_last_error = None
    db.session.flush()
    return bool(ok)


def get_public_site_by_host(host: str):
    """Retorna (organization, tenant_site) para renderizacao publica."""
    from app.services.domain_resolution import resolve_organization_from_host

    organization = resolve_organization_from_host(host)
    if not organization:
        return None, None
    site = get_or_create_site(organization.id)
    if not site.site_enabled:
        return organization, None
    return organization, site


def update_tenant_subdomain(organization_id: int, subdomain: str) -> Organization:
    """Atualiza subdominio do tenant com validacao de unicidade."""
    organization = (
        Organization.query.execution_options(include_all_tenants=True)
        .filter_by(id=organization_id, ativo=True)
        .first()
    )
    if not organization:
        from flask import abort

        abort(404)
    value = validate_unique_subdomain(subdomain, organization_id=organization_id)
    organization.subdomain = value
    db.session.flush()
    return organization
