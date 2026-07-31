"""archive products and services

Revision ID: 20260731_0012
Revises: 20260731_0011
Create Date: 2026-07-31
"""

import sqlalchemy as sa
from alembic import op

revision = "20260731_0012"
down_revision = "20260731_0011"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("pecas") as batch_op:
        batch_op.add_column(sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column("deletado_em", sa.DateTime(), nullable=True))
        batch_op.create_index("ix_pecas_ativo", ["ativo"])
        batch_op.create_index("ix_pecas_deletado_em", ["deletado_em"])

    with op.batch_alter_table("defeitos_padrao") as batch_op:
        batch_op.add_column(sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column("deletado_em", sa.DateTime(), nullable=True))
        batch_op.create_index("ix_defeitos_padrao_ativo", ["ativo"])
        batch_op.create_index("ix_defeitos_padrao_deletado_em", ["deletado_em"])


def downgrade():
    with op.batch_alter_table("defeitos_padrao") as batch_op:
        batch_op.drop_index("ix_defeitos_padrao_deletado_em")
        batch_op.drop_index("ix_defeitos_padrao_ativo")
        batch_op.drop_column("deletado_em")
        batch_op.drop_column("ativo")

    with op.batch_alter_table("pecas") as batch_op:
        batch_op.drop_index("ix_pecas_deletado_em")
        batch_op.drop_index("ix_pecas_ativo")
        batch_op.drop_column("deletado_em")
        batch_op.drop_column("ativo")
