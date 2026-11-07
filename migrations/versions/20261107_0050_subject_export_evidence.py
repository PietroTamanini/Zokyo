"""Record the hash of an export prepared for a subject request.

Revision ID: 20261107_0050
Revises: 20261106_0049
"""
import sqlalchemy as sa
from alembic import op

revision = "20261107_0050"
down_revision = "20261106_0049"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("data_subject_requests") as batch:
        batch.add_column(sa.Column("prepared_export_sha256", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("prepared_export_at", sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table("data_subject_requests") as batch:
        batch.drop_column("prepared_export_at")
        batch.drop_column("prepared_export_sha256")
