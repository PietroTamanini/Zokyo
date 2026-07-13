"""Portal do cliente e aprovacao de orcamento.

Revision ID: 20260712_0009
Revises: 20260712_0008
"""
from alembic import op
import sqlalchemy as sa


revision = "20260712_0009"
down_revision = "20260712_0008"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("ordens_servico") as batch:
        batch.add_column(sa.Column("orcamento_status", sa.String(length=20)))
        batch.add_column(sa.Column("orcamento_decidido_em", sa.DateTime()))
    op.create_table(
        "portal_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("os_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("purpose", sa.String(length=30), nullable=False, server_default="tracking"),
        sa.Column("criado_por_id", sa.Integer(), nullable=False),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.Column("expira_em", sa.DateTime(), nullable=False),
        sa.Column("usado_em", sa.DateTime()),
        sa.Column("revogado_em", sa.DateTime()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_portal_tokens_organization"),
        sa.ForeignKeyConstraint(["os_id"], ["ordens_servico.id"], name="fk_portal_tokens_os"),
        sa.ForeignKeyConstraint(["criado_por_id"], ["usuarios.id"], name="fk_portal_tokens_usuario"),
    )
    op.create_index("ix_portal_tokens_organization_id", "portal_tokens", ["organization_id"])
    op.create_index("ix_portal_tokens_os_id", "portal_tokens", ["os_id"])
    op.create_index("ix_portal_token_os_purpose", "portal_tokens", ["os_id", "purpose", "revogado_em"])


def downgrade():
    op.drop_index("ix_portal_token_os_purpose", table_name="portal_tokens")
    op.drop_index("ix_portal_tokens_os_id", table_name="portal_tokens")
    op.drop_index("ix_portal_tokens_organization_id", table_name="portal_tokens")
    op.drop_table("portal_tokens")
    with op.batch_alter_table("ordens_servico") as batch:
        batch.drop_column("orcamento_decidido_em")
        batch.drop_column("orcamento_status")
