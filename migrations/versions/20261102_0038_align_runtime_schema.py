"""align runtime defaults and cash foreign-key behavior

Revision ID: 20261102_0038
Revises: 20261102_0037
"""
import sqlalchemy as sa
from alembic import op

revision = "20261102_0038"
down_revision = "20261102_0037"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name not in {"mysql", "mariadb"}:
        return
    op.alter_column(
        "configuracoes",
        "onboarding_step",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default="1",
    )
    op.alter_column(
        "configuracoes",
        "onboarding_completed",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default="0",
    )


def downgrade():
    if op.get_bind().dialect.name not in {"mysql", "mariadb"}:
        return
    op.alter_column(
        "configuracoes",
        "onboarding_completed",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "configuracoes",
        "onboarding_step",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default=None,
    )
