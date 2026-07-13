"""Processamento isolado de relatorios gerenciais agendados."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func

from app.extensions import db
from app.models import OrdemServico, SavedReport, Transacao
from app.services.notifications import enqueue_email


def _now():
    return datetime.now(timezone.utc)


def _next_run(now, frequency):
    return now + {"daily": timedelta(days=1), "weekly": timedelta(days=7), "monthly": timedelta(days=30)}[frequency]


def process_scheduled_reports(limit=50):
    now = _now()
    reports = SavedReport.query.execution_options(include_all_tenants=True).filter(
        SavedReport.active.is_(True), SavedReport.next_run_at <= now,
    ).order_by(SavedReport.next_run_at).limit(limit).all()
    for report in reports:
        options = {"include_all_tenants": True}
        orders = db.session.execute(
            db.select(func.count(OrdemServico.id)).where(
                OrdemServico.organization_id == report.organization_id,
                OrdemServico.deletado_em.is_(None),
            ).execution_options(**options)
        ).scalar_one()
        revenues = db.session.execute(
            db.select(func.coalesce(func.sum(Transacao.valor), 0)).where(
                Transacao.organization_id == report.organization_id,
                Transacao.tipo == "receita", Transacao.status == "pago",
            ).execution_options(**options)
        ).scalar_one()
        expenses = db.session.execute(
            db.select(func.coalesce(func.sum(Transacao.valor), 0)).where(
                Transacao.organization_id == report.organization_id,
                Transacao.tipo == "despesa", Transacao.status == "pago",
            ).execution_options(**options)
        ).scalar_one()
        body = (
            f"Relatorio: {report.name}\n\nOrdens: {orders}\n"
            f"Receitas pagas: R$ {float(revenues):.2f}\nDespesas pagas: R$ {float(expenses):.2f}\n"
            f"Saldo: R$ {float(revenues - expenses):.2f}\n"
        )
        enqueue_email(
            report.organization_id, report.recipient, f"Relatorio agendado - {report.name}", body,
            "scheduled_report", f"scheduled-report-{report.id}-{now.date().isoformat()}",
        )
        report.last_run_at = now
        report.next_run_at = _next_run(now, report.frequency)
    db.session.commit()
    return len(reports)
