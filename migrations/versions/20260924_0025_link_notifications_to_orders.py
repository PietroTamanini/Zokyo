"""link notifications to service orders

Revision ID: 20260924_0025
Revises: 20260911_0024
Create Date: 2026-09-24 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = "20260924_0025"
down_revision = "20260911_0024"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("notifications") as batch:
        batch.add_column(sa.Column("os_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_notifications_os_id_ordens_servico",
            "ordens_servico",
            ["os_id"],
            ["id"],
        )
    op.create_index(
        "ix_notifications_org_os_created",
        "notifications",
        ["organization_id", "os_id", "created_at"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_notifications_org_os_created", table_name="notifications")
    with op.batch_alter_table("notifications") as batch:
        batch.drop_constraint("fk_notifications_os_id_ordens_servico", type_="foreignkey")
        batch.drop_column("os_id")
