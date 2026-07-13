"""propagate tenant ownership to remaining business tables

Revision ID: 20260712_0007
Revises: 20260712_0006
"""
from alembic import op
import sqlalchemy as sa

revision = "20260712_0007"
down_revision = "20260712_0006"
branch_labels = None
depends_on = None

TABLES = (
    "pecas", "fornecedores", "transacoes", "eventos_log", "coletas_agendadas",
    "os_fotos", "defeitos_padrao", "os_historico", "laudo_fotos", "laudo_eventos",
)


def upgrade():
    for table in TABLES:
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("organization_id", sa.Integer(), nullable=False, server_default="1"))
            batch.create_index(f"ix_{table}_organization_id", ["organization_id"])
            batch.create_foreign_key(f"fk_{table}_organization", "organizations", ["organization_id"], ["id"])
    with op.batch_alter_table("configuracoes") as batch:
        batch.add_column(sa.Column("organization_id", sa.Integer(), nullable=False, server_default="1"))
        batch.create_unique_constraint("uq_configuracoes_organization", ["organization_id"])
        batch.create_foreign_key("fk_configuracoes_organization", "organizations", ["organization_id"], ["id"])


def downgrade():
    with op.batch_alter_table("configuracoes") as batch:
        batch.drop_constraint("fk_configuracoes_organization", type_="foreignkey")
        batch.drop_constraint("uq_configuracoes_organization", type_="unique")
        batch.drop_column("organization_id")
    for table in reversed(TABLES):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(f"fk_{table}_organization", type_="foreignkey")
            batch.drop_index(f"ix_{table}_organization_id")
            batch.drop_column("organization_id")
