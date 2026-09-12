"""Consultas agregadas do painel admin global."""

from collections import defaultdict

from flask import current_app
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from app.admin.constants import (
    DNS_MODE_LABELS,
    SUBSCRIPTION_STATUS_BADGES,
    SUBSCRIPTION_STATUS_LABELS,
    SUBSCRIPTION_STATUSES,
)
from app.extensions import db
from app.models import (
    LaudoFoto,
    Organization,
    OrganizationSubscription,
    OSFoto,
    Plan,
    Usuario,
)


def admin_dashboard_context() -> dict:
    options = {"include_all_tenants": True}
    organizations = db.session.execute(
        db.select(Organization).order_by(Organization.nome).execution_options(**options)
    ).scalars().all()
    usage = _usage_by_organization(organizations, options)
    owners = _owners_by_organization(options)
    subscriptions = OrganizationSubscription.query.options(joinedload(OrganizationSubscription.plan)).all()
    subscriptions_by_org = {item.organization_id: item for item in subscriptions}
    dns = _dns_context()

    return {
        "organizations": organizations,
        "plans": Plan.query.order_by(Plan.nome).all(),
        "subscriptions": subscriptions,
        "subscriptions_by_org": subscriptions_by_org,
        "usage": usage,
        "summary": _summary(organizations, subscriptions, usage),
        "owners": owners,
        "dns": dns,
        "dns_mode": dns["mode"],
        "dns_target": dns["target"],
        "dns_ready": dns["ready"],
        "base_domain": dns["base_domain"],
        "subscription_statuses": SUBSCRIPTION_STATUSES,
        "subscription_status_labels": SUBSCRIPTION_STATUS_LABELS,
        "subscription_status_badges": SUBSCRIPTION_STATUS_BADGES,
    }


def _usage_by_organization(organizations, options: dict) -> dict[int, dict]:
    user_counts = dict(db.session.execute(
        db.select(Usuario.organization_id, func.count(Usuario.id)).group_by(Usuario.organization_id).execution_options(**options)
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
            "storage_bytes": int(os_storage.get(organization.id, 0) or 0)
            + int(report_storage.get(organization.id, 0) or 0),
        }
    return usage


def _owners_by_organization(options: dict) -> dict[int, list[dict]]:
    owners = defaultdict(list)
    rows = db.session.execute(
        db.select(Usuario.organization_id, Usuario.id, Usuario.nome, Usuario.email)
        .where(Usuario.nivel == "admin", Usuario.organization_id.is_not(None))
        .order_by(Usuario.nome)
        .execution_options(**options)
    ).all()
    for organization_id, user_id, name, email in rows:
        owners[organization_id].append({"id": user_id, "name": name, "email": email})
    return dict(owners)


def _summary(organizations, subscriptions, usage: dict[int, dict]) -> dict:
    return {
        "organizations": len(organizations),
        "active_organizations": sum(1 for item in organizations if item.ativo),
        "inactive_organizations": sum(1 for item in organizations if not item.ativo),
        "total_users": sum(item["users"] for item in usage.values()),
        "past_due": sum(1 for item in subscriptions if item.status == "past_due"),
        "suspended": sum(1 for item in subscriptions if item.status == "suspended"),
        "active_subscriptions": sum(1 for item in subscriptions if item.status in {"active", "trialing"}),
        "trialing": sum(1 for item in subscriptions if item.status == "trialing"),
        "dns_pending": sum(1 for item in organizations if item.dns_status != "active"),
    }


def _dns_context() -> dict:
    mode = (current_app.config.get("TENANT_DNS_MODE") or "manual").lower()
    target = current_app.config.get("TENANT_DNS_TARGET") or ""
    base_domain = current_app.config.get("TENANT_BASE_DOMAIN", "tamanini.dev.br")
    ready = mode == "wildcard" or (
        mode in {"cloudflare", "api"}
        and bool(current_app.config.get("CLOUDFLARE_API_TOKEN"))
        and bool(current_app.config.get("CLOUDFLARE_ZONE_ID"))
        and bool(target)
    )
    return {
        "mode": mode,
        "mode_label": DNS_MODE_LABELS.get(mode, mode),
        "target": target,
        "base_domain": base_domain,
        "ready": ready,
    }
