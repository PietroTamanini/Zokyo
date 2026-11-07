"""Sinais operacionais de prazos de privacidade, sem dados pessoais nos alertas."""
from datetime import datetime, timedelta, timezone

from app.models import DataSubjectRequest, PrivacyIncident
from app.services.operational_alerts import emit_alert


def monitor_privacy_deadlines(now=None):
    """Avisa sobre pedidos próximos/vencidos e incidentes sem decisão registrada."""
    moment = now or datetime.now(timezone.utc).replace(tzinfo=None)
    if moment.tzinfo:
        moment = moment.astimezone(timezone.utc).replace(tzinfo=None)
    pending = DataSubjectRequest.query.execution_options(include_all_tenants=True).filter(
        DataSubjectRequest.status.in_(("open", "in_progress")),
        DataSubjectRequest.due_at.is_not(None),
    )
    overdue = pending.filter(DataSubjectRequest.due_at < moment).count()
    approaching = pending.filter(
        DataSubjectRequest.due_at >= moment,
        DataSubjectRequest.due_at <= moment + timedelta(days=2),
    ).count()
    undecided_incidents = PrivacyIncident.query.execution_options(include_all_tenants=True).filter(
        PrivacyIncident.status != "closed",
        PrivacyIncident.known_at.is_not(None),
        PrivacyIncident.known_at <= moment - timedelta(hours=24),
        PrivacyIncident.notification_decision.is_(None),
    ).count()
    counts = {
        "requests_overdue": overdue,
        "requests_approaching": approaching,
        "incidents_without_decision": undecided_incidents,
    }
    if overdue:
        emit_alert("critical", "prazo_dsar_vencido", "Há solicitações de titulares vencidas. Verifique a fila de privacidade.")
    if approaching:
        emit_alert("warning", "prazo_dsar_proximo", "Há solicitações de titulares com prazo em até dois dias. Verifique a fila de privacidade.")
    if undecided_incidents:
        emit_alert("warning", "incidente_sem_decisao", "Há incidentes com afetação conhecida e sem decisão de comunicação registrada após 24 horas.")
    return counts
