"""Resolucao centralizada de dominio para sites publicos por tenant.

Identifica a organizacao pelo hostname da requisicao HTTP, considerando:
- subdominio (ex: alpha.zokyo.app.br)
- dominio customizado (ex: tecnico.empresa.com.br)

Nunca confia em organization_id enviado pelo cliente/navegador.
"""
from __future__ import annotations

import re
from typing import Optional

from flask import current_app, has_request_context, request

from app.extensions import db
from app.models import Organization, TenantSite

# Hostname valido: letras, digitos, hifen e pontos. Nao permite espacos ou caracteres especiais.
_HOSTNAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*$")


class DomainResolutionError(ValueError):
    """Erro ao validar ou resolver um dominio de tenant."""


def normalize_host(host: str) -> str:
    """Normaliza o valor do Host header: remove porta, minusculo, sem espacos."""
    if not host:
        return ""
    hostname = host.split(":", 1)[0].strip().lower().rstrip(".")
    return hostname


def is_valid_host(host: str) -> bool:
    """Verifica se o host e um nome de dominio valido."""
    hostname = normalize_host(host)
    if not hostname or len(hostname) > 253:
        return False
    return bool(_HOSTNAME_RE.match(hostname))


def resolve_organization_from_host(host: Optional[str], base_domain: Optional[str] = None) -> Optional[Organization]:
    """Resolve a organizacao a partir do hostname da requisicao.

    Prioridade:
    1. Dominio customizado do site publico (TenantSite.custom_domain)
    2. Dominio customizado da organizacao (Organization.custom_domain)
    3. Subdominio sobre TENANT_BASE_DOMAIN (Organization.subdomain)

    Retorna None se nao encontrar ou se o host for invalido.

    Nunca usa organization_id enviado pelo cliente — apenas o hostname.
    """
    if host is None:
        if has_request_context():
            host = request.host
        else:
            return None

    hostname = normalize_host(host)
    if not hostname or not is_valid_host(hostname):
        return None

    resolved_base = (
        base_domain
        or (current_app.config.get("TENANT_BASE_DOMAIN", "tamanini.dev.br") if current_app else None)
        or "tamanini.dev.br"
    )
    base = str(resolved_base).strip().lower().rstrip(".")

    # 1. Dominio customizado do site publico (TenantSite)
    site = (
        db.session.query(TenantSite)
        .execution_options(include_all_tenants=True)
        .filter_by(custom_domain=hostname, custom_domain_validated=True)
        .join(Organization, Organization.id == TenantSite.organization_id)
        .filter(Organization.ativo == True)  # noqa: E712
        .first()
    )
    if site and site.site_enabled:
        return site.organization

    # 2. Dominio customizado da organizacao
    org = (
        Organization.query.execution_options(include_all_tenants=True)
        .filter_by(custom_domain=hostname, ativo=True)
        .first()
    )
    if org:
        return org

    # 3. Subdominio sobre base domain
    if base and hostname != base and hostname.endswith("." + base):
        subdomain = hostname[: - (len(base) + 1)]
        if subdomain and "." not in subdomain:
            org = (
                Organization.query.execution_options(include_all_tenants=True)
                .filter(
                    db.or_(
                        Organization.subdomain == subdomain,
                        Organization.slug == subdomain,
                    ),
                    Organization.ativo == True,  # noqa: E712
                )
                .first()
            )
            if org:
                return org

    return None


def resolve_organization_from_current_request() -> Optional[Organization]:
    """Resolve a organizacao a partir do host da requisicao atual (Flask)."""
    if not has_request_context():
        return None
    return resolve_organization_from_host(request.host)


def validate_unique_domain(domain: str, organization_id: Optional[int] = None, base_domain: Optional[str] = None) -> str:
    """Valida que um dominio nao esta em uso por outra organizacao.

    Retorna o dominio normalizado ou levanta DomainResolutionError.
    """
    hostname = normalize_host(domain)
    if not hostname or not is_valid_host(hostname):
        raise DomainResolutionError("Dominio invalido.")

    resolved_base = (
        base_domain
        or (current_app.config.get("TENANT_BASE_DOMAIN", "tamanini.dev.br") if current_app else None)
        or "tamanini.dev.br"
    )
    base = str(resolved_base).strip().lower().rstrip(".")

    # Verifica em TenantSite.custom_domain
    q = (
        db.session.query(TenantSite)
        .execution_options(include_all_tenants=True)
        .filter_by(custom_domain=hostname)
    )
    if organization_id:
        q = q.filter(TenantSite.organization_id != organization_id)
    existing = q.first()
    if existing:
        raise DomainResolutionError(
            f"O dominio '{hostname}' ja esta cadastrado para outra empresa."
        )

    # Verifica em Organization.custom_domain
    q_org = Organization.query.execution_options(include_all_tenants=True).filter_by(custom_domain=hostname)
    if organization_id:
        q_org = q_org.filter(Organization.id != organization_id)
    existing_org = q_org.first()
    if existing_org:
        raise DomainResolutionError(
            f"O dominio '{hostname}' ja esta cadastrado como dominio da organizacao."
        )

    # Verifica em Organization.subdomain (conflito com base_domain)
    if base and hostname.endswith("." + base):
        subdomain = hostname[: - (len(base) + 1)]
        q_sub = Organization.query.execution_options(include_all_tenants=True).filter_by(subdomain=subdomain)
        existing_sub = q_sub.first()
        if existing_sub:
            if organization_id and existing_sub.id == organization_id:
                return hostname
            raise DomainResolutionError(
                f"O subdominio '{subdomain}' ja esta em uso por outra empresa."
            )

    # A custom domain cannot reuse another tenant's public name as its first
    # label, even when it uses a different DNS base domain.
    label = hostname.split(".", 1)[0]
    existing_sub = (
        Organization.query.execution_options(include_all_tenants=True)
        .filter(Organization.subdomain == label)
        .first()
    )
    if existing_sub and existing_sub.id != organization_id:
        raise DomainResolutionError(
            f"O subdominio '{label}' ja esta em uso por outra empresa."
        )

    return hostname


_SUBDOMAIN_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def normalize_subdomain(value) -> str:
    """Normaliza e valida subdominio de tenant (1-63 chars)."""
    text = str(value or "").strip().lower()
    if not text or not _SUBDOMAIN_RE.fullmatch(text):
        raise DomainResolutionError("Subdominio invalido. Use 1-63 caracteres: letras minusculas, numeros e hifen.")
    return text


def validate_unique_subdomain(subdomain: str, organization_id: Optional[int] = None) -> str:
    """Valida unicidade de subdominio entre empresas. Retorna o valor normalizado."""
    value = normalize_subdomain(subdomain)
    q = Organization.query.execution_options(include_all_tenants=True).filter_by(subdomain=value)
    if organization_id:
        q = q.filter(Organization.id != organization_id)
    if q.first():
        raise DomainResolutionError(f"O subdominio '{value}' ja esta em uso por outra empresa.")
    return value
