"""add physical inventory schema

Revision ID: 20261102_0036
Revises: 20261102_0035
"""
import sqlalchemy as sa
from alembic import op

revision = "20261102_0036"
down_revision = "20261102_0035"
branch_labels = None
depends_on = None


def _tables():
    return {row[0] for row in sa.inspect(op.get_bind()).get_table_names()}


def upgrade():
    tables = _tables()
    if "inventario_sessoes" not in tables:
        op.create_table(
            "inventario_sessoes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="aberto"),
            sa.Column("data_abertura", sa.DateTime(), nullable=False),
            sa.Column("data_fechamento", sa.DateTime()),
            sa.Column("responsavel_id", sa.Integer()),
            sa.Column("responsavel_nome", sa.String(120)),
            sa.Column("observacoes", sa.Text()),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.ForeignKeyConstraint(["responsavel_id"], ["usuarios.id"]),
        )
        op.create_index("ix_inventario_sessoes_organization_id", "inventario_sessoes", ["organization_id"])
        op.create_index("ix_inventario_sessao_org_status", "inventario_sessoes", ["organization_id", "status"])
        op.create_index("ix_inventario_sessao_org_aberta", "inventario_sessoes", ["organization_id", "status", "data_abertura"])

    if "inventario_itens" not in tables:
        op.create_table(
            "inventario_itens",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("sessao_id", sa.Integer(), nullable=False),
            sa.Column("peca_id", sa.Integer(), nullable=False),
            sa.Column("quantidade_sistema", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("quantidade_fisica", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("divergencia", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("justificativa", sa.Text()),
            sa.Column("aprovado", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("aprovado_em", sa.DateTime()),
            sa.Column("aprovado_por_id", sa.Integer()),
            sa.Column("aprovado_por_nome", sa.String(120)),
            sa.ForeignKeyConstraint(["sessao_id"], ["inventario_sessoes.id"]),
            sa.ForeignKeyConstraint(["peca_id"], ["pecas.id"]),
            sa.ForeignKeyConstraint(["aprovado_por_id"], ["usuarios.id"]),
            sa.UniqueConstraint("peca_id", "sessao_id", name="uq_inventario_peca_sessao"),
        )
        op.create_index("ix_inventario_itens_sessao_id", "inventario_itens", ["sessao_id"])
        op.create_index("ix_inventario_itens_peca_id", "inventario_itens", ["peca_id"])
        op.create_index("ix_inventario_peca_sessao", "inventario_itens", ["peca_id", "sessao_id"])

    if "inventario_ajustes" not in tables:
        op.create_table(
            "inventario_ajustes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organizacao_id", sa.Integer(), nullable=False),
            sa.Column("sessao_id", sa.Integer(), nullable=False),
            sa.Column("peca_id", sa.Integer(), nullable=False),
            sa.Column("quantidade_anterior", sa.Integer(), nullable=False),
            sa.Column("quantidade_nova", sa.Integer(), nullable=False),
            sa.Column("divergencia", sa.Integer(), nullable=False),
            sa.Column("justificativa", sa.Text(), nullable=False),
            sa.Column("aplicado_em", sa.DateTime(), nullable=False),
            sa.Column("aplicado_por_id", sa.Integer(), nullable=False),
            sa.Column("aplicado_por_nome", sa.String(120), nullable=False),
            sa.ForeignKeyConstraint(["organizacao_id"], ["organizations.id"]),
            sa.ForeignKeyConstraint(["sessao_id"], ["inventario_sessoes.id"]),
            sa.ForeignKeyConstraint(["peca_id"], ["pecas.id"]),
            sa.ForeignKeyConstraint(["aplicado_por_id"], ["usuarios.id"]),
        )
        op.create_index("ix_inventario_ajustes_organizacao_id", "inventario_ajustes", ["organizacao_id"])
        op.create_index("ix_inventario_ajustes_sessao_id", "inventario_ajustes", ["sessao_id"])
        op.create_index("ix_inventario_ajustes_peca_id", "inventario_ajustes", ["peca_id"])
        op.create_index("ix_inventario_ajuste_org_data", "inventario_ajustes", ["organizacao_id", "aplicado_em"])

    inspector = sa.inspect(op.get_bind())
    inventory_columns = {column["name"] for column in inspector.get_columns("inventory_movements")}
    if "quantity_delta" not in inventory_columns:
        op.add_column("inventory_movements", sa.Column("quantity_delta", sa.Integer(), nullable=True))
        op.execute("UPDATE inventory_movements SET quantity_delta = quantity_after - quantity_before")
        op.alter_column("inventory_movements", "quantity_delta", nullable=False)


def downgrade():
    op.drop_table("inventario_ajustes")
    op.drop_table("inventario_itens")
    op.drop_table("inventario_sessoes")
