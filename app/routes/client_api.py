"""API de cliente autenticada por token de portal."""
from flask import Blueprint, g, jsonify, request

from app.extensions import db
from app.models import OrdemServico, Transacao, Usuario
from app.services.portal import buscar_token_portal
from app.utils.rate_limit import rate_limit_route
from app.utils.sanitizers import sanitize_text

client_api_bp = Blueprint("client_api", __name__)
BEARER_SCHEME = "Bearer"


def _raw_token():
    auth = request.headers.get("Authorization", "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    data = request.get_json(silent=True) or {}
    return (
        request.headers.get("X-Portal-Token", "").strip()
        or request.args.get("portal_token", "").strip()
        or request.args.get("token", "").strip()
        or str(data.get("portal_token") or data.get("token") or "").strip()
    )


def _client_context():
    token = buscar_token_portal(_raw_token())
    if not token:
        return None, None, None
    os_obj = token.os
    if not os_obj or os_obj.deletado_em is not None:
        return None, None, None
    g.organization_id = token.organization_id
    return token, os_obj.cliente, os_obj


def _require_client():
    token, cliente, os_obj = _client_context()
    if not token or not cliente:
        return None, None, None, (jsonify({"status": False, "message": "Token inválido ou expirado"}), 401)
    return token, cliente, os_obj, None


def _serialize_os(os_obj):
    equipamento = " ".join(part for part in [os_obj.tipo_aparelho, os_obj.marca, os_obj.modelo] if part)
    return {
        "id": os_obj.id,
        "numero": f"OS #{os_obj.codigo_os}",
        "status": os_obj.status,
        "equipamento": equipamento or "-",
        "defeito_alegado": os_obj.defeito_alegado or "",
        "solucao": os_obj.solucao or "",
        "observacoes": os_obj.observacoes or "",
        "valor_servico": float(os_obj.valor_servico or 0),
        "valor_pecas": float(os_obj.valor_pecas or 0),
        "desconto": float(os_obj.desconto or 0),
        "valor_total": os_obj.valor_total,
        "data_entrada": os_obj.data_entrada.isoformat() if os_obj.data_entrada else None,
        "data_prev": os_obj.data_prev.isoformat() if os_obj.data_prev else None,
        "data_saida": os_obj.data_saida.isoformat() if os_obj.data_saida else None,
        "orcamento_status": os_obj.orcamento_status,
    }


def _serialize_transacao(item):
    return {
        "id": item.id,
        "os_id": item.os_id,
        "descricao": item.descricao,
        "valor": float(item.valor or 0),
        "categoria": item.categoria,
        "status": item.status,
        "forma_pagamento": item.forma_pagamento,
        "payment_gateway": item.payment_gateway,
        "payment_method": item.payment_method,
        "payment_status": item.payment_status,
        "payment_url": item.payment_url,
        "payment_link": item.payment_link,
        "payment_barcode": item.payment_barcode,
        "payment_payload": item.payment_payload,
        "payment_expires_at": item.payment_expires_at.isoformat() if item.payment_expires_at else None,
        "data_vencimento": item.data_vencimento.isoformat() if item.data_vencimento else None,
        "data_pagamento": item.data_pagamento.isoformat() if item.data_pagamento else None,
    }


def _orders_for_client(cliente):
    return (
        OrdemServico.query
        .filter_by(cliente_id=cliente.id, organization_id=cliente.organization_id)
        .filter(OrdemServico.deletado_em.is_(None))
        .order_by(OrdemServico.data_entrada.desc())
    )


@client_api_bp.route("/api/v1/client/auth", methods=["POST"])
@rate_limit_route(max_hits=30, window_seconds=300)
def auth():
    _token, cliente, os_obj, error = _require_client()
    if error:
        return error
    return jsonify({
        "status": True,
        "message": "Autenticado",
        "token_type": BEARER_SCHEME,
        "cliente": {
            "id": cliente.id,
            "nome": cliente.nome,
            "email": cliente.email or "",
            "telefone": cliente.telefone or "",
        },
        "os": _serialize_os(os_obj),
    })


@client_api_bp.route("/api/v1/client", methods=["GET"])
def index():
    _token, cliente, _os_obj, error = _require_client()
    if error:
        return error
    orders = _orders_for_client(cliente).limit(5).all()
    transactions = _transactions_for_client(cliente).limit(5).all()
    return jsonify({
        "status": True,
        "message": "Listando resultados",
        "result": {
            "Os": [_serialize_os(item) for item in orders],
            "compras": [_serialize_transacao(item) for item in transactions],
        },
    })


@client_api_bp.route("/api/v1/client/os", methods=["GET", "POST"])
@rate_limit_route(max_hits=120, window_seconds=300)
def os_collection():
    token, cliente, _os_obj, error = _require_client()
    if error:
        return error
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        descricao = sanitize_text(
            data.get("descricaoProduto") or data.get("descricao") or data.get("tipo_aparelho") or "",
            max_length=120,
        )
        defeito = sanitize_text(data.get("defeito") or data.get("defeito_alegado") or "", max_length=5000)
        observacoes = sanitize_text(data.get("observacoes") or "", max_length=5000)
        if not descricao:
            return jsonify({"status": False, "message": "descricaoProduto é obrigatório"}), 400
        usuario = db.session.get(Usuario, token.criado_por_id)
        if not usuario or usuario.organization_id != token.organization_id:
            return jsonify({"status": False, "message": "Técnico responsável não encontrado"}), 500
        novo = OrdemServico(
            organization_id=cliente.organization_id,
            cliente_id=cliente.id,
            usuario_id=usuario.id,
            tipo_aparelho=descricao,
            defeito_alegado=defeito or None,
            observacoes=observacoes or None,
            status="recepcao",
        )
        db.session.add(novo)
        db.session.commit()
        return jsonify({"status": True, "message": "OS criada", "result": _serialize_os(novo)}), 201

    orders = _orders_for_client(cliente).limit(200).all()
    return jsonify({
        "status": True,
        "message": "Listando resultados",
        "result": {"Os": [_serialize_os(item) for item in orders]},
    })


@client_api_bp.route("/api/v1/client/os/<int:id>", methods=["GET"])
def os_detail(id):
    _token, cliente, _os_obj, error = _require_client()
    if error:
        return error
    os_obj = _orders_for_client(cliente).filter_by(id=id).first()
    if not os_obj:
        return jsonify({"status": False, "message": "Ordem de serviço não encontrada"}), 404
    return jsonify({"status": True, "message": "Listando resultados", "result": {"os": _serialize_os(os_obj)}})


def _transactions_for_client(cliente):
    return (
        Transacao.query
        .join(OrdemServico, Transacao.os_id == OrdemServico.id)
        .filter(OrdemServico.cliente_id == cliente.id)
        .filter(Transacao.organization_id == cliente.organization_id)
        .order_by(Transacao.criado_em.desc())
    )


@client_api_bp.route("/api/v1/client/compras", methods=["GET"])
@client_api_bp.route("/api/v1/client/compras/<int:id>", methods=["GET"])
def compras(id=None):
    _token, cliente, _os_obj, error = _require_client()
    if error:
        return error
    query = _transactions_for_client(cliente).filter(Transacao.tipo == "receita")
    if id:
        item = query.filter(Transacao.id == id).first()
        if not item:
            return jsonify({"status": False, "message": "Compra não encontrada"}), 404
        return jsonify({"status": True, "message": "Listando resultados", "result": {"Compras": _serialize_transacao(item)}})
    items = query.limit(200).all()
    return jsonify({"status": True, "message": "Listando resultados", "result": {"Compras": [_serialize_transacao(item) for item in items]}})


@client_api_bp.route("/api/v1/client/cobrancas", methods=["GET"])
@client_api_bp.route("/api/v1/client/cobrancas/<int:id>", methods=["GET"])
def cobrancas(id=None):
    _token, cliente, _os_obj, error = _require_client()
    if error:
        return error
    query = (
        _transactions_for_client(cliente)
        .filter(Transacao.tipo == "receita", Transacao.status == "pendente")
    )
    if id:
        item = query.filter(Transacao.id == id).first()
        if not item:
            return jsonify({"status": False, "message": "Cobrança não encontrada"}), 404
        return jsonify({"status": True, "message": "Listando resultados", "result": _serialize_transacao(item)})
    items = query.limit(200).all()
    return jsonify({"status": True, "message": "Listando resultados", "result": [_serialize_transacao(item) for item in items]})
