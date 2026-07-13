"""Remove configuracao obsoleta do wkhtmltopdf.

Revision ID: 20260712_0015
Revises: 20260712_0014
"""
from alembic import op
import sqlalchemy as sa


revision = "20260712_0015"
down_revision = "20260712_0014"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column("configuracoes", "wkhtmltopdf_path")


def downgrade():
    op.add_column("configuracoes", sa.Column("wkhtmltopdf_path", sa.String(length=500)))
