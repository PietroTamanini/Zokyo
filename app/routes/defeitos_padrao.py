"""routes/defeitos_padrao.py — Base de conhecimento de defeitos e soluções.

Fix: LIKE injection — escapa % e _ nos campos de busca.
"""
from flask import Blueprint, jsonify, request

from app.extensions import db
from app.models import DefeitoPadrao
from app.utils.auth import api_login_required, nivel_required
from app.utils.sanitizers import sanitize_text

defeitos_bp = Blueprint("defeitos", __name__)


def _escape_like(q: str) -> str:
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@defeitos_bp.route("/api/defeitos", methods=["GET"])
@api_login_required
def listar():
    q    = request.args.get("q", "").strip()
    tipo = request.args.get("tipo_aparelho", "").strip()
    query = DefeitoPadrao.query
    if q:
        qe = _escape_like(q)
        query = query.filter(DefeitoPadrao.sintoma.ilike(f"%{qe}%"))
    if tipo:
        te = _escape_like(tipo)
        query = query.filter(DefeitoPadrao.tipo_aparelho.ilike(f"%{te}%"))
    return jsonify([d.to_dict() for d in
                    query.order_by(DefeitoPadrao.tipo_aparelho,
                                   DefeitoPadrao.sintoma).all()])


@defeitos_bp.route("/api/defeitos", methods=["POST"])
@nivel_required("admin", "operacional")
def criar():
    data = request.get_json(silent=True) or {}
    if not data.get("sintoma"):
        return jsonify({"erro": "sintoma é obrigatório"}), 400
    d = DefeitoPadrao(
        tipo_aparelho=sanitize_text(data.get("tipo_aparelho", ""), max_length=100) or None,
        sintoma=sanitize_text(data["sintoma"], max_length=500),
        causa=sanitize_text(data.get("causa", ""), max_length=2000) or None,
        solucao=sanitize_text(data.get("solucao", ""), max_length=2000) or None,
    )
    db.session.add(d)
    db.session.commit()
    return jsonify(d.to_dict()), 201


@defeitos_bp.route("/api/defeitos/<int:id>", methods=["PUT"])
@nivel_required("admin", "operacional")
def atualizar(id):
    d    = db.get_or_404(DefeitoPadrao, id)
    data = request.get_json(silent=True) or {}
    _LIMITES = {"tipo_aparelho": 100, "sintoma": 500, "causa": 2000, "solucao": 2000}
    for campo, max_len in _LIMITES.items():
        if campo in data:
            setattr(d, campo, sanitize_text(data[campo], max_length=max_len) or None)
    db.session.commit()
    return jsonify(d.to_dict())


@defeitos_bp.route("/api/defeitos/<int:id>", methods=["DELETE"])
@nivel_required("admin")
def deletar(id):
    d = db.get_or_404(DefeitoPadrao, id)
    db.session.delete(d)
    db.session.commit()
    return jsonify({"mensagem": "Defeito padrão removido"})
