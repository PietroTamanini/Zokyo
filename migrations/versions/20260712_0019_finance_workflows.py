"""Adiciona parcelamento, conciliacao e comissao.

Revision ID: 20260712_0019
Revises: 20260712_0018
"""
import sqlalchemy as sa
from alembic import op

revision = "20260712_0019"
down_revision = "20260712_0018"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("transacoes") as batch:
        batch.add_column(sa.Column("parent_id", sa.Integer()))
        batch.add_column(sa.Column("parcela_numero", sa.Integer(), nullable=False, server_default="1"))
        batch.add_column(sa.Column("parcela_total", sa.Integer(), nullable=False, server_default="1"))
        batch.add_column(sa.Column("recorrencia", sa.String(length=20)))
        batch.add_column(sa.Column("conciliado_em", sa.DateTime()))
        batch.add_column(sa.Column("conciliado_por_id", sa.Integer()))
        batch.add_column(sa.Column("conciliacao_ref", sa.String(length=120)))
        batch.add_column(sa.Column("comissao_usuario_id", sa.Integer()))
        batch.add_column(sa.Column("comissao_percentual", sa.Numeric(5, 2), server_default="0"))
        batch.add_column(sa.Column("comissao_valor", sa.Numeric(10, 2), server_default="0"))
        batch.create_foreign_key("fk_transaction_parent", "transacoes", ["parent_id"], ["id"])
        batch.create_foreign_key("fk_transaction_reconciled_by", "usuarios", ["conciliado_por_id"], ["id"])
        batch.create_foreign_key("fk_transaction_commission_user", "usuarios", ["comissao_usuario_id"], ["id"])
        batch.create_index("ix_transacoes_parent_id", ["parent_id"])


def downgrade():
    with op.batch_alter_table("transacoes") as batch:
        batch.drop_index("ix_transacoes_parent_id")
        batch.drop_constraint("fk_transaction_commission_user", type_="foreignkey")
        batch.drop_constraint("fk_transaction_reconciled_by", type_="foreignkey")
        batch.drop_constraint("fk_transaction_parent", type_="foreignkey")
        for column in (
            "comissao_valor", "comissao_percentual", "comissao_usuario_id", "conciliacao_ref",
            "conciliado_por_id", "conciliado_em", "recorrencia", "parcela_total", "parcela_numero", "parent_id",
        ):
            batch.drop_column(column)
