"""Fila persistente de notificacoes.

Revision ID: 20260712_0012
Revises: 20260712_0011
"""
from alembic import op
import sqlalchemy as sa


revision = "20260712_0012"
down_revision = "20260712_0011"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(length=30), nullable=False, server_default="whatsapp"),
        sa.Column("recipient", sa.String(length=80), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=False),
        sa.Column("last_error", sa.Text()),
        sa.Column("sent_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_notification_organization"),
        sa.UniqueConstraint("organization_id", "idempotency_key", name="uq_notification_org_key"),
    )
    op.create_index("ix_notifications_organization_id", "notifications", ["organization_id"])
    op.create_index("ix_notifications_status", "notifications", ["status"])
    op.create_index("ix_notifications_next_attempt_at", "notifications", ["next_attempt_at"])


def downgrade():
    op.drop_index("ix_notifications_next_attempt_at", table_name="notifications")
    op.drop_index("ix_notifications_status", table_name="notifications")
    op.drop_index("ix_notifications_organization_id", table_name="notifications")
    op.drop_table("notifications")
