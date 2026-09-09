"""Indicadores financeiros acionaveis por ordem de servico."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import case, func, text
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import OrdemServico, Transacao


def order_financial_rows(
    now: datetime | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[dict]:
    """Consolida faturamento, recebimentos, custo e atraso por OS do tenant atual."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is not None:
        now = now.astimezone(timezone.utc).replace(tzinfo=None)
    query = OrdemServico.query.options(joinedload(OrdemServico.cliente)).filter(OrdemServico.deletado_em.is_(None))
    if start is not None:
        query = query.filter(OrdemServico.data_entrada >= start)
    if end is not None:
        query = query.filter(OrdemServico.data_entrada <= end)
    orders = query.all()
    if not orders:
        return []

    order_ids = [item.id for item in orders]
    tx_rows = db.session.query(
        Transacao.os_id,
        func.coalesce(func.sum(case((
            (Transacao.tipo == "receita") & (Transacao.status == "pago"),
            Transacao.valor,
        ), else_=0)), 0).label("paid"),
        func.coalesce(func.sum(case((
            (Transacao.tipo == "receita") & (Transacao.status == "pendente"),
            Transacao.valor,
        ), else_=0)), 0).label("pending"),
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
        "FROM os_pecas op JOIN pecas p ON p.id = op.peca_id "
        "WHERE op.os_id IN :ids GROUP BY op.os_id"
    ).bindparams(db.bindparam("ids", expanding=True)), {"ids": order_ids}).mappings()
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
    return sorted(result, key=lambda row: (row["overdue"], row["pending"] + row["uncovered"]), reverse=True)


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
