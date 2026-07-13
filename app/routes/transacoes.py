"""routes/transacoes.py — CRUD financeiro + resumo.

Segurança:
  - Sanitização de inputs de texto
  - Validação de tipo e status contra whitelist
  - Bloqueio de valores negativos e fora de range
  - Parsing seguro de datas
  - MySQL-only date_format mantido (produção usa MySQL)
"""
import csv
import io
import math
from datetime import datetime, timezone

from flask import Blueprint, Response, jsonify, request, session
from sqlalchemy import extract, func

from app.extensions import db
from app.models import OrdemServico, Transacao, Usuario, registrar
from app.models.transacao import STATUS_TRANSACAO, TIPOS_TRANSACAO
from app.services.finance import create_installments
from app.utils.auth import nivel_required
from app.utils.request_data import get_request_data
from app.utils.sanitizers import sanitize_text

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


def _valid_os_id(value):
    if value in (None, ""):
        return None, None
    try:
        os_id = int(value)
    except (TypeError, ValueError):
        return None, "os_id invalido"
    if not OrdemServico.query.filter_by(id=os_id).first():
        return None, "OS invalida para esta organizacao"
    return os_id, None


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
    if tipo:
        query = query.filter_by(tipo=tipo)
    if status:
        query = query.filter_by(status=status)
    if mes and ano:
        if not (1 <= mes <= 12):
            return jsonify({"success": False, "erro": "mês inválido (1-12)"}), 400
        if not (2000 <= ano <= 2100):
            return jsonify({"success": False, "erro": "ano inválido"}), 400
        query = query.filter(
            extract("month", Transacao.criado_em) == mes,
            extract("year", Transacao.criado_em) == ano,
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

    os_id, os_error = _valid_os_id(data.get("os_id"))
    if os_error:
        return jsonify({"success": False, "erro": os_error}), 400
    try:
        installments = int(data.get("parcelas", 1))
        commission_user_id = int(data["comissao_usuario_id"]) if data.get("comissao_usuario_id") else None
        if commission_user_id and not Usuario.query.filter_by(id=commission_user_id, ativo=True).first():
            return jsonify({"success": False, "erro": "Usuario de comissao invalido"}), 400
        created = create_installments(
            organization_id=None,
            installments=installments,
            recurrence=data.get("recorrencia"),
            os_id=os_id,
            tipo=data["tipo"], categoria=categoria, descricao=descricao,
            valor=valor, status=status,
            data_vencimento=_parse_date_safe(data.get("data_vencimento")),
            data_pagamento=_parse_date_safe(data.get("data_pagamento")),
            forma_pagamento=sanitize_text(data.get("forma_pagamento", ""), max_length=50) or None,
            comissao_usuario_id=commission_user_id,
            comissao_percentual=data.get("comissao_percentual", 0),
        )
    except (TypeError, ValueError) as exc:
        return jsonify({"success": False, "erro": str(exc)}), 400
    db.session.commit()
    if len(created) == 1:
        return jsonify(created[0].to_dict()), 201
    return jsonify({"transactions": [item.to_dict() for item in created]}), 201


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
        os_id, os_error = _valid_os_id(data["os_id"])
        if os_error:
            return jsonify({"success": False, "erro": os_error}), 400
        t.os_id = os_id

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
                extract("month", Transacao.criado_em) == mes,
                extract("year", Transacao.criado_em) == ano,
            ).scalar() or 0
        )

    receitas = total_tipo("receita")
    despesas = total_tipo("despesa")
    return jsonify({
        "mes": mes, "ano": ano,
        "receitas": receitas, "despesas": despesas,
        "saldo": round(receitas - despesas, 2),
    })


@transacoes_bp.route("/api/transacoes/<int:id>/conciliar", methods=["POST"])
@nivel_required("admin", "financeiro")
def conciliar(id):
    transaction = db.get_or_404(Transacao, id)
    data, _ = get_request_data()
    reference = sanitize_text(data.get("referencia", ""), max_length=120)
    if len(reference) < 3:
        return jsonify({"erro": "Referencia de conciliacao e obrigatoria"}), 400
    transaction.conciliado_em = _now()
    transaction.conciliado_por_id = session["usuario_id"]
    transaction.conciliacao_ref = reference
    registrar("conciliacao", "financeiro", f"Transacao #{id} conciliada: {reference}")
    db.session.commit()
    return jsonify(transaction.to_dict())


@transacoes_bp.route("/api/transacoes/<int:id>/desconciliar", methods=["POST"])
@nivel_required("admin", "financeiro")
def desconciliar(id):
    transaction = db.get_or_404(Transacao, id)
    transaction.conciliado_em = None
    transaction.conciliado_por_id = None
    transaction.conciliacao_ref = None
    registrar("conciliacao", "financeiro", f"Conciliacao removida da transacao #{id}")
    db.session.commit()
    return jsonify(transaction.to_dict())


@transacoes_bp.route("/api/transacoes/dre")
@nivel_required("admin", "financeiro")
def dre():
    start = _parse_date_safe(request.args.get("inicio"))
    end = _parse_date_safe(request.args.get("fim"))
    query = Transacao.query.filter(Transacao.status == "pago")
    if start:
        query = query.filter(Transacao.data_pagamento >= start)
    if end:
        query = query.filter(Transacao.data_pagamento < end)
    rows = query.all()
    revenues = sum(float(item.valor or 0) for item in rows if item.tipo == "receita")
    expenses_by_category = {}
    for item in rows:
        if item.tipo == "despesa":
            category = item.categoria or "outros"
            expenses_by_category[category] = expenses_by_category.get(category, 0) + float(item.valor or 0)
    expenses = sum(expenses_by_category.values())
    commissions = sum(float(item.comissao_valor or 0) for item in rows if item.tipo == "receita")
    return jsonify({
        "receita_bruta": revenues,
        "despesas_por_categoria": expenses_by_category,
        "despesas": expenses,
        "comissoes": commissions,
        "resultado": round(revenues - expenses - commissions, 2),
    })


@transacoes_bp.route("/api/transacoes/contabilidade.csv")
@nivel_required("admin", "financeiro")
def contabilidade_csv():
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["ID", "Tipo", "Categoria", "Descricao", "Valor", "Vencimento", "Pagamento", "Status", "Conciliacao"])
    for item in Transacao.query.order_by(Transacao.criado_em).all():
        description = str(item.descricao or "")
        if description.startswith(("=", "+", "-", "@", "\t", "\r")):
            description = "'" + description
        writer.writerow([
            item.id, item.tipo, item.categoria or "", description, f"{float(item.valor or 0):.2f}",
            item.data_vencimento.date().isoformat() if item.data_vencimento else "",
            item.data_pagamento.date().isoformat() if item.data_pagamento else "",
            item.status, item.conciliacao_ref or "",
        ])
    return Response(
        "\ufeff" + output.getvalue(), mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=contabilidade.csv", "X-Content-Type-Options": "nosniff"},
    )
