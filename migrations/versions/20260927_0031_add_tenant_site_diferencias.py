"""add tenant site diferencias fields

Revision ID: 20260927_0031
Revises: 20260926_0030
Create Date: 2026-09-27 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = "20260927_0031"
down_revision = "20260926_0030"
branch_labels = None
depends_on = None


def _columns(table):
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "tenant_sites" in inspector.get_table_names():
        if "diferencias_json" not in _columns("tenant_sites"):
            op.add_column("tenant_sites", sa.Column("diferencias_json", sa.Text(), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "tenant_sites" in inspector.get_table_names():
        if "diferencias_json" in _columns("tenant_sites"):
            op.drop_column("tenant_sites", "diferencias_json")
