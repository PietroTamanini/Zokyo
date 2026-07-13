"""Planos, assinaturas e eventos de billing sandbox.

Revision ID: 20260712_0010
Revises: 20260712_0009
"""
from alembic import op
import sqlalchemy as sa


revision = "20260712_0010"
down_revision = "20260712_0009"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=50), nullable=False, unique=True),
        sa.Column("nome", sa.String(length=100), nullable=False),
        sa.Column("limites", sa.JSON(), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "organization_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False, server_default="sandbox"),
        sa.Column("external_id", sa.String(length=120)),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="trialing"),
        sa.Column("periodo_fim", sa.DateTime()),
        sa.Column("cancelado_em", sa.DateTime()),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_subscription_organization"),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], name="fk_subscription_plan"),
    )
    op.create_table(
        "billing_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("external_event_id", sa.String(length=160), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("processado_em", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_billing_event_organization"),
        sa.UniqueConstraint("provider", "external_event_id", name="uq_billing_provider_event"),
    )


def downgrade():
    op.drop_table("billing_events")
    op.drop_table("organization_subscriptions")
    op.drop_table("plans")
