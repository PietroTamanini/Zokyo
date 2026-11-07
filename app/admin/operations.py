"""Visao operacional global, sem expor payloads ou dados pessoais."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import func

from app.extensions import db
from app.models import DataSubjectRequest, EventoLog, Notification, OperationalAlert, OperationalHeartbeat, Organization, PrivacyIncident, TenantSite


_JOB_MAX_AGE = {
    "processar_notificacoes": timedelta(minutes=5),
    "processar_relatorios": timedelta(hours=2),
    "limpar_rate_limit": timedelta(hours=30),
    "aplicar_retencao": timedelta(hours=30),
    "verificar_auditoria": timedelta(hours=30),
    "monitorar_prazos_privacidade": timedelta(hours=30),
    "limpar_importacoes_temporarias": timedelta(hours=30),
}


def _job_stale(heartbeat, now):
    if heartbeat.consecutive_failures:
        return True
    if not heartbeat.last_success_at:
        return False
    last_success = heartbeat.last_success_at
    if last_success.tzinfo:
        last_success = last_success.astimezone(timezone.utc).replace(tzinfo=None)
    return now - last_success > _JOB_MAX_AGE.get(heartbeat.job_name, timedelta(hours=2))


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
    stale_jobs = [item for item in heartbeats if _job_stale(item, now)]
    audit_heartbeat = next((item for item in heartbeats if item.job_name == "verificar_auditoria"), None)
    audit_unverified = audit_heartbeat is None or (
        audit_heartbeat.last_success_at is None and not audit_heartbeat.consecutive_failures
    )
    organizations = {item.id: item.nome for item in Organization.query.execution_options(include_all_tenants=True).all()}
    open_requests = DataSubjectRequest.query.execution_options(include_all_tenants=True).filter(
        DataSubjectRequest.status.in_(('open', 'in_progress'))
    ).count()
    overdue_requests = DataSubjectRequest.query.execution_options(include_all_tenants=True).filter(
        DataSubjectRequest.status.in_(('open', 'in_progress')),
        DataSubjectRequest.due_at.is_not(None), DataSubjectRequest.due_at < now,
    ).count()
    open_incidents = PrivacyIncident.query.execution_options(include_all_tenants=True).filter_by(status="open").count()
    critical_incidents = PrivacyIncident.query.execution_options(include_all_tenants=True).filter_by(
        status="open", severity="critical",
    ).count()
    undecided_incidents = PrivacyIncident.query.execution_options(include_all_tenants=True).filter(
        PrivacyIncident.status != "closed",
        PrivacyIncident.known_at.is_not(None),
        PrivacyIncident.known_at <= now - timedelta(hours=24),
        PrivacyIncident.notification_decision.is_(None),
    ).count()
    return {
        "open_alerts": open_alerts, "heartbeats": heartbeats, "stale_jobs": stale_jobs,
        "audit_heartbeat": audit_heartbeat, "audit_unverified": audit_unverified,
        "queue": queue, "recent_events": recent_events, "event_counts": event_counts,
        "organizations": organizations, "events_24h": sum(event_counts.values()),
        "sites_published": sum(1 for site in sites if site.site_mode == "upload" and site.site_bundle_version),
        "sites_without_bundle": sum(1 for site in sites if site.site_mode != "upload" or not site.site_bundle_version),
        "privacy_open_requests": open_requests, "privacy_overdue_requests": overdue_requests,
        "privacy_open_incidents": open_incidents, "privacy_critical_incidents": critical_incidents,
        "privacy_undecided_incidents": undecided_incidents,
    }
