"""add onboarding step to tenant configuration

Revision ID: 20261102_0034
Revises: 20261102_0033
Create Date: 2026-11-02 18:16:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = "20261102_0034"
down_revision = "20261102_0033"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("configuracoes")}
    if "onboarding_step" not in columns:
        op.add_column(
            "configuracoes",
            sa.Column("onboarding_step", sa.Integer(), nullable=False, server_default="1"),
        )


def downgrade():
    op.drop_column("configuracoes", "onboarding_step")
