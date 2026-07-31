"""add blind indexes for sensitive exact-match fields

Revision ID: 20260731_0011
Revises: 20260731_0010
Create Date: 2026-07-31
"""
import sqlalchemy as sa
from alembic import op

revision = "20260731_0011"
down_revision = "20260731_0010"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("clientes") as batch_op:
        batch_op.add_column(sa.Column("cpf_bidx", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("cnpj_bidx", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("telefone_bidx", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("email_bidx", sa.String(length=64), nullable=True))
        batch_op.create_index("ix_clientes_cpf_bidx", ["cpf_bidx"])
        batch_op.create_index("ix_clientes_cnpj_bidx", ["cnpj_bidx"])
        batch_op.create_index("ix_clientes_telefone_bidx", ["telefone_bidx"])
        batch_op.create_index("ix_clientes_email_bidx", ["email_bidx"])

    with op.batch_alter_table("fornecedores") as batch_op:
        batch_op.add_column(sa.Column("cnpj_bidx", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("telefone_bidx", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("email_bidx", sa.String(length=64), nullable=True))
        batch_op.create_index("ix_fornecedores_cnpj_bidx", ["cnpj_bidx"])
        batch_op.create_index("ix_fornecedores_telefone_bidx", ["telefone_bidx"])
        batch_op.create_index("ix_fornecedores_email_bidx", ["email_bidx"])

    with op.batch_alter_table("usuarios") as batch_op:
        batch_op.add_column(sa.Column("email_bidx", sa.String(length=64), nullable=True))
        batch_op.create_index("ix_usuarios_email_bidx", ["email_bidx"])


def downgrade():
    with op.batch_alter_table("usuarios") as batch_op:
        batch_op.drop_index("ix_usuarios_email_bidx")
        batch_op.drop_column("email_bidx")

    with op.batch_alter_table("fornecedores") as batch_op:
        batch_op.drop_index("ix_fornecedores_email_bidx")
        batch_op.drop_index("ix_fornecedores_telefone_bidx")
        batch_op.drop_index("ix_fornecedores_cnpj_bidx")
        batch_op.drop_column("email_bidx")
        batch_op.drop_column("telefone_bidx")
        batch_op.drop_column("cnpj_bidx")

    with op.batch_alter_table("clientes") as batch_op:
        batch_op.drop_index("ix_clientes_email_bidx")
        batch_op.drop_index("ix_clientes_telefone_bidx")
        batch_op.drop_index("ix_clientes_cnpj_bidx")
        batch_op.drop_index("ix_clientes_cpf_bidx")
        batch_op.drop_column("email_bidx")
        batch_op.drop_column("telefone_bidx")
        batch_op.drop_column("cnpj_bidx")
        batch_op.drop_column("cpf_bidx")
