"""Indicadores financeiros acionaveis por ordem de servico."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import text

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
    query = OrdemServico.query.filter(OrdemServico.deletado_em.is_(None))
    if start is not None:
        query = query.filter(OrdemServico.data_entrada >= start)
    if end is not None:
        query = query.filter(OrdemServico.data_entrada <= end)
    orders = query.all()
    if not orders:
        return []

    order_ids = [item.id for item in orders]
    transactions = Transacao.query.filter(
        Transacao.os_id.in_(order_ids), Transacao.status != "cancelado",
    ).all()
    by_order = defaultdict(list)
    for transaction in transactions:
        by_order[transaction.os_id].append(transaction)

    costs = defaultdict(float)
    cost_rows = db.session.execute(text(
        "SELECT op.os_id, SUM(op.quantidade * COALESCE(op.custo_unitario, p.custo, 0)) AS custo "
        "FROM os_pecas op JOIN pecas p ON p.id = op.peca_id "
        "WHERE op.os_id IN :ids GROUP BY op.os_id"
    ).bindparams(db.bindparam("ids", expanding=True)), {"ids": order_ids}).mappings()
    for row in cost_rows:
        costs[row["os_id"]] = float(row["custo"] or 0)

    result = []
    for order in orders:
        items = by_order[order.id]
        paid = sum(float(item.valor or 0) for item in items if item.tipo == "receita" and item.status == "pago")
        pending_items = [item for item in items if item.tipo == "receita" and item.status == "pendente"]
        pending = sum(float(item.valor or 0) for item in pending_items)
        commissions = sum(
            float(item.comissao_valor or 0)
            for item in items
            if item.tipo == "receita" and item.status == "pago"
        )
        overdue_items = [
            item for item in pending_items
            if item.data_vencimento and _naive_utc(item.data_vencimento) < now
        ]
        overdue = sum(float(item.valor or 0) for item in overdue_items)
        part_cost = round(costs[order.id], 2)
        labor_cost = order.custo_mao_obra
        result.append({
            "order": order,
            "customer": order.cliente,
            "total": order.valor_total,
            "paid": round(paid, 2),
            "pending": round(pending, 2),
            "uncovered": round(max(0, order.valor_total - paid - pending), 2),
            "overdue": round(overdue, 2),
            "oldest_due": min((item.data_vencimento for item in overdue_items), default=None),
            "part_cost": part_cost,
            "labor_cost": labor_cost,
            "commissions": round(commissions, 2),
            "profit": round(order.valor_total - part_cost - labor_cost - commissions, 2),
        })
    return sorted(result, key=lambda row: (row["overdue"], row["pending"] + row["uncovered"]), reverse=True)


def _naive_utc(value: datetime) -> datetime:
    """Normaliza datas do banco para UTC sem tzinfo, como as colunas DateTime atuais."""
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


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
