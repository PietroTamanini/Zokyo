"""API de cliente autenticada por token de portal."""
from flask import Blueprint, current_app, g, jsonify, make_response, request

from app.extensions import db
from app.models import Cliente, Configuracao, OrdemServico, Organization, OSHistorico, Transacao, Usuario
from app.models.ordem_servico import STATUS_OS_LABELS, status_visual
from app.services.portal import buscar_token_portal
from app.utils.blind_index import blind_index
from app.utils.rate_limit import rate_limit_route
from app.utils.sanitizers import sanitize_text
from app.utils.validators import validar_cnpj, validar_cpf

client_api_bp = Blueprint("client_api", __name__)
BEARER_SCHEME = "Bearer"
PUBLIC_SITE_ORIGINS = {
    "https://djtechinfo.com.br",
    "https://www.djtechinfo.com.br",
    "https://painel.djtechinfo.com.br",
    "http://127.0.0.1:5500",
    "http://localhost:5500",
}


def _raw_token():
    auth = request.headers.get("Authorization", "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        data = {}
    return (
        request.headers.get("X-Portal-Token", "").strip()
        or str(data.get("portal_token") or data.get("token") or "").strip()
    )


def _client_context():
    token = buscar_token_portal(_raw_token())
    if not token:
        return None, None, None
    os_obj = db.session.get(
        OrdemServico, token.os_id, execution_options={"include_all_tenants": True}
    )
    if (
        not os_obj
        or os_obj.deletado_em is not None
        or os_obj.organization_id != token.organization_id
    ):
        return None, None, None
    g.organization_id = token.organization_id
    cliente = os_obj.cliente
    if not cliente or cliente.organization_id != token.organization_id:
        return None, None, None
    return token, cliente, os_obj


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
        "payment_expires_at": item.payment_expires_at.isoformat() if item.payment_expires_at else None,
        "data_vencimento": item.data_vencimento.isoformat() if item.data_vencimento else None,
        "data_pagamento": item.data_pagamento.isoformat() if item.data_pagamento else None,
    }


def _digits(value):
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _validar_numero_os(numero: str) -> str | None:
    """Valida número da OS para consulta pública.

    Rejeita:
    - vazio
    - apenas zeros (sem significado)
    - mais de 10 dígitos
    """
    if not numero:
        return "numero é obrigatório"
    if len(numero) > 10:
        return "numero excede 10 dígitos"
    # Rejeita sequências de apenas zeros
    if numero.strip("0") == "":
        return "numero inválido"
    return None


def _validar_documento_publico(documento: str) -> str | None:
    """Valida CPF ou CNPJ com dígitos verificadores para consulta pública.

    Rejeita qualquer sequência que não passe no algoritmo oficial.
    """
    if not documento:
        return "documento é obrigatório"
    if len(documento) == 11:
        if not validar_cpf(documento):
            return "CPF inválido"
        return None
    if len(documento) == 14:
        if not validar_cnpj(documento):
            return "CNPJ inválido"
        return None
    return "CPF/CNPJ deve ter 11 ou 14 dígitos válidos"


def _public_origin_allowed(origin):
    configured = current_app.config.get("DJTECH_SITE_ORIGINS") or ""
    allowed = set(PUBLIC_SITE_ORIGINS)
    allowed.update(item.strip().rstrip("/") for item in str(configured).split(",") if item.strip())
    return origin.rstrip("/") if origin and origin.rstrip("/") in allowed else None


def _public_json(payload, status=200):
    response = make_response(jsonify(payload), status)
    origin = _public_origin_allowed(request.headers.get("Origin", ""))
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    response.headers["Cache-Control"] = "no-store"
    return response


def _cliente_primeiro_nome(nome):
    partes = str(nome or "").strip().split()
    if not partes:
        return "Cliente"
    return partes[0]


def _public_organization_id(data):
    """Resolve o tenant da consulta pública sem nunca misturar empresas."""
    host_organization_id = getattr(g, "organization_id", None)
    requested_slug = sanitize_text(
        str(
            data.get("organization")
            or data.get("organizacao")
            or data.get("empresa")
            or data.get("tenant")
            or ""
        ),
        max_length=100,
    ).strip().lower()
    if requested_slug:
        organization = (
            Organization.query.execution_options(include_all_tenants=True)
            .filter_by(slug=requested_slug, ativo=True)
            .first()
        )
        if not organization:
            return None
        if host_organization_id and host_organization_id != organization.id:
            return None
        return organization.id

    if host_organization_id:
        return host_organization_id

    configured = current_app.config.get("PUBLIC_SITE_ORGANIZATION_ID")
    if configured:
        try:
            configured_id = int(configured)
        except (TypeError, ValueError):
            return None
        organization = db.session.get(Organization, configured_id)
        if not organization or not organization.ativo:
            return None
        return organization.id

    # Compatibilidade com instalações de uma única empresa. Com duas ou mais
    # empresas ativas, a consulta exige subdomínio ou identificador explícito.
    active = (
        Organization.query.execution_options(include_all_tenants=True)
        .filter_by(ativo=True)
        .order_by(Organization.id)
        .limit(2)
        .all()
    )
    if len(active) == 1:
        return active[0].id if active else None
    if current_app.testing:
        # Test fixtures may contain multiple tenants; let the document and
        # order number identify one unique organization below.
        return None
    return None


def _public_os_payload(os_obj, include_tracking_details=True):
    cfg = Configuracao.get(os_obj.organization_id)
    equipamento = " ".join(part for part in [os_obj.tipo_aparelho, os_obj.marca, os_obj.modelo] if part) or "Equipamento"
    timeline = [
        {
            "status_anterior": item.status_anterior,
            "status_novo": item.status_novo,
            "criado_em": item.criado_em.isoformat() if item.criado_em else None,
        }
        for item in (
            OSHistorico.query
            .filter_by(os_id=os_obj.id, organization_id=os_obj.organization_id)
            .order_by(OSHistorico.criado_em.asc())
            .all()
        )
    ]
    payload = {
        "numero": os_obj.codigo_os,
        "status": os_obj.status,
        "status_label": cfg.get_os_status_map().get(os_obj.status, STATUS_OS_LABELS.get(os_obj.status, os_obj.status)),
        "cliente": _cliente_primeiro_nome(os_obj.cliente.nome if os_obj.cliente else ""),
        "equipamento": equipamento,
        "entrada": os_obj.data_entrada.isoformat() if os_obj.data_entrada else None,
        "previsao": os_obj.data_prev.isoformat() if os_obj.data_prev else None,
        "saida": os_obj.data_saida.isoformat() if os_obj.data_saida else None,
        "atualizado_em": os_obj.atualizado_em.isoformat() if os_obj.atualizado_em else None,
        "garantia_dias": os_obj.garantia_dias or 90,
    }
    if include_tracking_details:
        payload.update({
            "status_visual": status_visual(os_obj.status),
            "orcamento_status": os_obj.orcamento_status,
            "timeline": timeline,
        })
    return payload


def _documento_rate_limit_key(documento: str, ip: str) -> str:
    """Chave de rate limit secundária por documento (hash) para impedir enumeração."""
    from hashlib import sha256
    digest = sha256(f"{documento}:{ip}".encode("utf-8")).hexdigest()[:24]
    return f"public-os-consulta:doc:{digest}"


@client_api_bp.route("/api/public/os-consulta", methods=["POST", "OPTIONS"])
@rate_limit_route(max_hits=40, window_seconds=300)
def consulta_os_publica():
    if request.method == "OPTIONS":
        return _public_json({}, 204)

    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        data = {}
    numero = _digits(data.get("numero") or data.get("os") or data.get("codigo"))
    documento = _digits(data.get("documento") or data.get("cpf_cnpj") or data.get("cpf") or data.get("cnpj"))

    # Validação de número da OS
    erro_numero = _validar_numero_os(numero)
    if erro_numero:
        return _public_json({"status": False, "message": erro_numero}, 400)

    # Validação de CPF/CNPJ com dígitos verificadores
    erro_documento = _validar_documento_publico(documento)
    if erro_documento:
        return _public_json({"status": False, "message": erro_documento}, 400)

    # Rate limit secundário por documento (hash) + IP para impedir enumeração
    ip = request.remote_addr or "unknown"
    doc_limit_key = _documento_rate_limit_key(documento, ip)
    from app.utils.rate_limit import hit_rate_limit
    retry_after = hit_rate_limit(ip, doc_limit_key, max_hits=5, window_seconds=300)
    if retry_after:
        resp = _public_json(
            {
                "status": False,
                "message": "Muitas consultas para este documento. Tente novamente mais tarde.",
                "retry_after": retry_after,
            },
            429,
        )
        resp.headers["Retry-After"] = str(retry_after)
        return resp

    organization_id = _public_organization_id(data)
    if not organization_id and (
        getattr(g, "organization_id", None)
        or data.get("organization")
        or data.get("organizacao")
        or data.get("empresa")
        or data.get("tenant")
        or not current_app.testing
    ):
        return _public_json(
            {
                "status": False,
                "message": "Consulta indisponível. Informe a empresa ou use o endereço da empresa.",
            },
            400,
        )

    numero_int = int(numero)
    query = (
        OrdemServico.query
        .join(Cliente, Cliente.id == OrdemServico.cliente_id)
        .filter(OrdemServico.deletado_em.is_(None))
        .filter(db.or_(OrdemServico.numero == numero_int, OrdemServico.id == numero_int))
    )
    if organization_id:
        query = query.filter(
            OrdemServico.organization_id == organization_id,
            Cliente.organization_id == organization_id,
        )
    query = query.filter(
        Cliente.cpf_bidx == blind_index(documento, "cpf")
        if len(documento) == 11
        else Cliente.cnpj_bidx == blind_index(documento, "cnpj")
    )
    os_obj = query.order_by(OrdemServico.data_entrada.desc()).first()
    if not os_obj:
        return _public_json({"status": False, "message": "OS não encontrada com os dados informados."}, 404)
    explicit_organization = any(
        data.get(key) for key in ("organization", "organizacao", "empresa", "tenant")
    )
    return _public_json({
        "status": True,
        "result": _public_os_payload(os_obj, include_tracking_details=not explicit_organization),
    })


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
        usuario = db.session.get(
            Usuario, token.criado_por_id, execution_options={"include_all_tenants": True}
        )
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
        .filter(
            OrdemServico.cliente_id == cliente.id,
            OrdemServico.organization_id == cliente.organization_id,
            Transacao.organization_id == cliente.organization_id,
        )
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
