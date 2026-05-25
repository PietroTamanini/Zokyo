"""
routes/logs.py — Registro de eventos e auditoria.

Fixes:
  - usuario_id validado como inteiro
  - Endpoint de API JSON adicionado: GET /api/logs
"""
from flask import Blueprint, render_template, request, jsonify
from app.extensions import db
from app.models import EventoLog, Usuario
from app.utils.auth import page_nivel_required, nivel_required

logs_bp = Blueprint("logs", __name__)


def _build_query(data_ini, data_fim, usuario_id, tipo, modulo):
    """Constrói query de logs com os filtros informados."""
    from datetime import datetime
    q = EventoLog.query
    if data_ini:
        try:
            q = q.filter(EventoLog.criado_em >= datetime.fromisoformat(data_ini))
        except ValueError:
            pass
    if data_fim:
        try:
            q = q.filter(EventoLog.criado_em <= datetime.fromisoformat(data_fim + " 23:59:59"))
        except ValueError:
            pass
    # FIX: validar usuario_id como inteiro
    if usuario_id:
        try:
            q = q.filter_by(usuario_id=int(usuario_id))
        except (ValueError, TypeError):
            pass
    if tipo:
        q = q.filter_by(tipo=tipo)
    if modulo:
        q = q.filter_by(modulo=modulo)
    return q


@logs_bp.route("/logs")
@page_nivel_required("admin")
def index():
    data_ini   = request.args.get("data_ini", "")
    data_fim   = request.args.get("data_fim", "")
    usuario_id = request.args.get("usuario_id", "")
    tipo       = request.args.get("tipo", "")
    modulo     = request.args.get("modulo", "")
    page       = request.args.get("page", 1, type=int)

    q = _build_query(data_ini, data_fim, usuario_id, tipo, modulo)
    pag = q.order_by(EventoLog.criado_em.desc()).paginate(
        page=page, per_page=50, error_out=False)
    usuarios = Usuario.query.order_by(Usuario.nome).all()
    modulos  = [r[0] for r in db.session.query(
        EventoLog.modulo).distinct().all() if r[0]]

    return render_template("pages/logs.html",
        active="logs", eventos=pag.items, paginacao=pag,
        usuarios=usuarios, modulos=modulos,
        filtros={"data_ini": data_ini, "data_fim": data_fim,
                 "usuario_id": usuario_id, "tipo": tipo, "modulo": modulo}
    )


@logs_bp.route("/api/logs", methods=["GET"])
@nivel_required("admin")
def api_logs():
    """Endpoint JSON para integração e exportação de logs."""
    data_ini   = request.args.get("data_ini", "")
    data_fim   = request.args.get("data_fim", "")
    usuario_id = request.args.get("usuario_id", "")
    tipo       = request.args.get("tipo", "")
    modulo     = request.args.get("modulo", "")
    page       = request.args.get("page", 1, type=int)
    per_page   = min(request.args.get("per_page", 50, type=int), 200)

    q = _build_query(data_ini, data_fim, usuario_id, tipo, modulo)
    pag = q.order_by(EventoLog.criado_em.desc()).paginate(
        page=page, per_page=per_page, error_out=False)

    return jsonify({
        "items": [e.to_dict() for e in pag.items],
        "total": pag.total,
        "page":  pag.page,
        "pages": pag.pages,
    })
