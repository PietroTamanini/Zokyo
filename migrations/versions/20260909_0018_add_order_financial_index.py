"""add index for order financial analytics

Revision ID: 20260909_0018
Revises: 20260909_0017
"""
from alembic import op

revision = "20260909_0018"
down_revision = "20260909_0017"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "ix_transacoes_org_os_status_tipo_venc",
        "transacoes",
        ["organization_id", "os_id", "status", "tipo", "data_vencimento"],
    )


def downgrade():
    op.drop_index("ix_transacoes_org_os_status_tipo_venc", table_name="transacoes")
