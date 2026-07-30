"""Add payment gateway fields to transacoes."""

import sqlalchemy as sa
from alembic import op

revision = "20260729_0002"
down_revision = "20260718_0001"
branch_labels = None
depends_on = None


PAYMENT_COLUMNS = {
    "payment_gateway": sa.Column("payment_gateway", sa.String(length=40), nullable=True),
    "payment_method": sa.Column("payment_method", sa.String(length=40), nullable=True),
    "payment_provider_id": sa.Column("payment_provider_id", sa.String(length=160), nullable=True),
    "payment_status": sa.Column("payment_status", sa.String(length=40), nullable=True),
    "payment_url": sa.Column("payment_url", sa.String(length=600), nullable=True),
    "payment_link": sa.Column("payment_link", sa.String(length=600), nullable=True),
    "payment_barcode": sa.Column("payment_barcode", sa.String(length=300), nullable=True),
    "payment_payload": sa.Column("payment_payload", sa.Text(), nullable=True),
    "payment_expires_at": sa.Column("payment_expires_at", sa.DateTime(), nullable=True),
}


def _existing_columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade():
    existing = _existing_columns("transacoes")
    for name, column in PAYMENT_COLUMNS.items():
        if name not in existing:
            op.add_column("transacoes", column)


def downgrade():
    existing = _existing_columns("transacoes")
    for name in reversed(PAYMENT_COLUMNS):
        if name in existing:
            op.drop_column("transacoes", name)
