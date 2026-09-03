"""Portal público mínimo para acompanhamento e aprovação de orçamento."""
import io

from flask import Blueprint, abort, make_response, redirect, render_template, request, send_file, session, url_for

from app.extensions import db
from app.models import OrdemServico, OSHistorico, Usuario
from app.models.ordem_servico import STATUS_OS_LABELS
from app.services.portal import buscar_token_portal, criar_link_portal, decidir_orcamento
from app.utils.auth import nivel_required

portal_bp = Blueprint("portal", __name__)


def _public_response(template, **context):
    response = make_response(render_template(template, **context))
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    return response


def _portal_context(portal_token, **extra):
    historico = (
        OSHistorico.query.execution_options(include_all_tenants=True)
        .filter_by(os_id=portal_token.os_id, organization_id=portal_token.organization_id)
        .order_by(OSHistorico.criado_em.asc())
        .all()
    )
    context = {
        "portal_token": portal_token,
        "os": portal_token.os,
        "historico": historico,
        "status_labels": STATUS_OS_LABELS,
    }
    context.update(extra)
    return context


def _pdf_publico_os(portal_token) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    os_obj = portal_token.os
    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm)
    styles = getSampleStyleSheet()
    equipamento = " ".join(part for part in [os_obj.tipo_aparelho, os_obj.marca, os_obj.modelo] if part) or "-"
    rows = [
        ["OS", f"#{os_obj.id:04d}"],
        ["Status", STATUS_OS_LABELS.get(os_obj.status, os_obj.status)],
        ["Equipamento", equipamento],
        ["Entrada", os_obj.data_entrada.strftime("%d/%m/%Y") if os_obj.data_entrada else "-"],
        ["Previsão", os_obj.data_prev.strftime("%d/%m/%Y") if os_obj.data_prev else "-"],
        ["Valor total", f"R$ {float(os_obj.valor_total or 0):.2f}"],
    ]
    table = Table(rows, colWidths=[35 * mm, 135 * mm])
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story = [
        Paragraph("Acompanhamento da ordem de serviço", styles["Title"]),
        Paragraph("Documento público gerado pelo Zokyo. Dados internos de diagnóstico e identificadores sensíveis não são exibidos.", styles["Normal"]),
        Spacer(1, 7 * mm),
        table,
    ]
    doc.build(story)
    return output.getvalue()


@portal_bp.route("/os/<int:os_id>/portal-link", methods=["POST"])
@nivel_required("admin", "operacional")
def gerar_link(os_id):
    usuario = db.session.get(Usuario, session.get("usuario_id"))
    os_obj = OrdemServico.query.filter_by(id=os_id, organization_id=usuario.organization_id).first_or_404()
    purpose = request.form.get("purpose", "tracking")
    try:
        raw_token = criar_link_portal(os_obj, usuario, purpose, request.form.get("dias", 30, type=int))
        db.session.commit()
    except (TypeError, ValueError) as exc:
        db.session.rollback()
        return render_template("pages/portal_link_result.html", erro=str(exc), os=os_obj), 400
    link = url_for("portal.publico", token=raw_token, _external=True)
    return render_template("pages/portal_link_result.html", link=link, purpose=purpose, os=os_obj)


@portal_bp.route("/portal/os/<token>", methods=["GET", "POST"])
def publico(token):
    portal_token = buscar_token_portal(token)
    if not portal_token:
        abort(404)
    if request.method == "POST":
        decision = request.form.get("decisao", "")
        try:
            decidir_orcamento(portal_token, decision)
            db.session.commit()
        except ValueError as exc:
            db.session.rollback()
            response = _public_response("pages/portal_os.html", **_portal_context(portal_token, erro=str(exc)))
            response.status_code = 409
            return response
        if decision == "approved":
            from app.services.order_notifications import queue_order_event
            queue_order_event(
                portal_token.os,
                "os_status_em_reparo",
                f"budget-approved-{portal_token.id}",
            )
        return redirect(url_for("portal.publico", token=token))
    return _public_response("pages/portal_os.html", **_portal_context(portal_token))


@portal_bp.route("/portal/os/<token>/pdf")
def publico_pdf(token):
    portal_token = buscar_token_portal(token)
    if not portal_token:
        abort(404)
    pdf = _pdf_publico_os(portal_token)
    codigo_os = portal_token.os.codigo_os if portal_token.os else f"{portal_token.os_id:04d}"
    return send_file(
        io.BytesIO(pdf),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"OS_{codigo_os}.pdf",
    )
