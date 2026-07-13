"""Adiciona filtros salvos e relatorios agendados.

Revision ID: 20260712_0023
Revises: 20260712_0022
"""
import sqlalchemy as sa
from alembic import op

revision = "20260712_0023"
down_revision = "20260712_0022"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "saved_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("report_type", sa.String(length=40), nullable=False),
        sa.Column("filters", sa.JSON(), nullable=False),
        sa.Column("frequency", sa.String(length=20)),
        sa.Column("recipient", sa.String(length=254)),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("next_run_at", sa.DateTime()),
        sa.Column("last_run_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_saved_report_org"),
        sa.ForeignKeyConstraint(["user_id"], ["usuarios.id"], name="fk_saved_report_user"),
    )
    op.create_index("ix_saved_reports_organization_id", "saved_reports", ["organization_id"])
    op.create_index("ix_saved_reports_next_run_at", "saved_reports", ["next_run_at"])


def downgrade():
    op.drop_table("saved_reports")
