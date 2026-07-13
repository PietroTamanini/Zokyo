"""Adiciona sessoes persistentes e revogaveis.

Revision ID: 20260712_0017
Revises: 20260712_0016
"""
import sqlalchemy as sa
from alembic import op

revision = "20260712_0017"
down_revision = "20260712_0016"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("security_version", sa.Integer(), nullable=False),
        sa.Column("ip_address", sa.String(length=45)),
        sa.Column("user_agent", sa.String(length=300)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime()),
        sa.Column("revoked_reason", sa.String(length=100)),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_user_session_organization"),
        sa.ForeignKeyConstraint(["user_id"], ["usuarios.id"], name="fk_user_session_user"),
    )
    op.create_index("ix_user_sessions_organization_id", "user_sessions", ["organization_id"])
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_index("ix_user_sessions_user_active", "user_sessions", ["user_id", "revoked_at", "expires_at"])


def downgrade():
    op.drop_index("ix_user_sessions_user_active", table_name="user_sessions")
    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_index("ix_user_sessions_organization_id", table_name="user_sessions")
    op.drop_table("user_sessions")
