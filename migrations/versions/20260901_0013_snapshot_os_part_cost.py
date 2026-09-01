"""snapshot cost of parts used in service orders

Revision ID: 20260901_0013
Revises: 20260731_0012
"""
import sqlalchemy as sa
from alembic import op

revision = "20260901_0013"
down_revision = "20260731_0012"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("os_pecas", sa.Column("custo_unitario", sa.Numeric(10, 2), nullable=True))
    op.execute(
        "UPDATE os_pecas SET custo_unitario = "
        "(SELECT p.custo FROM pecas p WHERE p.id = os_pecas.peca_id) "
        "WHERE custo_unitario IS NULL"
    )


def downgrade():
    op.drop_column("os_pecas", "custo_unitario")
