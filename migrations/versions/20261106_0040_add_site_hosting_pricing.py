"""add optional hosted site pricing to plans and subscriptions

Revision ID: 20261106_0040
Revises: 20261105_0039
"""
import sqlalchemy as sa
from alembic import op

revision = "20261106_0040"
down_revision = "20261105_0039"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("plans", sa.Column("hospedagem_percentual", sa.Numeric(5, 2), nullable=False, server_default="0"))
    op.add_column("organization_subscriptions", sa.Column("site_hospedado", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column("organization_subscriptions", "site_hospedado")
    op.drop_column("plans", "hospedagem_percentual")
