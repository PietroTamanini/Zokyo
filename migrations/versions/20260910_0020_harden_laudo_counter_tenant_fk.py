"""harden tenant integrity for report counters

Revision ID: 20260910_0020
Revises: 20260909_0019
"""
from alembic import op


revision = "20260910_0020"
down_revision = "20260909_0019"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("laudo_counters") as batch_op:
        batch_op.create_foreign_key(
            "fk_laudo_counters_organization_id",
            "organizations",
            ["organization_id"],
            ["id"],
        )


def downgrade():
    with op.batch_alter_table("laudo_counters") as batch_op:
        batch_op.drop_constraint("fk_laudo_counters_organization_id", type_="foreignkey")
