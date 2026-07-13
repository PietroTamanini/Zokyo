"""add organizations and core tenant ownership

Revision ID: 20260712_0006
Revises: 20260712_0005
"""
from alembic import op
import sqlalchemy as sa

revision = "20260712_0006"
down_revision = "20260712_0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_uuid", sa.String(length=36), nullable=False, unique=True),
        sa.Column("nome", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False, unique=True),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("criado_em", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.execute(sa.text(
        "INSERT INTO organizations (id, public_uuid, nome, slug, ativo) "
        "VALUES (1, '00000000-0000-4000-8000-000000000001', 'Organizacao padrao', 'default', true)"
    ))
    for table in ("usuarios", "clientes", "ordens_servico"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("organization_id", sa.Integer(), nullable=False, server_default="1"))
            batch.create_index(f"ix_{table}_organization_id", ["organization_id"])
            batch.create_foreign_key(f"fk_{table}_organization", "organizations", ["organization_id"], ["id"])
    with op.batch_alter_table("laudos_tecnicos") as batch:
        batch.create_foreign_key("fk_laudos_organization", "organizations", ["organization_id"], ["id"])


def downgrade():
    with op.batch_alter_table("laudos_tecnicos") as batch:
        batch.drop_constraint("fk_laudos_organization", type_="foreignkey")
    for table in ("ordens_servico", "clientes", "usuarios"):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(f"fk_{table}_organization", type_="foreignkey")
            batch.drop_index(f"ix_{table}_organization_id")
            batch.drop_column("organization_id")
    op.drop_table("organizations")
