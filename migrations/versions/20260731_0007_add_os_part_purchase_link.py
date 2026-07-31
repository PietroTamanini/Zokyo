"""Add purchase link to order parts."""

import sqlalchemy as sa
from alembic import op

revision = "20260731_0007"
down_revision = "20260730_0006"
branch_labels = None
depends_on = None


def _existing_columns(table_name):
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade():
    columns = _existing_columns("os_pecas")
    if "link_compra" not in columns:
        op.add_column("os_pecas", sa.Column("link_compra", sa.String(length=1000), nullable=True))


def downgrade():
    columns = _existing_columns("os_pecas")
    if "link_compra" in columns:
        op.drop_column("os_pecas", "link_compra")
