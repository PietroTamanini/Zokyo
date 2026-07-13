"""Templates versionados de laudos.

Revision ID: 20260712_0008
Revises: 20260712_0007
"""
from alembic import op
import sqlalchemy as sa


revision = "20260712_0008"
down_revision = "20260712_0007"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "laudo_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(length=120), nullable=False),
        sa.Column("tipo_laudo", sa.String(length=30), nullable=False, server_default="diagnostico"),
        sa.Column("versao", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("titulo", sa.String(length=160), nullable=False, server_default="Laudo tecnico"),
        sa.Column("declaracao_final", sa.Text()),
        sa.Column("rodape", sa.String(length=500)),
        sa.Column("fotos_obrigatorias", sa.JSON(), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("criado_por_id", sa.Integer(), nullable=False),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_laudo_templates_organization"),
        sa.ForeignKeyConstraint(["criado_por_id"], ["usuarios.id"], name="fk_laudo_templates_usuario"),
        sa.UniqueConstraint("organization_id", "nome", "versao", name="uq_laudo_template_org_nome_versao"),
    )
    op.create_index("ix_laudo_templates_organization_id", "laudo_templates", ["organization_id"])
    op.create_index(
        "ix_laudo_template_org_tipo_ativo",
        "laudo_templates",
        ["organization_id", "tipo_laudo", "ativo"],
    )
    with op.batch_alter_table("laudos_tecnicos") as batch:
        batch.add_column(sa.Column("template_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("template_snapshot", sa.JSON(), nullable=True))
        batch.create_foreign_key("fk_laudos_template", "laudo_templates", ["template_id"], ["id"])


def downgrade():
    with op.batch_alter_table("laudos_tecnicos") as batch:
        batch.drop_constraint("fk_laudos_template", type_="foreignkey")
        batch.drop_column("template_snapshot")
        batch.drop_column("template_id")
    op.drop_index("ix_laudo_template_org_tipo_ativo", table_name="laudo_templates")
    op.drop_index("ix_laudo_templates_organization_id", table_name="laudo_templates")
    op.drop_table("laudo_templates")
