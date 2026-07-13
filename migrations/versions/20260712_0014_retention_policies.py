"""Politicas operacionais de retencao.

Revision ID: 20260712_0014
Revises: 20260712_0013
"""
from alembic import op
import sqlalchemy as sa


revision = "20260712_0014"
down_revision = "20260712_0013"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "retention_policies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=60), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("approved_by_id", sa.Integer()), sa.Column("approved_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_retention_organization"),
        sa.ForeignKeyConstraint(["approved_by_id"], ["usuarios.id"], name="fk_retention_approver"),
        sa.UniqueConstraint("organization_id", "category", name="uq_retention_org_category"),
    )
    op.create_index("ix_retention_policies_organization_id", "retention_policies", ["organization_id"])


def downgrade():
    op.drop_index("ix_retention_policies_organization_id", table_name="retention_policies")
    op.drop_table("retention_policies")
