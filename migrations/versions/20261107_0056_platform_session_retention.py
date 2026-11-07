"""Add an independent, approval-gated platform retention policy.

Revision ID: 20261107_0056
Revises: 20261107_0055
"""
import sqlalchemy as sa
from alembic import op

revision = "20261107_0056"
down_revision = "20261107_0055"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "platform_retention_policies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("category", sa.String(length=60), nullable=False, unique=True),
        sa.Column("retention_days", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("approval_reference", sa.String(length=40)),
        sa.Column("approved_by_id", sa.Integer(), sa.ForeignKey("usuarios.id")),
        sa.Column("approved_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade():
    op.drop_table("platform_retention_policies")
