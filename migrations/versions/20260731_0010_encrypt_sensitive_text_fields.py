"""prepare sensitive text fields for transparent encryption

Revision ID: 20260731_0010
Revises: 20260731_0009
Create Date: 2026-07-31
"""
import sqlalchemy as sa
from alembic import op

revision = "20260731_0010"
down_revision = "20260731_0009"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("clientes") as batch_op:
        batch_op.alter_column("endereco", existing_type=sa.String(length=300), type_=sa.Text(), existing_nullable=True)
        batch_op.alter_column("numero_casa", existing_type=sa.String(length=20), type_=sa.Text(), existing_nullable=True)

    with op.batch_alter_table("fornecedores") as batch_op:
        batch_op.alter_column("endereco", existing_type=sa.String(length=300), type_=sa.Text(), existing_nullable=True)

    with op.batch_alter_table("coletas_agendadas") as batch_op:
        batch_op.alter_column("telefone_contato", existing_type=sa.String(length=20), type_=sa.Text(), existing_nullable=True)
        batch_op.alter_column("endereco", existing_type=sa.String(length=300), type_=sa.Text(), existing_nullable=True)
        batch_op.alter_column("numero_casa", existing_type=sa.String(length=20), type_=sa.Text(), existing_nullable=True)
        batch_op.alter_column("observacoes", existing_type=sa.Text(), type_=sa.Text(), existing_nullable=True)

    with op.batch_alter_table("configuracoes") as batch_op:
        batch_op.alter_column("endereco", existing_type=sa.String(length=300), type_=sa.Text(), existing_nullable=True)
        batch_op.alter_column("pix_chave", existing_type=sa.String(length=200), type_=sa.Text(), existing_nullable=True)
        batch_op.alter_column("dados_pagamento", existing_type=sa.Text(), type_=sa.Text(), existing_nullable=True)


def downgrade():
    with op.batch_alter_table("configuracoes") as batch_op:
        batch_op.alter_column("dados_pagamento", existing_type=sa.Text(), type_=sa.Text(), existing_nullable=True)
        batch_op.alter_column("pix_chave", existing_type=sa.Text(), type_=sa.String(length=200), existing_nullable=True)
        batch_op.alter_column("endereco", existing_type=sa.Text(), type_=sa.String(length=300), existing_nullable=True)

    with op.batch_alter_table("coletas_agendadas") as batch_op:
        batch_op.alter_column("observacoes", existing_type=sa.Text(), type_=sa.Text(), existing_nullable=True)
        batch_op.alter_column("numero_casa", existing_type=sa.Text(), type_=sa.String(length=20), existing_nullable=True)
        batch_op.alter_column("endereco", existing_type=sa.Text(), type_=sa.String(length=300), existing_nullable=True)
        batch_op.alter_column("telefone_contato", existing_type=sa.Text(), type_=sa.String(length=20), existing_nullable=True)

    with op.batch_alter_table("fornecedores") as batch_op:
        batch_op.alter_column("endereco", existing_type=sa.Text(), type_=sa.String(length=300), existing_nullable=True)

    with op.batch_alter_table("clientes") as batch_op:
        batch_op.alter_column("numero_casa", existing_type=sa.Text(), type_=sa.String(length=20), existing_nullable=True)
        batch_op.alter_column("endereco", existing_type=sa.Text(), type_=sa.String(length=300), existing_nullable=True)
