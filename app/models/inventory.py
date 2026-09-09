from datetime import datetime, timezone

from app.extensions import db


def _now():
    return datetime.now(timezone.utc)


class InventoryMovement(db.Model):
    __tablename__ = "inventory_movements"
    __table_args__ = (
        db.Index("ix_inventory_movements_org_created", "organization_id", "created_at"),
        db.Index("ix_inventory_movements_org_part_created", "organization_id", "part_id", "created_at"),
        db.Index("ix_inventory_movements_org_type_created", "organization_id", "movement_type", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    part_id = db.Column(db.Integer, db.ForeignKey("pecas.id"), nullable=False, index=True)
    lot_id = db.Column(db.Integer, db.ForeignKey("inventory_lots.id"), index=True)
    order_id = db.Column(db.Integer, db.ForeignKey("ordens_servico.id"), index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    movement_type = db.Column(db.String(30), nullable=False, index=True)
    quantity_delta = db.Column(db.Integer, nullable=False)
    quantity_before = db.Column(db.Integer, nullable=False)
    quantity_after = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(300), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=_now, index=True)

    part = db.relationship("Peca", backref=db.backref("movements", lazy=True))
    order = db.relationship("OrdemServico")
    user = db.relationship("Usuario")
    lot = db.relationship("InventoryLot", backref=db.backref("movements", lazy=True))


class InventoryLot(db.Model):
    __tablename__ = "inventory_lots"
    __table_args__ = (
        db.UniqueConstraint("organization_id", "part_id", "code", name="uq_inventory_lot_part_code"),
        db.CheckConstraint("quantity >= 0", name="ck_inventory_lot_quantity_nonnegative"),
        db.Index("ix_inventory_lots_org_part_active", "organization_id", "part_id", "active"),
        db.Index("ix_inventory_lots_org_expires", "organization_id", "expires_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    part_id = db.Column(db.Integer, db.ForeignKey("pecas.id"), nullable=False, index=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey("fornecedores.id"))
    code = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    initial_quantity = db.Column(db.Integer, nullable=False)
    unit_cost = db.Column(db.Numeric(10, 2), nullable=False)
    location = db.Column(db.String(100))
    received_at = db.Column(db.DateTime, nullable=False, default=_now)
    expires_at = db.Column(db.DateTime, index=True)
    active = db.Column(db.Boolean, nullable=False, default=True)

    part = db.relationship("Peca", backref=db.backref("lots", lazy=True))
    supplier = db.relationship("Fornecedor")

    def to_dict(self):
        return {
            "id": self.id, "peca_id": self.part_id, "fornecedor_id": self.supplier_id,
            "codigo": self.code, "quantidade": self.quantity,
            "quantidade_inicial": self.initial_quantity, "custo_unitario": float(self.unit_cost or 0),
            "localizacao": self.location,
            "recebido_em": self.received_at.isoformat() if self.received_at else None,
            "validade": self.expires_at.isoformat() if self.expires_at else None,
            "ativo": self.active,
        }


class StockReservation(db.Model):
    __tablename__ = "stock_reservations"
    __table_args__ = (
        db.Index("ix_stock_reservation_active", "part_id", "status"),
        db.Index("ix_stock_reservation_org_part_status", "organization_id", "part_id", "status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    part_id = db.Column(db.Integer, db.ForeignKey("pecas.id"), nullable=False, index=True)
    order_id = db.Column(db.Integer, db.ForeignKey("ordens_servico.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="active", index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_now)
    closed_at = db.Column(db.DateTime)

    part = db.relationship("Peca", backref=db.backref("reservations", lazy=True))
    order = db.relationship("OrdemServico", backref=db.backref("stock_reservations", lazy=True))
    user = db.relationship("Usuario")
