"""allow platform admin without tenant

Revision ID: 20260911_0024
Revises: 20260911_0023
Create Date: 2026-09-11 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = "20260911_0024"
down_revision = "20260911_0023"
branch_labels = None
depends_on = None


def _columns(table):
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"]: column for column in inspector.get_columns(table)}


def _set_nullable(table, column, nullable):
    existing = _columns(table)
    if column not in existing or existing[column].get("nullable") is nullable:
        return
    with op.batch_alter_table(table) as batch:
        batch.alter_column(
            column,
            existing_type=sa.Integer(),
            nullable=nullable,
            existing_nullable=not nullable,
        )


def upgrade():
    _set_nullable("usuarios", "organization_id", True)
    _set_nullable("user_sessions", "organization_id", True)
    _set_nullable("eventos_log", "organization_id", True)


def downgrade():
    op.execute("UPDATE usuarios SET organization_id = 1 WHERE organization_id IS NULL")
    op.execute("UPDATE user_sessions SET organization_id = 1 WHERE organization_id IS NULL")
    op.execute("UPDATE eventos_log SET organization_id = 1 WHERE organization_id IS NULL")
    _set_nullable("eventos_log", "organization_id", False)
    _set_nullable("user_sessions", "organization_id", False)
    _set_nullable("usuarios", "organization_id", False)
