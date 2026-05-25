"""routes/transacoes.py — CRUD financeiro + resumo.

Segurança:
  - Sanitização de inputs de texto
  - Validação de tipo e status contra whitelist
  - Bloqueio de valores negativos e fora de range
  - Parsing seguro de datas
  - MySQL-only date_format mantido (produção usa MySQL)
"""
import math
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from sqlalchemy import func

from app.extensions import db
from app.models import Transacao
from app.models.transacao import TIPOS_TRANSACAO, STATUS_TRANSACAO
from app.utils.auth import nivel_required
from app.utils.sanitizers import sanitize_text
from app.utils.request_data import get_request_data

transacoes_bp = Blueprint("transacoes", __name__)

_MAX_VALOR = 9_999_999.99


def _now():
    return datetime.now(timezone.utc)


def _parse_date_safe(valor) -> datetime | None:
    """Parsing seguro de data ISO com tratamento de erros."""
    if not valor:
        return None
    try:
        return datetime.fromisoformat(str(valor)[:19])
    except (ValueError, TypeError):
        return None


def _validar_valor(valor) -> tuple[float | None, str | None]:
    """Valida e retorna (float, erro_ou_None)."""
    try:
        v = float(valor)
    except (ValueError, TypeError):
        return None, "valor deve ser numérico"
    if math.isnan(v) or math.isinf(v):
        return None, "valor deve ser um número finito"
    if v < 0:
        return None, "Valor não pode ser negativo"
    if v > _MAX_VALOR:
        return None, f"Valor excede o máximo permitido (R$ {_MAX_VALOR:,.2f})"
    return v, None


@transacoes_bp.route("/api/transacoes", methods=["GET"])
@nivel_required("admin", "financeiro")
def listar():
    tipo   = request.args.get("tipo")
    status = request.args.get("status")
    mes    = request.args.get("mes",  type=int)
    ano    = request.args.get("ano",  type=int)

    # Valida filtros contra whitelist
    if tipo and tipo not in TIPOS_TRANSACAO:
        return jsonify({"success": False, "erro": "tipo de filtro inválido"}), 400
    if status and status not in STATUS_TRANSACAO:
        return jsonify({"success": False, "erro": "status de filtro inválido"}), 400

    query = Transacao.query
    if tipo:   query = query.filter_by(tipo=tipo)
    if status: query = query.filter_by(status=status)
    if mes and ano:
        if not (1 <= mes <= 12):
            return jsonify({"success": False, "erro": "mês inválido (1-12)"}), 400
        if not (2000 <= ano <= 2100):
            return jsonify({"success": False, "erro": "ano inválido"}), 400
        query = query.filter(
            func.date_format(Transacao.criado_em, "%m") == f"{mes:02d}",
            func.date_format(Transacao.criado_em, "%Y") == str(ano),
        )
    return jsonify([t.to_dict() for t in
                    query.order_by(Transacao.criado_em.desc()).all()])


@transacoes_bp.route("/api/transacoes/<int:id>", methods=["GET"])
@nivel_required("admin", "financeiro")
def obter(id):
    return jsonify(db.get_or_404(Transacao, id).to_dict())


@transacoes_bp.route("/api/transacoes", methods=["POST"])
@nivel_required("admin", "financeiro")
def criar():
    data, _ = get_request_data()

    if not data.get("tipo") or data["tipo"] not in TIPOS_TRANSACAO:
        return jsonify({
            "success": False,
            "erro": f"tipo inválido. Use: {', '.join(TIPOS_TRANSACAO)}"
        }), 400

    valor, erro_valor = _validar_valor(data.get("valor"))
    if erro_valor:
        return jsonify({"success": False, "erro": erro_valor}), 400

    status = data.get("status", "pendente")
    if status not in STATUS_TRANSACAO:
        return jsonify({
            "success": False,
            "erro": f"status inválido. Use: {', '.join(STATUS_TRANSACAO)}"
        }), 400

    # Sanitiza campos de texto
    categoria = sanitize_text(data.get("categoria", ""), max_length=100) or None
    descricao = sanitize_text(data.get("descricao", ""), max_length=500) or None

    t = Transacao(
        os_id            = data.get("os_id"),
        tipo             = data["tipo"],
        categoria        = categoria,
        descricao        = descricao,
        valor            = valor,
        status           = status,
        data_vencimento  = _parse_date_safe(data.get("data_vencimento")),
        data_pagamento   = _parse_date_safe(data.get("data_pagamento")),
    )
    db.session.add(t)
    db.session.commit()
    return jsonify(t.to_dict()), 201


@transacoes_bp.route("/api/transacoes/<int:id>", methods=["PUT"])
@nivel_required("admin", "financeiro")
def atualizar(id):
    t       = db.get_or_404(Transacao, id)
    data, _ = get_request_data()

    if "tipo" in data:
        if data["tipo"] not in TIPOS_TRANSACAO:
            return jsonify({"success": False,
                            "erro": f"tipo inválido. Use: {', '.join(TIPOS_TRANSACAO)}"}), 400
        t.tipo = data["tipo"]

    if "status" in data:
        if data["status"] not in STATUS_TRANSACAO:
            return jsonify({"success": False,
                            "erro": f"status inválido. Use: {', '.join(STATUS_TRANSACAO)}"}), 400
        t.status = data["status"]

    if "valor" in data:
        valor, erro_valor = _validar_valor(data["valor"])
        if erro_valor:
            return jsonify({"success": False, "erro": erro_valor}), 400
        t.valor = valor

    if "categoria" in data:
        t.categoria = sanitize_text(data["categoria"], max_length=100) or None
    if "descricao" in data:
        t.descricao = sanitize_text(data["descricao"], max_length=500) or None
    if "os_id" in data:
        t.os_id = data["os_id"]

    if "data_vencimento" in data:
        t.data_vencimento = _parse_date_safe(data["data_vencimento"])
    if "data_pagamento" in data:
        t.data_pagamento = _parse_date_safe(data["data_pagamento"])

    db.session.commit()
    return jsonify(t.to_dict())


@transacoes_bp.route("/api/transacoes/<int:id>", methods=["DELETE"])
@nivel_required("admin")
def deletar(id):
    t = db.get_or_404(Transacao, id)
    db.session.delete(t)
    db.session.commit()
    return jsonify({"success": True, "mensagem": "Transação removida"})


@transacoes_bp.route("/api/transacoes/resumo", methods=["GET"])
@nivel_required("admin", "financeiro")
def resumo():
    mes = request.args.get("mes", type=int, default=_now().month)
    ano = request.args.get("ano", type=int, default=_now().year)

    if not (1 <= mes <= 12):
        return jsonify({"success": False, "erro": "mês inválido (1-12)"}), 400
    if not (2000 <= ano <= 2100):
        return jsonify({"success": False, "erro": "ano inválido"}), 400

    def total_tipo(tipo):
        return float(
            db.session.query(func.coalesce(func.sum(Transacao.valor), 0))
            .filter(
                Transacao.tipo   == tipo,
                Transacao.status != "cancelado",
                func.date_format(Transacao.criado_em, "%m") == f"{mes:02d}",
                func.date_format(Transacao.criado_em, "%Y") == str(ano),
            ).scalar() or 0
        )

    receitas = total_tipo("receita")
    despesas = total_tipo("despesa")
    return jsonify({
        "mes": mes, "ano": ano,
        "receitas": receitas, "despesas": despesas,
        "saldo": round(receitas - despesas, 2),
    })
