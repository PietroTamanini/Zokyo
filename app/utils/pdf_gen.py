"""
utils/pdf_gen.py — Geração de PDF da OS.

Fix M05: validação de wkhtmltopdf_path contra path injection/traversal.
  - Aceita apenas caminhos absolutos dentro de uma allowlist de diretórios.
  - Verifica que o binário existe e é executável.
  - Não interpola input do usuário no caminho.
"""
import io
import logging
import os
from pathlib import Path

from flask import render_template, current_app

logger = logging.getLogger(__name__)

# Diretórios onde o wkhtmltopdf pode estar instalado legitimamente
_WKHTMLTOPDF_ALLOWED_DIRS = {
    "/usr/bin",
    "/usr/local/bin",
    "/snap/bin",
    "/opt/wkhtmltopdf/bin",
}


def _validar_wkhtmltopdf_path(path: str) -> str | None:
    """
    M05: Valida o caminho do wkhtmltopdf.
    Retorna o caminho se for seguro, None caso contrário.
    """
    if not path:
        return None

    try:
        p = Path(path).resolve()
    except (ValueError, OSError):
        logger.warning("[PDF] Caminho inválido: %r", path)
        return None

    # Deve ser absoluto
    if not p.is_absolute():
        logger.warning("[PDF] Caminho não absoluto rejeitado: %r", path)
        return None

    # Deve estar em um diretório permitido
    if str(p.parent) not in _WKHTMLTOPDF_ALLOWED_DIRS:
        logger.warning("[PDF] Diretório não autorizado: %r", str(p.parent))
        return None

    # Deve existir e ser executável
    if not p.exists():
        logger.warning("[PDF] Arquivo não existe: %r", str(p))
        return None

    if not os.access(str(p), os.X_OK):
        logger.warning("[PDF] Arquivo não é executável: %r", str(p))
        return None

    return str(p)


def _pdf_via_pdfkit(html: str, wkhtmltopdf_path: str, options: dict) -> bytes:
    import pdfkit
    config = pdfkit.configuration(wkhtmltopdf=wkhtmltopdf_path)
    # Garante que opções de segurança estejam sempre presentes
    opts = dict(options)
    opts.setdefault("disable-local-file-access", None)
    opts.setdefault("no-background", None)
    return pdfkit.from_string(html, False, options=opts, configuration=config)


def _pdf_via_reportlab(os_obj) -> bytes:
    """Fallback: PDF simples com reportlab."""
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                    Table, TableStyle)
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

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
        return [Paragraph(label, label_style),
                Paragraph(str(value or "—"), value_style)]

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
        Paragraph(cfg.nome_empresa or "Zokyo Platform", title_style),
        Paragraph(
            f"Ordem de Serviço #{os_obj.id:04d}  |  Status: {os_obj.status}  |  "
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
        Paragraph(os_obj.defeito_alegado or "—", value_style),
        Spacer(1, 3 * mm),
        section_header("Defeito Encontrado / Solução"),
        Paragraph(os_obj.defeito_encontrado or "—", value_style),
        Paragraph(os_obj.solucao or "—", value_style),
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
    from app.models import Configuracao
    cfg = Configuracao.get()

    raw_path = (cfg.wkhtmltopdf_path or "").strip() or \
               current_app.config.get("PDFKIT_WKHTMLTOPDF")

    # M05: valida antes de usar o caminho
    wkhtmltopdf_path = _validar_wkhtmltopdf_path(raw_path) if raw_path else None

    if wkhtmltopdf_path:
        try:
            html = render_template(
                "os_pdf.html",
                os=os_obj,
                cliente=os_obj.cliente,
                empresa=Configuracao.get(),
                tecnico=os_obj.usuario,
            )
            options = dict(current_app.config.get("PDFKIT_OPTIONS", {}))
            return _pdf_via_pdfkit(html, wkhtmltopdf_path, options)
        except Exception as exc:
            logger.warning("pdfkit falhou (%s), usando fallback reportlab", exc)

    try:
        return _pdf_via_reportlab(os_obj)
    except ImportError:
        raise RuntimeError(
            "Nem wkhtmltopdf nem reportlab estão disponíveis. "
            "Instale: pip install reportlab"
        )
    except Exception as exc:
        logger.error("Erro no fallback reportlab: %s", exc)
        raise RuntimeError(f"Erro ao gerar PDF: {exc}") from exc
