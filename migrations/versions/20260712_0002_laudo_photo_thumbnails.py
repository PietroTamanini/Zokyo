"""add private thumbnail key to report photos

Revision ID: 20260712_0002
Revises: 20260711_0001
Create Date: 2026-07-12
"""
from alembic import op
import sqlalchemy as sa

revision = "20260712_0002"
down_revision = "20260711_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("laudo_fotos", sa.Column("thumbnail_key", sa.String(length=600), nullable=True))


def downgrade():
    op.drop_column("laudo_fotos", "thumbnail_key")
