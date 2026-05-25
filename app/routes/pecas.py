"""routes/pecas.py — CRUD de peças (estoque).

Segurança:
  - Sanitização de inputs
  - Validação numérica com limites
  - LIKE injection: escapa %, _
  - quantidade e custo não podem ser negativos
"""
from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models import Peca, registrar
from app.utils.auth import api_login_required as login_required, nivel_required
from app.utils.sanitizers import sanitize_text, sanitize_search_query

pecas_bp = Blueprint("pecas", __name__)

_MAX_CUSTO  = 999_999.99
_MAX_MARGEM = 10_000.0   # 10000%


def _escape_like(q: str) -> str:
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@pecas_bp.route("/api/pecas", methods=["GET"])
@login_required
def listar():
    q             = sanitize_search_query(request.args.get("q", ""), max_length=100)
    baixo_estoque = request.args.get("baixo_estoque", type=int)
    query         = Peca.query
    if q:
        qe = _escape_like(q)
        query = query.filter(Peca.nome.ilike(f"%{qe}%"))
    if baixo_estoque is not None:
        query = query.filter(Peca.quantidade <= baixo_estoque)
    return jsonify([p.to_dict() for p in query.order_by(Peca.nome).all()])


@pecas_bp.route("/api/pecas/<int:id>", methods=["GET"])
@login_required
def obter(id):
    return jsonify(Peca.query.filter_by(id=id).first_or_404().to_dict())


@pecas_bp.route("/api/pecas", methods=["POST"])
@nivel_required("admin", "tecnico")
def criar():
    data = request.get_json(silent=True) or {}

    nome = sanitize_text(data.get("nome", ""), max_length=200)
    if not nome or len(nome) < 2:
        return jsonify({"success": False, "erro": "Nome é obrigatório (mínimo 2 caracteres)"}), 400

    try:
        quantidade = int(data.get("quantidade", 0))
        custo      = float(data.get("custo", 0))
        margem     = float(data.get("margem", 0))
    except (ValueError, TypeError):
        return jsonify({"success": False,
                        "erro": "quantidade, custo e margem devem ser numéricos"}), 400

    if quantidade < 0:
        return jsonify({"success": False, "erro": "Quantidade não pode ser negativa"}), 400
    if custo < 0:
        return jsonify({"success": False, "erro": "Custo não pode ser negativo"}), 400
    if custo > _MAX_CUSTO:
        return jsonify({"success": False,
                        "erro": f"Custo não pode exceder R$ {_MAX_CUSTO:,.2f}"}), 400
    if margem < 0:
        return jsonify({"success": False, "erro": "Margem não pode ser negativa"}), 400
    if margem > _MAX_MARGEM:
        return jsonify({"success": False,
                        "erro": f"Margem não pode exceder {_MAX_MARGEM}%"}), 400

    codigo = sanitize_text(data.get("codigo", ""), max_length=50) or None

    peca = Peca(
        nome=nome, codigo=codigo,
        quantidade=quantidade, custo=custo, margem=margem,
        fornecedor_id=data.get("fornecedor_id"),
    )
    db.session.add(peca)
    registrar("criacao", "estoque", f"Peça criada: {nome}")
    db.session.commit()
    return jsonify(peca.to_dict()), 201


@pecas_bp.route("/api/pecas/<int:id>", methods=["PUT"])
@nivel_required("admin", "tecnico")
def atualizar(id):
    peca = Peca.query.filter_by(id=id).first_or_404()
    data = request.get_json(silent=True) or {}

    if "nome" in data:
        nome = sanitize_text(data["nome"], max_length=200)
        if not nome or len(nome) < 2:
            return jsonify({"success": False, "erro": "Nome inválido"}), 400
        peca.nome = nome

    if "codigo" in data:
        peca.codigo = sanitize_text(data["codigo"], max_length=50) or None

    for campo_num, min_v, max_v in (
        ("quantidade", 0, 999_999),
        ("custo",      0, _MAX_CUSTO),
        ("margem",     0, _MAX_MARGEM),
    ):
        if campo_num in data:
            try:
                val = float(data[campo_num])
            except (ValueError, TypeError):
                return jsonify({"success": False,
                                "erro": f"{campo_num} deve ser numérico"}), 400
            if val < min_v:
                return jsonify({"success": False,
                                "erro": f"{campo_num} não pode ser negativo"}), 400
            if val > max_v:
                return jsonify({"success": False,
                                "erro": f"{campo_num} excede o valor máximo"}), 400
            if campo_num == "quantidade":
                val = int(val)
            setattr(peca, campo_num, val)

    if "fornecedor_id" in data:
        peca.fornecedor_id = data["fornecedor_id"]

    db.session.commit()
    return jsonify(peca.to_dict())


@pecas_bp.route("/api/pecas/<int:id>", methods=["DELETE"])
@nivel_required("admin")
def deletar(id):
    peca = Peca.query.filter_by(id=id).first_or_404()
    db.session.delete(peca)
    db.session.commit()
    return jsonify({"success": True, "mensagem": "Peça removida"})


@pecas_bp.route("/api/pecas/<int:id>/ajuste-estoque", methods=["POST"])
@nivel_required("admin", "tecnico")
def ajuste_estoque(id):
    peca = Peca.query.filter_by(id=id).first_or_404()
    data = request.get_json(silent=True) or {}
    try:
        delta = int(data.get("delta", 0))
    except (ValueError, TypeError):
        return jsonify({"success": False, "erro": "delta deve ser inteiro"}), 400

    nova_qtd = peca.quantidade + delta
    if nova_qtd < 0:
        return jsonify({"success": False,
                        "erro": f"Estoque insuficiente. Disponível: {peca.quantidade}"}), 400
    if nova_qtd > 999_999:
        return jsonify({"success": False, "erro": "Quantidade excede o limite máximo"}), 400

    peca.quantidade = nova_qtd
    db.session.commit()
    return jsonify(peca.to_dict())
