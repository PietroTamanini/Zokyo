"""Adiciona templates versionados de mensagens.

Revision ID: 20260712_0021
Revises: 20260712_0020
"""
import sqlalchemy as sa
from alembic import op

revision = "20260712_0021"
down_revision = "20260712_0020"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "message_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("subject", sa.String(length=200)),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_message_template_org"),
        sa.UniqueConstraint("organization_id", "event_type", "channel", "version", name="uq_message_template_version"),
    )
    op.create_index("ix_message_templates_organization_id", "message_templates", ["organization_id"])
    op.create_index("ix_message_templates_event_type", "message_templates", ["event_type"])


def downgrade():
    op.drop_table("message_templates")
