"""Geração determinística do PDF de ordem de serviço com ReportLab."""
from __future__ import annotations

import io
import ipaddress
import logging
import socket
from pathlib import Path
from urllib.parse import unquote, urlparse

logger = logging.getLogger(__name__)


def _pdf_via_reportlab(os_obj) -> bytes:
    """Gera a OS em A4 paisagem, com duas vias do cliente."""
    from flask import current_app
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfgen import canvas

    models = __import__("app.models", fromlist=["Configuracao"])
    cfg = models.Configuracao.get()
    cliente = getattr(os_obj, "cliente", None)
    codigo_os = getattr(os_obj, "codigo_os", f"{getattr(os_obj, 'id', 0):04d}")
    page_w, page_h = landscape(A4)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=landscape(A4))
    c.setTitle(f"OS {codigo_os}")

    accent = colors.HexColor("#111111")
    accent_dark = colors.HexColor("#111111")
    accent_soft = colors.HexColor("#f3f4f6")
    ink = colors.HexColor("#111827")
    muted = colors.HexColor("#4b5563")
    border = colors.HexColor("#1f2937")
    hairline = colors.HexColor("#9ca3af")
    paper = colors.white
    panel = colors.HexColor("#f9fafb")

    def clean(value, fallback="-"):
        text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
        return text or fallback

    def digits(value):
        return "".join(ch for ch in str(value or "") if ch.isdigit())

    def date_fmt(value):
        return value.strftime("%d/%m/%Y") if value else "-"

    def phone_fmt(value):
        raw = digits(value)
        if len(raw) == 11:
            return f"({raw[:2]}) {raw[2:7]}-{raw[7:]}"
        if len(raw) == 10:
            return f"({raw[:2]}) {raw[2:6]}-{raw[6:]}"
        return clean(value)

    def doc_fmt():
        if not cliente:
            return "-"
        if getattr(cliente, "documento", ""):
            return cliente.documento
        raw = digits(getattr(cliente, "cpf", "") or getattr(cliente, "cnpj", ""))
        return raw or "-"

    def company_lines():
        contact = []
        if getattr(cfg, "telefone", None):
            contact.append(phone_fmt(cfg.telefone))
        if getattr(cfg, "whatsapp_publico", None):
            contact.append(f"WhatsApp {phone_fmt(cfg.whatsapp_publico)}")
        if getattr(cfg, "instagram_url", None):
            contact.append(cfg.instagram_url)
        if getattr(cfg, "site_url", None):
            contact.append(cfg.site_url)
        if getattr(cfg, "email", None):
            contact.append(cfg.email)
        location = " - ".join(part for part in [cfg.endereco, cfg.cidade, cfg.uf] if part)
        return clean(cfg.nome_empresa, "Nome da loja"), clean(cfg.subtitulo_empresa, "Assistência técnica e manutenção"), location, " | ".join(contact)

    def fit_text(text, max_width, font="Helvetica", size=7, min_size=4.6):
        text = clean(text, "")
        current_size = size
        while current_size > min_size and stringWidth(text, font, current_size) > max_width:
            current_size -= 0.2
        if stringWidth(text, font, current_size) <= max_width:
            return text, current_size
        while text and stringWidth(text, font, min_size) > max_width:
            text = text[:-1].rstrip()
        return text or "-", min_size

    def draw_fit_text(x, y, text, max_width, font="Helvetica", size=7, min_size=4.6):
        line_text, font_size = fit_text(text, max_width, font, size, min_size)
        c.setFont(font, font_size)
        c.drawString(x, y, line_text)

    def draw_centered_fit_text(x, y, text, max_width, font="Helvetica", size=7, min_size=4.6):
        line_text, font_size = fit_text(text, max_width, font, size, min_size)
        c.setFont(font, font_size)
        c.drawCentredString(x, y, line_text)

    def wrap_text(text, max_width, font="Helvetica", size=7, max_lines=3):
        words = clean(text, "").split()
        lines = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if stringWidth(candidate, font, size) <= max_width:
                current = candidate
            elif stringWidth(word, font, size) > max_width:
                if current:
                    lines.append(current)
                    current = ""
                chunk = ""
                for char in word:
                    candidate = f"{chunk}{char}"
                    if stringWidth(candidate, font, size) <= max_width:
                        chunk = candidate
                    else:
                        if chunk:
                            lines.append(chunk)
                        chunk = char
                    if len(lines) >= max_lines:
                        break
                current = chunk
            else:
                if current:
                    lines.append(current)
                current = word
            if len(lines) >= max_lines:
                break
        if current and len(lines) < max_lines:
            lines.append(current)
        return lines or ["-"]

    def draw_wrapped(x, y, text, max_width, font="Helvetica", size=7, leading=10, max_lines=3):
        c.setFont(font, size)
        for idx, line_text in enumerate(wrap_text(text, max_width, font, size, max_lines)):
            c.drawString(x, y - idx * leading, line_text)

    def draw_label_line(x, y, width, label, value="", font_size=6):
        c.setFillColor(muted)
        c.setFont("Helvetica-Bold", font_size)
        c.drawString(x, y, label.upper())
        c.setStrokeColor(hairline)
        c.setLineWidth(0.45)
        c.line(x, y - 12, x + width, y - 12)
        if value:
            c.setFillColor(ink)
            draw_fit_text(x + 1, y - 9, value, width - 2, size=7, min_size=4.8)

    def logo_path():
        raw = clean(getattr(cfg, "logo_url", ""), "")
        if not raw:
            return None
        parsed = urlparse(raw)
        candidate = None
        if parsed.scheme in {"http", "https"} and parsed.path.startswith("/static/"):
            candidate = Path(current_app.static_folder) / unquote(parsed.path.removeprefix("/static/"))
        elif raw.startswith("/static/"):
            candidate = Path(current_app.static_folder) / unquote(raw.removeprefix("/static/"))
        elif not parsed.scheme:
            candidate = (Path(current_app.root_path) / raw).resolve()
        if not candidate or not candidate.exists():
            return None
        allowed = [Path(current_app.static_folder).resolve(), Path(current_app.instance_path).resolve()]
        resolved = candidate.resolve()
        return resolved if any(resolved == base or base in resolved.parents for base in allowed) else None

    def safe_external_logo():
        raw = clean(getattr(cfg, "logo_url", ""), "")
        parsed = urlparse(raw)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            return None
        try:
            for result in socket.getaddrinfo(parsed.hostname, parsed.port or 443):
                ip = ipaddress.ip_address(result[4][0])
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                    return None
            import requests
            response = requests.get(raw, timeout=2, allow_redirects=False, stream=True)
            content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            content_length = int(response.headers.get("content-length") or 0)
            if response.status_code != 200 or content_type not in {"image/png", "image/jpeg", "image/webp"}:
                return None
            if content_length and content_length > 1_000_000:
                return None
            data = response.raw.read(1_000_001, decode_content=True)
            return io.BytesIO(data) if len(data) <= 1_000_000 else None
        except Exception as exc:
            logger.warning("Logo externo da OS não pôde ser carregado: %s", exc)
            return None

    resolved_logo = logo_path()
    external_logo = None if resolved_logo else safe_external_logo()
    law_notice = "Legislação de Santa Catarina - Lei Estadual 18.119/2021: equipamento não retirado em até 90 dias poderá permanecer na loja conforme aviso e política de retirada."

    def draw_logo(x, y, w, h):
        if resolved_logo or external_logo:
            try:
                source = str(resolved_logo) if resolved_logo else external_logo
                reader = ImageReader(source)
                image_w, image_h = reader.getSize()
                usable_w = w
                usable_h = h
                scale = min(usable_w / image_w, usable_h / image_h)
                draw_w = image_w * scale
                draw_h = image_h * scale
                draw_x = x + (w - draw_w) / 2
                draw_y = y + (h - draw_h) / 2
                c.drawImage(reader, draw_x, draw_y, draw_w, draw_h, preserveAspectRatio=True, mask="auto")
                return
            except Exception as exc:
                logger.warning("Logo da OS não pôde ser carregado: %s", exc)
        c.setFillColor(accent_dark)
        c.setFont("Helvetica-Bold", 6)
        c.drawCentredString(x + w / 2, y + h / 2 - 2, "LOGO")

    def section_title(x, y, width, text):
        c.setFillColor(accent_soft)
        c.setStrokeColor(hairline)
        c.setLineWidth(0.35)
        c.roundRect(x, y - 8, width, 13, 3, stroke=1, fill=1)
        c.setFillColor(accent)
        c.roundRect(x, y - 8, 3, 13, 1.5, stroke=0, fill=1)
        c.setFillColor(accent_dark)
        c.setFont("Helvetica-Bold", 6.3)
        c.drawString(x + 7, y - 3, text.upper())

    def summary_chip(x, y, width, label, value):
        c.setFillColor(colors.HexColor("#ffffff"))
        c.setStrokeColor(hairline)
        c.setLineWidth(0.35)
        c.roundRect(x, y, width, 16, 4, stroke=1, fill=1)
        c.setFillColor(muted)
        c.setFont("Helvetica-Bold", 4.5)
        c.drawString(x + 5, y + 9.5, label.upper())
        c.setFillColor(ink)
        draw_fit_text(x + 5, y + 3, value, width - 10, font="Helvetica-Bold", size=6.6, min_size=4.8)

    def law_box(x, y, width):
        c.setFillColor(colors.HexColor("#ffffff"))
        c.setStrokeColor(hairline)
        c.setLineWidth(0.35)
        c.roundRect(x, y, width, 16, 4, stroke=1, fill=1)
        c.setFillColor(muted)
        c.setFont("Helvetica-Bold", 4.5)
        c.drawString(x + 5, y + 9.5, "RETIRADA EM ATÉ 90 DIAS")
        c.setFillColor(ink)
        draw_fit_text(x + 5, y + 3, law_notice, width - 10, size=5.4, min_size=4.2)

    checklist_labels = [item["label"] for item in cfg.get_entry_checklist_options()]
    checklist_answers = getattr(os_obj, "checklist_answers", None) or {}

    def checklist_answer(label):
        norm = label.lower()
        for key, value in checklist_answers.items():
            if norm in str(key).lower() and value in (True, False):
                return value
        return None

    def draw_yes_no_item(x, y, label):
        c.setFillColor(ink)
        draw_fit_text(x, y - 5, label, 86, size=6.1, min_size=4.8)
        answer = checklist_answer(label)
        for idx, option in enumerate((("Sim", True), ("Não", False))):
            box_x = x + 93 + idx * 31
            c.setFillColor(paper)
            c.setStrokeColor(hairline)
            c.setLineWidth(0.45)
            c.rect(box_x, y - 6, 5, 5, stroke=1, fill=0)
            if answer is option[1]:
                c.setStrokeColor(accent)
                c.setLineWidth(0.8)
                c.line(box_x + 1, y - 3, box_x + 2.2, y - 5)
                c.line(box_x + 2.2, y - 5, box_x + 4.5, y - 1)
                c.setLineWidth(0.45)
            c.setFillColor(ink)
            c.setFont("Helvetica", 5.8)
            c.drawString(box_x + 8, y - 5, option[0])

    def draw_signature_lines(x, y, width):
        line_w = (width - 30) / 2
        c.setStrokeColor(hairline)
        c.setLineWidth(0.5)
        c.line(x + 10, y, x + 10 + line_w, y)
        c.line(x + 20 + line_w, y, x + 20 + line_w * 2, y)
        c.setFillColor(muted)
        c.setFont("Helvetica-Bold", 5.3)
        c.drawCentredString(x + 10 + line_w / 2, y - 8, "ASSINATURA DO CLIENTE")
        c.drawCentredString(x + 20 + line_w + line_w / 2, y - 8, "ASSINATURA DO TÉCNICO")

    def draw_common_copy(x, y, width, height, via_label):
        c.setFillColor(paper)
        c.setStrokeColor(border)
        c.setLineWidth(0.65)
        c.roundRect(x, y, width, height, 5, stroke=1, fill=1)
        top = y + height

        c.setFillColor(panel)
        c.setStrokeColor(hairline)
        c.roundRect(x + 4, top - 50, width - 8, 42, 4, stroke=1, fill=1)
        draw_logo(x + 10, top - 43, 45, 29)
        nome, subtitulo, location, contact = company_lines()
        c.setFillColor(ink)
        c.setFont("Helvetica-Bold", 8.5)
        draw_wrapped(x + 64, top - 22, nome.upper(), 112, font="Helvetica-Bold", size=8.5, leading=9, max_lines=2)
        c.setFillColor(muted)
        draw_fit_text(x + 64, top - 39, subtitulo, 112, size=5.8, min_size=4.8)

        c.setFillColor(muted)
        c.setFont("Helvetica-Bold", 4.8)
        c.drawRightString(x + width - 12, top - 20, "NÚMERO DA ORDEM DE SERVIÇO")
        c.setFillColor(accent_dark)
        c.setFont("Helvetica-Bold", 13.5)
        c.drawRightString(x + width - 12, top - 37, f"OS Nº {codigo_os}")
        c.setFillColor(accent)
        c.roundRect(x + width - 77, top - 50, 65, 9, 4, stroke=0, fill=1)
        c.setFillColor(paper)
        c.setFont("Helvetica-Bold", 5.6)
        c.drawCentredString(x + width - 44.5, top - 47.2, via_label.upper())
        chip_y = top - 74
        summary_chip(x + 8, chip_y, 58, "Entrada", date_fmt(getattr(os_obj, "data_entrada", None)))
        law_box(x + 70, chip_y, width - 78)
        c.setStrokeColor(border)
        c.setLineWidth(0.55)
        c.line(x, top - 83, x + width, top - 83)

        section_title(x + 8, top - 97, width - 16, "Identificação do cliente")
        draw_label_line(x + 9, top - 113, width - 18, "Nome / Razão Social", getattr(cliente, "nome", None))
        draw_label_line(x + 9, top - 139, (width - 26) * 0.62, "Telefone / WhatsApp", phone_fmt(getattr(cliente, "telefone", "")))
        draw_label_line(x + 17 + (width - 26) * 0.62, top - 139, (width - 26) * 0.38, "CPF / CNPJ", doc_fmt())
        draw_label_line(x + 9, top - 165, width - 18, "E-mail", getattr(cliente, "email", ""))
        c.setStrokeColor(hairline)
        c.line(x + 4, top - 180, x + width - 4, top - 180)

        section_title(x + 8, top - 194, width - 16, "Identificação do dispositivo")
        half = (width - 24) / 2
        draw_label_line(x + 9, top - 210, half, "Tipo do dispositivo", getattr(os_obj, "tipo_aparelho", ""))
        draw_label_line(x + 17 + half, top - 210, half, "Marca", getattr(os_obj, "marca", ""))
        draw_label_line(x + 9, top - 236, half, "Modelo", getattr(os_obj, "modelo", ""))
        draw_label_line(x + 17 + half, top - 236, half, "Número de série / IMEI", getattr(os_obj, "numero_serie", ""))
        draw_label_line(x + 9, top - 262, width - 18, "Acessórios entregues com o dispositivo", "")
        draw_label_line(x + 9, top - 288, width - 18, "Observação rápida sobre o estado de entrada", getattr(os_obj, "observacoes", ""))
        c.setStrokeColor(hairline)
        c.line(x + 4, top - 303, x + width - 4, top - 303)
        return top

    def draw_footer(x, y, width):
        nome, _subtitulo, location, contact = company_lines()
        c.setFillColor(panel)
        c.setStrokeColor(hairline)
        c.roundRect(x + 5, y + 6, width - 10, 31, 4, stroke=1, fill=1)
        c.setFillColor(ink)
        draw_centered_fit_text(x + width / 2, y + 26, nome.upper(), width - 28, font="Helvetica-Bold", size=5.8, min_size=4.8)
        c.setFillColor(muted)
        draw_centered_fit_text(x + width / 2, y + 17, location, width - 28, size=5.3, min_size=4.4)
        draw_centered_fit_text(x + width / 2, y + 9, contact, width - 28, size=5.3, min_size=4.4)

    margin = 9 * mm
    gap = 3 * mm
    copy_w = (page_w - 2 * margin - gap) / 2
    copy_h = page_h - 2 * margin
    left_x = margin
    right_x = margin + copy_w + gap
    bottom = margin

    c.setStrokeColor(hairline)
    c.setDash(2, 3)
    c.line(left_x + copy_w + gap / 2, bottom + 3, left_x + copy_w + gap / 2, bottom + copy_h - 3)
    c.setDash()

    left_top = draw_common_copy(left_x, bottom, copy_w, copy_h, "Cliente")
    c.setFillColor(panel)
    c.setStrokeColor(hairline)
    c.roundRect(left_x + 6, bottom + 47, copy_w - 12, left_top - bottom - 355, 4, stroke=1, fill=1)
    section_title(left_x + 10, left_top - 317, copy_w - 20, "Serviço solicitado / informações adicionais")
    service_text = " ".join(part for part in [
        getattr(os_obj, "defeito_alegado", ""),
        getattr(os_obj, "defeito_encontrado", ""),
        getattr(os_obj, "solucao", ""),
    ] if part)
    y = left_top - 337
    for line_text in wrap_text(service_text, copy_w - 22, size=7, max_lines=5):
        c.setFillColor(ink)
        c.setFont("Helvetica", 7)
        c.drawString(left_x + 11, y, line_text)
        y -= 13
    c.setStrokeColor(hairline)
    for yy in (left_top - 335, left_top - 362, left_top - 389, left_top - 416):
        c.line(left_x + 10, yy - 5, left_x + copy_w - 10, yy - 5)
    draw_signature_lines(left_x + 6, bottom + 57, copy_w - 12)
    c.line(left_x + 4, bottom + 42, left_x + copy_w - 4, bottom + 42)
    draw_footer(left_x, bottom, copy_w)

    right_top = draw_common_copy(right_x, bottom, copy_w, copy_h, "Técnico")
    split = right_x + copy_w * 0.48
    c.setStrokeColor(hairline)
    c.line(split, bottom + 42, split, right_top - 303)
    c.setFillColor(panel)
    c.setStrokeColor(hairline)
    c.roundRect(right_x + 6, bottom + 47, split - right_x - 12, right_top - bottom - 355, 4, stroke=1, fill=1)
    c.roundRect(split + 6, bottom + 47, right_x + copy_w - split - 12, right_top - bottom - 355, 4, stroke=1, fill=1)
    section_title(right_x + 10, right_top - 317, split - right_x - 20, "Checklist de entrada")
    col1_x = right_x + 12
    start_y = right_top - 336
    checklist_spacing = min(13, max(9, 135 / max(len(checklist_labels) - 1, 1)))
    for idx, label in enumerate(checklist_labels[:16]):
        draw_yes_no_item(col1_x, start_y - idx * checklist_spacing, label)

    obs_x = split + 8
    obs_w = right_x + copy_w - obs_x - 8
    section_title(obs_x, right_top - 317, obs_w, "Observações do técnico")
    c.setFillColor(ink)
    c.setStrokeColor(hairline)
    for idx in range(7):
        yy = right_top - 341 - idx * 22
        c.line(obs_x, yy, obs_x + obs_w, yy)
    c.line(right_x + 4, bottom + 42, right_x + copy_w - 4, bottom + 42)
    draw_footer(right_x, bottom, copy_w)

    c.showPage()
    c.save()
    return buf.getvalue()


def gerar_pdf_os(os_obj) -> bytes:
    try:
        return _pdf_via_reportlab(os_obj)
    except ImportError:
        raise RuntimeError("ReportLab não está disponível. Instale as dependências do projeto.")
    except Exception as exc:
        logger.error("Erro ao gerar PDF de OS: %s", exc)
        raise RuntimeError(f"Erro ao gerar PDF: {exc}") from exc
