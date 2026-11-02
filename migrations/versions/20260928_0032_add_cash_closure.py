"""add cash closure tables

Revision ID: 20260928_0032
Revises: 20260927_0031
Create Date: 2026-09-28 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = "20260928_0032"
down_revision = "20260927_0031"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "caixas_sessoes" not in tables:
        op.create_table(
            "caixas_sessoes",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column(
                "organization_id",
                sa.Integer(),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("status", sa.String(length=10), nullable=False, server_default=sa.text("'aberto'")),
            sa.Column("data_abertura", sa.DateTime(), nullable=False),
            sa.Column("saldo_inicial", sa.Numeric(precision=12, scale=2), nullable=False, server_default=sa.text("0")),
            sa.Column("valor_fechado_esperado", sa.Numeric(precision=12, scale=2), nullable=False, server_default=sa.text("0")),
            sa.Column("valor_conferido", sa.Numeric(precision=12, scale=2), nullable=False, server_default=sa.text("0")),
            sa.Column("diferenca", sa.Numeric(precision=12, scale=2), nullable=False, server_default=sa.text("0")),
            sa.Column("observacoes", sa.Text(), nullable=True),
            sa.Column("responsavel_id", sa.Integer(), sa.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True),
            sa.Column("responsavel_nome", sa.String(length=120), nullable=True),
            sa.Column("fechada_em", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_caixas_org_status_abertura",
            "caixas_sessoes",
            ["organization_id", "status", "data_abertura"],
            unique=False,
        )

    if "caixa_movimentos" not in tables:
        op.create_table(
            "caixa_movimentos",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column(
                "organization_id",
                sa.Integer(),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "sessao_id",
                sa.Integer(),
                sa.ForeignKey("caixas_sessoes.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("tipo", sa.String(length=10), nullable=False),
            sa.Column("valor", sa.Numeric(precision=12, scale=2), nullable=False, server_default=sa.text("0")),
            sa.Column("forma_pagamento", sa.String(length=50), nullable=True),
            sa.Column("descricao", sa.String(length=300), nullable=True),
            sa.Column("responsavel_id", sa.Integer(), sa.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True),
            sa.Column("responsavel_nome", sa.String(length=120), nullable=True),
            sa.Column("criado_em", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_caixa_movimentos_org_sessao",
            "caixa_movimentos",
            ["organization_id", "sessao_id", "criado_em"],
            unique=False,
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()
    if "caixa_movimentos" in tables:
        op.drop_index("ix_caixa_movimentos_org_sessao", table_name="caixa_movimentos")
        op.drop_table("caixa_movimentos")
    if "caixas_sessoes" in tables:
        op.drop_index("ix_caixas_org_status_abertura", table_name="caixas_sessoes")
        op.drop_table("caixas_sessoes")
