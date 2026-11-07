"""Document identity verification for subject requests.

Revision ID: 20261106_0047
Revises: 20261106_0046
"""
import sqlalchemy as sa
from alembic import op

revision = "20261106_0047"
down_revision = "20261106_0046"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("data_subject_requests", sa.Column("identity_method", sa.String(length=30), nullable=True))
    op.add_column("data_subject_requests", sa.Column("identity_reference", sa.String(length=200), nullable=True))
    op.add_column("data_subject_requests", sa.Column("identity_verified_at", sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column("data_subject_requests", "identity_verified_at")
    op.drop_column("data_subject_requests", "identity_reference")
    op.drop_column("data_subject_requests", "identity_method")
