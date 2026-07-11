"""Servicos de negocio para laudos tecnicos."""
from __future__ import annotations

import hashlib
import io
import secrets
import shutil
from datetime import datetime, timezone
from pathlib import Path

from flask import current_app
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Cliente, Configuracao, OrdemServico, Usuario, registrar
from app.models.laudo import (
    LAUDO_FOTO_TIPOS,
    LAUDO_FOTOS_OBRIGATORIAS,
    LAUDO_STATUS,
    LAUDO_TIPOS,
    LaudoCounter,
    LaudoEvento,
    LaudoFoto,
    LaudoTecnico,
)
from app.utils.sanitizers import sanitize_text

TEXT_FIELDS = (
    "defeito_relatado",
    "inspecao_visual",
    "testes_realizados",
    "instrumentos_metodos",
    "medicoes",
    "diagnostico_tecnico",
    "causa_provavel",
    "servicos_realizados",
    "pecas_utilizadas",
    "conclusao_tecnica",
    "recomendacoes",
    "riscos_limitacoes",
    "observacoes",
)
SHORT_FIELDS = ("estado_final", "garantia", "tecnico_responsavel_nome")
MAX_FOTOS = 20
MAX_FOTO_BYTES = 8 * 1024 * 1024
MIMES_IMAGEM = {
    "JPEG": ("image/jpeg", "jpg"),
    "PNG": ("image/png", "png"),
    "WEBP": ("image/webp", "webp"),
}


def now_utc():
    return datetime.now(timezone.utc)


def can_manage_laudos(usuario: Usuario | None) -> bool:
    return bool(usuario and usuario.nivel in ("admin", "operacional"))


def can_view_laudos(usuario: Usuario | None) -> bool:
    return bool(usuario and usuario.nivel in ("admin", "operacional", "consulta", "cadastro"))


def can_cancel_laudos(usuario: Usuario | None) -> bool:
    return bool(usuario and usuario.nivel == "admin")


def _reports_root() -> Path:
    root = Path(current_app.config.get("REPORTS_UPLOAD_FOLDER") or current_app.instance_path)
    if root.name != "reports":
        root = root / "uploads" / "reports"
    root.mkdir(parents=True, exist_ok=True)
    return root


def laudo_dir(laudo: LaudoTecnico) -> Path:
    path = _reports_root() / str(laudo.organization_id or 1) / laudo.public_uuid
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_file_path(storage_key: str) -> Path:
    root = _reports_root().resolve()
    target = (root / storage_key).resolve()
    if not str(target).startswith(str(root)):
        raise ValueError("Caminho de arquivo invalido.")
    return target


def registrar_evento(laudo: LaudoTecnico, tipo: str, descricao: str = "", dados: dict | None = None, usuario_id: int | None = None):
    db.session.add(LaudoEvento(
        laudo_id=laudo.id,
        usuario_id=usuario_id,
        tipo=tipo,
        descricao=descricao,
        dados=dados or {},
    ))


def gerar_numero_laudo(organization_id: int = 1, ano: int | None = None) -> tuple[str, int]:
    ano = ano or now_utc().year
    counter = (
        LaudoCounter.query
        .filter_by(organization_id=organization_id, ano=ano)
        .with_for_update()
        .first()
    )
    if not counter:
        counter = LaudoCounter(organization_id=organization_id, ano=ano, proximo_numero=1)
        db.session.add(counter)
        db.session.flush()
    sequencial = counter.proximo_numero
    counter.proximo_numero += 1
    return f"LAU-{ano}-{sequencial:06d}", ano


def snapshot_empresa() -> dict:
    cfg = Configuracao.get()
    return {
        "nome_empresa": cfg.nome_empresa,
        "cnpj": cfg.cnpj,
        "telefone": cfg.telefone,
        "email": cfg.email,
        "endereco": cfg.endereco,
        "cidade": cfg.cidade,
        "uf": cfg.uf,
        "responsavel_tecnico": getattr(cfg, "responsavel_tecnico", None),
        "registro_profissional": getattr(cfg, "registro_profissional", None),
        "rodape": getattr(cfg, "rodape_pdf", None),
    }


def snapshot_cliente(cliente: Cliente | None) -> dict:
    if not cliente:
        return {}
    return {
        "nome": cliente.nome,
        "cpf": cliente.cpf,
        "cnpj": cliente.cnpj,
        "telefone": cliente.telefone,
        "email": cliente.email,
        "cep": cliente.cep,
        "endereco": cliente.endereco,
        "numero_casa": cliente.numero_casa,
        "cidade": cliente.cidade,
        "uf": cliente.uf,
    }


def snapshot_equipamento(os_obj: OrdemServico | None) -> dict:
    if not os_obj:
        return {}
    return {
        "tipo": os_obj.tipo_aparelho,
        "marca": os_obj.marca,
        "modelo": os_obj.modelo,
        "numero_serie": os_obj.numero_serie,
        "defeito_relatado": os_obj.defeito_alegado,
        "defeito_encontrado": os_obj.defeito_encontrado,
        "solucao": os_obj.solucao,
        "observacoes": os_obj.observacoes,
    }


def snapshot_tecnico(laudo: LaudoTecnico) -> dict:
    tecnico = laudo.tecnico_responsavel
    return {
        "id": tecnico.id if tecnico else None,
        "nome": laudo.tecnico_responsavel_nome or (tecnico.nome if tecnico else None),
        "email": tecnico.email if tecnico else None,
    }


def popular_de_os(laudo: LaudoTecnico, os_obj: OrdemServico):
    laudo.cliente_id = os_obj.cliente_id
    laudo.tecnico_responsavel_nome = os_obj.tecnico_nome or laudo.tecnico_responsavel_nome
    laudo.defeito_relatado = laudo.defeito_relatado or os_obj.defeito_alegado
    laudo.diagnostico_tecnico = laudo.diagnostico_tecnico or os_obj.defeito_encontrado
    laudo.servicos_realizados = laudo.servicos_realizados or os_obj.solucao
    laudo.observacoes = laudo.observacoes or os_obj.observacoes


def criar_rascunho(os_id: int, usuario: Usuario, tipo: str = "diagnostico") -> LaudoTecnico:
    if tipo not in LAUDO_TIPOS:
        raise ValueError("Tipo de laudo invalido.")
    os_obj = OrdemServico.query.filter_by(id=os_id).filter(OrdemServico.deletado_em.is_(None)).first()
    if not os_obj:
        raise ValueError("Ordem de servico nao encontrada.")
    laudo = LaudoTecnico(
        os_id=os_obj.id,
        cliente_id=os_obj.cliente_id,
        tipo=tipo,
        criado_por_id=usuario.id,
        atualizado_por_id=usuario.id,
        tecnico_responsavel_id=os_obj.usuario_id,
        tecnico_responsavel_nome=os_obj.tecnico_nome or (os_obj.usuario.nome if os_obj.usuario else None),
    )
    popular_de_os(laudo, os_obj)
    db.session.add(laudo)
    db.session.flush()
    registrar_evento(laudo, "criacao", "Rascunho criado.", usuario_id=usuario.id)
    registrar("criacao", "laudos", f"Laudo rascunho criado para OS #{os_obj.id:04d}", usuario_id=usuario.id, usuario_nome=usuario.nome)
    return laudo


def atualizar_laudo(laudo: LaudoTecnico, data: dict, usuario: Usuario):
    if laudo.status != "draft":
        raise ValueError("Laudos finalizados ou cancelados nao podem ser editados.")
    if data.get("tipo") in LAUDO_TIPOS:
        laudo.tipo = data["tipo"]
    for field in TEXT_FIELDS:
        if field in data:
            laudo.__setattr__(field, sanitize_text(data.get(field), max_length=12000, strip=False))
    for field in SHORT_FIELDS:
        if field in data:
            laudo.__setattr__(field, sanitize_text(data.get(field), max_length=200))
    if data.get("analisado_em"):
        try:
            laudo.analisado_em = datetime.fromisoformat(str(data["analisado_em"])[:10])
        except ValueError:
            raise ValueError("Data da analise invalida.")
    laudo.atualizado_por_id = usuario.id
    registrar_evento(laudo, "edicao", "Laudo atualizado.", usuario_id=usuario.id)


def campos_obrigatorios_pendentes(laudo: LaudoTecnico) -> list[str]:
    campos = {
        "Defeito relatado": laudo.defeito_relatado,
        "Inspecao visual": laudo.inspecao_visual,
        "Testes realizados": laudo.testes_realizados,
        "Diagnostico tecnico": laudo.diagnostico_tecnico,
        "Conclusao tecnica": laudo.conclusao_tecnica,
        "Estado final": laudo.estado_final,
    }
    return [nome for nome, valor in campos.items() if not (valor or "").strip()]


def fotos_obrigatorias_pendentes(laudo: LaudoTecnico) -> list[str]:
    presentes = {foto.tipo for foto in laudo.fotos}
    return [tipo for tipo in LAUDO_FOTOS_OBRIGATORIAS if tipo not in presentes]


def validar_imagem_upload(file_storage) -> tuple[bytes, str, str, int, int, str]:
    if not file_storage or not file_storage.filename:
        raise ValueError("Arquivo ausente.")
    original_name = file_storage.filename
    raw = file_storage.read()
    file_storage.stream.seek(0)
    if len(raw) > MAX_FOTO_BYTES:
        raise ValueError("Foto excede 8 MB.")
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError as exc:
        raise ValueError("Pillow nao esta instalado. Instale Pillow para validar fotos de laudos.") from exc
    try:
        image = Image.open(io.BytesIO(raw))
        image.verify()
        image = Image.open(io.BytesIO(raw))
    except UnidentifiedImageError as exc:
        raise ValueError("Arquivo nao e uma imagem valida.") from exc
    fmt = (image.format or "").upper()
    if fmt not in MIMES_IMAGEM:
        raise ValueError("Formato de imagem nao permitido. Use JPEG, PNG ou WebP.")
    mime, ext = MIMES_IMAGEM[fmt]
    largura, altura = image.size
    if largura < 50 or altura < 50 or largura > 8000 or altura > 8000:
        raise ValueError("Dimensoes da imagem fora do limite permitido.")
    clean = Image.open(io.BytesIO(raw))
    out = io.BytesIO()
    save_format = "JPEG" if fmt == "JPEG" else fmt
    save_kwargs = {"quality": 88, "optimize": True} if fmt == "JPEG" else {}
    clean.save(out, format=save_format, **save_kwargs)
    data = out.getvalue()
    sha = hashlib.sha256(data).hexdigest()
    return data, mime, ext, largura, altura, sha


def adicionar_foto(laudo: LaudoTecnico, file_storage, tipo: str, legenda: str, ordem: int, usuario: Usuario) -> LaudoFoto:
    if laudo.status != "draft":
        raise ValueError("Nao e possivel alterar fotos de laudo finalizado.")
    if tipo not in LAUDO_FOTO_TIPOS:
        raise ValueError("Tipo de foto invalido.")
    if len(laudo.fotos) >= MAX_FOTOS:
        raise ValueError("Limite de fotos do laudo atingido.")
    data, mime, ext, largura, altura, sha = validar_imagem_upload(file_storage)
    rel_dir = Path(str(laudo.organization_id or 1)) / laudo.public_uuid / "photos"
    dest_dir = _reports_root() / rel_dir
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{secrets.token_hex(16)}.{ext}"
    target = dest_dir / filename
    target.write_bytes(data)
    storage_key = (rel_dir / filename).as_posix()
    foto = LaudoFoto(
        laudo_id=laudo.id,
        tipo=tipo,
        legenda=sanitize_text(legenda, max_length=255),
        ordem=ordem,
        nome_original=sanitize_text(file_storage.filename, max_length=255),
        storage_key=storage_key,
        mime_type=mime,
        tamanho_bytes=len(data),
        largura=largura,
        altura=altura,
        sha256=sha,
        usuario_id=usuario.id,
    )
    db.session.add(foto)
    registrar_evento(laudo, "foto", f"Foto adicionada: {tipo}", {"foto_tipo": tipo}, usuario.id)
    return foto


def remover_foto(foto: LaudoFoto, usuario: Usuario):
    laudo = foto.laudo
    if laudo.status != "draft":
        raise ValueError("Nao e possivel remover fotos de laudo finalizado.")
    try:
        target = safe_file_path(foto.storage_key)
        if target.exists():
            target.unlink()
    except Exception:
        current_app.logger.warning("Falha ao remover arquivo de foto %s", foto.storage_key, exc_info=True)
    registrar_evento(laudo, "foto", f"Foto removida: {foto.tipo}", {"foto_id": foto.id}, usuario.id)
    db.session.delete(foto)


def gerar_pdf_laudo(laudo: LaudoTecnico) -> bytes:
    try:
        return _pdf_via_reportlab(laudo)
    except Exception as exc:
        raise RuntimeError(f"Erro ao gerar PDF do laudo: {exc}") from exc


def _pdf_via_reportlab(laudo: LaudoTecnico) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm, bottomMargin=14 * mm)
    styles = getSampleStyleSheet()
    normal = ParagraphStyle("normal_laudo", parent=styles["Normal"], fontSize=9, leading=12)
    title = ParagraphStyle("title_laudo", parent=styles["Heading1"], fontSize=15, leading=18, textColor=colors.HexColor("#10243f"))
    section = ParagraphStyle("section_laudo", parent=styles["Heading2"], fontSize=10, leading=13, textColor=colors.HexColor("#0f5f6f"), spaceBefore=8)
    small = ParagraphStyle("small_laudo", parent=styles["Normal"], fontSize=7, leading=9, textColor=colors.grey)

    def p(text, style=normal):
        text = str(text or "-").replace("\n", "<br/>")
        return Paragraph(text, style)

    empresa = laudo.empresa_snapshot or snapshot_empresa()
    cliente = laudo.cliente_snapshot or snapshot_cliente(laudo.cliente)
    equipamento = laudo.equipamento_snapshot or snapshot_equipamento(laudo.os)
    verification_path = f"/laudos/verificar/{laudo.verification_token}" if laudo.verification_token else "-"
    story = [
        p(empresa.get("nome_empresa") or "Zokyo Platform", title),
        p(f"Laudo tecnico {laudo.numero or ''} | OS #{laudo.os_id:04d} | Versao {laudo.versao}", small),
        p(f"Codigo de verificacao: {laudo.verification_token or '-'} | Consulta: {verification_path}", small),
        p(f"SHA-256: {(laudo.pdf_sha256 or '')[:16] or 'gerado apos finalizacao'}", small),
        Spacer(1, 5 * mm),
    ]
    story.append(_kv_table([
        ("Empresa", empresa.get("nome_empresa")),
        ("CNPJ", empresa.get("cnpj")),
        ("Contato", " | ".join(x for x in [empresa.get("telefone"), empresa.get("email")] if x)),
        ("Endereco", " - ".join(x for x in [empresa.get("endereco"), empresa.get("cidade"), empresa.get("uf")] if x)),
    ], normal))
    story.append(p("Cliente", section))
    story.append(_kv_table([
        ("Nome", cliente.get("nome")),
        ("Documento", cliente.get("cpf") or cliente.get("cnpj")),
        ("Telefone", cliente.get("telefone")),
        ("E-mail", cliente.get("email")),
    ], normal))
    story.append(p("Equipamento", section))
    story.append(_kv_table([
        ("Tipo", equipamento.get("tipo")),
        ("Marca/modelo", f"{equipamento.get('marca') or ''} {equipamento.get('modelo') or ''}".strip()),
        ("Numero de serie", equipamento.get("numero_serie")),
        ("Defeito relatado", laudo.defeito_relatado or equipamento.get("defeito_relatado")),
    ], normal))
    for label, value in [
        ("Inspecao visual", laudo.inspecao_visual),
        ("Testes realizados", laudo.testes_realizados),
        ("Instrumentos e metodos", laudo.instrumentos_metodos),
        ("Medicoes", laudo.medicoes),
        ("Diagnostico tecnico", laudo.diagnostico_tecnico),
        ("Causa provavel", laudo.causa_provavel),
        ("Servicos realizados", laudo.servicos_realizados),
        ("Pecas utilizadas", laudo.pecas_utilizadas),
        ("Conclusao tecnica", laudo.conclusao_tecnica),
        ("Estado final", laudo.estado_final),
        ("Recomendacoes", laudo.recomendacoes),
        ("Riscos e limitacoes", laudo.riscos_limitacoes),
        ("Garantia", laudo.garantia),
        ("Observacoes", laudo.observacoes),
    ]:
        if value:
            story.append(p(label, section))
            story.append(p(value, normal))
    fotos = sorted(laudo.fotos, key=lambda f: (f.ordem, f.id))
    if fotos:
        story.append(PageBreak())
        story.append(p("Fotografias", section))
        rows = []
        current = []
        for foto in fotos:
            target = safe_file_path(foto.storage_key)
            if target.exists():
                img = Image(str(target), width=80 * mm, height=55 * mm, kind="proportional")
                current.append([img, p(foto.legenda or foto.tipo, small)])
                if len(current) == 2:
                    rows.append(current)
                    current = []
        if current:
            rows.append(current)
        for row in rows:
            story.append(Table([row], colWidths=[88 * mm, 88 * mm]))
            story.append(Spacer(1, 4 * mm))
    story += [
        Spacer(1, 12 * mm),
        p("Assinaturas", section),
        Table([["", ""], ["Responsavel tecnico", "Cliente / ciencia"]], colWidths=[85 * mm, 85 * mm], style=[
            ("LINEABOVE", (0, 0), (-1, 0), 0.8, colors.grey),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
        ]),
        Spacer(1, 5 * mm),
        p("Assinatura eletronica simples, quando usada, nao equivale a assinatura digital certificada ICP-Brasil.", small),
    ]

    def footer(canvas, _doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.grey)
        canvas.drawString(14 * mm, 8 * mm, f"{laudo.numero or '-'} | {laudo.public_uuid}")
        canvas.drawRightString(196 * mm, 8 * mm, f"Pagina {canvas.getPageNumber()}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


def _kv_table(rows: list[tuple[str, str]], style):
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Table, TableStyle
    label_style = ParagraphStyle("kv_label", parent=style, fontName="Helvetica-Bold", textColor=colors.HexColor("#475569"))
    data = [[Paragraph(str(k), label_style), Paragraph(str(v or "-"), style)] for k, v in rows]
    table = Table(data, colWidths=[38 * mm, 132 * mm])
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d9e2ec")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f3f6f9")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def finalizar_laudo(laudo: LaudoTecnico, usuario: Usuario) -> LaudoTecnico:
    if laudo.status == "finalized" and laudo.pdf_path and laudo.pdf_sha256:
        return laudo
    if laudo.status != "draft":
        raise ValueError("Somente rascunhos podem ser finalizados.")
    pendentes = campos_obrigatorios_pendentes(laudo)
    if pendentes:
        raise ValueError("Preencha os campos obrigatorios: " + ", ".join(pendentes))
    fotos_pendentes = fotos_obrigatorias_pendentes(laudo)
    if fotos_pendentes:
        raise ValueError("Fotos obrigatorias pendentes: " + ", ".join(fotos_pendentes))

    tmp_dir = laudo_dir(laudo) / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_pdf = tmp_dir / f"{secrets.token_hex(8)}.pdf"
    try:
        if not laudo.numero:
            laudo.numero, laudo.ano = gerar_numero_laudo(laudo.organization_id or 1)
        laudo.emitido_em = laudo.emitido_em or now_utc()
        laudo.finalizado_em = now_utc()
        laudo.status = "finalized"
        laudo.atualizado_por_id = usuario.id
        laudo.empresa_snapshot = snapshot_empresa()
        laudo.cliente_snapshot = snapshot_cliente(laudo.cliente)
        laudo.equipamento_snapshot = snapshot_equipamento(laudo.os)
        laudo.tecnico_snapshot = snapshot_tecnico(laudo)
        laudo.verification_token = laudo.verification_token or secrets.token_urlsafe(24)
        laudo.verificacao_publica = bool(current_app.config.get("REPORTS_PUBLIC_VERIFICATION", True))
        db.session.flush()
        pdf_bytes = gerar_pdf_laudo(laudo)
        tmp_pdf.write_bytes(pdf_bytes)
        sha = hashlib.sha256(pdf_bytes).hexdigest()
        final_name = f"{laudo.numero}.pdf"
        rel_path = Path(str(laudo.organization_id or 1)) / laudo.public_uuid / final_name
        final_path = _reports_root() / rel_path
        final_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(tmp_pdf), str(final_path))
        laudo.pdf_path = rel_path.as_posix()
        laudo.pdf_sha256 = sha
        laudo.pdf_gerado_em = now_utc()
        registrar_evento(laudo, "finalizacao", "Laudo finalizado.", usuario_id=usuario.id)
        registrar_evento(laudo, "pdf_gerado", "PDF gerado e armazenado.", {"sha256": sha}, usuario.id)
        registrar("status", "laudos", f"Laudo {laudo.numero} finalizado", usuario_id=usuario.id, usuario_nome=usuario.nome)
        registrar("status", "os", f"OS #{laudo.os_id:04d}: laudo {laudo.numero} finalizado", usuario_id=usuario.id, usuario_nome=usuario.nome)
        db.session.commit()
        return laudo
    except IntegrityError:
        db.session.rollback()
        raise ValueError("Falha ao reservar numero unico do laudo. Tente novamente.")
    except Exception:
        db.session.rollback()
        try:
            if tmp_pdf.exists():
                tmp_pdf.unlink()
        except Exception:
            pass
        raise


def cancelar_laudo(laudo: LaudoTecnico, motivo: str, usuario: Usuario):
    if laudo.status == "cancelled":
        return
    if not motivo or len(motivo.strip()) < 10:
        raise ValueError("Informe uma justificativa de cancelamento com pelo menos 10 caracteres.")
    laudo.status = "cancelled"
    laudo.motivo_cancelamento = sanitize_text(motivo, max_length=3000)
    laudo.cancelado_em = now_utc()
    laudo.atualizado_por_id = usuario.id
    registrar_evento(laudo, "cancelamento", laudo.motivo_cancelamento, usuario_id=usuario.id)
    registrar("status", "laudos", f"Laudo {laudo.numero or laudo.id} cancelado", usuario_id=usuario.id, usuario_nome=usuario.nome)


def duplicar_laudo(laudo: LaudoTecnico, usuario: Usuario, revisao: bool = False) -> LaudoTecnico:
    novo = LaudoTecnico(
        organization_id=laudo.organization_id,
        os_id=laudo.os_id,
        cliente_id=laudo.cliente_id,
        tipo="revisao" if revisao else laudo.tipo,
        criado_por_id=usuario.id,
        atualizado_por_id=usuario.id,
        tecnico_responsavel_id=laudo.tecnico_responsavel_id,
        tecnico_responsavel_nome=laudo.tecnico_responsavel_nome,
        versao=(laudo.versao or 1) + 1 if revisao else 1,
        laudo_origem_id=laudo.id if revisao else None,
    )
    for field in TEXT_FIELDS + SHORT_FIELDS:
        setattr(novo, field, getattr(laudo, field))
    db.session.add(novo)
    db.session.flush()
    registrar_evento(novo, "revisao" if revisao else "duplicacao", "Laudo criado a partir de outro documento.", {"origem_id": laudo.id}, usuario.id)
    return novo
