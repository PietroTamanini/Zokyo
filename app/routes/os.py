"""
routes/os.py — CRUD de OS via API JSON.

Fixes:
  - per_page limitado a 200 (evita DoS)
  - prio validada contra whitelist
  - desconto não pode ser maior que total
  - valor_servico e valor_pecas não podem ser negativos
  - datas com try/except em todos os casos
"""
import io
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request, send_file, session
from sqlalchemy import text
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import (
    Cliente,
    OrdemServico,
    OrderSignature,
    OSHistorico,
    Peca,
    ServiceChecklistTemplate,
    StockReservation,
    Transacao,
    Usuario,
    registrar,
)
from app.models.ordem_servico import STATUS_OS
from app.services.billing import assert_limit, assert_write_allowed
from app.services.inventory import cancel_reservation, consume_reservation, record_movement, reserve_stock
from app.services.order_signatures import capture_signature, signature_path
from app.utils.auth import api_login_required, nivel_required
from app.utils.pdf_gen import gerar_pdf_os
from app.utils.request_data import get_request_data
from app.utils.sanitizers import sanitize_text
from app.utils.whatsapp import enviar_whatsapp, mensagem_os_pronta

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
    if not valor:
        return None
    try:
        return datetime.fromisoformat(str(valor)[:10])
    except (ValueError, TypeError):
        return None

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
        if s:
            query = query.filter_by(status=s)
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
@nivel_required("admin", "operacional")
def criar():
    data, _ = get_request_data()
    user = db.session.get(Usuario, session.get("usuario_id"))
    try:
        assert_write_allowed(user.organization_id)
        open_count = OrdemServico.query.filter(
            OrdemServico.deletado_em.is_(None), ~OrdemServico.status.in_(["entregue", "cancelado"]),
        ).count()
        assert_limit(user.organization_id, "max_open_orders", open_count)
    except PermissionError as exc:
        return jsonify({"erro": str(exc)}), 403
    if not data.get("cliente_id"):
        return jsonify({"erro": "cliente_id é obrigatório"}), 400
    if not Cliente.query.filter_by(id=data["cliente_id"]).first():
        return jsonify({"erro": "Cliente não encontrado"}), 404

    warranty_origin = None
    if data.get("warranty_return_of_id"):
        try:
            warranty_origin = OrdemServico.query.filter_by(id=int(data["warranty_return_of_id"])).first()
        except (TypeError, ValueError):
            warranty_origin = None
        if not warranty_origin or warranty_origin.cliente_id != int(data["cliente_id"]):
            return jsonify({"erro": "OS de garantia invalida para este cliente"}), 400

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

    category = sanitize_text(data.get("tipo_aparelho", ""), max_length=100) or "geral"
    checklist_template = ServiceChecklistTemplate.query.filter_by(category=category, active=True).order_by(
        ServiceChecklistTemplate.version.desc(),
    ).first()
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
        warranty_return_of_id=warranty_origin.id if warranty_origin else None,
        checklist_template_id=checklist_template.id if checklist_template else None,
        checklist_snapshot=list(checklist_template.items) if checklist_template else [],
        checklist_answers={},
    )
    db.session.add(os_obj)
    db.session.flush()
    _registrar_historico(os_obj.id, None, os_obj.status, session["usuario_id"])
    db.session.commit()
    return jsonify(os_obj.to_dict()), 201


@os_bp.route("/api/checklists", methods=["GET"])
@nivel_required("admin", "operacional")
def listar_checklists():
    templates = ServiceChecklistTemplate.query.order_by(
        ServiceChecklistTemplate.category, ServiceChecklistTemplate.version.desc(),
    ).all()
    return jsonify([{
        "id": item.id, "categoria": item.category, "versao": item.version,
        "itens": item.items, "ativo": item.active,
    } for item in templates])


@os_bp.route("/api/checklists", methods=["POST"])
@nivel_required("admin")
def criar_checklist():
    data, _ = get_request_data()
    category = sanitize_text(data.get("categoria", ""), max_length=100)
    raw_items = data.get("itens")
    if not category or not isinstance(raw_items, list) or not 1 <= len(raw_items) <= 50:
        return jsonify({"erro": "Categoria e lista de 1 a 50 itens sao obrigatorias"}), 400
    items = [sanitize_text(str(item), max_length=200) for item in raw_items]
    if any(len(item) < 2 for item in items):
        return jsonify({"erro": "Cada item deve ter pelo menos 2 caracteres"}), 400
    previous = ServiceChecklistTemplate.query.filter_by(category=category).order_by(
        ServiceChecklistTemplate.version.desc(),
    ).first()
    for old in ServiceChecklistTemplate.query.filter_by(category=category, active=True).all():
        old.active = False
    template = ServiceChecklistTemplate(
        category=category, version=(previous.version + 1 if previous else 1), items=items,
    )
    db.session.add(template)
    db.session.commit()
    return jsonify({"id": template.id, "categoria": category, "versao": template.version, "itens": items}), 201


@os_bp.route("/api/os/<int:id>/checklist", methods=["PUT"])
@nivel_required("admin", "operacional")
def atualizar_checklist(id):
    order = OrdemServico.query.filter_by(id=id).first_or_404()
    data, _ = get_request_data()
    answers = data.get("respostas")
    if not isinstance(answers, dict):
        return jsonify({"erro": "respostas deve ser um objeto"}), 400
    allowed = set(order.checklist_snapshot or [])
    if set(answers) - allowed or any(value not in (True, False, None) for value in answers.values()):
        return jsonify({"erro": "Respostas de checklist invalidas"}), 400
    order.checklist_answers = {item: answers.get(item) for item in order.checklist_snapshot or []}
    registrar("checklist", "ordens_servico", f"Checklist atualizado na OS #{order.id}")
    db.session.commit()
    return jsonify(order.to_dict())


@os_bp.route("/api/os/<int:id>/autorizacao", methods=["POST"])
@nivel_required("admin", "operacional")
def aceitar_autorizacao(id):
    order = OrdemServico.query.filter_by(id=id).first_or_404()
    data, _ = get_request_data()
    accepted_by = sanitize_text(data.get("aceito_por", ""), max_length=120)
    if data.get("aceito") is not True or len(accepted_by) < 2:
        return jsonify({"erro": "Aceite expresso e nome do responsavel sao obrigatorios"}), 400
    order.authorization_accepted_at = _now()
    order.authorization_accepted_by = accepted_by
    registrar("autorizacao", "ordens_servico", f"Termo aceito na OS #{order.id} por {accepted_by}")
    db.session.commit()
    return jsonify(order.to_dict())


@os_bp.route("/api/os/<int:id>/assinatura", methods=["POST"])
@nivel_required("admin", "operacional")
def capturar_assinatura(id):
    order = OrdemServico.query.filter_by(id=id).first_or_404()
    uploaded = request.files.get("assinatura")
    if not uploaded:
        return jsonify({"erro": "Arquivo de assinatura e obrigatorio"}), 400
    try:
        signature = capture_signature(
            order, session["usuario_id"], request.form.get("signatario"), uploaded, request.remote_addr,
        )
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    registrar("assinatura", "ordens_servico", f"Assinatura capturada na OS #{order.id}")
    db.session.commit()
    return jsonify({"id": signature.id, "sha256": signature.sha256, "signatario": signature.signer_name}), 201


@os_bp.route("/api/os/<int:id>/assinatura")
@api_login_required
def baixar_assinatura(id):
    signature = OrderSignature.query.filter_by(order_id=id, revoked_at=None).order_by(
        OrderSignature.created_at.desc(),
    ).first_or_404()
    try:
        path = signature_path(signature)
    except FileNotFoundError:
        return jsonify({"erro": "Assinatura nao encontrada"}), 404
    return send_file(path, mimetype="image/png", as_attachment=False, download_name=f"assinatura-os-{id}.png")


# ── ATUALIZAR ─────────────────────────────────────────────────
@os_bp.route("/api/os/<int:id>", methods=["PUT"])
@nivel_required("admin", "operacional")
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
@nivel_required("admin", "operacional")
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
    own_reservation = StockReservation.query.filter_by(
        part_id=peca.id, order_id=os_obj.id, status="active",
    ).first()
    available_for_order = peca.quantidade_disponivel + (own_reservation.quantity if own_reservation else 0)

    if existing:
        diff = quantidade - existing.quantidade
        if diff > 0 and available_for_order < diff:
            return jsonify({
                "erro": f"Estoque insuficiente. Disponível: {peca.quantidade}"}), 400
        before = peca.quantidade
        peca.quantidade -= diff
        if diff:
            record_movement(
                peca, session["usuario_id"], "order_consumption" if diff > 0 else "order_return",
                before, peca.quantidade, f"Alteracao de pecas da OS #{os_obj.id}", order_id=os_obj.id,
            )
        if diff > 0:
            consume_reservation(peca.id, os_obj.id, diff)
        db.session.execute(
            text("UPDATE os_pecas SET quantidade=:q, valor_unitario=:v "
                 "WHERE os_id=:o AND peca_id=:p"),
            {"q": quantidade, "v": valor_unitario,
             "o": os_obj.id, "p": peca_id},
        )
    else:
        if available_for_order < quantidade:
            return jsonify({
                "erro": f"Estoque insuficiente. Disponível: {peca.quantidade}"}), 400
        before = peca.quantidade
        peca.quantidade -= quantidade
        record_movement(
            peca, session["usuario_id"], "order_consumption", before, peca.quantidade,
            f"Consumo na OS #{os_obj.id}", order_id=os_obj.id,
        )
        consume_reservation(peca.id, os_obj.id, quantidade)
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
@nivel_required("admin", "operacional")
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
        if peca:
            before = peca.quantidade
            peca.quantidade += old_row.quantidade
            record_movement(
                peca, session["usuario_id"], "order_return", before, peca.quantidade,
                f"Remocao da OS #{os_obj.id}", order_id=os_obj.id,
            )

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


@os_bp.route("/api/os/<int:id>/reservas", methods=["POST"])
@nivel_required("admin", "operacional")
def reservar_peca(id):
    os_obj = OrdemServico.query.filter_by(id=id).filter(OrdemServico.deletado_em.is_(None)).first_or_404()
    data, _ = get_request_data()
    try:
        part_id = int(data.get("peca_id"))
        quantity = int(data.get("quantidade"))
    except (TypeError, ValueError):
        return jsonify({"erro": "peca_id e quantidade devem ser inteiros"}), 400
    part = Peca.query.filter_by(id=part_id).first_or_404()
    try:
        reservation = reserve_stock(part, os_obj, session["usuario_id"], quantity)
    except ValueError as exc:
        return jsonify({"erro": str(exc)}), 400
    db.session.commit()
    return jsonify({
        "id": reservation.id, "peca_id": reservation.part_id,
        "os_id": reservation.order_id, "quantidade": reservation.quantity,
        "status": reservation.status,
    }), 201


@os_bp.route("/api/os/<int:id>/reservas/<int:reservation_id>", methods=["DELETE"])
@nivel_required("admin", "operacional")
def cancelar_reserva(id, reservation_id):
    reservation = StockReservation.query.filter_by(
        id=reservation_id, order_id=id, status="active",
    ).first_or_404()
    cancel_reservation(reservation)
    db.session.commit()
    return jsonify({"success": True})


# ── PDF ───────────────────────────────────────────────────────
@os_bp.route("/api/os/<int:id>/pdf", methods=["GET"])
@api_login_required
def pdf(id):
    os_obj = (OrdemServico.query.filter_by(id=id)
              .filter(OrdemServico.deletado_em.is_(None))
              .first_or_404())
    try:
        pdf_bytes = gerar_pdf_os(os_obj)
    except RuntimeError as exc:
        return jsonify({"erro": str(exc)}), 500
    return send_file(
        io.BytesIO(pdf_bytes), mimetype="application/pdf",
        as_attachment=True, download_name=f"OS_{os_obj.id:04d}.pdf",
    )


# ── WHATSAPP ──────────────────────────────────────────────────
@os_bp.route("/api/os/<int:id>/whatsapp", methods=["POST"])
@nivel_required("admin", "operacional")
def whatsapp(id):
    os_obj = (OrdemServico.query.filter_by(id=id)
              .filter(OrdemServico.deletado_em.is_(None))
              .first_or_404())
    if not os_obj.cliente or not os_obj.cliente.telefone:
        return jsonify({"erro": "Cliente sem telefone cadastrado."}), 400
    resultado = enviar_whatsapp(
        os_obj.cliente.telefone, mensagem_os_pronta(os_obj))
    return jsonify(resultado), 200
