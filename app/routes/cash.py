"""routes/cash.py — caixa: abertura, movimentacoes, conferencia e fechamento."""
from flask import Blueprint, g, jsonify, request

from app.services import cash as cash_service
from app.utils.auth import nivel_required
from app.utils.request_data import get_request_data

cash_bp = Blueprint("cash", __name__)


def _organization_id() -> int:
    return int(getattr(g, "organization_id", None) or 0) or None


@cash_bp.route("/api/cash/sessoes", methods=["GET"])
@nivel_required("admin", "financeiro")
def sessoes():
    organization_id = _organization_id()
    limit = request.args.get("limit", default=30, type=int)
    rows = cash_service.list_caixa_sessoes(organization_id, limit=limit)
    return jsonify({
        "sessoes": [
            {
                "id": item.id,
                "status": item.status,
                "data_abertura": item.data_abertura.isoformat() if item.data_abertura else None,
                "saldo_inicial": float(item.saldo_inicial or 0),
                "valor_fechado_esperado": float(item.valor_fechado_esperado or 0),
                "valor_conferido": float(item.valor_conferido or 0),
                "diferenca": float(item.diferenca or 0),
                "fechada_em": item.fechada_em.isoformat() if item.fechada_em else None,
            }
            for item in rows
        ]
    }), 200


@cash_bp.route("/api/cash/sessoes/abrir", methods=["POST"])
@nivel_required("admin", "financeiro")
def abrir():
    organization_id = _organization_id()
    data, _ = get_request_data()
    saldo_inicial = float(data.get("saldo_inicial") or 0)
    session_obj = cash_service.open_caixa(
        organization_id,
        saldo_inicial=saldo_inicial,
        responsavel_id=data.get("responsavel_id") or None,
        responsavel_nome=data.get("responsavel_nome") or None,
    )
    return jsonify({
        "success": True,
        "sessao": {
            "id": session_obj.id,
            "status": session_obj.status,
            "saldo_inicial": float(session_obj.saldo_inicial or 0),
        },
    }), 201


@cash_bp.route("/api/cash/sessoes/<int:sessao_id>", methods=["GET"])
@nivel_required("admin", "financeiro")
def sessao_detail(sessao_id):
    organization_id = _organization_id()
    session_obj = cash_service.get_caixa_sessao(organization_id, sessao_id)
    if not session_obj:
        return jsonify({"success": False, "erro": "Sessao de caixa nao encontrada"}), 404
    return jsonify({"sessao": {
        "id": session_obj.id,
        "status": session_obj.status,
        "data_abertura": session_obj.data_abertura.isoformat() if session_obj.data_abertura else None,
        "saldo_inicial": float(session_obj.saldo_inicial or 0),
        "valor_fechado_esperado": float(session_obj.valor_fechado_esperado or 0),
        "valor_conferido": float(session_obj.valor_conferido or 0),
        "diferenca": float(session_obj.diferenca or 0),
        "fechada_em": session_obj.fechada_em.isoformat() if session_obj.fechada_em else None,
    }})


@cash_bp.route("/api/cash/sessoes/<int:sessao_id>/fechar", methods=["POST"])
@nivel_required("admin", "financeiro")
def fechar(sessao_id):
    organization_id = _organization_id()
    data, _ = get_request_data()
    valor_conferido = float(data.get("valor_conferido") or 0)
    try:
        session_obj = cash_service.close_caixa(
            organization_id,
            sessao_id=sessao_id,
            valor_conferido=valor_conferido,
            observacoes=data.get("observacoes") or None,
            usuario_id=data.get("usuario_id") or None,
            usuario_nome=data.get("usuario_nome") or None,
        )
    except ValueError as exc:
        return jsonify({"success": False, "erro": str(exc)}), 409 if "ja fechada" in str(exc) else 400
    return jsonify({
        "success": True,
        "sessao": {
            "id": session_obj.id,
            "status": session_obj.status,
            "valor_fechado_esperado": float(session_obj.valor_fechado_esperado or 0),
            "valor_conferido": float(session_obj.valor_conferido or 0),
            "diferenca": float(session_obj.diferenca or 0),
        },
    }), 200


@cash_bp.route("/api/cash/movimentos", methods=["GET"])
@nivel_required("admin", "financeiro")
def movimentos():
    organization_id = _organization_id()
    sessao_id = request.args.get("sessao_id", type=int)
    if sessao_id:
        session_obj = cash_service.get_caixa_sessao(organization_id, sessao_id)
        if not session_obj:
            return jsonify({"success": False, "erro": "Sessao de caixa nao encontrada"}), 404
        movimentos = sorted(session_obj.movimentos, key=lambda item: (item.criado_em, item.id or 0))
    else:
        session_obj = cash_service.get_open_caixa(organization_id)
        movimentos = (
            sorted(session_obj.movimentos, key=lambda item: (item.criado_em, item.id or 0))
            if session_obj else []
        )
    return jsonify({
        "movimentos": [
            {
                "id": item.id,
                "tipo": item.tipo,
                "valor": float(item.valor or 0),
                "forma_pagamento": item.forma_pagamento,
                "descricao": item.descricao,
                "criado_em": item.criado_em.isoformat() if item.criado_em else None,
            }
            for item in movimentos
        ]
    }), 200


@cash_bp.route("/api/cash/movimentos", methods=["POST"])
@nivel_required("admin", "financeiro")
def criar_movimento():
    organization_id = _organization_id()
    data, _ = get_request_data()
    tipo = data.get("tipo")
    try:
        valor_float = float(data.get("valor"))
    except (TypeError, ValueError):
        return jsonify({"success": False, "erro": "valor deve ser numerico"}), 400
    session_obj = cash_service.get_open_caixa(organization_id)
    if not session_obj:
        return jsonify({"success": False, "erro": "Caixa aberta nao encontrada"}), 409
    movement = None
    try:
        movement = cash_service.add_caixa_movimento(
            organization_id=organization_id,
            sessao_id=session_obj.id,
            tipo=tipo,
            valor=valor_float,
            forma_pagamento=data.get("forma_pagamento") or None,
            descricao=data.get("descricao") or None,
            responsavel_id=data.get("responsavel_id") or None,
            responsavel_nome=data.get("responsavel_nome") or None,
        )
    except ValueError as exc:
        return jsonify({"success": False, "erro": str(exc)}), 400
    return jsonify({
        "success": True,
        "movimento": {
            "id": movement.id,
            "tipo": movement.tipo,
            "valor": float(movement.valor or 0),
        },
    }), 201


@cash_bp.route("/api/cash/relatorio", methods=["GET"])
@nivel_required("admin", "financeiro")
def relatorio():
    organization_id = _organization_id()
    sessao_id = request.args.get("sessao_id", type=int)
    return jsonify(cash_service.caixa_resumo(organization_id, sessao_id=sessao_id)), 200
