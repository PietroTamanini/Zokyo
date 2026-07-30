"""Add configurable OS options."""

import sqlalchemy as sa
from alembic import op

revision = "20260730_0005"
down_revision = "20260729_0004"
branch_labels = None
depends_on = None


def _existing_columns(table_name):
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade():
    config_columns = _existing_columns("configuracoes")
    for name in ("os_status_options", "os_priority_options", "attendance_type_options"):
        if name not in config_columns:
            op.add_column("configuracoes", sa.Column(name, sa.Text(), nullable=True))

    order_columns = _existing_columns("ordens_servico")
    if "tipo_atendimento" not in order_columns:
        op.add_column("ordens_servico", sa.Column("tipo_atendimento", sa.String(length=50), nullable=True))


def downgrade():
    order_columns = _existing_columns("ordens_servico")
    if "tipo_atendimento" in order_columns:
        op.drop_column("ordens_servico", "tipo_atendimento")

    config_columns = _existing_columns("configuracoes")
    for name in ("attendance_type_options", "os_priority_options", "os_status_options"):
        if name in config_columns:
            op.drop_column("configuracoes", name)
