"""add static site bundle metadata to tenant sites

Revision ID: 20261105_0039
Revises: 20261102_0038
"""
import sqlalchemy as sa
from alembic import op

revision = "20261105_0039"
down_revision = "20261102_0038"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tenant_sites", sa.Column("site_mode", sa.String(length=20), nullable=False, server_default="builder"))
    op.add_column("tenant_sites", sa.Column("site_bundle_version", sa.String(length=64), nullable=True))
    op.add_column("tenant_sites", sa.Column("site_bundle_entrypoint", sa.String(length=255), nullable=False, server_default="index.html"))
    op.add_column("tenant_sites", sa.Column("site_bundle_uploaded_at", sa.DateTime(), nullable=True))
    op.add_column("tenant_sites", sa.Column("site_bundle_file_count", sa.Integer(), nullable=True))
    op.add_column("tenant_sites", sa.Column("site_bundle_size_bytes", sa.BigInteger(), nullable=True))


def downgrade():
    for name in ("site_bundle_size_bytes", "site_bundle_file_count", "site_bundle_uploaded_at", "site_bundle_entrypoint", "site_bundle_version", "site_mode"):
        op.drop_column("tenant_sites", name)
