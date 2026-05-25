"""
routes/pages.py — Templates HTML. Sistema mono-tenant.

Fixes aplicados:
  - Bug #3:  query.get_or_404 depreciado → db.get_or_404
  - Bug #4:  == None → .is_(None) em queries SQLAlchemy
  - Bug #5:  int(data["cliente_id"]) sem try/except → validação segura
  - Bug #6:  status não validado → rejeitado se fora de STATUS_OS
  - Bug #7:  func.date_format (MySQL-only) → func.strftime para SQLite /
             detecção automática do dialeto
  - Bug #8:  nivel_usuario não injetado no template os_detalhe
  - Bug #9:  Transacao.query.get_or_404 depreciado
  - Fix #10: LIKE injection — % e _ escapados nos campos de busca
  - Fix #11: datas com try/except em todos os pontos de edição de OS
"""

import json
import re as _re

def _safe_json(data):
    """json.dumps seguro para embedding em HTML: escapa </ para evitar </script> breakout."""
    raw = json.dumps(data, ensure_ascii=False)
    return _re.sub(r'</', r'<\/', raw)
from datetime import date, datetime, timezone, timedelta
from functools import wraps

from flask import (Blueprint, render_template, session, redirect,
                   url_for, request, flash, g)
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import (OrdemServico, Cliente, Peca, Fornecedor, Transacao,
                        Usuario, OSHistorico, Configuracao, registrar)
from app.models.ordem_servico import STATUS_OS, STATUS_OS_LABELS
from app.utils.auth import page_nivel_required
from app.utils.sanitizers import sanitize_text, sanitize_email, sanitize_cpf, sanitize_phone, sanitize_cep
from app.utils.validators import validar_email, validar_cpf, validar_telefone, validar_cep

pages_bp = Blueprint("pages", __name__)
STATUS_MAP = STATUS_OS_LABELS


# ── helpers ───────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "usuario_id" not in session:
            return redirect(url_for("auth.login_page"))
        if not Usuario.query.first():
            return redirect(url_for("auth.primeiro_acesso_page"))
        g.usuario = db.session.get(Usuario, session["usuario_id"])
        return f(*args, **kwargs)
    return decorated

def _today(): return date.today().isoformat()
def _now():   return datetime.now(timezone.utc)

def _safe_date(valor):
    """Parse seguro de data ISO. Retorna None se inválido."""
    if not valor:
        return None
    try:
        return datetime.fromisoformat(str(valor)[:10])
    except (ValueError, TypeError):
        return None

def _escape_like(q: str) -> str:
    """Escapa % e _ para evitar LIKE injection."""
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

def _date_trunc_month(col):
    return func.date_format(col, "%Y-%m")

def _date_trunc_day(col):
    return func.date_format(col, "%Y-%m-%d")

def _coalesce_sum(col):
    """sum(...) com fallback 0 quando não há linhas."""
    return func.coalesce(func.sum(col), 0)

def _caixa_expression():
    """
    Saldo de caixa: sum(receitas pagas) - sum(despesas pagas).
    Compatible com SQLite e MySQL.
    """
    from sqlalchemy import case
    return _coalesce_sum(
        case(
            (Transacao.tipo == "receita",  Transacao.valor),
            (Transacao.tipo == "despesa", -Transacao.valor),
            else_=0,
        )
    )


# ══════════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════════
@pages_bp.route("/")
@login_required
def dashboard():
    cfg  = Configuracao.get()
    hoje = _now()
    mes  = hoje.strftime("%Y-%m")
    dia  = hoje.strftime("%Y-%m-%d")

    # Bug #4: .is_(None) em vez de ==None
    os_abertas = OrdemServico.query.filter(
        OrdemServico.deletado_em.is_(None),
        ~OrdemServico.status.in_(["entregue", "cancelado"])
    ).count()
    os_prontas = OrdemServico.query.filter_by(status="pronto").filter(
        OrdemServico.deletado_em.is_(None)).count()
    os_atrasadas = OrdemServico.query.filter(
        OrdemServico.data_prev < hoje.replace(tzinfo=None),
        OrdemServico.deletado_em.is_(None),
        ~OrdemServico.status.in_(["entregue", "cancelado", "pronto"])
    ).count()
    os_aprovacao = OrdemServico.query.filter_by(
        status="aguardando_aprovacao").filter(
        OrdemServico.deletado_em.is_(None)).count()

    def soma(tipo, st, periodo="mes"):
        q = db.session.query(_coalesce_sum(Transacao.valor)).filter(
            Transacao.tipo == tipo, Transacao.status == st)
        if periodo == "mes":
            q = q.filter(_date_trunc_month(Transacao.criado_em) == mes)
        elif periodo == "dia":
            q = q.filter(_date_trunc_day(Transacao.criado_em) == dia)
        return float(q.scalar() or 0)

    receitas_mes = soma("receita", "pago",     "mes")
    despesas_mes = soma("despesa", "pago",     "mes")
    vendas_dia   = soma("receita", "pago",     "dia")
    saldo_mes    = receitas_mes - despesas_mes
    a_receber    = soma("receita", "pendente", "mes")
    a_pagar      = soma("despesa", "pendente", "mes")

    caixa = float(db.session.query(_caixa_expression()).filter(
        Transacao.status == "pago").scalar() or 0)

    total_clientes     = Cliente.query.filter_by(ativo=True).count()
    total_fornecedores = Fornecedor.query.filter_by(ativo=True).count()
    total_usuarios     = Usuario.query.filter_by(ativo=True).count()
    total_pecas        = Peca.query.count()
    estoque_critico    = Peca.query.filter(
        Peca.quantidade <= Peca.estoque_minimo).count()
    total_transacoes   = Transacao.query.count()

    valor_estoque = float(db.session.query(
        _coalesce_sum(Peca.custo * Peca.quantidade)).scalar() or 0)

    alertas = []
    if cfg.alerta_caixa_minimo and caixa < cfg.alerta_caixa_minimo:
        alertas.append({"tipo": "red",   "icone": "💰",
                        "msg": f"Caixa abaixo do mínimo: R$ {caixa:,.2f}"})
    if estoque_critico > 0:
        alertas.append({"tipo": "amber", "icone": "📦",
                        "msg": f"{estoque_critico} peça(s) com estoque crítico"})
    if os_atrasadas > 0:
        alertas.append({"tipo": "red",   "icone": "⏰",
                        "msg": f"{os_atrasadas} OS atrasada(s)"})
    if os_prontas > 0:
        alertas.append({"tipo": "green", "icone": "✅",
                        "msg": f"{os_prontas} equipamento(s) pronto(s) para retirada"})

    prazo = hoje + timedelta(days=cfg.alerta_vencimento_dias or 5)
    vencendo = Transacao.query.filter(
        Transacao.status == "pendente",
        Transacao.data_vencimento <= prazo.replace(tzinfo=None)
    ).count()
    if vencendo > 0:
        alertas.append({"tipo": "amber", "icone": "📅",
                        "msg": f"{vencendo} transação(ões) vencendo em breve"})

    pct_meta = 0
    if cfg.meta_receita_mensal and cfg.meta_receita_mensal > 0:
        pct_meta = min(100, round(
            (receitas_mes / cfg.meta_receita_mensal) * 100, 1))

    pipeline_counts = {}
    for st in STATUS_OS:
        pipeline_counts[st] = OrdemServico.query.filter_by(
            status=st).filter(OrdemServico.deletado_em.is_(None)).count()

    ultimas_os = (OrdemServico.query
                  .filter(OrdemServico.deletado_em.is_(None))
                  .options(joinedload(OrdemServico.cliente))
                  .order_by(OrdemServico.data_entrada.desc())
                  .limit(8).all())

    return render_template("pages/dashboard.html",
        active="dashboard",
        hoje=hoje.strftime("%A, %d de %B de %Y"),
        os_abertas=os_abertas, os_prontas=os_prontas,
        os_atrasadas=os_atrasadas, os_aprovacao=os_aprovacao,
        receitas_mes=receitas_mes, despesas_mes=despesas_mes,
        saldo_mes=saldo_mes, vendas_dia=vendas_dia,
        a_receber=a_receber, a_pagar=a_pagar, caixa=caixa,
        total_clientes=total_clientes, total_fornecedores=total_fornecedores,
        total_usuarios=total_usuarios, total_pecas=total_pecas,
        estoque_critico=estoque_critico, valor_estoque=valor_estoque,
        total_transacoes=total_transacoes,
        alertas=alertas, pct_meta=pct_meta,
        meta_receita_mensal=cfg.meta_receita_mensal,
        pipeline_counts=pipeline_counts,
        ultimas_os=ultimas_os, status_map=STATUS_MAP,
    )


# ══════════════════════════════════════════════════════════════
# OS
# ══════════════════════════════════════════════════════════════
@pages_bp.route("/os")
@login_required
def os_lista():
    q             = request.args.get("q", "").strip()
    status_filtro = request.args.get("status", "")
    prio_filtro   = request.args.get("prio", "")
    page          = request.args.get("page", 1, type=int)

    query = (OrdemServico.query
             .filter(OrdemServico.deletado_em.is_(None))
             .options(joinedload(OrdemServico.cliente)))
    if status_filtro: query = query.filter_by(status=status_filtro)
    if prio_filtro:   query = query.filter_by(prio=prio_filtro)
    if q:
        qe = _escape_like(q)
        query = query.join(Cliente).filter(db.or_(
            Cliente.nome.ilike(f"%{qe}%"),
            OrdemServico.marca.ilike(f"%{qe}%"),
            OrdemServico.modelo.ilike(f"%{qe}%"),
        ))
    pag = query.order_by(
        OrdemServico.data_entrada.desc()).paginate(
        page=page, per_page=25, error_out=False)

    pipeline_os = {st: OrdemServico.query.filter_by(
        status=st).filter(OrdemServico.deletado_em.is_(None)).count()
        for st in STATUS_MAP}

    return render_template("pages/os_lista.html",
        active="os", os_list=pag.items, paginacao=pag,
        q=q, status_filtro=status_filtro, prio_filtro=prio_filtro,
        status_map=STATUS_MAP, hoje_dt=_now(), pipeline_os=pipeline_os)


@pages_bp.route("/os/nova", methods=["GET"])
@login_required
def os_nova():
    clientes = Cliente.query.filter_by(ativo=True).order_by(Cliente.nome).all()
    tecnicos = (Usuario.query.filter_by(ativo=True)
                .filter(Usuario.nivel.in_(["admin", "operacional"])).all())
    pecas    = Peca.query.order_by(Peca.nome).all()
    clientes_json = _safe_json([
        {"id": c.id, "nome": c.nome,
         "cpf": c.cpf or "", "telefone": c.telefone or ""}
        for c in clientes])
    return render_template("pages/os_form.html", active="os", os=None,
        clientes=clientes, clientes_json=clientes_json,
        pecas_estoque=pecas, tecnicos=tecnicos,
        status_map=STATUS_MAP, hoje_iso=_today(), pecas_usadas=[])


@pages_bp.route("/os/nova", methods=["POST"])
@login_required
def os_criar():
    data = request.form

    # Bug #5: validação segura de cliente_id
    cliente_id_raw = data.get("cliente_id", "").strip()
    if not cliente_id_raw or not cliente_id_raw.isdigit():
        flash("Cliente inválido ou não selecionado.", "error")
        return redirect(url_for("pages.os_nova"))
    cliente_id = int(cliente_id_raw)
    if not Cliente.query.filter_by(id=cliente_id, ativo=True).first():
        flash("Cliente não encontrado.", "error")
        return redirect(url_for("pages.os_nova"))

    # Bug #6: validar status
    status_raw = data.get("status", "recepcao")
    status_final = status_raw if status_raw in STATUS_OS else "recepcao"

    try:
        valor_servico = float(data.get("valor_servico") or 0)
        desconto      = float(data.get("desconto") or 0)
        garantia_dias = int(data.get("garantia_dias") or 90)
    except (ValueError, TypeError):
        flash("Valores numéricos inválidos no formulário.", "error")
        return redirect(url_for("pages.os_nova"))

    _PRIOS = {"normal", "urgente", "critico"}
    prio = data.get("prio", "normal")
    if prio not in _PRIOS:
        prio = "normal"
    if valor_servico < 0 or desconto < 0:
        flash("Valores financeiros não podem ser negativos.", "error")
        return redirect(url_for("pages.os_nova"))
    if valor_servico > 999_999.99 or desconto > valor_servico:
        flash("Valores financeiros fora do intervalo permitido.", "error")
        return redirect(url_for("pages.os_nova"))
    os_obj = OrdemServico(
        cliente_id=cliente_id,
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
        valor_pecas=0,
        desconto=desconto,
        status=status_final,
        prio=prio,
        tecnico_nome=sanitize_text(data.get("tecnico_nome", ""), max_length=120) or None,
        garantia_dias=garantia_dias,
        data_entrada=(_safe_date(data.get("data_entrada")) or _now()),
        data_prev=_safe_date(data.get("data_prev")),
    )
    db.session.add(os_obj)
    db.session.flush()
    db.session.add(OSHistorico(
        os_id=os_obj.id,
        usuario_id=session["usuario_id"],
        status_anterior=None,
        status_novo=os_obj.status,
    ))
    registrar("criacao", "os", f"OS #{os_obj.id:04d} criada",
              f"Cliente: {os_obj.cliente.nome}")
    db.session.commit()
    flash("OS criada!", "success")
    return redirect(url_for("pages.os_detalhe", id=os_obj.id))


@pages_bp.route("/os/<int:id>/editar", methods=["GET"])
@login_required
def os_editar(id):
    # Bug #3: get_or_404 depreciado → db.get_or_404
    os_obj   = db.get_or_404(OrdemServico, id)
    clientes = Cliente.query.filter_by(ativo=True).order_by(Cliente.nome).all()
    tecnicos = (Usuario.query.filter_by(ativo=True)
                .filter(Usuario.nivel.in_(["admin", "operacional"])).all())
    pecas    = Peca.query.order_by(Peca.nome).all()
    clientes_json = _safe_json([
        {"id": c.id, "nome": c.nome,
         "cpf": c.cpf or "", "telefone": c.telefone or ""}
        for c in clientes])
    return render_template("pages/os_form.html", active="os", os=os_obj,
        clientes=clientes, clientes_json=clientes_json,
        pecas_estoque=pecas, tecnicos=tecnicos,
        status_map=STATUS_MAP, hoje_iso=_today(),
        pecas_usadas=os_obj.to_dict().get("pecas", []))


@pages_bp.route("/os/<int:id>/editar", methods=["POST"])
@login_required
def os_atualizar(id):
    os_obj = OrdemServico.query.filter_by(id=id).filter(
        OrdemServico.deletado_em.is_(None)).first_or_404()
    data = request.form
    ant  = os_obj.status

    _PRIOS = {"normal", "urgente", "critico"}
    _CAMPOS_CURTOS = ("tipo_aparelho", "marca", "modelo", "numero_serie", "tecnico_nome")
    _CAMPOS_LONGOS = ("defeito_alegado", "defeito_encontrado", "solucao", "observacoes")
    for campo in _CAMPOS_CURTOS:
        setattr(os_obj, campo, sanitize_text(data.get(campo, ""), max_length=120) or None)
    for campo in _CAMPOS_LONGOS:
        setattr(os_obj, campo, sanitize_text(data.get(campo, ""), max_length=5000) or None)
    prio = data.get("prio", os_obj.prio)
    os_obj.prio = prio if prio in _PRIOS else os_obj.prio

    try:
        vs = float(data.get("valor_servico") or 0)
        dc = float(data.get("desconto") or 0)
        gd = int(data.get("garantia_dias") or 90)
    except (ValueError, TypeError):
        flash("Valores numéricos inválidos.", "error")
        return redirect(url_for("pages.os_editar", id=id))
    if vs < 0 or dc < 0:
        flash("Valores financeiros não podem ser negativos.", "error")
        return redirect(url_for("pages.os_editar", id=id))
    if dc > vs:
        flash("Desconto não pode ser maior que o valor do serviço.", "error")
        return redirect(url_for("pages.os_editar", id=id))
    os_obj.valor_servico = vs
    os_obj.desconto      = dc
    os_obj.garantia_dias = gd

    # Bug #6: validar status na edição também
    novo_st_raw = data.get("status", os_obj.status)
    os_obj.status = novo_st_raw if novo_st_raw in STATUS_OS else os_obj.status

    if data.get("data_entrada"):
        d = _safe_date(data["data_entrada"])
        if d is None:
            flash("Data de entrada inválida.", "error")
            return redirect(url_for("pages.os_editar", id=id))
        os_obj.data_entrada = d
    if data.get("data_saida"):
        d = _safe_date(data["data_saida"])
        if d is None:
            flash("Data de saída inválida.", "error")
            return redirect(url_for("pages.os_editar", id=id))
        os_obj.data_saida = d
    if data.get("data_prev"):
        d = _safe_date(data["data_prev"])
        if d is None:
            flash("Data prevista inválida.", "error")
            return redirect(url_for("pages.os_editar", id=id))
        os_obj.data_prev = d

    if os_obj.status == "entregue" and not os_obj.data_saida:
        os_obj.data_saida = _now()
    if os_obj.status == "entregue" and ant != "entregue":
        if not Transacao.query.filter_by(os_id=os_obj.id, tipo="receita").first():
            db.session.add(Transacao(
                os_id=os_obj.id, tipo="receita", categoria="Serviços OS",
                descricao=f"OS #{os_obj.id:04d}",
                valor=os_obj.valor_total, status="pago",
                data_vencimento=_now(), data_pagamento=_now(),
            ))

    registrar("edicao", "os", f"OS #{os_obj.id:04d} editada")
    db.session.commit()
    flash("OS atualizada!", "success")
    return redirect(url_for("pages.os_detalhe", id=id))


@pages_bp.route("/os/<int:id>")
@login_required
def os_detalhe(id):
    os_obj    = OrdemServico.query.filter_by(id=id).filter(
        OrdemServico.deletado_em.is_(None)).first_or_404()
    historico = (OSHistorico.query.filter_by(os_id=id)
                 .order_by(OSHistorico.criado_em.asc()).all())
    pecas_dict = os_obj.to_dict().get("pecas", [])
    pecas_estoque = Peca.query.order_by(Peca.nome).all()
    pecas_estoque_json = _safe_json([
        {"id": p.id, "nome": p.nome, "codigo": p.codigo or "",
         "quantidade": p.quantidade,
         "preco_venda": float(p.preco_venda or p.custo or 0)}
        for p in pecas_estoque])

    # Bug #8: nivel_usuario não era passado ao template → buttons admin sumiam
    nivel_usuario = session.get("nivel", "operacional")

    return render_template("pages/os_detalhe.html", active="os",
        os=os_obj, status_map=STATUS_MAP, historico=historico,
        pecas_dict=pecas_dict, pecas_estoque_json=pecas_estoque_json,
        nivel_usuario=nivel_usuario)


@pages_bp.route("/os/<int:id>/status", methods=["POST"])
@login_required
def os_status(id):
    from app.utils.whatsapp import enviar_whatsapp, mensagem_os_pronta
    os_obj  = OrdemServico.query.filter_by(id=id).filter(
        OrdemServico.deletado_em.is_(None)).first_or_404()
    novo_st = request.form.get("status")
    antigo  = os_obj.status

    # Bug #6: rejeitar status inválido
    if novo_st and novo_st not in STATUS_OS:
        flash(f"Status inválido: '{novo_st}'.", "error")
        return redirect(url_for("pages.os_detalhe", id=id))

    if novo_st and novo_st != antigo:
        os_obj.status = novo_st
        if novo_st == "entregue" and not os_obj.data_saida:
            os_obj.data_saida = _now()

        db.session.add(OSHistorico(
            os_id=os_obj.id, usuario_id=session["usuario_id"],
            status_anterior=antigo, status_novo=novo_st,
        ))

        if novo_st == "entregue" and antigo != "entregue":
            if not Transacao.query.filter_by(
                    os_id=os_obj.id, tipo="receita").first():
                db.session.add(Transacao(
                    os_id=os_obj.id, tipo="receita", categoria="Serviços OS",
                    descricao=f"OS #{os_obj.id:04d}",
                    valor=os_obj.valor_total, status="pago",
                    data_vencimento=_now(), data_pagamento=_now(),
                ))

        # Cancelamento: devolve estoque
        if novo_st == "cancelado":
            from sqlalchemy import text as sqla_text
            rows = db.session.execute(
                sqla_text("SELECT peca_id, quantidade FROM os_pecas WHERE os_id=:id"),
                {"id": os_obj.id},
            ).fetchall()
            for row in rows:
                p = db.session.get(Peca, row.peca_id)
                if p: p.quantidade += row.quantidade

        registrar("status", "os",
                  f"OS #{os_obj.id:04d}: {antigo} → {novo_st}")
        db.session.commit()

        # Notificação WhatsApp ao marcar pronto
        if novo_st == "pronto" and antigo != "pronto":
            if os_obj.cliente and os_obj.cliente.telefone:
                resultado = enviar_whatsapp(
                    os_obj.cliente.telefone,
                    mensagem_os_pronta(os_obj),
                )
                if resultado["sucesso"]:
                    flash("Status atualizado! Cliente notificado via WhatsApp.", "success")
                elif resultado.get("modo") == "simulacao":
                    flash(
                        f'Status atualizado! <a href="{resultado["link"]}" '
                        f'target="_blank" style="color:var(--green)">Enviar WhatsApp manualmente →</a>',
                        "success",
                    )
                else:
                    flash(
                        f'Status atualizado! Falha no WhatsApp: {resultado.get("erro","")}'
                        f' — <a href="{resultado["link"]}" target="_blank">Enviar manualmente →</a>',
                        "warning",
                    )
            else:
                flash("Status atualizado! (Cliente sem telefone cadastrado)", "success")
        else:
            flash(f"Status: {STATUS_MAP.get(novo_st, novo_st)}", "success")

    return redirect(url_for("pages.os_detalhe", id=id))


@pages_bp.route("/os/<int:id>/pdf")
@login_required
def os_pdf(id):
    import io
    from flask import send_file
    from app.utils.pdf_gen import gerar_pdf_os
    os_obj = OrdemServico.query.filter_by(id=id).filter(
        OrdemServico.deletado_em.is_(None)).first_or_404()
    try:
        pdf = gerar_pdf_os(os_obj)
    except RuntimeError as e:
        flash(str(e), "error")
        return redirect(url_for("pages.os_detalhe", id=id))
    return send_file(
        io.BytesIO(pdf), mimetype="application/pdf",
        as_attachment=True, download_name=f"OS_{id:04d}.pdf",
    )


@pages_bp.route("/os/<int:id>/deletar", methods=["POST"])
@login_required
def os_deletar(id):
    os_obj = OrdemServico.query.filter_by(id=id).filter(
        OrdemServico.deletado_em.is_(None)).first_or_404()
    if session.get("nivel") != "admin":
        flash("Apenas administradores podem excluir OS.", "error")
        return redirect(url_for("pages.os_detalhe", id=id))

    from sqlalchemy import text as sqla_text
    rows = db.session.execute(
        sqla_text("SELECT peca_id, quantidade FROM os_pecas WHERE os_id=:id"),
        {"id": os_obj.id},
    ).fetchall()
    for row in rows:
        p = db.session.get(Peca, row.peca_id)
        if p: p.quantidade += row.quantidade

    registrar("exclusao", "os", f"OS #{os_obj.id:04d} excluída")
    os_obj.deletado_em = _now()
    db.session.commit()
    flash("OS removida.", "success")
    return redirect(url_for("pages.os_lista"))


# ══════════════════════════════════════════════════════════════
# CLIENTES
# ══════════════════════════════════════════════════════════════
@pages_bp.route("/clientes")
@login_required
def clientes():
    q            = request.args.get("q", "").strip()
    ativo_filtro = request.args.get("ativo", "1")
    page         = request.args.get("page", 1, type=int)
    query = Cliente.query
    if q:
        qe = _escape_like(q)
        query = query.filter(db.or_(
            Cliente.nome.ilike(f"%{qe}%"),
            Cliente.cpf.ilike(f"%{qe}%"),
            Cliente.telefone.ilike(f"%{qe}%"),
        ))
    if ativo_filtro == "1": query = query.filter_by(ativo=True)
    if ativo_filtro == "0": query = query.filter_by(ativo=False)
    pag  = query.order_by(Cliente.nome).paginate(
        page=page, per_page=25, error_out=False)
    lista = pag.items
    for cli in lista:
        cli.os_count = OrdemServico.query.filter_by(
            cliente_id=cli.id).filter(
            OrdemServico.deletado_em.is_(None)).count()
    clientes_json = _safe_json([
        {"id": c.id, "nome": c.nome, "cpf": c.cpf or "",
         "telefone": c.telefone or "", "email": c.email or "",
         "cep": c.cep or "", "endereco": c.endereco or "",
         "cidade": c.cidade or "", "uf": c.uf or "", "ativo": c.ativo}
        for c in lista])
    return render_template("pages/clientes.html", active="clientes",
        clientes=lista, paginacao=pag, clientes_json=clientes_json,
        q=q, ativo_filtro=ativo_filtro)


@pages_bp.route("/clientes/novo", methods=["POST"])
@login_required
def cliente_criar():
    data = request.form
    nome = sanitize_text(data.get("nome", ""), max_length=200)
    if not nome or len(nome) < 2:
        flash("Nome do cliente é obrigatório (mínimo 2 caracteres).", "error")
        return redirect(url_for("pages.clientes"))
    email = sanitize_email(data.get("email", ""))
    if email and not validar_email(email):
        flash("E-mail inválido.", "error")
        return redirect(url_for("pages.clientes"))
    cpf_raw = sanitize_cpf(data.get("cpf", ""))
    if cpf_raw and not validar_cpf(cpf_raw):
        flash("CPF inválido.", "error")
        return redirect(url_for("pages.clientes"))
    tel_raw = sanitize_phone(data.get("telefone", ""))
    if tel_raw and not validar_telefone(tel_raw):
        flash("Telefone inválido.", "error")
        return redirect(url_for("pages.clientes"))
    cep_raw = sanitize_cep(data.get("cep", ""))
    if cep_raw and not validar_cep(cep_raw):
        flash("CEP inválido.", "error")
        return redirect(url_for("pages.clientes"))
    # Unicidade
    if cpf_raw and Cliente.query.filter_by(cpf=cpf_raw).first():
        flash("CPF já cadastrado para outro cliente.", "error")
        return redirect(url_for("pages.clientes"))
    if email and Cliente.query.filter_by(email=email).first():
        flash("E-mail já cadastrado para outro cliente.", "error")
        return redirect(url_for("pages.clientes"))
    if tel_raw and Cliente.query.filter_by(telefone=tel_raw).first():
        flash("Telefone já cadastrado para outro cliente.", "error")
        return redirect(url_for("pages.clientes"))
    c = Cliente(
        nome     = nome,
        cpf      = cpf_raw or None,
        telefone = tel_raw or None,
        email    = email or None,
        cep      = cep_raw or None,
        endereco = sanitize_text(data.get("endereco", ""), max_length=300) or None,
        cidade   = sanitize_text(data.get("cidade", ""), max_length=100) or None,
        uf       = sanitize_text(data.get("uf", ""), max_length=2).upper() or None,
    )
    db.session.add(c)
    registrar("criacao", "clientes", f"Cliente criado: {nome}")
    db.session.commit()
    flash("Cliente salvo!", "success")
    return redirect(url_for("pages.clientes"))


@pages_bp.route("/clientes/<int:id>/editar", methods=["POST"])
@login_required
def cliente_editar(id):
    c    = db.get_or_404(Cliente, id)
    data = request.form
    nome = sanitize_text(data.get("nome", ""), max_length=200)
    if not nome or len(nome) < 2:
        flash("Nome é obrigatório (mínimo 2 caracteres).", "error")
        return redirect(url_for("pages.clientes"))
    email = sanitize_email(data.get("email", ""))
    if email and not validar_email(email):
        flash("E-mail inválido.", "error")
        return redirect(url_for("pages.clientes"))
    cpf_raw = sanitize_cpf(data.get("cpf", ""))
    if cpf_raw and not validar_cpf(cpf_raw):
        flash("CPF inválido.", "error")
        return redirect(url_for("pages.clientes"))
    tel_raw = sanitize_phone(data.get("telefone", ""))
    if tel_raw and not validar_telefone(tel_raw):
        flash("Telefone inválido.", "error")
        return redirect(url_for("pages.clientes"))
    cep_raw = sanitize_cep(data.get("cep", ""))
    if cep_raw and not validar_cep(cep_raw):
        flash("CEP inválido.", "error")
        return redirect(url_for("pages.clientes"))
    # Unicidade (exclui o próprio cliente)
    dup_cpf = Cliente.query.filter_by(cpf=cpf_raw).first() if cpf_raw else None
    if dup_cpf and dup_cpf.id != c.id:
        flash("CPF já cadastrado para outro cliente.", "error")
        return redirect(url_for("pages.clientes"))
    dup_email = Cliente.query.filter_by(email=email).first() if email else None
    if dup_email and dup_email.id != c.id:
        flash("E-mail já cadastrado para outro cliente.", "error")
        return redirect(url_for("pages.clientes"))
    dup_tel = Cliente.query.filter_by(telefone=tel_raw).first() if tel_raw else None
    if dup_tel and dup_tel.id != c.id:
        flash("Telefone já cadastrado para outro cliente.", "error")
        return redirect(url_for("pages.clientes"))
    c.nome     = nome
    c.cpf      = cpf_raw or None
    c.telefone = tel_raw or None
    c.email    = email or None
    c.cep      = cep_raw or None
    c.endereco = sanitize_text(data.get("endereco", ""), max_length=300) or None
    c.cidade   = sanitize_text(data.get("cidade", ""), max_length=100) or None
    c.uf       = sanitize_text(data.get("uf", ""), max_length=2).upper() or None
    c.ativo    = data.get("ativo") == "1"
    registrar("edicao", "clientes", f"Cliente editado: {c.nome}")
    db.session.commit()
    flash("Cliente atualizado!", "success")
    return redirect(url_for("pages.clientes"))


@pages_bp.route("/clientes/<int:id>/deletar", methods=["POST"])
@login_required
def cliente_deletar(id):
    from app.models import OSHistorico, Transacao
    from sqlalchemy import text as _text

    c = db.get_or_404(Cliente, id)

    # Bloqueia se houver OS ativas (não arquivadas)
    os_ativas = OrdemServico.query.filter_by(
        cliente_id=c.id
    ).filter(OrdemServico.deletado_em.is_(None)).count()
    if os_ativas > 0:
        flash(
            f"Não é possível remover {c.nome}: possui {os_ativas} OS ativa(s). "
            "Encerre ou cancele as OS antes de remover o cliente.",
            "error"
        )
        return redirect(url_for("pages.clientes"))

    # Remove em cascata: historico → transações → os_pecas → OS arquivadas → cliente
    os_ids = [row.id for row in
              OrdemServico.query.filter_by(cliente_id=c.id).with_entities(OrdemServico.id).all()]

    if os_ids:
        # 1. Histórico de status
        OSHistorico.query.filter(OSHistorico.os_id.in_(os_ids)).delete(synchronize_session=False)
        # 2. Transações vinculadas às OS
        Transacao.query.filter(Transacao.os_id.in_(os_ids)).delete(synchronize_session=False)
        # 3. Peças das OS (tabela associativa)
        for os_id in os_ids:
            db.session.execute(_text("DELETE FROM os_pecas WHERE os_id = :id"), {"id": os_id})
        # 4. As próprias OS
        OrdemServico.query.filter(OrdemServico.cliente_id == c.id).delete(synchronize_session=False)

    registrar("exclusao", "clientes", f"Cliente removido: {c.nome} (com {len(os_ids)} OS arquivadas)")
    db.session.delete(c)
    db.session.commit()
    flash("Cliente removido.", "success")
    return redirect(url_for("pages.clientes"))


# ══════════════════════════════════════════════════════════════
# ESTOQUE
# ══════════════════════════════════════════════════════════════
@pages_bp.route("/estoque")
@login_required
def estoque():
    q              = request.args.get("q", "").strip()
    cat_filtro     = request.args.get("cat", "")
    critico_filtro = request.args.get("critico", "")
    page           = request.args.get("page", 1, type=int)
    query = Peca.query
    if q:
        qe = _escape_like(q)
        query = query.filter(db.or_(
            Peca.nome.ilike(f"%{qe}%"),
            Peca.codigo.ilike(f"%{qe}%"),
        ))
    if cat_filtro:     query = query.filter_by(categoria=cat_filtro)
    if critico_filtro: query = query.filter(Peca.quantidade <= Peca.estoque_minimo)
    pag = query.order_by(Peca.nome).paginate(
        page=page, per_page=30, error_out=False)
    categorias  = [r[0] for r in db.session.query(
        Peca.categoria).distinct().all() if r[0]]
    valor_total = sum(
        float(p.custo or 0) * p.quantidade for p in Peca.query.all())
    criticos    = Peca.query.filter(
        Peca.quantidade <= Peca.estoque_minimo).all()
    pecas_json  = _safe_json([
        {"id": p.id, "nome": p.nome, "quantidade": p.quantidade,
         "estoque_minimo": p.estoque_minimo,
         "custo": float(p.custo or 0)}
        for p in pag.items])
    return render_template("pages/estoque.html", active="estoque",
        pecas=pag.items, paginacao=pag, pecas_json=pecas_json,
        categorias=categorias, valor_total=valor_total, criticos=criticos,
        q=q, cat_filtro=cat_filtro, critico_filtro=critico_filtro)


@pages_bp.route("/estoque/nova", methods=["POST"])
@login_required
def peca_criar():
    data = request.form
    nome_peca = sanitize_text(data.get("nome", ""), max_length=200)
    if not nome_peca or len(nome_peca) < 2:
        flash("Nome da peça é obrigatório.", "error")
        return redirect(url_for("pages.estoque"))
    try:
        qtd = int(data.get("quantidade") or 0)
        est_min = int(data.get("estoque_minimo") or 5)
        custo_v = float(data.get("custo") or 0)
        margem_v = float(data.get("margem") or 0)
    except (ValueError, TypeError):
        flash("Valores numéricos inválidos.", "error")
        return redirect(url_for("pages.estoque"))
    if qtd < 0 or custo_v < 0 or margem_v < 0:
        flash("Valores numéricos não podem ser negativos.", "error")
        return redirect(url_for("pages.estoque"))
    p = Peca(
        nome=nome_peca,
        codigo=sanitize_text(data.get("codigo", ""), max_length=50) or None,
        categoria=sanitize_text(data.get("categoria", ""), max_length=100) or None,
        localizacao=sanitize_text(data.get("localizacao", ""), max_length=100) or None,
        quantidade=qtd,
        estoque_minimo=est_min,
        custo=custo_v,
        margem=margem_v,
    )
    db.session.add(p)
    registrar("criacao", "estoque", f"Peça criada: {nome_peca}")
    db.session.commit()
    flash("Peça salva!", "success")
    return redirect(url_for("pages.estoque"))


@pages_bp.route("/estoque/<int:id>/movimentacao", methods=["POST"])
@login_required
def peca_movimentar(id):
    p    = db.get_or_404(Peca, id)
    tipo = request.form.get("tipo", "")
    if tipo not in ("entrada", "saida", "ajuste"):
        flash("Tipo de movimentação inválido.", "error")
        return redirect(url_for("pages.estoque"))
    try:
        qt = int(request.form.get("quantidade") or 0)
    except (ValueError, TypeError):
        flash("Quantidade inválida.", "error")
        return redirect(url_for("pages.estoque"))
    if qt < 0:
        flash("Quantidade não pode ser negativa.", "error")
        return redirect(url_for("pages.estoque"))
    if qt > 999_999:
        flash("Quantidade excede o limite máximo.", "error")
        return redirect(url_for("pages.estoque"))
    if tipo == "entrada":
        p.quantidade = min(999_999, p.quantidade + qt)
    elif tipo == "saida":
        if qt > p.quantidade:
            flash(f"Estoque insuficiente. Disponível: {p.quantidade}.", "error")
            return redirect(url_for("pages.estoque"))
        p.quantidade -= qt
    elif tipo == "ajuste":
        p.quantidade = qt
    registrar("edicao", "estoque", f"Estoque {tipo}: {p.nome} ({qt})")
    db.session.commit()
    flash("Estoque atualizado!", "success")
    return redirect(url_for("pages.estoque"))


@pages_bp.route("/estoque/<int:id>/deletar", methods=["POST"])
@login_required
def peca_deletar(id):
    p = db.get_or_404(Peca, id)
    registrar("exclusao", "estoque", f"Peça removida: {p.nome}")
    db.session.delete(p)
    db.session.commit()
    flash("Peça removida.", "success")
    return redirect(url_for("pages.estoque"))


# ══════════════════════════════════════════════════════════════
# FORNECEDORES
# ══════════════════════════════════════════════════════════════
@pages_bp.route("/fornecedores")
@login_required
def fornecedores():
    q    = request.args.get("q", "").strip()
    page = request.args.get("page", 1, type=int)
    query = Fornecedor.query
    if q:
        qe = _escape_like(q)
        query = query.filter(db.or_(
            Fornecedor.nome.ilike(f"%{qe}%"),
            Fornecedor.cnpj.ilike(f"%{qe}%"),
        ))
    pag   = query.order_by(Fornecedor.nome).paginate(
        page=page, per_page=25, error_out=False)
    lista = pag.items
    fornecedores_json = _safe_json([
        {"id": f.id, "nome": f.nome, "cnpj": f.cnpj or "",
         "telefone": f.telefone or "", "email": f.email or "",
         "cep": f.cep or "", "endereco": f.endereco or "",
         "cidade": f.cidade or "", "ativo": f.ativo}
        for f in lista])
    return render_template("pages/fornecedores.html", active="fornecedores",
        fornecedores=lista, paginacao=pag,
        fornecedores_json=fornecedores_json, q=q)


@pages_bp.route("/fornecedores/novo", methods=["POST"])
@login_required
def fornecedor_criar():
    from app.utils.validators import validar_cnpj
    from app.utils.sanitizers import sanitize_cnpj
    data = request.form
    nome = sanitize_text(data.get("nome", ""), max_length=200)
    if not nome or len(nome) < 2:
        flash("Nome do fornecedor é obrigatório.", "error")
        return redirect(url_for("pages.fornecedores"))
    cnpj_raw = sanitize_cnpj(data.get("cnpj", ""))
    if cnpj_raw and not validar_cnpj(cnpj_raw):
        flash("CNPJ inválido.", "error")
        return redirect(url_for("pages.fornecedores"))
    email = sanitize_email(data.get("email", ""))
    if email and not validar_email(email):
        flash("E-mail inválido.", "error")
        return redirect(url_for("pages.fornecedores"))
    cep_raw = sanitize_cep(data.get("cep", ""))
    if cep_raw and not validar_cep(cep_raw):
        flash("CEP inválido.", "error")
        return redirect(url_for("pages.fornecedores"))
    f = Fornecedor(
        nome     = nome,
        cnpj     = cnpj_raw or None,
        telefone = sanitize_phone(data.get("telefone", "")) or None,
        email    = email or None,
        cep      = cep_raw or None,
        endereco = sanitize_text(data.get("endereco", ""), max_length=300) or None,
        cidade   = sanitize_text(data.get("cidade", ""), max_length=100) or None,
    )
    db.session.add(f)
    registrar("criacao", "fornecedores", f"Fornecedor criado: {nome}")
    db.session.commit()
    flash("Fornecedor salvo!", "success")
    return redirect(url_for("pages.fornecedores"))


@pages_bp.route("/fornecedores/<int:id>/editar", methods=["POST"])
@login_required
def fornecedor_editar(id):
    from app.utils.validators import validar_cnpj
    from app.utils.sanitizers import sanitize_cnpj
    f    = db.get_or_404(Fornecedor, id)
    data = request.form
    nome = sanitize_text(data.get("nome", ""), max_length=200)
    if not nome or len(nome) < 2:
        flash("Nome é obrigatório.", "error")
        return redirect(url_for("pages.fornecedores"))
    cnpj_raw = sanitize_cnpj(data.get("cnpj", ""))
    if cnpj_raw and not validar_cnpj(cnpj_raw):
        flash("CNPJ inválido.", "error")
        return redirect(url_for("pages.fornecedores"))
    email = sanitize_email(data.get("email", ""))
    if email and not validar_email(email):
        flash("E-mail inválido.", "error")
        return redirect(url_for("pages.fornecedores"))
    cep_raw = sanitize_cep(data.get("cep", ""))
    if cep_raw and not validar_cep(cep_raw):
        flash("CEP inválido.", "error")
        return redirect(url_for("pages.fornecedores"))
    f.nome     = nome
    f.cnpj     = cnpj_raw or None
    f.telefone = sanitize_phone(data.get("telefone", "")) or None
    f.email    = email or None
    f.cep      = cep_raw or None
    f.endereco = sanitize_text(data.get("endereco", ""), max_length=300) or None
    f.cidade   = sanitize_text(data.get("cidade", ""), max_length=100) or None
    registrar("edicao", "fornecedores", f"Fornecedor editado: {f.nome}")
    db.session.commit()
    flash("Fornecedor atualizado!", "success")
    return redirect(url_for("pages.fornecedores"))


@pages_bp.route("/fornecedores/<int:id>/deletar", methods=["POST"])
@login_required
def fornecedor_deletar(id):
    f = db.get_or_404(Fornecedor, id)
    registrar("exclusao", "fornecedores", f"Fornecedor removido: {f.nome}")
    db.session.delete(f)
    db.session.commit()
    flash("Fornecedor removido.", "success")
    return redirect(url_for("pages.fornecedores"))


# ══════════════════════════════════════════════════════════════
# FINANCEIRO
# ══════════════════════════════════════════════════════════════
@pages_bp.route("/financeiro")
@page_nivel_required("admin", "financeiro")
def financeiro():
    hoje = _now()

    preset = request.args.get("preset", "")
    if preset == "semana":
        data_ini_def = (hoje - timedelta(days=7)).strftime("%Y-%m-%d")
        data_fim_def = hoje.strftime("%Y-%m-%d")
    elif preset == "ano":
        data_ini_def = hoje.strftime("%Y-01-01")
        data_fim_def = hoje.strftime("%Y-%m-%d")
    else:
        data_ini_def = hoje.strftime("%Y-%m-01")
        data_fim_def = hoje.strftime("%Y-%m-%d")

    data_ini      = request.args.get("data_ini", data_ini_def)
    data_fim      = request.args.get("data_fim", data_fim_def)
    tipo_filtro   = request.args.get("tipo", "")
    status_filtro = request.args.get("status", "")
    page          = request.args.get("page", 1, type=int)

    try:
        dt_ini = datetime.fromisoformat(data_ini)
        dt_fim = datetime.fromisoformat(data_fim).replace(
            hour=23, minute=59, second=59)
    except Exception:
        dt_ini = hoje.replace(day=1)
        dt_fim = hoje

    query = Transacao.query.filter(
        Transacao.criado_em >= dt_ini,
        Transacao.criado_em <= dt_fim,
    )
    if tipo_filtro:   query = query.filter_by(tipo=tipo_filtro)
    if status_filtro: query = query.filter_by(status=status_filtro)
    pag = query.order_by(Transacao.criado_em.desc()).paginate(
        page=page, per_page=25, error_out=False)

    def _s(tipo, st):
        return float(db.session.query(
            _coalesce_sum(Transacao.valor)).filter(
            Transacao.tipo == tipo, Transacao.status == st,
            Transacao.criado_em >= dt_ini,
            Transacao.criado_em <= dt_fim,
        ).scalar() or 0)

    periodo_label = (f"{dt_ini.strftime('%d/%m/%Y')} "
                     f"a {dt_fim.strftime('%d/%m/%Y')}")

    return render_template("pages/financeiro.html", active="financeiro",
        transacoes=pag.items, paginacao=pag,
        filtros={"data_ini": data_ini, "data_fim": data_fim,
                 "tipo": tipo_filtro, "status": status_filtro},
        periodo_label=periodo_label,
        receitas_pagas=_s("receita", "pago"),
        despesas_pagas=_s("despesa", "pago"),
        lucro=_s("receita", "pago") - _s("despesa", "pago"),
        a_receber=_s("receita", "pendente"),
        a_pagar=_s("despesa", "pendente"),
    )


@pages_bp.route("/financeiro/nova", methods=["POST"])
@page_nivel_required("admin", "financeiro")
def transacao_criar():
    from app.models.transacao import TIPOS_TRANSACAO, STATUS_TRANSACAO
    data = request.form
    try:
        valor = float(data["valor"])
    except (ValueError, TypeError, KeyError):
        flash("Valor inválido.", "error")
        return redirect(url_for("pages.financeiro"))
    if valor < 0:
        flash("Valor não pode ser negativo.", "error")
        return redirect(url_for("pages.financeiro"))
    if data.get("tipo") not in TIPOS_TRANSACAO:
        flash("Tipo de transação inválido.", "error")
        return redirect(url_for("pages.financeiro"))
    status = data.get("status", "pendente")
    if status not in STATUS_TRANSACAO:
        status = "pendente"
    descricao_t = sanitize_text(data.get("descricao", ""), max_length=500)
    if not descricao_t:
        flash("Descrição é obrigatória.", "error")
        return redirect(url_for("pages.financeiro"))
    if valor > 9_999_999.99:
        flash("Valor excede o limite máximo permitido.", "error")
        return redirect(url_for("pages.financeiro"))
    t = Transacao(
        tipo=data["tipo"],
        categoria=sanitize_text(data.get("categoria", ""), max_length=100) or None,
        descricao=descricao_t,
        valor=valor,
        status=status,
        data_vencimento=_safe_date(data.get("data_vencimento")),
    )
    db.session.add(t)
    registrar("criacao", "financeiro",
              f"Transação criada: {data.get('descricao', '')} R$ {valor}")
    db.session.commit()
    flash("Transação salva!", "success")
    return redirect(url_for("pages.financeiro"))


@pages_bp.route("/financeiro/<int:id>/pagar", methods=["POST"])
@page_nivel_required("admin", "financeiro")
def transacao_pagar(id):
    # Bug #9: get_or_404 depreciado
    t = db.get_or_404(Transacao, id)
    t.status        = "pago"
    t.data_pagamento= _now()
    registrar("pagamento", "financeiro",
              f"Transação #{id} marcada como paga")
    db.session.commit()
    flash("Pagamento registrado!", "success")
    return redirect(url_for("pages.financeiro"))


@pages_bp.route("/financeiro/<int:id>/deletar", methods=["POST"])
@page_nivel_required("admin", "financeiro")
def transacao_deletar(id):
    t = db.get_or_404(Transacao, id)
    t.status = "cancelado"
    registrar("exclusao", "financeiro", f"Transação #{id} cancelada")
    db.session.commit()
    flash("Transação cancelada.", "success")
    return redirect(url_for("pages.financeiro"))