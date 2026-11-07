"""Record incident knowledge and notification timestamps.

Revision ID: 20261106_0042
Revises: 20261106_0041
"""
import sqlalchemy as sa
from alembic import op

revision = "20261106_0042"
down_revision = "20261106_0041"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("privacy_incidents") as batch:
        batch.add_column(sa.Column("known_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("anpd_notified_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("subjects_notified_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("notification_reference", sa.String(length=200), nullable=True))


def downgrade():
    with op.batch_alter_table("privacy_incidents") as batch:
        batch.drop_column("notification_reference")
        batch.drop_column("subjects_notified_at")
        batch.drop_column("anpd_notified_at")
        batch.drop_column("known_at")
