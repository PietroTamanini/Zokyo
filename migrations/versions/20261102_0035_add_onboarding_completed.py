"""add onboarding completed flag to tenant configuration

Revision ID: 20261102_0035
Revises: 20261102_0034
Create Date: 2026-11-02 18:20:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = "20261102_0035"
down_revision = "20261102_0034"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("configuracoes")}
    if "onboarding_completed" not in columns:
        op.add_column(
            "configuracoes",
            sa.Column("onboarding_completed", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        )


def downgrade():
    op.drop_column("configuracoes", "onboarding_completed")
