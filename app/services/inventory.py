"""Regras transacionais de estoque, reservas e auditoria."""
from datetime import datetime, timezone

from app.extensions import db
from app.models import InventoryLot, InventoryMovement, StockReservation


def record_movement(part, user_id, movement_type, before, after, reason, order_id=None, lot_id=None):
    reason = (reason or "").strip()
    if len(reason) < 5:
        raise ValueError("Informe uma justificativa com pelo menos 5 caracteres.")
    movement = InventoryMovement(
        organization_id=part.organization_id,
        part_id=part.id,
        order_id=order_id,
        lot_id=lot_id,
        user_id=user_id,
        movement_type=movement_type,
        quantity_delta=after - before,
        quantity_before=before,
        quantity_after=after,
        reason=reason[:300],
    )
    db.session.add(movement)
    return movement


def receive_lot(part, user_id, code, quantity, unit_cost, reason, supplier_id=None, location=None, expires_at=None):
    if quantity <= 0:
        raise ValueError("Quantidade do lote deve ser maior que zero.")
    if unit_cost < 0:
        raise ValueError("Custo unitário não pode ser negativo.")
    if InventoryLot.query.filter_by(part_id=part.id, code=code).first():
        raise ValueError("Código de lote já cadastrado para esta peça.")
    before = part.quantidade
    total_cost = float(part.custo or 0) * before + float(unit_cost) * quantity
    after = before + quantity
    lot = InventoryLot(
        organization_id=part.organization_id, part_id=part.id, supplier_id=supplier_id,
        code=code, quantity=quantity, initial_quantity=quantity, unit_cost=unit_cost,
        location=location, expires_at=expires_at,
    )
    db.session.add(lot)
    db.session.flush()
    part.quantidade = after
    part.custo = round(total_cost / after, 2)
    record_movement(part, user_id, "lot_receipt", before, after, reason, lot_id=lot.id)
    return lot


def reserve_stock(part, order, user_id, quantity):
    if quantity <= 0:
        raise ValueError("Quantidade deve ser maior que zero.")
    existing = StockReservation.query.filter_by(part_id=part.id, order_id=order.id, status="active").first()
    current = existing.quantity if existing else 0
    available_with_current = part.quantidade_disponivel + current
    if quantity > available_with_current:
        raise ValueError(f"Estoque disponivel insuficiente: {available_with_current}.")
    if existing:
        existing.quantity = quantity
        return existing
    reservation = StockReservation(
        organization_id=part.organization_id,
        part_id=part.id,
        order_id=order.id,
        user_id=user_id,
        quantity=quantity,
    )
    db.session.add(reservation)
    return reservation


def consume_reservation(part_id, order_id, quantity):
    reservation = StockReservation.query.filter_by(part_id=part_id, order_id=order_id, status="active").first()
    if not reservation:
        return
    if quantity >= reservation.quantity:
        reservation.status = "consumed"
        reservation.closed_at = datetime.now(timezone.utc)
    else:
        reservation.quantity -= quantity


def cancel_reservation(reservation):
    reservation.status = "cancelled"
    reservation.closed_at = datetime.now(timezone.utc)
