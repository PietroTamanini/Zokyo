"""Adiciona versao de seguranca para revogacao de sessoes.

Revision ID: 20260712_0016
Revises: 20260712_0015
"""
import sqlalchemy as sa
from alembic import op

revision = "20260712_0016"
down_revision = "20260712_0015"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("usuarios") as batch:
        batch.add_column(sa.Column("security_version", sa.Integer(), nullable=False, server_default="1"))


def downgrade():
    with op.batch_alter_table("usuarios") as batch:
        batch.drop_column("security_version")
