"""Parcelamento e calculos financeiros deterministas."""
import calendar
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from app.extensions import db
from app.models import Transacao


def add_months(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def split_money(total, count: int) -> list[Decimal]:
    if not 1 <= count <= 60:
        raise ValueError("Parcelas devem estar entre 1 e 60.")
    cents = int((Decimal(str(total)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    base, remainder = divmod(cents, count)
    return [Decimal(base + (1 if index < remainder else 0)) / 100 for index in range(count)]


def create_installments(*, organization_id, installments=1, recurrence=None, **values):
    installments = int(installments or 1)
    total_value = Decimal(str(values.pop("valor")))
    amounts = split_money(total_value, installments)
    due_date = values.pop("data_vencimento", None) or datetime.now()
    commission_percent = Decimal(str(values.pop("comissao_percentual", 0) or 0))
    if commission_percent < 0 or commission_percent > 100:
        raise ValueError("Comissao deve estar entre 0 e 100%.")
    commission_amounts = split_money(total_value * commission_percent / 100, installments)
    if recurrence not in (None, "", "mensal"):
        raise ValueError("Recorrencia invalida.")
    created = []
    parent = None
    for index, amount in enumerate(amounts, 1):
        transaction = Transacao(
            organization_id=organization_id,
            valor=amount,
            data_vencimento=add_months(due_date, index - 1),
            parcela_numero=index,
            parcela_total=installments,
            recorrencia=recurrence or None,
            comissao_percentual=commission_percent,
            comissao_valor=commission_amounts[index - 1],
            **values,
        )
        if parent:
            transaction.parent = parent
        db.session.add(transaction)
        db.session.flush()
        parent = parent or transaction
        created.append(transaction)
    return created
