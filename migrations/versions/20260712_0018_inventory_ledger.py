"""Adiciona livro de estoque e reservas por OS.

Revision ID: 20260712_0018
Revises: 20260712_0017
"""
import sqlalchemy as sa
from alembic import op

revision = "20260712_0018"
down_revision = "20260712_0017"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "inventory_movements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("part_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer()),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("movement_type", sa.String(length=30), nullable=False),
        sa.Column("quantity_delta", sa.Integer(), nullable=False),
        sa.Column("quantity_before", sa.Integer(), nullable=False),
        sa.Column("quantity_after", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=300), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_inventory_movement_org"),
        sa.ForeignKeyConstraint(["part_id"], ["pecas.id"], name="fk_inventory_movement_part"),
        sa.ForeignKeyConstraint(["order_id"], ["ordens_servico.id"], name="fk_inventory_movement_order"),
        sa.ForeignKeyConstraint(["user_id"], ["usuarios.id"], name="fk_inventory_movement_user"),
    )
    for name, columns in (
        ("ix_inventory_movements_organization_id", ["organization_id"]),
        ("ix_inventory_movements_part_id", ["part_id"]),
        ("ix_inventory_movements_order_id", ["order_id"]),
        ("ix_inventory_movements_movement_type", ["movement_type"]),
        ("ix_inventory_movements_created_at", ["created_at"]),
    ):
        op.create_index(name, "inventory_movements", columns)

    op.create_table(
        "stock_reservations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("part_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("closed_at", sa.DateTime()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_stock_reservation_org"),
        sa.ForeignKeyConstraint(["part_id"], ["pecas.id"], name="fk_stock_reservation_part"),
        sa.ForeignKeyConstraint(["order_id"], ["ordens_servico.id"], name="fk_stock_reservation_order"),
        sa.ForeignKeyConstraint(["user_id"], ["usuarios.id"], name="fk_stock_reservation_user"),
    )
    for name, columns in (
        ("ix_stock_reservations_organization_id", ["organization_id"]),
        ("ix_stock_reservations_part_id", ["part_id"]),
        ("ix_stock_reservations_order_id", ["order_id"]),
        ("ix_stock_reservations_status", ["status"]),
        ("ix_stock_reservation_active", ["part_id", "status"]),
    ):
        op.create_index(name, "stock_reservations", columns)


def downgrade():
    op.drop_table("stock_reservations")
    op.drop_table("inventory_movements")
