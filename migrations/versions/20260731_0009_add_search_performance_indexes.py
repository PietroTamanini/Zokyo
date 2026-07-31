"""Add indexes for daily search and dashboard queries."""

import sqlalchemy as sa
from alembic import op

revision = "20260731_0009"
down_revision = "20260731_0008"
branch_labels = None
depends_on = None


INDEXES = (
    ("ix_clientes_nome", "clientes", ("nome",), False),
    ("ix_clientes_telefone", "clientes", ("telefone",), False),
    ("ix_defeitos_padrao_sintoma", "defeitos_padrao", ("sintoma",), False),
    ("ix_defeitos_padrao_tipo_aparelho", "defeitos_padrao", ("tipo_aparelho",), False),
    ("ix_fornecedores_nome", "fornecedores", ("nome",), False),
    ("ix_fornecedores_telefone", "fornecedores", ("telefone",), False),
    ("ix_ordens_servico_numero_serie", "ordens_servico", ("numero_serie",), False),
    ("ix_pecas_nome", "pecas", ("nome",), False),
    ("ix_pecas_codigo", "pecas", ("codigo",), False),
    ("ix_transacoes_status_tipo_criado", "transacoes", ("status", "tipo", "criado_em"), False),
    ("ix_transacoes_descricao", "transacoes", ("descricao",), False),
)


def _existing_indexes(table_name):
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {item["name"] for item in inspector.get_indexes(table_name)}


def upgrade():
    for name, table_name, columns, unique in INDEXES:
        if name not in _existing_indexes(table_name):
            op.create_index(name, table_name, list(columns), unique=unique)


def downgrade():
    for name, table_name, _columns, _unique in reversed(INDEXES):
        if name in _existing_indexes(table_name):
            op.drop_index(name, table_name=table_name)
