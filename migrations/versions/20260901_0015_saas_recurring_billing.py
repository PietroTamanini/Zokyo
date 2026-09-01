"""saas recurring billing fields

Revision ID: 20260901_0015
Revises: 20260901_0014
"""
import sqlalchemy as sa
from alembic import op

revision = "20260901_0015"
down_revision = "20260901_0014"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("plans", sa.Column("preco_mensal", sa.Numeric(10, 2), nullable=False, server_default="0"))
    op.add_column("plans", sa.Column("ciclo", sa.String(20), nullable=False, server_default="MONTHLY"))
    op.add_column("organization_subscriptions", sa.Column("external_customer_id", sa.String(120)))
    op.add_column("organization_subscriptions", sa.Column("checkout_url", sa.String(600)))
    op.add_column("organization_subscriptions", sa.Column("trial_fim", sa.DateTime()))
    op.add_column("organization_subscriptions", sa.Column("cancelar_no_fim", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column("organization_subscriptions", "cancelar_no_fim")
    op.drop_column("organization_subscriptions", "trial_fim")
    op.drop_column("organization_subscriptions", "checkout_url")
    op.drop_column("organization_subscriptions", "external_customer_id")
    op.drop_column("plans", "ciclo")
    op.drop_column("plans", "preco_mensal")
