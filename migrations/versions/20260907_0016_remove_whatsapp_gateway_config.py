"""remove legacy whatsapp gateway config

Revision ID: 20260907_0016
Revises: 20260901_0015
"""
import sqlalchemy as sa
from alembic import op

revision = "20260907_0016"
down_revision = "20260901_0015"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = ("wpp_server_url", "evolution_api_url", "evolution_api_key", "evolution_instance")
    existing = {column["name"] for column in sa.inspect(bind).get_columns("configuracoes")}
    columns = tuple(column for column in columns if column in existing)
    if not columns:
        return
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("configuracoes") as batch_op:
            for column in columns:
                batch_op.drop_column(column)
        return
    for column in columns:
        op.drop_column("configuracoes", column)


def downgrade():
    op.add_column("configuracoes", sa.Column("wpp_server_url", sa.String(length=300), nullable=True))
    op.add_column("configuracoes", sa.Column("evolution_api_url", sa.String(length=600), nullable=True))
    op.add_column("configuracoes", sa.Column("evolution_api_key", sa.String(length=600), nullable=True))
    op.add_column("configuracoes", sa.Column("evolution_instance", sa.String(length=100), nullable=True))
