"""add single-use password reset tokens

Revision ID: 20260712_0003
Revises: 20260712_0002
"""
from alembic import op
import sqlalchemy as sa

revision = "20260712_0003"
down_revision = "20260712_0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.Column("expira_em", sa.DateTime(), nullable=False),
        sa.Column("usado_em", sa.DateTime()),
        sa.Column("solicitado_ip_hash", sa.String(length=64)),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
    )
    op.create_index("ix_password_reset_user_created", "password_reset_tokens", ["usuario_id", "criado_em"])
    op.create_index("ix_password_reset_expires", "password_reset_tokens", ["expira_em"])


def downgrade():
    op.drop_index("ix_password_reset_expires", table_name="password_reset_tokens")
    op.drop_index("ix_password_reset_user_created", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")
