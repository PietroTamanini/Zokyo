"""Adiciona assinaturas verificaveis de OS.

Revision ID: 20260712_0026
Revises: 20260712_0025
"""
import sqlalchemy as sa
from alembic import op

revision = "20260712_0026"
down_revision = "20260712_0025"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "order_signatures",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("captured_by_id", sa.Integer(), nullable=False),
        sa.Column("signer_name", sa.String(length=120), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False, unique=True),
        sa.Column("mime_type", sa.String(length=40), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("ip_address", sa.String(length=45)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_order_signature_org"),
        sa.ForeignKeyConstraint(["order_id"], ["ordens_servico.id"], name="fk_order_signature_order"),
        sa.ForeignKeyConstraint(["captured_by_id"], ["usuarios.id"], name="fk_order_signature_user"),
    )
    op.create_index("ix_order_signatures_organization_id", "order_signatures", ["organization_id"])
    op.create_index("ix_order_signatures_order_id", "order_signatures", ["order_id"])


def downgrade():
    op.drop_table("order_signatures")
