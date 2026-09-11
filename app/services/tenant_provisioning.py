"""Provisionamento SaaS de empresas, donos e subdominios."""
import ipaddress
import re
import secrets

import requests
from flask import current_app, has_app_context

from app.extensions import db
from app.models import Configuracao, Organization, Usuario, registrar
from app.services.billing import ensure_trial_subscription
from app.services.message_templates import seed_default_templates
from app.utils.auth import validar_senha_forte
from app.utils.sanitizers import sanitize_email, sanitize_text
from app.utils.validators import validar_email

SLUG_RE = re.compile(r"[a-z0-9][a-z0-9-]{1,78}[a-z0-9]")


class TenantProvisioningError(ValueError):
    pass


def normalize_slug(value: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9-]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    if not SLUG_RE.fullmatch(text):
        raise TenantProvisioningError("Slug invalido. Use 3-80 caracteres: letras minusculas, numeros e hifen.")
    return text


def tenant_hostname(slug: str, base_domain: str | None = None) -> str:
    base = (base_domain or _config_value("TENANT_BASE_DOMAIN") or "tamanini.dev.br").strip().lower().strip(".")
    return f"{normalize_slug(slug)}.{base}"


def _config_value(name: str):
    if has_app_context():
        return current_app.config.get(name)
    return None


def _validate_owner(name: str, email: str, password: str | None, require_password: bool):
    owner_name = sanitize_text(name, max_length=120)
    owner_email = sanitize_email(email)
    if len(owner_name) < 2:
        raise TenantProvisioningError("Nome do dono deve ter pelo menos 2 caracteres.")
    if not validar_email(owner_email):
        raise TenantProvisioningError("E-mail do dono invalido.")
    if require_password:
        errors = validar_senha_forte(password or "")
        if errors:
            raise TenantProvisioningError("Senha invalida: " + " ".join(errors))
    return owner_name, owner_email


def provision_tenant(
    *,
    name: str,
    slug: str,
    owner_name: str,
    owner_email: str,
    owner_password: str | None = None,
    plan_id: int | None = None,
    trial_days: int = 14,
    active: bool = True,
    provision_dns: bool = True,
) -> tuple[Organization, Usuario]:
    organization_name = sanitize_text(name, max_length=200)
    normalized_slug = normalize_slug(slug)
    owner_name, owner_email = _validate_owner(owner_name, owner_email, owner_password, owner_password is not None)
    if not organization_name:
        raise TenantProvisioningError("Nome da empresa e obrigatorio.")
    if Organization.query.execution_options(include_all_tenants=True).filter_by(slug=normalized_slug).first():
        raise TenantProvisioningError("Slug ja cadastrado.")
    if Organization.query.execution_options(include_all_tenants=True).filter_by(subdomain=normalized_slug).first():
        raise TenantProvisioningError("Subdominio ja cadastrado.")
    if Usuario.query.execution_options(include_all_tenants=True).filter_by(email=owner_email).first():
        raise TenantProvisioningError("E-mail do dono ja cadastrado.")

    hostname = tenant_hostname(normalized_slug)
    organization = Organization(
        nome=organization_name,
        slug=normalized_slug,
        subdomain=normalized_slug,
        custom_domain=hostname,
        ativo=active,
        dns_status="pending",
    )
    db.session.add(organization)
    db.session.flush()

    owner = Usuario(
        organization_id=organization.id,
        nome=owner_name,
        email=owner_email,
        nivel="admin",
        ativo=True,
        onboarding_completed=False,
    )
    if owner_password:
        owner.set_senha(owner_password)
    else:
        owner.set_senha(secrets.token_urlsafe(48))
        owner.ativo = False
    db.session.add(owner)
    db.session.flush()
    db.session.add(Configuracao(organization_id=organization.id, nome_empresa=organization_name))
    seed_default_templates(organization.id)
    subscription = ensure_trial_subscription(organization.id, trial_days=trial_days)
    if plan_id:
        subscription.plan_id = plan_id

    if provision_dns:
        sync_tenant_dns(organization)
    else:
        organization.dns_status = "manual"
        organization.dns_last_error = "Use wildcard DNS ou sincronize via Cloudflare no painel global."
    registrar(
        "criacao",
        "organizations",
        f"Empresa provisionada: {organization.nome} ({organization.custom_domain})",
        usuario_id=owner.id,
        usuario_nome=owner.nome,
        organization_id=organization.id,
    )
    return organization, owner


def sync_tenant_dns(organization: Organization) -> bool:
    token = _config_value("CLOUDFLARE_API_TOKEN")
    zone_id = _config_value("CLOUDFLARE_ZONE_ID")
    target = (_config_value("TENANT_DNS_TARGET") or "").strip()
    if not token or not zone_id or not target:
        organization.dns_status = "manual"
        organization.dns_last_error = "Configure wildcard DNS ou defina CLOUDFLARE_API_TOKEN, CLOUDFLARE_ZONE_ID e TENANT_DNS_TARGET."
        return False
    try:
        _upsert_cloudflare_record(token, zone_id, organization.custom_domain, target)
    except requests.RequestException as exc:
        organization.dns_status = "error"
        organization.dns_last_error = str(exc)[:500]
        return False
    organization.dns_status = "active"
    organization.dns_last_error = None
    return True


def _record_type(target: str) -> str:
    try:
        ipaddress.ip_address(target)
    except ValueError:
        return "CNAME"
    return "AAAA" if ":" in target else "A"


def _upsert_cloudflare_record(token: str, zone_id: str, hostname: str, target: str):
    base_url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    record_type = _record_type(target)
    params = {"type": record_type, "name": hostname}
    existing = requests.get(base_url, headers=headers, params=params, timeout=15)
    existing.raise_for_status()
    payload = {
        "type": record_type,
        "name": hostname,
        "content": target,
        "ttl": 1,
        "proxied": True,
    }
    result = existing.json()
    records = result.get("result") or []
    if records:
        response = requests.put(f"{base_url}/{records[0]['id']}", headers=headers, json=payload, timeout=15)
    else:
        response = requests.post(base_url, headers=headers, json=payload, timeout=15)
    response.raise_for_status()
    data = response.json()
    if not data.get("success"):
        raise requests.RequestException(str(data.get("errors") or "Cloudflare recusou o registro DNS."))
