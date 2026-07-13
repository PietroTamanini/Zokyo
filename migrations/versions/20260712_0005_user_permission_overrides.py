"""add granular user permission overrides

Revision ID: 20260712_0005
Revises: 20260712_0004
"""
from alembic import op
import sqlalchemy as sa

revision = "20260712_0005"
down_revision = "20260712_0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("usuarios", sa.Column("permissoes_extra", sa.JSON()))
    op.add_column("usuarios", sa.Column("permissoes_negadas", sa.JSON()))


def downgrade():
    op.drop_column("usuarios", "permissoes_negadas")
    op.drop_column("usuarios", "permissoes_extra")
