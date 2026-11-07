"""Mark sent notifications whose personal content was redacted.

Revision ID: 20261107_0051
Revises: 20261107_0050
"""
import sqlalchemy as sa
from alembic import op

revision = "20261107_0051"
down_revision = "20261107_0050"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("notifications") as batch:
        batch.add_column(sa.Column("redacted_at", sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table("notifications") as batch:
        batch.drop_column("redacted_at")
