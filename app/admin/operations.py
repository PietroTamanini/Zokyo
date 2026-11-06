"""Visao operacional global, sem expor payloads ou dados pessoais."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import func

from app.extensions import db
from app.models import EventoLog, Notification, OperationalAlert, OperationalHeartbeat, Organization, TenantSite


def operations_context() -> dict:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    last_24h = now - timedelta(hours=24)
    open_alerts = OperationalAlert.query.filter_by(resolved_at=None).order_by(OperationalAlert.last_seen_at.desc()).limit(50).all()
    heartbeats = OperationalHeartbeat.query.order_by(OperationalHeartbeat.job_name).all()
    queue = dict(db.session.query(Notification.status, func.count(Notification.id)).group_by(Notification.status).execution_options(include_all_tenants=True).all())
    recent_events = EventoLog.query.execution_options(include_all_tenants=True).filter(EventoLog.criado_em >= last_24h).order_by(EventoLog.criado_em.desc()).limit(20).all()
    event_counts = Counter(
        row[0] for row in db.session.query(EventoLog.modulo, func.count(EventoLog.id))
        .filter(EventoLog.criado_em >= last_24h).group_by(EventoLog.modulo)
        .order_by(func.count(EventoLog.id).desc()).limit(10)
        .execution_options(include_all_tenants=True).all()
    )
    sites = TenantSite.query.execution_options(include_all_tenants=True).all()
    stale_jobs = [item for item in heartbeats if item.consecutive_failures or (item.last_success_at and (now - item.last_success_at).total_seconds() > 3600)]
    organizations = {item.id: item.nome for item in Organization.query.execution_options(include_all_tenants=True).all()}
    return {
        "open_alerts": open_alerts, "heartbeats": heartbeats, "stale_jobs": stale_jobs,
        "queue": queue, "recent_events": recent_events, "event_counts": event_counts,
        "organizations": organizations, "events_24h": sum(event_counts.values()),
        "sites_published": sum(1 for site in sites if site.site_mode == "upload" and site.site_bundle_version),
        "sites_without_bundle": sum(1 for site in sites if site.site_mode != "upload" or not site.site_bundle_version),
    }
