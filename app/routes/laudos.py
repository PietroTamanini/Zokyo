"""Rotas HTML do modulo de laudos tecnicos."""
import csv
import io

import click
from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import Cliente, OrdemServico, Usuario
from app.models.laudo import (
    LAUDO_FOTO_TIPOS,
    LAUDO_FOTO_TIPOS_LABELS,
    LAUDO_STATUS_LABELS,
    LAUDO_TIPOS_LABELS,
    LaudoEvento,
    LaudoFoto,
    LaudoTecnico,
    LaudoTemplate,
)
from app.services.laudos import (
    adicionar_foto,
    arquivos_orfaos,
    atualizar_laudo,
    can_cancel_laudos,
    can_manage_laudo,
    can_manage_laudos,
    can_view_laudos,
    cancelar_laudo,
    criar_rascunho,
    duplicar_laudo,
    finalizar_laudo,
    gerar_comprovante_cancelamento,
    limpar_arquivos_orfaos,
    registrar_evento,
    remover_foto,
    reordenar_fotos,
    safe_file_path,
)
from app.utils.permissions import has_permission
from app.utils.sanitizers import sanitize_cpf_cnpj, sanitize_text

laudos_bp = Blueprint("laudos", __name__, url_prefix="/laudos")


@laudos_bp.cli.command("storage-audit")
@click.option("--delete", "delete_files", is_flag=True, help="Remove os arquivos orfaos encontrados.")
def storage_audit(delete_files):
    """Lista ou remove arquivos de laudos sem referência no banco."""
    encontrados = arquivos_orfaos()
    for path in encontrados:
        click.echo(path)
    if delete_files:
        removidos = limpar_arquivos_orfaos()
        click.echo(f"{removidos} arquivo(s) removido(s).")
    else:
        click.echo(f"{len(encontrados)} arquivo(s) orfao(s). Use --delete para remover.")


def _usuario_atual():
    uid = session.get("usuario_id")
    return db.session.get(Usuario, uid) if uid else None


def _require_view():
    usuario = _usuario_atual()
    if not can_view_laudos(usuario):
        abort(403)
    return usuario


def _require_manage():
    usuario = _usuario_atual()
    if not can_manage_laudos(usuario):
        abort(403)
    return usuario


def _get_laudo(id):
    usuario = _usuario_atual()
    return (
        LaudoTecnico.query
        .options(
            joinedload(LaudoTecnico.os),
            joinedload(LaudoTecnico.cliente),
            joinedload(LaudoTecnico.tecnico_responsavel),
        )
        .filter_by(id=id, organization_id=usuario.organization_id if usuario else -1)
        .first_or_404()
    )


def _require_manage_laudo(laudo):
    usuario = _require_manage()
    if not can_manage_laudo(usuario, laudo):
        abort(403)
    return usuario


def _require_laudo_permission(permission, laudo=None):
    usuario = _usuario_atual()
    if not has_permission(usuario, permission):
        abort(403)
    if laudo is not None and usuario.organization_id != laudo.organization_id:
        abort(404)
    return usuario


def _os_options():
    usuario = _usuario_atual()
    return (
        OrdemServico.query
        .filter(OrdemServico.organization_id == (usuario.organization_id if usuario else -1))
        .filter(OrdemServico.deletado_em.is_(None))
        .options(joinedload(OrdemServico.cliente))
        .order_by(OrdemServico.data_entrada.desc())
        .limit(100)
        .all()
    )


def _template_options(usuario):
    return (
        LaudoTemplate.query
        .filter_by(organization_id=usuario.organization_id, ativo=True)
        .order_by(LaudoTemplate.tipo_laudo, LaudoTemplate.nome, LaudoTemplate.versao.desc())
        .all()
    )


def _laudos_filtrados(usuario):
    q = sanitize_text(request.args.get("q", ""), max_length=100)
    status = request.args.get("status", "")
    tipo = request.args.get("tipo", "")
    tecnico = sanitize_text(request.args.get("tecnico", ""), max_length=80)
    query = (
        LaudoTecnico.query
        .options(joinedload(LaudoTecnico.os), joinedload(LaudoTecnico.cliente))
        .filter(LaudoTecnico.organization_id == usuario.organization_id)
    )
    if status in LAUDO_STATUS_LABELS:
        query = query.filter(LaudoTecnico.status == status)
    if tipo in LAUDO_TIPOS_LABELS:
        query = query.filter(LaudoTecnico.tipo == tipo)
    if tecnico:
        query = query.filter(LaudoTecnico.tecnico_responsavel_nome.ilike(f"%{tecnico}%"))
    if q:
        digitos = sanitize_cpf_cnpj(q)
        like = f"%{q}%"
        filtros = [
            LaudoTecnico.numero.ilike(like),
            LaudoTecnico.tecnico_responsavel_nome.ilike(like),
            OrdemServico.marca.ilike(like),
            OrdemServico.modelo.ilike(like),
            OrdemServico.numero_serie.ilike(like),
            Cliente.nome.ilike(like),
        ]
        if q.isdigit():
            filtros.append(LaudoTecnico.os_id == int(q))
        if digitos:
            filtros.extend([Cliente.cpf.ilike(f"%{digitos}%"), Cliente.cnpj.ilike(f"%{digitos}%")])
        query = query.join(OrdemServico).join(Cliente).filter(db.or_(*filtros))
    return query, {"q": q, "status": status, "tipo": tipo, "tecnico": tecnico}


def _csv_safe(value):
    text = str(value or "")
    return "'" + text if text.startswith(("=", "+", "-", "@", "\t", "\r")) else text


@laudos_bp.route("/")
def index():
    usuario = _require_view()
    page = request.args.get("page", 1, type=int)
    query, filtros = _laudos_filtrados(usuario)
    pag = query.order_by(LaudoTecnico.criado_em.desc()).paginate(page=page, per_page=25, error_out=False)
    return render_template(
        "pages/laudos_lista.html",
        active="laudos",
        laudos=pag.items,
        paginacao=pag,
        filtros=filtros,
        status_labels=LAUDO_STATUS_LABELS,
        tipo_labels=LAUDO_TIPOS_LABELS,
    )


@laudos_bp.route("/exportar.csv")
def exportar_csv():
    usuario = _require_view()
    query, _filtros = _laudos_filtrados(usuario)
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["Número", "OS", "Cliente", "Equipamento", "Série", "Técnico", "Tipo", "Versão", "Status", "Emissão"])
    for laudo in query.order_by(LaudoTecnico.criado_em.desc()).yield_per(250):
        equipamento = " ".join(filter(None, [laudo.os.tipo_aparelho, laudo.os.marca, laudo.os.modelo])) if laudo.os else ""
        writer.writerow([_csv_safe(value) for value in [
            laudo.numero or f"Rascunho #{laudo.id}", laudo.os_id,
            laudo.cliente.nome if laudo.cliente else "", equipamento,
            laudo.os.numero_serie if laudo.os else "", laudo.tecnico_responsavel_nome or "",
            LAUDO_TIPOS_LABELS.get(laudo.tipo, laudo.tipo), laudo.versao,
            LAUDO_STATUS_LABELS.get(laudo.status, laudo.status),
            laudo.emitido_em.strftime("%d/%m/%Y") if laudo.emitido_em else "",
        ]])
    current_app.logger.info(
        "Exportacao CSV de laudos realizada.",
        extra={"organization_id": usuario.organization_id, "usuario_id": usuario.id},
    )
    return Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=laudos.csv", "X-Content-Type-Options": "nosniff"},
    )


@laudos_bp.route("/novo", methods=["GET"])
def novo():
    usuario = _require_manage()
    os_id = request.args.get("os_id", type=int)
    return render_template(
        "pages/laudo_form.html",
        active="laudos",
        laudo=None,
        os_options=_os_options(),
        selected_os_id=os_id,
        tipo_labels=LAUDO_TIPOS_LABELS,
        foto_labels=LAUDO_FOTO_TIPOS_LABELS,
        modo="novo",
        template_options=_template_options(usuario),
    )


@laudos_bp.route("/novo", methods=["POST"])
def criar():
    usuario = _require_manage()
    os_id = request.form.get("os_id", type=int)
    tipo = request.form.get("tipo", "diagnostico")
    try:
        laudo = criar_rascunho(os_id, usuario, tipo, request.form.get("template_id", type=int))
        atualizar_laudo(laudo, request.form.to_dict(), usuario)
        db.session.commit()
        flash("Rascunho de laudo criado.", "success")
        return redirect(url_for("laudos.editar", id=laudo.id))
    except (ValueError, PermissionError) as exc:
        db.session.rollback()
        flash(str(exc), "error")
        return redirect(url_for("laudos.novo", os_id=os_id or ""))


@laudos_bp.route("/<int:id>")
def detalhe(id):
    _require_view()
    laudo = _get_laudo(id)
    eventos = LaudoEvento.query.filter_by(laudo_id=laudo.id).order_by(LaudoEvento.criado_em.desc()).all()
    return render_template(
        "pages/laudo_detalhe.html",
        active="laudos",
        laudo=laudo,
        eventos=eventos,
        status_labels=LAUDO_STATUS_LABELS,
        tipo_labels=LAUDO_TIPOS_LABELS,
        foto_labels=LAUDO_FOTO_TIPOS_LABELS,
    )


@laudos_bp.route("/<int:id>/editar", methods=["GET"])
def editar(id):
    laudo = _get_laudo(id)
    _require_manage_laudo(laudo)
    if laudo.status != "draft":
        flash("Laudos finalizados ou cancelados não podem ser editados. Crie uma revisão formal.", "warning")
        return redirect(url_for("laudos.detalhe", id=id))
    return render_template(
        "pages/laudo_form.html",
        active="laudos",
        laudo=laudo,
        os_options=_os_options(),
        selected_os_id=laudo.os_id,
        tipo_labels=LAUDO_TIPOS_LABELS,
        foto_labels=LAUDO_FOTO_TIPOS_LABELS,
        modo="editar",
        template_options=_template_options(_usuario_atual()),
    )


@laudos_bp.route("/templates", methods=["GET", "POST"])
def templates():
    usuario = _require_laudo_permission("laudos.admin_templates")
    if request.method == "POST":
        nome = sanitize_text(request.form.get("nome"), max_length=120)
        tipo = request.form.get("tipo_laudo", "diagnostico")
        titulo = sanitize_text(request.form.get("titulo"), max_length=160)
        if not nome or len(nome) < 3 or tipo not in LAUDO_TIPOS_LABELS or not titulo:
            flash("Informe nome, tipo e título válidos.", "error")
            return redirect(url_for("laudos.templates"))
        obrigatorias = [item for item in request.form.getlist("fotos_obrigatorias") if item in LAUDO_FOTO_TIPOS]
        ultima = (
            LaudoTemplate.query
            .filter_by(organization_id=usuario.organization_id, nome=nome)
            .order_by(LaudoTemplate.versao.desc())
            .first()
        )
        template = LaudoTemplate(
            organization_id=usuario.organization_id,
            nome=nome,
            tipo_laudo=tipo,
            versao=(ultima.versao + 1) if ultima else 1,
            titulo=titulo,
            declaracao_final=sanitize_text(request.form.get("declaracao_final"), max_length=5000, strip=False),
            rodape=sanitize_text(request.form.get("rodape"), max_length=500),
            fotos_obrigatorias=obrigatorias,
            ativo=True,
            criado_por_id=usuario.id,
        )
        db.session.add(template)
        db.session.commit()
        flash(f"Template {template.nome} v{template.versao} criado.", "success")
        return redirect(url_for("laudos.templates"))
    items = (
        LaudoTemplate.query
        .filter_by(organization_id=usuario.organization_id)
        .order_by(LaudoTemplate.atualizado_em.desc())
        .all()
    )
    return render_template(
        "pages/laudo_templates.html", active="laudos", templates=items,
        tipo_labels=LAUDO_TIPOS_LABELS, foto_labels=LAUDO_FOTO_TIPOS_LABELS,
    )


@laudos_bp.route("/templates/<int:template_id>/toggle", methods=["POST"])
def template_toggle(template_id):
    usuario = _require_laudo_permission("laudos.admin_templates")
    template = LaudoTemplate.query.filter_by(
        id=template_id, organization_id=usuario.organization_id,
    ).first_or_404()
    template.ativo = not template.ativo
    db.session.commit()
    flash("Status do template atualizado.", "success")
    return redirect(url_for("laudos.templates"))


@laudos_bp.route("/<int:id>/editar", methods=["POST"])
def salvar(id):
    laudo = _get_laudo(id)
    usuario = _require_manage_laudo(laudo)
    try:
        atualizar_laudo(laudo, request.form.to_dict(), usuario)
        db.session.commit()
        flash("Rascunho salvo.", "success")
        return redirect(url_for("laudos.editar", id=laudo.id))
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "error")
        return redirect(url_for("laudos.editar", id=laudo.id))


@laudos_bp.route("/<int:id>/fotos", methods=["POST"])
def upload_foto(id):
    laudo = _get_laudo(id)
    usuario = _require_manage_laudo(laudo)
    try:
        adicionar_foto(
            laudo,
            request.files.get("foto"),
            request.form.get("tipo", "adicional"),
            request.form.get("legenda", ""),
            request.form.get("ordem", 0, type=int),
            usuario,
        )
        db.session.commit()
        flash("Foto adicionada.", "success")
    except (ValueError, PermissionError) as exc:
        db.session.rollback()
        flash(str(exc), "error")
    return redirect(url_for("laudos.editar", id=laudo.id))


@laudos_bp.route("/fotos/<int:foto_id>")
def foto(foto_id):
    usuario = _require_view()
    foto = (
        LaudoFoto.query.join(LaudoTecnico)
        .filter(LaudoFoto.id == foto_id, LaudoTecnico.organization_id == usuario.organization_id)
        .first_or_404()
    )
    storage_key = foto.thumbnail_key if request.args.get("thumbnail") == "1" and foto.thumbnail_key else foto.storage_key
    target = safe_file_path(storage_key)
    if not target.exists():
        abort(404)
    return send_file(target, mimetype=foto.mime_type, as_attachment=False)


@laudos_bp.route("/<int:id>/fotos/reordenar", methods=["POST"])
def reordenar_fotos_rota(id):
    laudo = _get_laudo(id)
    usuario = _require_manage_laudo(laudo)
    try:
        foto_ids = [int(value) for value in request.form.getlist("foto_ids")]
        reordenar_fotos(laudo, foto_ids, usuario)
        db.session.commit()
        flash("Ordem das fotos atualizada.", "success")
    except (TypeError, ValueError) as exc:
        db.session.rollback()
        flash(str(exc), "error")
    return redirect(url_for("laudos.editar", id=laudo.id))


@laudos_bp.route("/fotos/<int:foto_id>/remover", methods=["POST"])
def excluir_foto(foto_id):
    usuario_atual = _usuario_atual()
    foto = (
        LaudoFoto.query.join(LaudoTecnico)
        .filter(LaudoFoto.id == foto_id, LaudoTecnico.organization_id == (usuario_atual.organization_id if usuario_atual else -1))
        .first_or_404()
    )
    usuario = _require_manage_laudo(foto.laudo)
    laudo_id = foto.laudo_id
    try:
        remover_foto(foto, usuario)
        db.session.commit()
        flash("Foto removida.", "success")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "error")
    return redirect(url_for("laudos.editar", id=laudo_id))


@laudos_bp.route("/<int:id>/finalizar", methods=["POST"])
def finalizar(id):
    laudo = _get_laudo(id)
    usuario = _require_laudo_permission("laudos.finalize", laudo)
    if not can_manage_laudo(usuario, laudo):
        abort(403)
    try:
        finalizar_laudo(laudo, usuario)
        flash("Laudo finalizado e PDF gerado.", "success")
        return redirect(url_for("laudos.detalhe", id=laudo.id))
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("laudos.editar", id=laudo.id))
    except RuntimeError as exc:
        flash(str(exc), "error")
        return redirect(url_for("laudos.editar", id=laudo.id))


@laudos_bp.route("/<int:id>/pdf")
def baixar_pdf(id):
    laudo = _get_laudo(id)
    usuario = _require_laudo_permission("laudos.download_pdf", laudo)
    if not laudo.pdf_path:
        flash("PDF ainda não foi gerado.", "warning")
        return redirect(url_for("laudos.detalhe", id=id))
    target = safe_file_path(laudo.pdf_path)
    if not target.exists():
        abort(404)
    registrar_evento(laudo, "download_pdf", "Download do PDF.", usuario_id=usuario.id)
    db.session.commit()
    return send_file(target, mimetype="application/pdf", as_attachment=True, download_name=f"{laudo.numero or laudo.id}.pdf")


@laudos_bp.route("/<int:id>/duplicar", methods=["POST"])
def duplicar(id):
    laudo = _get_laudo(id)
    usuario = _require_laudo_permission("laudos.create", laudo)
    novo = duplicar_laudo(laudo, usuario, revisao=False)
    db.session.commit()
    flash("Laudo duplicado como novo rascunho.", "success")
    return redirect(url_for("laudos.editar", id=novo.id))


@laudos_bp.route("/<int:id>/revisao", methods=["POST"])
def revisao(id):
    laudo = _get_laudo(id)
    usuario = _require_laudo_permission("laudos.revise", laudo)
    novo = duplicar_laudo(laudo, usuario, revisao=True)
    db.session.commit()
    flash("Revisao formal criada como rascunho.", "success")
    return redirect(url_for("laudos.editar", id=novo.id))


@laudos_bp.route("/<int:id>/cancelar", methods=["POST"])
def cancelar(id):
    usuario = _usuario_atual()
    if not can_cancel_laudos(usuario):
        abort(403)
    laudo = _get_laudo(id)
    try:
        cancelar_laudo(laudo, request.form.get("motivo", ""), usuario)
        db.session.commit()
        flash("Laudo cancelado com auditoria.", "success")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "error")
    return redirect(url_for("laudos.detalhe", id=laudo.id))


@laudos_bp.route("/<int:id>/comprovante-cancelamento.pdf")
def comprovante_cancelamento(id):
    laudo = _get_laudo(id)
    usuario = _require_laudo_permission("laudos.download_pdf", laudo)
    try:
        pdf = gerar_comprovante_cancelamento(laudo)
    except ValueError as exc:
        flash(str(exc), "warning")
        return redirect(url_for("laudos.detalhe", id=laudo.id))
    registrar_evento(laudo, "download_pdf", "Download do comprovante de cancelamento.", usuario_id=usuario.id)
    db.session.commit()
    return send_file(
        pdf,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"{laudo.numero or laudo.id}-CANCELADO.pdf",
    )


@laudos_bp.route("/verificar/<token>")
def verificar(token):
    if not current_app.config.get("REPORTS_PUBLIC_VERIFICATION", True):
        abort(404)
    laudo = LaudoTecnico.query.filter_by(verification_token=token, verificacao_publica=True).first_or_404()
    return render_template("pages/laudo_verificar.html", laudo=laudo)
