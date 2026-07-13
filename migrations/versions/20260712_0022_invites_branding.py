"""Adiciona convites e branding por organizacao.

Revision ID: 20260712_0022
Revises: 20260712_0021
"""
import sqlalchemy as sa
from alembic import op

revision = "20260712_0022"
down_revision = "20260712_0021"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_invites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("invited_by_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime()),
        sa.Column("revoked_at", sa.DateTime()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_user_invite_org"),
        sa.ForeignKeyConstraint(["invited_by_id"], ["usuarios.id"], name="fk_user_invite_sender"),
    )
    op.create_index("ix_user_invites_organization_id", "user_invites", ["organization_id"])
    op.create_index("ix_user_invites_email", "user_invites", ["email"])
    with op.batch_alter_table("configuracoes") as batch:
        batch.add_column(sa.Column("primary_color", sa.String(length=7), server_default="#2563eb"))
        batch.add_column(sa.Column("accent_color", sa.String(length=7), server_default="#6366f1"))


def downgrade():
    with op.batch_alter_table("configuracoes") as batch:
        batch.drop_column("accent_color")
        batch.drop_column("primary_color")
    op.drop_table("user_invites")
