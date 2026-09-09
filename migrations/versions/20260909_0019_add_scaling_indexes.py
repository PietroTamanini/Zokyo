"""add scaling indexes for large tenant datasets

Revision ID: 20260909_0019
Revises: 20260909_0018
Create Date: 2026-09-09 17:05:00.000000
"""
from alembic import op


revision = "20260909_0019"
down_revision = "20260909_0018"
branch_labels = None
depends_on = None


def _create_index(name, table, columns, unique=False):
    bind = op.get_bind()
    inspector = __import__("sqlalchemy").inspect(bind)
    existing = {idx["name"] for idx in inspector.get_indexes(table)}
    if name not in existing:
        op.create_index(name, table, columns, unique=unique)


def _drop_index(name, table):
    bind = op.get_bind()
    inspector = __import__("sqlalchemy").inspect(bind)
    existing = {idx["name"] for idx in inspector.get_indexes(table)}
    if name in existing:
        op.drop_index(name, table_name=table)


def upgrade():
    _create_index("ix_os_org_cliente_deleted", "ordens_servico", ["organization_id", "cliente_id", "deletado_em"])
    _create_index("ix_os_org_baixada_saida", "ordens_servico", ["organization_id", "baixada_em", "data_saida"])
    _create_index("ix_fornecedores_org_active_nome", "fornecedores", ["organization_id", "ativo", "nome"])
    _create_index(
        "ix_defeitos_org_active_tipo_sintoma",
        "defeitos_padrao",
        ["organization_id", "ativo", "deletado_em", "tipo_aparelho", "sintoma"],
    )
    _create_index("ix_eventos_org_criado", "eventos_log", ["organization_id", "criado_em"])
    _create_index("ix_eventos_org_tipo_criado", "eventos_log", ["organization_id", "tipo", "criado_em"])
    _create_index("ix_eventos_org_modulo_criado", "eventos_log", ["organization_id", "modulo", "criado_em"])
    _create_index("ix_os_historico_os_criado", "os_historico", ["os_id", "criado_em"])
    _create_index("ix_os_historico_org_criado", "os_historico", ["organization_id", "criado_em"])
    _create_index("ix_inventory_movements_org_created", "inventory_movements", ["organization_id", "created_at"])
    _create_index("ix_inventory_movements_org_part_created", "inventory_movements", ["organization_id", "part_id", "created_at"])
    _create_index("ix_inventory_movements_org_type_created", "inventory_movements", ["organization_id", "movement_type", "created_at"])
    _create_index("ix_inventory_lots_org_part_active", "inventory_lots", ["organization_id", "part_id", "active"])
    _create_index("ix_inventory_lots_org_expires", "inventory_lots", ["organization_id", "expires_at"])


def downgrade():
    _drop_index("ix_inventory_lots_org_expires", "inventory_lots")
    _drop_index("ix_inventory_lots_org_part_active", "inventory_lots")
    _drop_index("ix_inventory_movements_org_type_created", "inventory_movements")
    _drop_index("ix_inventory_movements_org_part_created", "inventory_movements")
    _drop_index("ix_inventory_movements_org_created", "inventory_movements")
    _drop_index("ix_os_historico_org_criado", "os_historico")
    _drop_index("ix_os_historico_os_criado", "os_historico")
    _drop_index("ix_eventos_org_modulo_criado", "eventos_log")
    _drop_index("ix_eventos_org_tipo_criado", "eventos_log")
    _drop_index("ix_eventos_org_criado", "eventos_log")
    _drop_index("ix_defeitos_org_active_tipo_sintoma", "defeitos_padrao")
    _drop_index("ix_fornecedores_org_active_nome", "fornecedores")
    _drop_index("ix_os_org_baixada_saida", "ordens_servico")
    _drop_index("ix_os_org_cliente_deleted", "ordens_servico")
