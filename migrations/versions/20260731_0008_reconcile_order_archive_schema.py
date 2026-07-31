"""Reconcile archived order schema constraints."""

import sqlalchemy as sa
from alembic import op

revision = "20260731_0008"
down_revision = "20260731_0007"
branch_labels = None
depends_on = None


def _foreign_key_name(table_name, constrained_columns, referred_table):
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    expected_columns = tuple(constrained_columns)
    for fk in inspector.get_foreign_keys(table_name):
        if tuple(fk.get("constrained_columns") or ()) != expected_columns:
            continue
        if fk.get("referred_table") == referred_table:
            return fk.get("name")
    return None


def upgrade():
    if op.get_bind().dialect.name == "sqlite":
        return
    if not _foreign_key_name("ordens_servico", ("baixada_por_id",), "usuarios"):
        op.create_foreign_key(
            "fk_ordens_servico_baixada_por_id_usuarios",
            "ordens_servico",
            "usuarios",
            ["baixada_por_id"],
            ["id"],
        )


def downgrade():
    if op.get_bind().dialect.name == "sqlite":
        return
    fk_name = _foreign_key_name("ordens_servico", ("baixada_por_id",), "usuarios")
    if fk_name:
        op.drop_constraint(fk_name, "ordens_servico", type_="foreignkey")
