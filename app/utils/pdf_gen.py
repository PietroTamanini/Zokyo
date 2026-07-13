"""Geracao deterministica do PDF de ordem de servico com ReportLab."""
import io
import logging
from xml.sax.saxutils import escape

logger = logging.getLogger(__name__)

def _pdf_via_reportlab(os_obj) -> bytes:
    """Gera PDF A4 sem depender de binario, shell, rede ou template HTML."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                            leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=12 * mm, bottomMargin=12 * mm)
    styles = getSampleStyleSheet()
    azul   = colors.HexColor("#1e3a5f")
    cinza  = colors.HexColor("#f5f7fa")
    verde  = colors.HexColor("#2e7d32")

    title_style   = ParagraphStyle("title",   parent=styles["Heading1"],
                                   textColor=azul, fontSize=16, spaceAfter=4)
    sub_style     = ParagraphStyle("sub",     parent=styles["Normal"],
                                   textColor=colors.grey, fontSize=9)
    label_style   = ParagraphStyle("label",   parent=styles["Normal"],
                                   textColor=colors.grey, fontSize=8,
                                   fontName="Helvetica-Bold")
    value_style   = ParagraphStyle("value",   parent=styles["Normal"], fontSize=10)
    section_style = ParagraphStyle("section", parent=styles["Normal"],
                                   textColor=colors.white, fontSize=9,
                                   fontName="Helvetica-Bold")

    cfg     = __import__("app.models", fromlist=["Configuracao"]).Configuracao.get()
    cliente = os_obj.cliente
    total   = float(os_obj.valor_total or 0)

    def row(label, value):
        return [Paragraph(escape(str(label)), label_style),
                Paragraph(escape(str(value or "—")), value_style)]

    def section_header(text):
        t = Table([[Paragraph(text, section_style)]], colWidths=[260 * mm])
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), azul),
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ]))
        return t

    story = [
        Paragraph(escape(cfg.nome_empresa or "Zokyo Platform"), title_style),
        Paragraph(
            escape(f"Ordem de Serviço #{os_obj.id:04d}  |  Status: {os_obj.status}  |  ") +
            f"Entrada: {os_obj.data_entrada.strftime('%d/%m/%Y') if os_obj.data_entrada else '—'}",
            sub_style,
        ),
        Spacer(1, 8 * mm),
    ]

    dados = Table([
        row("Cliente",    cliente.nome if cliente else "—"),
        row("Telefone",   cliente.telefone if cliente else "—"),
        row("Aparelho",   f"{os_obj.tipo_aparelho or ''} {os_obj.marca or ''} {os_obj.modelo or ''}".strip()),
        row("Nº Série",   os_obj.numero_serie),
        row("Técnico",    os_obj.tecnico_nome),
        row("Prioridade", os_obj.prio),
        row("Garantia",   f"{os_obj.garantia_dias or 90} dias"),
    ], colWidths=[60 * mm, 200 * mm])
    dados.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, cinza]),
        ("TOPPADDING",     (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 5),
        ("LEFTPADDING",    (0, 0), (-1, -1), 6),
    ]))
    story += [dados, Spacer(1, 5 * mm)]

    story += [
        section_header("Defeito Alegado pelo Cliente"),
        Paragraph(escape(os_obj.defeito_alegado or "—"), value_style),
        Spacer(1, 3 * mm),
        section_header("Defeito Encontrado / Solução"),
        Paragraph(escape(os_obj.defeito_encontrado or "—"), value_style),
        Paragraph(escape(os_obj.solucao or "—"), value_style),
        Spacer(1, 5 * mm),
    ]

    tot_style = ParagraphStyle("tot", parent=styles["Normal"],
                               fontName="Helvetica-Bold", fontSize=13, textColor=verde)
    fin = Table([
        [Paragraph("Mão de Obra", label_style),
         Paragraph(f"R$ {float(os_obj.valor_servico or 0):.2f}", value_style)],
        [Paragraph("Peças",       label_style),
         Paragraph(f"R$ {float(os_obj.valor_pecas or 0):.2f}",   value_style)],
        [Paragraph("Desconto",    label_style),
         Paragraph(f"R$ {float(os_obj.desconto or 0):.2f}",      value_style)],
        [Paragraph("TOTAL", tot_style),
         Paragraph(f"R$ {total:.2f}", tot_style)],
    ], colWidths=[60 * mm, 60 * mm])
    fin.setStyle(TableStyle([
        ("LINEABOVE",      (0, 3), (-1, 3), 1.5, verde),
        ("TOPPADDING",     (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 5),
        ("LEFTPADDING",    (0, 0), (-1, -1), 6),
    ]))
    story.append(fin)

    checklist = getattr(os_obj, "checklist_snapshot", None) or []
    answers = getattr(os_obj, "checklist_answers", None) or {}
    if checklist:
        story += [Spacer(1, 4 * mm), section_header("Checklist tecnico")]
        checklist_rows = [
            [Paragraph("OK" if answers.get(item) is True else "Pendente", label_style), Paragraph(escape(item), value_style)]
            for item in checklist
        ]
        checklist_table = Table(checklist_rows, colWidths=[30 * mm, 230 * mm])
        checklist_table.setStyle(TableStyle([
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, cinza]),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(checklist_table)

    accepted_at = getattr(os_obj, "authorization_accepted_at", None)
    accepted_by = getattr(os_obj, "authorization_accepted_by", None)
    term = (
        "O cliente autoriza o diagnostico e a execucao dos servicos aprovados, "
        "ciente de que dados importantes devem possuir copia de seguranca previa."
    )
    story += [Spacer(1, 4 * mm), section_header("Termo de autorizacao"), Paragraph(term, value_style)]
    if accepted_at:
        accepted_text = f"Aceite registrado por {accepted_by or 'responsavel'} em {accepted_at.strftime('%d/%m/%Y %H:%M')}."
        story.append(Paragraph(escape(accepted_text), label_style))

    story.append(Spacer(1, 12 * mm))
    ass = Table([
        ["", ""],
        [Paragraph("Assinatura do Técnico", sub_style),
         Paragraph("Assinatura do Cliente", sub_style)],
    ], colWidths=[130 * mm, 130 * mm])
    ass.setStyle(TableStyle([
        ("LINEABOVE",  (0, 0), (-1, 0), 0.8, colors.grey),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("ALIGN",      (0, 0), (-1, -1), "CENTER"),
    ]))
    story.append(ass)

    doc.build(story)
    return buf.getvalue()


def gerar_pdf_os(os_obj) -> bytes:
    try:
        return _pdf_via_reportlab(os_obj)
    except ImportError:
        raise RuntimeError("ReportLab nao esta disponivel. Instale as dependencias do projeto.")
    except Exception as exc:
        logger.error("Erro ao gerar PDF de OS: %s", exc)
        raise RuntimeError(f"Erro ao gerar PDF: {exc}") from exc
