"""Add visible OS number and archive fields."""

import sqlalchemy as sa
from alembic import op

revision = "20260729_0003"
down_revision = "20260729_0002"
branch_labels = None
depends_on = None


def _existing_columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table_name)}


def _existing_indexes(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade():
    existing = _existing_columns("ordens_servico")
    if "numero" not in existing:
        op.add_column("ordens_servico", sa.Column("numero", sa.Integer(), nullable=True))
    if "baixada_em" not in existing:
        op.add_column("ordens_servico", sa.Column("baixada_em", sa.DateTime(), nullable=True))
    if "baixada_por_id" not in existing:
        op.add_column("ordens_servico", sa.Column("baixada_por_id", sa.Integer(), nullable=True))
    if "baixa_observacao" not in existing:
        op.add_column("ordens_servico", sa.Column("baixa_observacao", sa.String(length=300), nullable=True))

    bind = op.get_bind()
    bind.execute(sa.text("UPDATE ordens_servico SET numero = id WHERE numero IS NULL"))

    indexes = _existing_indexes("ordens_servico")
    if "ix_ordens_servico_numero" not in indexes:
        op.create_index("ix_ordens_servico_numero", "ordens_servico", ["numero"], unique=False)
    if "ix_ordens_servico_baixada_em" not in indexes:
        op.create_index("ix_ordens_servico_baixada_em", "ordens_servico", ["baixada_em"], unique=False)
    if "uq_ordens_servico_org_numero" not in indexes:
        op.create_index("uq_ordens_servico_org_numero", "ordens_servico", ["organization_id", "numero"], unique=True)


def downgrade():
    indexes = _existing_indexes("ordens_servico")
    for name in ("uq_ordens_servico_org_numero", "ix_ordens_servico_baixada_em", "ix_ordens_servico_numero"):
        if name in indexes:
            op.drop_index(name, table_name="ordens_servico")
    existing = _existing_columns("ordens_servico")
    for name in ("baixa_observacao", "baixada_por_id", "baixada_em", "numero"):
        if name in existing:
            op.drop_column("ordens_servico", name)
