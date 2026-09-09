"""add performance indexes for daily screens

Revision ID: 20260909_0017
Revises: 20260907_0016
"""
from alembic import op

revision = "20260909_0017"
down_revision = "20260907_0016"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "ix_os_org_open_status_data",
        "ordens_servico",
        ["organization_id", "deletado_em", "baixada_em", "status", "data_entrada"],
    )
    op.create_index(
        "ix_os_org_open_prev",
        "ordens_servico",
        ["organization_id", "deletado_em", "baixada_em", "data_prev"],
    )
    op.create_index(
        "ix_transacoes_org_status_tipo_criado",
        "transacoes",
        ["organization_id", "status", "tipo", "criado_em"],
    )
    op.create_index(
        "ix_transacoes_org_status_venc",
        "transacoes",
        ["organization_id", "status", "data_vencimento"],
    )
    op.create_index(
        "ix_pecas_org_active_nome",
        "pecas",
        ["organization_id", "ativo", "deletado_em", "nome"],
    )
    op.create_index(
        "ix_pecas_org_active_categoria",
        "pecas",
        ["organization_id", "ativo", "deletado_em", "categoria"],
    )
    op.create_index(
        "ix_clientes_org_active_nome",
        "clientes",
        ["organization_id", "ativo", "nome"],
    )
    op.create_index(
        "ix_stock_reservation_org_part_status",
        "stock_reservations",
        ["organization_id", "part_id", "status"],
    )


def downgrade():
    op.drop_index("ix_stock_reservation_org_part_status", table_name="stock_reservations")
    op.drop_index("ix_clientes_org_active_nome", table_name="clientes")
    op.drop_index("ix_pecas_org_active_categoria", table_name="pecas")
    op.drop_index("ix_pecas_org_active_nome", table_name="pecas")
    op.drop_index("ix_transacoes_org_status_venc", table_name="transacoes")
    op.drop_index("ix_transacoes_org_status_tipo_criado", table_name="transacoes")
    op.drop_index("ix_os_org_open_prev", table_name="ordens_servico")
    op.drop_index("ix_os_org_open_status_data", table_name="ordens_servico")
