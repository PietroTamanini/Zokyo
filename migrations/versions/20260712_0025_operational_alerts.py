"""Adiciona heartbeats e alertas operacionais.

Revision ID: 20260712_0025
Revises: 20260712_0024
"""
import sqlalchemy as sa
from alembic import op

revision = "20260712_0025"
down_revision = "20260712_0024"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "operational_heartbeats",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_name", sa.String(length=100), nullable=False, unique=True),
        sa.Column("last_started_at", sa.DateTime()),
        sa.Column("last_success_at", sa.DateTime()),
        sa.Column("last_failure_at", sa.DateTime()),
        sa.Column("last_duration_ms", sa.Integer()),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(length=500)),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "operational_alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("message", sa.String(length=500), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("occurrences", sa.Integer(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime()),
    )
    op.create_index("ix_operational_alerts_severity", "operational_alerts", ["severity"])
    op.create_index("ix_operational_alerts_source", "operational_alerts", ["source"])
    op.create_index("ix_operational_alerts_fingerprint", "operational_alerts", ["fingerprint"])


def downgrade():
    op.drop_table("operational_alerts")
    op.drop_table("operational_heartbeats")
