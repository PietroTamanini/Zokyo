"""Estado individual de onboarding.

Revision ID: 20260712_0013
Revises: 20260712_0012
"""
from alembic import op
import sqlalchemy as sa


revision = "20260712_0013"
down_revision = "20260712_0012"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("usuarios", sa.Column("onboarding_completed", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade():
    op.drop_column("usuarios", "onboarding_completed")
