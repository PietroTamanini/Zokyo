"""add order labor cost fields

Revision ID: 20260901_0014
Revises: 20260901_0013
"""
import sqlalchemy as sa
from alembic import op

revision = "20260901_0014"
down_revision = "20260901_0013"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ordens_servico", sa.Column("horas_trabalho", sa.Numeric(8, 2), nullable=False, server_default="0"))
    op.add_column("ordens_servico", sa.Column("custo_hora", sa.Numeric(10, 2), nullable=False, server_default="0"))


def downgrade():
    op.drop_column("ordens_servico", "custo_hora")
    op.drop_column("ordens_servico", "horas_trabalho")
