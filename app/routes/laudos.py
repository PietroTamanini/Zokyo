"""Rotas HTML do modulo de laudos tecnicos."""
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_file, session, url_for
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import Cliente, OrdemServico, Usuario
from app.models.laudo import (
    LAUDO_FOTO_TIPOS_LABELS,
    LAUDO_STATUS_LABELS,
    LAUDO_TIPOS_LABELS,
    LaudoEvento,
    LaudoFoto,
    LaudoTecnico,
)
from app.services.laudos import (
    adicionar_foto,
    can_cancel_laudos,
    can_manage_laudos,
    can_view_laudos,
    cancelar_laudo,
    criar_rascunho,
    duplicar_laudo,
    finalizar_laudo,
    remover_foto,
    safe_file_path,
    atualizar_laudo,
    registrar_evento,
)
from app.utils.sanitizers import sanitize_cpf_cnpj, sanitize_text

laudos_bp = Blueprint("laudos", __name__, url_prefix="/laudos")


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
    return (
        LaudoTecnico.query
        .options(
            joinedload(LaudoTecnico.os),
            joinedload(LaudoTecnico.cliente),
            joinedload(LaudoTecnico.tecnico_responsavel),
        )
        .filter_by(id=id)
        .first_or_404()
    )


def _os_options():
    return (
        OrdemServico.query
        .filter(OrdemServico.deletado_em.is_(None))
        .options(joinedload(OrdemServico.cliente))
        .order_by(OrdemServico.data_entrada.desc())
        .limit(100)
        .all()
    )


@laudos_bp.route("/")
def index():
    _require_view()
    q = sanitize_text(request.args.get("q", ""), max_length=100)
    status = request.args.get("status", "")
    tipo = request.args.get("tipo", "")
    tecnico = sanitize_text(request.args.get("tecnico", ""), max_length=80)
    page = request.args.get("page", 1, type=int)

    query = (
        LaudoTecnico.query
        .options(joinedload(LaudoTecnico.os), joinedload(LaudoTecnico.cliente))
    )
    if status:
        query = query.filter(LaudoTecnico.status == status)
    if tipo:
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

    pag = query.order_by(LaudoTecnico.criado_em.desc()).paginate(page=page, per_page=25, error_out=False)
    return render_template(
        "pages/laudos_lista.html",
        active="laudos",
        laudos=pag.items,
        paginacao=pag,
        filtros={"q": q, "status": status, "tipo": tipo, "tecnico": tecnico},
        status_labels=LAUDO_STATUS_LABELS,
        tipo_labels=LAUDO_TIPOS_LABELS,
    )


@laudos_bp.route("/novo", methods=["GET"])
def novo():
    _require_manage()
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
    )


@laudos_bp.route("/novo", methods=["POST"])
def criar():
    usuario = _require_manage()
    os_id = request.form.get("os_id", type=int)
    tipo = request.form.get("tipo", "diagnostico")
    try:
        laudo = criar_rascunho(os_id, usuario, tipo)
        atualizar_laudo(laudo, request.form.to_dict(), usuario)
        db.session.commit()
        flash("Rascunho de laudo criado.", "success")
        return redirect(url_for("laudos.editar", id=laudo.id))
    except ValueError as exc:
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
    _require_manage()
    laudo = _get_laudo(id)
    if laudo.status != "draft":
        flash("Laudos finalizados ou cancelados nao podem ser editados. Crie uma revisao formal.", "warning")
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
    )


@laudos_bp.route("/<int:id>/editar", methods=["POST"])
def salvar(id):
    usuario = _require_manage()
    laudo = _get_laudo(id)
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
    usuario = _require_manage()
    laudo = _get_laudo(id)
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
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "error")
    return redirect(url_for("laudos.editar", id=laudo.id))


@laudos_bp.route("/fotos/<int:foto_id>")
def foto(foto_id):
    _require_view()
    foto = db.get_or_404(LaudoFoto, foto_id)
    target = safe_file_path(foto.storage_key)
    if not target.exists():
        abort(404)
    return send_file(target, mimetype=foto.mime_type, as_attachment=False)


@laudos_bp.route("/fotos/<int:foto_id>/remover", methods=["POST"])
def excluir_foto(foto_id):
    usuario = _require_manage()
    foto = db.get_or_404(LaudoFoto, foto_id)
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
    usuario = _require_manage()
    laudo = _get_laudo(id)
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
    usuario = _require_view()
    laudo = _get_laudo(id)
    if not laudo.pdf_path:
        flash("PDF ainda nao foi gerado.", "warning")
        return redirect(url_for("laudos.detalhe", id=id))
    target = safe_file_path(laudo.pdf_path)
    if not target.exists():
        abort(404)
    registrar_evento(laudo, "download_pdf", "Download do PDF.", usuario_id=usuario.id)
    db.session.commit()
    return send_file(target, mimetype="application/pdf", as_attachment=True, download_name=f"{laudo.numero or laudo.id}.pdf")


@laudos_bp.route("/<int:id>/duplicar", methods=["POST"])
def duplicar(id):
    usuario = _require_manage()
    laudo = _get_laudo(id)
    novo = duplicar_laudo(laudo, usuario, revisao=False)
    db.session.commit()
    flash("Laudo duplicado como novo rascunho.", "success")
    return redirect(url_for("laudos.editar", id=novo.id))


@laudos_bp.route("/<int:id>/revisao", methods=["POST"])
def revisao(id):
    usuario = _require_manage()
    laudo = _get_laudo(id)
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


@laudos_bp.route("/verificar/<token>")
def verificar(token):
    if not current_app.config.get("REPORTS_PUBLIC_VERIFICATION", True):
        abort(404)
    laudo = LaudoTecnico.query.filter_by(verification_token=token, verificacao_publica=True).first_or_404()
    return render_template("pages/laudo_verificar.html", laudo=laudo)
