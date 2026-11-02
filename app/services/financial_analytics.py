"""Indicadores financeiros acionaveis por ordem de servico."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import case, func, text
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import OrdemServico, Peca, Transacao
from app.models.ordem_servico import os_pecas


def _normalized_now(value: datetime | None = None) -> datetime:
    value = value or datetime.now(timezone.utc)
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _period_date_range(period: str, now: datetime | None = None) -> tuple[datetime, datetime]:
    """Retorna (start, end) para os periodos: 'hoje', 'this_month', 'last_month', 'this_quarter', 'last_quarter', 'this_year', 'last_year'."""
    now = now or _normalized_now()
    today = now.replace(tzinfo=None) if now.tzinfo else now
    from datetime import timedelta
    if period == "hoje":
        start = today
        end = today + timedelta(days=1)
    elif period == "this_month":
        start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
    elif period == "last_month":
        first = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if first.month == 1:
            start = first.replace(year=first.year - 1, month=12)
        else:
            start = first.replace(month=first.month - 1)
        start = start.replace(day=1)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
    elif period == "this_quarter":
        quarter_start_month = (today.month - 1) // 3 * 3 + 1
        start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0).replace(month=quarter_start_month)
        end = start.replace(month=start.month + 3)
    elif period == "last_quarter":
        q_start = ((today.month - 1) // 3 * 3)  # quarter number * 3
        q_month = q_start - 3 if q_start > 3 else 9  # previous quarter
        start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0).replace(month=q_month)
        if start.month in (1, 2, 3):
            end = start.replace(month=start.month + 3)
        else:
            # crossing year boundary
            end = datetime(start.year + 1, 1, 1)
    elif period == "this_year":
        start = today.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end = datetime(today.year + 1, 1, 1)
    elif period == "last_year":
        start = datetime(today.year - 1, 1, 1)
        end = datetime(today.year, 1, 1)
    else:
        # default to current month
        start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
    return start, end


def average_attendance_time(orders: list[OrdemServico], now: datetime | None = None) -> dict:
    """Calcula o tempo médio de atendimento (em dias) entre entrada e saida/pronto."""
    now = now or _normalized_now()
    valid = [o for o in orders if o.data_entrada and o.status in ["entregue", "pronto", "cancelado"]]
    if not valid:
        return {"dias_medio": 0, "total": 0, "with_entry": len(valid)}
    # dias = (saida/pronto/cancelado - entrada). days
    # Usamos case para pegar a data de saida/conclucao
    # Para entregue usa baixada_em, para pronto usa a data estimada, para cancelado usa data de cancelamento
    days_map = []
    for o in valid:
        data_inicio = o.data_entrada.replace(tzinfo=None) if o.data_entrada.tzinfo else o.data_entrada
        if o.status == "entregue" and o.baixada_em:
            data_fim = o.baixada_em.replace(tzinfo=None) if o.baixada_em.tzinfo else o.baixada_em
        elif o.status == "pronto":
            # Pronto não tem data automática; usa data_prev ou today
            data_fim = o.data_prev.replace(tzinfo=None) if o.data_prev and o.data_prev.tzinfo else (o.data_prev or data_inicio)
        elif o.status == "cancelado":
            # sem data de cancelamento padrão; ignora ou usa data_entrada
            continue
        else:
            continue
        delta = (data_fim - data_inicio).days
        if delta >= 0:
            days_map.append(delta)
    total = len(days_map)
    medio = round(sum(days_map) / total, 2) if total else 0
    return {"dias_medio": medio, "total": total}


def most_performed_services(orders: list[OrdemServico], limit: int = 5) -> list[dict]:
    """Retorna os serviços (pecas/categorias) mais realizados no intervalo."""
    from sqlalchemy import func
    # Pecas mais usadas nas OS
    peca_rows = db.session.query(
        Peca.nome, func.count(os_pecas.c.os_id).label("qtd")
    ).join(
        os_pecas, os_pecas.c.peca_id == Peca.id
    ).filter(
        os_pecas.c.os_id.in_([o.id for o in orders])
    ).group_by(Peca.nome).order_by(func.count(os_pecas.c.os_id).desc()).limit(limit).all()
    return [{"nome": row.nome, "quantidade": row.qtd} for row in peca_rows]


def period_financial_summary(organization_id: int, start: datetime, end: datetime) -> dict:
    """Resumo financeiro filtrado por período e organização."""
    from sqlalchemy import func
    # Receitas pagas
    receitas = db.session.query(func.coalesce(func.sum(case(
        (((Transacao.tipo == "receita") & (Transacao.status == "pago") & (Transacao.criado_em >= start) & (Transacao.criado_em < end)), Transacao.valor),
        else_=0,
    )), 0)).scalar() or 0
    # Despesas pagas
    despesas = db.session.query(func.coalesce(func.sum(case(
        (((Transacao.tipo == "despesa") & (Transacao.status == "pago") & (Transacao.criado_em >= start) & (Transacao.criado_em < end)), Transacao.valor),
        else_=0,
    )), 0)).scalar() or 0
    # OS no período
    os_count = OrdemServico.query.filter(
        OrdemServico.organization_id == organization_id,
        OrdemServico.data_entrada >= start,
        OrdemServico.data_entrada <= end,
        OrdemServico.deletado_em.is_(None),
    ).count()
    # OS atrasadas no período
    os_atrasadas = OrdemServico.query.filter(
        OrdemServico.organization_id == organization_id,
        OrdemServico.data_prev < end,
        OrdemServico.status.notin_(["entregue", "cancelado"]),
        OrdemServico.deletado_em.is_(None),
    ).count()
    # Contas a receber (receitas pendentes vencendo)
    a_receber = db.session.query(func.coalesce(func.sum(case(
        (((Transacao.tipo == "receita") & (Transacao.status == "pendente") & (Transacao.data_vencimento < end) & (Transacao.criado_em >= start)), Transacao.valor),
        else_=0,
    )), 0)).scalar() or 0
    # Lucro bruto (receitas - despesas de pecas - comissoes)
    # Usando custo das pecas
    peca_custos = db.session.query(func.coalesce(func.sum(
        os_pecas.c.quantidade * func.coalesce(os_pecas.c.custo_unitario, Peca.custo, 0)
    ), 0)).select_from(OrdemServico).join(
        os_pecas, os_pecas.c.os_id == OrdemServico.id
    ).join(Peca, Peca.id == os_pecas.c.peca_id).filter(
        OrdemServico.organization_id == organization_id,
        OrdemServico.data_entrada >= start,
        OrdemServico.data_entrada <= end,
        OrdemServico.deletado_em.is_(None),
    ).scalar() or 0

    lucro_bruto = round(float(receitas) - float(peca_custos), 2)
    margem = round((lucro_bruto / float(receitas) * 100) if float(receitas) > 0 else 0, 2)

    return {
        "receitas": round(float(receitas), 2),
        "despesas": round(float(despesas), 2),
        "lucro_bruto": lucro_bruto,
        "margem": margem,
        "os_count": os_count,
        "os_atrasadas": os_atrasadas,
        "a_receber": round(float(a_receber), 2),
    }


def _financial_rows_for_orders(orders: list[OrdemServico], now: datetime) -> list[dict]:
    if not orders:
        return []

    organization_id = orders[0].organization_id
    order_ids = [item.id for item in orders]
    tx_rows = db.session.query(
        Transacao.os_id,
        func.coalesce(func.sum(case(((Transacao.tipo == "receita") & (Transacao.status == "pago"), Transacao.valor), else_=0)), 0).label("paid"),
        func.coalesce(func.sum(case(((Transacao.tipo == "receita") & (Transacao.status == "pendente"), Transacao.valor), else_=0)), 0).label("pending"),
        func.coalesce(func.sum(case((
            (Transacao.tipo == "receita")
            & (Transacao.status == "pendente")
            & (Transacao.data_vencimento < now),
            Transacao.valor,
        ), else_=0)), 0).label("overdue"),
        func.min(case((
            (Transacao.tipo == "receita")
            & (Transacao.status == "pendente")
            & (Transacao.data_vencimento < now),
            Transacao.data_vencimento,
        ), else_=None)).label("oldest_due"),
        func.coalesce(func.sum(case((
            (Transacao.tipo == "receita") & (Transacao.status == "pago"),
            Transacao.comissao_valor,
        ), else_=0)), 0).label("commissions"),
    ).filter(
        Transacao.organization_id == organization_id,
        Transacao.os_id.in_(order_ids),
        Transacao.status != "cancelado",
    ).group_by(Transacao.os_id).all()
    by_order = {
        row.os_id: {
            "paid": float(row.paid or 0),
            "pending": float(row.pending or 0),
            "overdue": float(row.overdue or 0),
            "oldest_due": row.oldest_due,
            "commissions": float(row.commissions or 0),
        }
        for row in tx_rows
    }

    costs = {}
    cost_rows = db.session.execute(text(
        "SELECT op.os_id, SUM(op.quantidade * COALESCE(op.custo_unitario, p.custo, 0)) AS custo "
        "FROM os_pecas op "
        "JOIN ordens_servico o ON o.id = op.os_id "
        "JOIN pecas p ON p.id = op.peca_id "
        "WHERE op.os_id IN :ids AND o.organization_id = :organization_id "
        "AND p.organization_id = :organization_id GROUP BY op.os_id"
    ).bindparams(db.bindparam("ids", expanding=True)), {
        "ids": order_ids,
        "organization_id": organization_id,
    }).mappings()
    for row in cost_rows:
        costs[row["os_id"]] = float(row["custo"] or 0)

    result = []
    for order in orders:
        tx = by_order.get(order.id, {})
        paid = tx.get("paid", 0)
        pending = tx.get("pending", 0)
        commissions = tx.get("commissions", 0)
        overdue = tx.get("overdue", 0)
        part_cost = round(costs.get(order.id, 0), 2)
        labor_cost = order.custo_mao_obra
        result.append({
            "order": order,
            "customer": order.cliente,
            "total": order.valor_total,
            "paid": round(paid, 2),
            "pending": round(pending, 2),
            "uncovered": round(max(0, order.valor_total - paid - pending), 2),
            "overdue": round(overdue, 2),
            "oldest_due": tx.get("oldest_due"),
            "part_cost": part_cost,
            "labor_cost": labor_cost,
            "commissions": round(commissions, 2),
            "profit": round(order.valor_total - part_cost - labor_cost - commissions, 2),
        })
    return result


def order_financial_rows(
    now: datetime | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[dict]:
    """Consolida faturamento, recebimentos, custo e atraso por OS do tenant atual."""
    now = _normalized_now(now)
    query = OrdemServico.query.options(joinedload(OrdemServico.cliente)).filter(OrdemServico.deletado_em.is_(None))
    if start is not None:
        query = query.filter(OrdemServico.data_entrada >= start)
    if end is not None:
        query = query.filter(OrdemServico.data_entrada <= end)
    result = _financial_rows_for_orders(query.all(), now)
    return sorted(result, key=lambda row: (row["overdue"], row["pending"] + row["uncovered"]), reverse=True)


def order_financial_snapshot(order: OrdemServico, now: datetime | None = None) -> dict:
    """Calcula os mesmos indicadores da tela financeira para uma unica OS."""
    return _financial_rows_for_orders([order], _normalized_now(now))[0]


def period_summary(rows: list[dict], paid_revenue: float, paid_expenses: float) -> dict:
    """Resume os indicadores das OS e transacoes do intervalo selecionado."""
    return {
        "orders": len(rows),
        "billed": round(sum(row["total"] for row in rows), 2),
        "received": round(paid_revenue, 2),
        "expenses": round(paid_expenses, 2),
        "outstanding": round(sum(row["pending"] + row["uncovered"] for row in rows), 2),
        "overdue": round(sum(row["overdue"] for row in rows), 2),
        "order_profit": round(sum(row["profit"] for row in rows), 2),
    }


# Compatibilidade para importacoes anteriores; novos usos devem refletir o periodo filtrado.
monthly_summary = period_summary
