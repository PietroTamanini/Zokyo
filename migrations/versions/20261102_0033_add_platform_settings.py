"""add platform settings

Revision ID: 20261102_0033
Revises: 20260928_0032
Create Date: 2026-11-02 18:10:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = "20261102_0033"
down_revision = "20260928_0032"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "platform_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("value", sa.String(length=500), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )


def downgrade():
    op.drop_table("platform_settings")
