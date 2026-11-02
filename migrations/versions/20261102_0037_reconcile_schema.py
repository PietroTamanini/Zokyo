"""reconcile inventory association and configuration constraints

Revision ID: 20261102_0037
Revises: 20261102_0036
"""
import sqlalchemy as sa
from alembic import op

revision = "20261102_0037"
down_revision = "20261102_0036"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "pecas_inventario" not in tables:
        op.create_table(
            "pecas_inventario",
            sa.Column("peca_id", sa.Integer(), nullable=False),
            sa.Column("sessao_id", sa.Integer(), nullable=False),
            sa.Column("quantidade_sistema", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("quantidade_fisica", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("divergencia", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("justificativa", sa.Text()),
            sa.Column("aprovado", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("aprovado_em", sa.DateTime()),
            sa.Column("aprovado_por_id", sa.Integer()),
            sa.Column("aprovado_por_nome", sa.String(120)),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["peca_id"], ["pecas.id"]),
            sa.ForeignKeyConstraint(["sessao_id"], ["inventario_sessoes.id"]),
            sa.ForeignKeyConstraint(["aprovado_por_id"], ["usuarios.id"]),
            sa.PrimaryKeyConstraint("peca_id", "sessao_id"),
        )

    op.execute("UPDATE configuracoes SET onboarding_step = COALESCE(onboarding_step, 1)")
    op.execute("UPDATE configuracoes SET onboarding_completed = COALESCE(onboarding_completed, 0)")
    op.alter_column("configuracoes", "onboarding_step", existing_type=sa.Integer(), nullable=False)
    op.alter_column("configuracoes", "onboarding_completed", existing_type=sa.Boolean(), nullable=False)


def downgrade():
    op.drop_table("pecas_inventario")
