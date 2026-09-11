"""add platform admin flag

Revision ID: 20260911_0023
Revises: 20260911_0022
Create Date: 2026-09-11 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = "20260911_0023"
down_revision = "20260911_0022"
branch_labels = None
depends_on = None


def _columns(table):
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade():
    existing = _columns("usuarios")
    if "is_platform_admin" not in existing:
        with op.batch_alter_table("usuarios") as batch:
            batch.add_column(sa.Column("is_platform_admin", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    existing = _columns("usuarios")
    if "is_platform_admin" in existing:
        with op.batch_alter_table("usuarios") as batch:
            batch.drop_column("is_platform_admin")
