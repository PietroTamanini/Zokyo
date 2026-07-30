"""Add configurable entry checklist options."""

import sqlalchemy as sa
from alembic import op

revision = "20260730_0006"
down_revision = "20260730_0005"
branch_labels = None
depends_on = None


def _existing_columns(table_name):
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade():
    config_columns = _existing_columns("configuracoes")
    if "entry_checklist_options" not in config_columns:
        op.add_column("configuracoes", sa.Column("entry_checklist_options", sa.Text(), nullable=True))


def downgrade():
    config_columns = _existing_columns("configuracoes")
    if "entry_checklist_options" in config_columns:
        op.drop_column("configuracoes", "entry_checklist_options")
