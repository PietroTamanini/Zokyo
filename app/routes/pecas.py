"""routes/pecas.py — CRUD de peças (estoque).

Segurança:
  - Sanitização de inputs
  - Validação numérica com limites
  - LIKE injection: escapa %, _
  - quantidade e custo não podem ser negativos
"""
from datetime import datetime

from flask import Blueprint, jsonify, request, session

from app.extensions import db
from app.models import Fornecedor, InventoryLot, Peca, registrar
from app.services.inventory import receive_lot, record_movement
from app.utils.auth import api_login_required as login_required
from app.utils.auth import nivel_required
from app.utils.sanitizers import sanitize_search_query, sanitize_text

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
@nivel_required("admin", "operacional")
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

    fornecedor_id = data.get("fornecedor_id") or None
    if fornecedor_id and not Fornecedor.query.filter_by(id=fornecedor_id, ativo=True).first():
        return jsonify({"success": False, "erro": "Fornecedor invalido para esta organizacao"}), 400
    peca = Peca(
        nome=nome, codigo=codigo,
        quantidade=quantidade, custo=custo, margem=margem,
        fornecedor_id=fornecedor_id,
    )
    db.session.add(peca)
    db.session.flush()
    if quantidade:
        record_movement(peca, session["usuario_id"], "initial", 0, quantidade, "Estoque inicial")
    registrar("criacao", "estoque", f"Peça criada: {nome}")
    db.session.commit()
    return jsonify(peca.to_dict()), 201


@pecas_bp.route("/api/pecas/<int:id>", methods=["PUT"])
@nivel_required("admin", "operacional")
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
            setattr(peca, campo_num, val)

    if "fornecedor_id" in data:
        fornecedor_id = data["fornecedor_id"] or None
        if fornecedor_id and not Fornecedor.query.filter_by(id=fornecedor_id, ativo=True).first():
            return jsonify({"success": False, "erro": "Fornecedor invalido para esta organizacao"}), 400
        peca.fornecedor_id = fornecedor_id

    db.session.commit()
    return jsonify(peca.to_dict())


@pecas_bp.route("/api/pecas/<int:id>", methods=["DELETE"])
@nivel_required("admin")
def deletar(id):
    peca = Peca.query.filter_by(id=id).first_or_404()
    if peca.ordens:
        return jsonify({"success": False, "erro": "Peca usada em OS deve ser preservada"}), 409
    db.session.delete(peca)
    db.session.commit()
    return jsonify({"success": True, "mensagem": "Peça removida"})


@pecas_bp.route("/api/pecas/<int:id>/ajuste-estoque", methods=["POST"])
@nivel_required("admin", "operacional")
def ajuste_estoque(id):
    peca = Peca.query.filter_by(id=id).first_or_404()
    data = request.get_json(silent=True) or {}
    try:
        delta = int(data.get("delta", 0))
    except (ValueError, TypeError):
        return jsonify({"success": False, "erro": "delta deve ser inteiro"}), 400

    reason = sanitize_text(data.get("justificativa", ""), max_length=300)
    if len(reason) < 5:
        return jsonify({"success": False, "erro": "Justificativa deve ter pelo menos 5 caracteres"}), 400
    before = peca.quantidade
    nova_qtd = before + delta
    if nova_qtd < 0:
        return jsonify({"success": False,
                        "erro": f"Estoque insuficiente. Disponível: {peca.quantidade}"}), 400
    if nova_qtd > 999_999:
        return jsonify({"success": False, "erro": "Quantidade excede o limite máximo"}), 400

    peca.quantidade = nova_qtd
    record_movement(peca, session["usuario_id"], "adjustment", before, nova_qtd, reason)
    db.session.commit()
    return jsonify(peca.to_dict())


@pecas_bp.route("/api/pecas/<int:id>/lotes", methods=["GET"])
@login_required
def listar_lotes(id):
    Peca.query.filter_by(id=id).first_or_404()
    lots = InventoryLot.query.filter_by(part_id=id).order_by(
        InventoryLot.expires_at.is_(None), InventoryLot.expires_at, InventoryLot.received_at,
    ).all()
    return jsonify([lot.to_dict() for lot in lots])


@pecas_bp.route("/api/pecas/<int:id>/lotes", methods=["POST"])
@nivel_required("admin", "operacional")
def receber_lote(id):
    part = Peca.query.filter_by(id=id).with_for_update().first_or_404()
    data = request.get_json(silent=True) or {}
    code = sanitize_text(data.get("codigo", ""), max_length=100)
    reason = sanitize_text(data.get("justificativa", ""), max_length=300)
    location = sanitize_text(data.get("localizacao", ""), max_length=100) or None
    try:
        quantity = int(data.get("quantidade"))
        unit_cost = float(data.get("custo_unitario"))
    except (TypeError, ValueError):
        return jsonify({"erro": "Quantidade e custo unitario devem ser numericos"}), 400
    supplier_id = data.get("fornecedor_id") or None
    if supplier_id and not Fornecedor.query.filter_by(id=supplier_id, ativo=True).first():
        return jsonify({"erro": "Fornecedor invalido"}), 400
    try:
        expires_at = datetime.fromisoformat(str(data["validade"])[:10]) if data.get("validade") else None
    except ValueError:
        return jsonify({"erro": "Validade invalida"}), 400
    if len(code) < 2:
        return jsonify({"erro": "Codigo do lote e obrigatorio"}), 400
    try:
        lot = receive_lot(
            part, session["usuario_id"], code, quantity, unit_cost, reason,
            supplier_id=supplier_id, location=location, expires_at=expires_at,
        )
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    db.session.commit()
    return jsonify({"lote": lot.to_dict(), "peca": part.to_dict()}), 201
