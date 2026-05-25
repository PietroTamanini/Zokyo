"""
routes/os.py — CRUD de OS via API JSON.

Fixes:
  - per_page limitado a 200 (evita DoS)
  - prio validada contra whitelist
  - desconto não pode ser maior que total
  - valor_servico e valor_pecas não podem ser negativos
  - datas com try/except em todos os casos
"""
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, send_file, session
import io

from sqlalchemy.orm import joinedload
from sqlalchemy import text

from app.extensions import db
from app.models import OrdemServico, Cliente, Peca, OSHistorico, Transacao
from app.models.ordem_servico import STATUS_OS
from app.utils.auth import api_login_required, nivel_required
from app.utils.whatsapp import enviar_whatsapp, mensagem_os_pronta
from app.utils.pdf_gen import gerar_pdf_os
from app.utils.request_data import get_request_data
from app.utils.sanitizers import sanitize_text

os_bp = Blueprint("os", __name__)

PRIOS_VALIDAS = {"normal", "urgente", "critico"}

_STATUS_ALIAS = {
    "analise":   "em_analise",
    "aprovacao": "aguardando_aprovacao",
    "reparo":    "em_reparo",
}

def _normalizar_status(raw: str) -> str | None:
    if not raw:
        return None
    s = raw.strip().lower()
    if s in STATUS_OS:
        return s
    return _STATUS_ALIAS.get(s)

def _now(): return datetime.now(timezone.utc)

def _parse_date(valor):
    if not valor: return None
    try:    return datetime.fromisoformat(str(valor)[:10])
    except: return None

def _registrar_historico(os_id, anterior, novo, usuario_id):
    db.session.add(OSHistorico(
        os_id=os_id, usuario_id=usuario_id,
        status_anterior=anterior, status_novo=novo,
    ))


# ── LISTAR ────────────────────────────────────────────────────
@os_bp.route("/api/os", methods=["GET"])
@api_login_required
def listar():
    status     = request.args.get("status")
    cliente_id = request.args.get("cliente_id", type=int)
    page       = request.args.get("page", 1, type=int)
    # FIX: limitar per_page para evitar DoS
    per_page   = min(request.args.get("per_page", 50, type=int), 200)

    query = (OrdemServico.query
             .options(joinedload(OrdemServico.cliente))
             .filter(OrdemServico.deletado_em.is_(None)))
    if status:
        s = _normalizar_status(status)
        if s: query = query.filter_by(status=s)
    if cliente_id:
        query = query.filter_by(cliente_id=cliente_id)

    pag = query.order_by(
        OrdemServico.data_entrada.desc()).paginate(
        page=page, per_page=per_page, error_out=False)

    return jsonify({
        "items":    [o.to_dict() for o in pag.items],
        "total":    pag.total,
        "page":     pag.page,
        "pages":    pag.pages,
        "per_page": pag.per_page,
    })


# ── OBTER ─────────────────────────────────────────────────────
@os_bp.route("/api/os/<int:id>", methods=["GET"])
@api_login_required
def obter(id):
    os_obj = (OrdemServico.query.filter_by(id=id)
              .filter(OrdemServico.deletado_em.is_(None))
              .first_or_404())
    return jsonify(os_obj.to_dict())


# ── CRIAR ─────────────────────────────────────────────────────
@os_bp.route("/api/os", methods=["POST"])
@api_login_required
def criar():
    data, _ = get_request_data()
    if not data.get("cliente_id"):
        return jsonify({"erro": "cliente_id é obrigatório"}), 400
    if not Cliente.query.filter_by(id=data["cliente_id"]).first():
        return jsonify({"erro": "Cliente não encontrado"}), 404

    status_final = _normalizar_status(
        data.get("status", "recepcao")) or "recepcao"

    try:
        valor_servico = float(data.get("valor_servico") or 0)
        valor_pecas   = float(data.get("valor_pecas")   or 0)
        desconto      = float(data.get("desconto")      or 0)
        garantia_dias = int(data.get("garantia_dias")   or 90)
    except (ValueError, TypeError):
        return jsonify({"erro": "Campos numéricos inválidos"}), 400

    # FIX: valores não podem ser negativos
    if valor_servico < 0 or valor_pecas < 0 or desconto < 0:
        return jsonify({"erro": "Valores financeiros não podem ser negativos"}), 400

    # FIX: desconto não pode ser maior que total
    total = valor_servico + valor_pecas
    if desconto > total:
        return jsonify({"erro": "Desconto não pode ser maior que o total"}), 400

    # FIX: validar prio
    prio = data.get("prio", "normal")
    if prio not in PRIOS_VALIDAS:
        return jsonify({"erro": f"prio inválida. Use: {', '.join(PRIOS_VALIDAS)}"}), 400

    # FIX: validar tamanho máximo dos campos de texto
    MAX_TEXT = 5000
    for campo in ("defeito_alegado", "defeito_encontrado", "solucao", "observacoes"):
        val = data.get(campo)
        if val and len(str(val)) > MAX_TEXT:
            return jsonify({"erro": f"{campo} excede {MAX_TEXT} caracteres"}), 400

    os_obj = OrdemServico(
        cliente_id=data["cliente_id"],
        usuario_id=session["usuario_id"],
        tipo_aparelho=sanitize_text(data.get("tipo_aparelho", ""), max_length=100) or None,
        marca=sanitize_text(data.get("marca", ""), max_length=100) or None,
        modelo=sanitize_text(data.get("modelo", ""), max_length=100) or None,
        numero_serie=sanitize_text(data.get("numero_serie", ""), max_length=100) or None,
        defeito_alegado=sanitize_text(data.get("defeito_alegado", ""), max_length=5000) or None,
        defeito_encontrado=sanitize_text(data.get("defeito_encontrado", ""), max_length=5000) or None,
        solucao=sanitize_text(data.get("solucao", ""), max_length=5000) or None,
        observacoes=sanitize_text(data.get("observacoes", ""), max_length=5000) or None,
        valor_servico=valor_servico,
        valor_pecas=valor_pecas,
        desconto=desconto,
        status=status_final,
        prio=prio,
        tecnico_nome=sanitize_text(data.get("tecnico_nome", ""), max_length=120) or None,
        garantia_dias=garantia_dias,
        data_entrada=_parse_date(data.get("data_entrada")) or _now(),
        data_saida=_parse_date(data.get("data_saida")),
        data_prev=_parse_date(data.get("data_prev")),
    )
    db.session.add(os_obj)
    db.session.flush()
    _registrar_historico(os_obj.id, None, os_obj.status, session["usuario_id"])
    db.session.commit()
    return jsonify(os_obj.to_dict()), 201


# ── ATUALIZAR ─────────────────────────────────────────────────
@os_bp.route("/api/os/<int:id>", methods=["PUT"])
@api_login_required
def atualizar(id):
    os_obj = (OrdemServico.query.filter_by(id=id)
              .filter(OrdemServico.deletado_em.is_(None))
              .first_or_404())
    data, _ = get_request_data()
    status_anterior = os_obj.status

    _CAMPOS_CURTOS = ("tipo_aparelho", "marca", "modelo", "numero_serie", "tecnico_nome")
    _CAMPOS_LONGOS = ("defeito_alegado", "defeito_encontrado", "solucao", "observacoes")
    for campo in _CAMPOS_CURTOS:
        if campo in data:
            setattr(os_obj, campo, sanitize_text(data[campo], max_length=120) or None)
    for campo in _CAMPOS_LONGOS:
        if campo in data:
            setattr(os_obj, campo, sanitize_text(data[campo], max_length=5000) or None)

    # FIX: validar prio
    if "prio" in data:
        if data["prio"] not in PRIOS_VALIDAS:
            return jsonify({"erro": f"prio inválida. Use: {', '.join(PRIOS_VALIDAS)}"}), 400
        os_obj.prio = data["prio"]

    # FIX: validar valores numéricos e não negativos
    for campo_num, tp in (
        ("valor_servico", float), ("desconto", float),
        ("garantia_dias", int),   ("valor_pecas", float),
    ):
        if campo_num in data:
            try:
                val = tp(data[campo_num])
            except (ValueError, TypeError):
                return jsonify({"erro": f"{campo_num} deve ser numérico"}), 400
            if campo_num != "garantia_dias" and val < 0:
                return jsonify({"erro": f"{campo_num} não pode ser negativo"}), 400
            setattr(os_obj, campo_num, val)

    # FIX: desconto não pode ser maior que total após atualização
    total = float(os_obj.valor_servico or 0) + float(os_obj.valor_pecas or 0)
    if float(os_obj.desconto or 0) > total:
        return jsonify({"erro": "Desconto não pode ser maior que o total"}), 400

    novo_status_raw = data.get("status")
    if novo_status_raw:
        novo_status = _normalizar_status(novo_status_raw)
        if not novo_status:
            return jsonify({"erro": f"Status inválido: {novo_status_raw}"}), 400
        os_obj.status = novo_status

        if novo_status == "entregue" and not os_obj.data_saida:
            os_obj.data_saida = _now()

        if novo_status == "entregue" and status_anterior != "entregue":
            if not Transacao.query.filter_by(
                    os_id=os_obj.id, tipo="receita").first():
                db.session.add(Transacao(
                    os_id=os_obj.id, tipo="receita", categoria="Serviços OS",
                    descricao=f"OS #{os_obj.id:04d}",
                    valor=os_obj.valor_total, status="pago",
                    data_vencimento=_now(), data_pagamento=_now(),
                ))

        if novo_status != status_anterior:
            _registrar_historico(
                os_obj.id, status_anterior, novo_status, session["usuario_id"])

    db.session.commit()
    return jsonify(os_obj.to_dict())


# ── DELETAR (soft) ────────────────────────────────────────────
@os_bp.route("/api/os/<int:id>", methods=["DELETE"])
@nivel_required("admin")
def deletar(id):
    os_obj = (OrdemServico.query.filter_by(id=id)
              .filter(OrdemServico.deletado_em.is_(None))
              .first_or_404())
    os_obj.deletado_em = _now()
    db.session.commit()
    return jsonify({"mensagem": "OS removida"})


# ── PEÇAS ─────────────────────────────────────────────────────
@os_bp.route("/api/os/<int:id>/pecas", methods=["POST"])
@api_login_required
def adicionar_peca(id):
    os_obj = (OrdemServico.query.filter_by(id=id)
              .filter(OrdemServico.deletado_em.is_(None))
              .first_or_404())
    data, _ = get_request_data()
    peca_id = data.get("peca_id")
    if not peca_id:
        return jsonify({"erro": "peca_id é obrigatório"}), 400

    try:
        quantidade     = int(data.get("quantidade", 1))
        valor_unitario = float(data.get("valor_unitario", 0))
    except (ValueError, TypeError):
        return jsonify({"erro": "quantidade e valor_unitario devem ser numéricos"}), 400
    if quantidade <= 0:
        return jsonify({"erro": "quantidade deve ser maior que zero"}), 400
    if valor_unitario < 0:
        return jsonify({"erro": "valor_unitario não pode ser negativo"}), 400

    peca = Peca.query.filter_by(id=peca_id).first()
    if not peca:
        return jsonify({"erro": "Peça não encontrada"}), 404

    existing = db.session.execute(
        text("SELECT quantidade FROM os_pecas WHERE os_id=:o AND peca_id=:p"),
        {"o": os_obj.id, "p": peca_id},
    ).fetchone()

    if existing:
        diff = quantidade - existing.quantidade
        if diff > 0 and peca.quantidade < diff:
            return jsonify({
                "erro": f"Estoque insuficiente. Disponível: {peca.quantidade}"}), 400
        peca.quantidade -= diff
        db.session.execute(
            text("UPDATE os_pecas SET quantidade=:q, valor_unitario=:v "
                 "WHERE os_id=:o AND peca_id=:p"),
            {"q": quantidade, "v": valor_unitario,
             "o": os_obj.id, "p": peca_id},
        )
    else:
        if peca.quantidade < quantidade:
            return jsonify({
                "erro": f"Estoque insuficiente. Disponível: {peca.quantidade}"}), 400
        peca.quantidade -= quantidade
        db.session.execute(
            text("INSERT INTO os_pecas (os_id,peca_id,quantidade,valor_unitario) "
                 "VALUES (:o,:p,:q,:v)"),
            {"o": os_obj.id, "p": peca_id,
             "q": quantidade, "v": valor_unitario},
        )

    total_pecas = db.session.execute(
        text("SELECT COALESCE(SUM(quantidade*valor_unitario),0) "
             "FROM os_pecas WHERE os_id=:o"),
        {"o": os_obj.id},
    ).scalar()
    os_obj.valor_pecas = total_pecas
    db.session.commit()
    return jsonify(os_obj.to_dict()), 200


@os_bp.route("/api/os/<int:id>/pecas/<int:peca_id>", methods=["DELETE"])
@api_login_required
def remover_peca(id, peca_id):
    os_obj = (OrdemServico.query.filter_by(id=id)
              .filter(OrdemServico.deletado_em.is_(None))
              .first_or_404())
    old_row = db.session.execute(
        text("SELECT quantidade FROM os_pecas WHERE os_id=:o AND peca_id=:p"),
        {"o": os_obj.id, "p": peca_id},
    ).fetchone()
    if old_row:
        peca = db.session.get(Peca, peca_id)
        if peca: peca.quantidade += old_row.quantidade

    db.session.execute(
        text("DELETE FROM os_pecas WHERE os_id=:o AND peca_id=:p"),
        {"o": os_obj.id, "p": peca_id},
    )
    total_pecas = db.session.execute(
        text("SELECT COALESCE(SUM(quantidade*valor_unitario),0) "
             "FROM os_pecas WHERE os_id=:o"),
        {"o": os_obj.id},
    ).scalar()
    os_obj.valor_pecas = total_pecas
    db.session.commit()
    return jsonify(os_obj.to_dict()), 200


# ── PDF ───────────────────────────────────────────────────────
@os_bp.route("/api/os/<int:id>/pdf", methods=["GET"])
@api_login_required
def pdf(id):
    os_obj = (OrdemServico.query.filter_by(id=id)
              .filter(OrdemServico.deletado_em.is_(None))
              .first_or_404())
    try:    pdf_bytes = gerar_pdf_os(os_obj)
    except RuntimeError as exc:
        return jsonify({"erro": str(exc)}), 500
    return send_file(
        io.BytesIO(pdf_bytes), mimetype="application/pdf",
        as_attachment=True, download_name=f"OS_{os_obj.id:04d}.pdf",
    )


# ── WHATSAPP ──────────────────────────────────────────────────
@os_bp.route("/api/os/<int:id>/whatsapp", methods=["POST"])
@api_login_required
def whatsapp(id):
    os_obj = (OrdemServico.query.filter_by(id=id)
              .filter(OrdemServico.deletado_em.is_(None))
              .first_or_404())
    if not os_obj.cliente or not os_obj.cliente.telefone:
        return jsonify({"erro": "Cliente sem telefone cadastrado."}), 400
    resultado = enviar_whatsapp(
        os_obj.cliente.telefone, mensagem_os_pronta(os_obj))
    return jsonify(resultado), 200
