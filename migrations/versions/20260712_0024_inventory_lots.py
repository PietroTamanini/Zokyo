"""Adiciona lotes, validade e custo medio.

Revision ID: 20260712_0024
Revises: 20260712_0023
"""
import sqlalchemy as sa
from alembic import op

revision = "20260712_0024"
down_revision = "20260712_0023"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "inventory_lots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("part_id", sa.Integer(), nullable=False),
        sa.Column("supplier_id", sa.Integer()),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("initial_quantity", sa.Integer(), nullable=False),
        sa.Column("unit_cost", sa.Numeric(10, 2), nullable=False),
        sa.Column("location", sa.String(length=100)),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime()),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.CheckConstraint("quantity >= 0", name="ck_inventory_lot_quantity_nonnegative"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_inventory_lot_org"),
        sa.ForeignKeyConstraint(["part_id"], ["pecas.id"], name="fk_inventory_lot_part"),
        sa.ForeignKeyConstraint(["supplier_id"], ["fornecedores.id"], name="fk_inventory_lot_supplier"),
        sa.UniqueConstraint("organization_id", "part_id", "code", name="uq_inventory_lot_part_code"),
    )
    op.create_index("ix_inventory_lots_organization_id", "inventory_lots", ["organization_id"])
    op.create_index("ix_inventory_lots_part_id", "inventory_lots", ["part_id"])
    op.create_index("ix_inventory_lots_expires_at", "inventory_lots", ["expires_at"])
    with op.batch_alter_table("inventory_movements") as batch:
        batch.add_column(sa.Column("lot_id", sa.Integer()))
        batch.create_foreign_key("fk_inventory_movement_lot", "inventory_lots", ["lot_id"], ["id"])
        batch.create_index("ix_inventory_movements_lot_id", ["lot_id"])


def downgrade():
    with op.batch_alter_table("inventory_movements") as batch:
        batch.drop_index("ix_inventory_movements_lot_id")
        batch.drop_constraint("fk_inventory_movement_lot", type_="foreignkey")
        batch.drop_column("lot_id")
    op.drop_table("inventory_lots")
