"""Relatórios gerenciais e exportações autorizadas."""
import csv
import io
from datetime import date, datetime, time, timedelta

from flask import Blueprint, Response, flash, redirect, render_template, request, send_file, session, url_for
from sqlalchemy import case, func, text
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import Cliente, OrdemServico, SavedReport, Transacao, registrar
from app.models.ordem_servico import STATUS_OS_LABELS
from app.utils.permissions import permission_required
from app.utils.sanitizers import sanitize_email, sanitize_text
from app.utils.validators import validar_email

relatorios_bp = Blueprint("relatorios", __name__, url_prefix="/relatorios")


def _periodo():
    today = date.today()
    try:
        start = date.fromisoformat(request.args.get("inicio", ""))
    except ValueError:
        start = today.replace(day=1)
    try:
        end = date.fromisoformat(request.args.get("fim", ""))
    except ValueError:
        end = today
    if end < start:
        start, end = end, start
    if end - start > timedelta(days=366):
        start = end - timedelta(days=366)
    return start, end, datetime.combine(start, time.min), datetime.combine(end + timedelta(days=1), time.min)


def _dados():
    start, end, start_dt, end_dt = _periodo()
    orders = (
        OrdemServico.query
        .filter(OrdemServico.deletado_em.is_(None), OrdemServico.data_entrada >= start_dt, OrdemServico.data_entrada < end_dt)
        .options(joinedload(OrdemServico.cliente))
        .order_by(OrdemServico.data_entrada.desc())
        .all()
    )
    totals = db.session.query(
        func.coalesce(func.sum(case((Transacao.tipo == "receita", Transacao.valor), else_=0)), 0),
        func.coalesce(func.sum(case((Transacao.tipo == "despesa", Transacao.valor), else_=0)), 0),
    ).filter(
        Transacao.criado_em >= start_dt,
        Transacao.criado_em < end_dt,
        Transacao.status != "cancelado",
    ).one()
    revenues = float(totals[0] or 0)
    expenses = float(totals[1] or 0)
    status_counts = dict(
        db.session.query(OrdemServico.status, func.count(OrdemServico.id))
        .filter(OrdemServico.deletado_em.is_(None), OrdemServico.data_entrada >= start_dt, OrdemServico.data_entrada < end_dt)
        .group_by(OrdemServico.status)
        .all()
    )
    completed = [item for item in orders if item.data_saida and item.data_entrada]
    average_hours = (
        sum((item.data_saida - item.data_entrada.replace(tzinfo=None)).total_seconds() for item in completed)
        / len(completed) / 3600
        if completed else 0
    )
    decided_quotes = [item for item in orders if item.orcamento_status in {"aprovado", "rejeitado"}]
    approved_quotes = sum(item.orcamento_status == "aprovado" for item in decided_quotes)
    recurring_clients = db.session.query(func.count()).select_from(
        db.session.query(OrdemServico.cliente_id)
        .filter(
            OrdemServico.deletado_em.is_(None),
            OrdemServico.data_entrada >= start_dt,
            OrdemServico.data_entrada < end_dt,
        )
        .group_by(OrdemServico.cliente_id)
        .having(func.count(OrdemServico.id) > 1)
        .subquery()
    ).scalar() or 0
    inactive_since = datetime.combine(date.today() - timedelta(days=90), time.min)
    active_client_count = Cliente.query.filter_by(ativo=True).count()
    recently_active_clients = db.session.query(func.count(func.distinct(OrdemServico.cliente_id))).filter(
        OrdemServico.deletado_em.is_(None),
        OrdemServico.data_entrada >= inactive_since,
    ).scalar() or 0
    order_ids = [item.id for item in orders]
    parts_cost = 0
    if order_ids:
        parts_cost = float(db.session.execute(text(
            "SELECT COALESCE(SUM(op.quantidade * COALESCE(op.custo_unitario, p.custo, 0)), 0) AS custo "
            "FROM os_pecas op JOIN pecas p ON p.id = op.peca_id "
            "WHERE op.os_id IN :ids"
        ).bindparams(db.bindparam("ids", expanding=True)), {"ids": order_ids}).scalar() or 0)
    return {
        "inicio": start, "fim": end, "ordens": orders,
        "receitas": revenues, "despesas": expenses, "saldo": revenues - expenses,
        "status_counts": status_counts,
        "margem_estimada": sum(item.valor_total for item in orders) - parts_cost,
        "tempo_medio_horas": average_hours,
        "conversao_orcamento": (approved_quotes / len(decided_quotes) * 100) if decided_quotes else 0,
        "os_em_garantia": sum(item.em_garantia for item in orders),
        "clientes_recorrentes": int(recurring_clients),
        "clientes_inativos": max(0, int(active_client_count or 0) - int(recently_active_clients or 0)),
    }


def _safe_cell(value):
    text = str(value or "")
    return "'" + text if text.startswith(("=", "+", "-", "@", "\t", "\r")) else text


@relatorios_bp.route("")
@permission_required("relatorios.view", api=False)
def index():
    return render_template(
        "pages/relatorios.html", active="relatorios", dados=_dados(), status_labels=STATUS_OS_LABELS,
        saved_reports=SavedReport.query.filter_by(user_id=session["usuario_id"]).order_by(SavedReport.name).all(),
    )


@relatorios_bp.route("/salvos", methods=["POST"])
@permission_required("relatorios.view", api=False)
def save_report():
    name = sanitize_text(request.form.get("nome", ""), max_length=120)
    recipient = sanitize_email(request.form.get("destinatario", ""))
    frequency = request.form.get("frequencia", "") or None
    if not name or (frequency and frequency not in {"daily", "weekly", "monthly"}):
        flash("Nome ou frequencia invalida.", "error")
        return redirect(url_for("relatorios.index"))
    if frequency and not validar_email(recipient):
        flash("E-mail é obrigatório para agendamento.", "error")
        return redirect(url_for("relatorios.index"))
    now = datetime.now()
    report = SavedReport(
        user_id=session["usuario_id"], name=name,
        filters={"inicio": request.form.get("inicio", ""), "fim": request.form.get("fim", "")},
        frequency=frequency, recipient=recipient or None,
        next_run_at=(now + timedelta(days=1)) if frequency else None,
    )
    db.session.add(report)
    db.session.flush()
    registrar("criacao", "relatorios", f"Relatorio salvo #{report.id} criado", f"frequencia={frequency or 'manual'}")
    db.session.commit()
    flash("Relatório salvo.", "success")
    return redirect(url_for("relatorios.index"))


@relatorios_bp.route("/salvos/<int:report_id>/excluir", methods=["POST"])
@permission_required("relatorios.view", api=False)
def delete_saved_report(report_id):
    report = SavedReport.query.filter_by(id=report_id, user_id=session["usuario_id"]).first_or_404()
    db.session.delete(report)
    registrar("exclusao", "relatorios", f"Relatorio salvo #{report_id} removido")
    db.session.commit()
    flash("Relatório salvo removido.", "success")
    return redirect(url_for("relatorios.index"))


@relatorios_bp.route("/ordens.csv")
@permission_required("relatorios.export", api=False)
def ordens_csv():
    dados = _dados()
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["OS", "Entrada", "Cliente", "Equipamento", "Status", "Técnico", "Total"])
    for order in dados["ordens"]:
        values = [
            order.id, order.data_entrada.strftime("%d/%m/%Y") if order.data_entrada else "",
            order.cliente.nome if order.cliente else "",
            " ".join(filter(None, [order.tipo_aparelho, order.marca, order.modelo])),
            STATUS_OS_LABELS.get(order.status, order.status), order.tecnico_nome, f"{order.valor_total:.2f}",
        ]
        writer.writerow([_safe_cell(value) for value in values])
    return Response(
        "\ufeff" + output.getvalue(), mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=ordens-periodo.csv", "X-Content-Type-Options": "nosniff"},
    )


@relatorios_bp.route("/gerencial.xlsx")
@permission_required("relatorios.export", api=False)
def gerencial_xlsx():
    from openpyxl import Workbook
    from openpyxl.styles import Font

    dados = _dados()
    workbook = Workbook()
    summary = workbook.active
    summary.title = "Resumo"
    summary.append(["Periodo", f"{dados['inicio']:%d/%m/%Y} a {dados['fim']:%d/%m/%Y}"])
    summary.append(["Ordens", len(dados["ordens"])])
    summary.append(["Receitas", dados["receitas"]])
    summary.append(["Despesas", dados["despesas"]])
    summary.append(["Saldo", dados["saldo"]])
    summary["A1"].font = Font(bold=True)
    orders = workbook.create_sheet("Ordens")
    orders.append(["OS", "Entrada", "Cliente", "Equipamento", "Status", "Técnico", "Total"])
    for cell in orders[1]:
        cell.font = Font(bold=True)
    for order in dados["ordens"]:
        orders.append([
            order.id, order.data_entrada.date() if order.data_entrada else None,
            _safe_cell(order.cliente.nome if order.cliente else ""),
            _safe_cell(" ".join(filter(None, [order.tipo_aparelho, order.marca, order.modelo]))),
            STATUS_OS_LABELS.get(order.status, order.status), _safe_cell(order.tecnico_nome), order.valor_total,
        ])
    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)
    return send_file(
        output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True, download_name="relatorio-gerencial.xlsx",
    )


@relatorios_bp.route("/gerencial.pdf")
@permission_required("relatorios.export", api=False)
def gerencial_pdf():
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    dados = _dados()
    output = io.BytesIO()
    document = SimpleDocTemplate(output, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm)
    styles = getSampleStyleSheet()
    rows = [["OS", "Entrada", "Cliente", "Status", "Total"]]
    for order in dados["ordens"][:500]:
        rows.append([
            str(order.id), order.data_entrada.strftime("%d/%m/%Y") if order.data_entrada else "",
            (order.cliente.nome if order.cliente else "")[:45], STATUS_OS_LABELS.get(order.status, order.status),
            f"R$ {order.valor_total:.2f}",
        ])
    table = Table(rows, colWidths=[18 * mm, 28 * mm, 72 * mm, 38 * mm, 28 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
        ("FONTSIZE", (0, 0), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story = [
        Paragraph("Relatório gerencial", styles["Title"]),
        Paragraph(f"Periodo: {dados['inicio']:%d/%m/%Y} a {dados['fim']:%d/%m/%Y}", styles["Normal"]),
        Spacer(1, 5 * mm),
        Paragraph(
            f"Ordens: {len(dados['ordens'])} | Receitas: R$ {dados['receitas']:.2f} | "
            f"Despesas: R$ {dados['despesas']:.2f} | Saldo: R$ {dados['saldo']:.2f}", styles["Normal"],
        ),
        Spacer(1, 5 * mm), table,
    ]
    document.build(story)
    output.seek(0)
    return send_file(output, mimetype="application/pdf", as_attachment=True, download_name="relatorio-gerencial.pdf")
