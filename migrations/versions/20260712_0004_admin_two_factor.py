"""add administrator TOTP fields

Revision ID: 20260712_0004
Revises: 20260712_0003
"""
from alembic import op
import sqlalchemy as sa

revision = "20260712_0004"
down_revision = "20260712_0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("usuarios", sa.Column("totp_secret_encrypted", sa.Text()))
    op.add_column("usuarios", sa.Column("totp_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("usuarios", sa.Column("recovery_codes_hash", sa.JSON()))


def downgrade():
    op.drop_column("usuarios", "recovery_codes_hash")
    op.drop_column("usuarios", "totp_enabled")
    op.drop_column("usuarios", "totp_secret_encrypted")
