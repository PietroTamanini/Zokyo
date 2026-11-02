"""add tenant site content fields

Revision ID: 20260926_0030
Revises: 20260925_0026
Create Date: 2026-09-26 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = "20260926_0030"
down_revision = "20260925_0026"
branch_labels = None
depends_on = None


def _columns(table):
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table)}


def _add_if_missing(table, name, type_, nullable=True):
    existing = _columns(table)
    if name not in existing:
        op.add_column(
            table,
            sa.Column(name, type_, nullable=nullable),
        )


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "tenant_sites" in tables:
        _add_if_missing("tenant_sites", "site_name", sa.String(length=200))
        _add_if_missing("tenant_sites", "tagline", sa.String(length=300))
        _add_if_missing("tenant_sites", "description", sa.Text())
        _add_if_missing("tenant_sites", "story", sa.Text())
        _add_if_missing("tenant_sites", "cover_image", sa.String(length=600))
        _add_if_missing("tenant_sites", "secondary_color", sa.String(length=7))
        _add_if_missing("tenant_sites", "seo_title", sa.String(length=200))
        _add_if_missing("tenant_sites", "seo_description", sa.String(length=500))
        _add_if_missing("tenant_sites", "seo_image", sa.String(length=600))
        _add_if_missing("tenant_sites", "services_json", sa.Text())
        _add_if_missing("tenant_sites", "socials_json", sa.Text())
        _add_if_missing("tenant_sites", "phone", sa.String(length=20))
        _add_if_missing("tenant_sites", "whatsapp", sa.String(length=20))
        _add_if_missing("tenant_sites", "address", sa.Text())
        _add_if_missing("tenant_sites", "hours", sa.Text())


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "tenant_sites" in tables:
        for name, type_ in [
            ("site_name", sa.String(length=200)),
            ("tagline", sa.String(length=300)),
            ("description", sa.Text()),
            ("story", sa.Text()),
            ("cover_image", sa.String(length=600)),
            ("secondary_color", sa.String(length=7)),
            ("seo_title", sa.String(length=200)),
            ("seo_description", sa.String(length=500)),
            ("seo_image", sa.String(length=600)),
            ("services_json", sa.Text()),
            ("socials_json", sa.Text()),
            ("phone", sa.String(length=20)),
            ("whatsapp", sa.String(length=20)),
            ("address", sa.Text()),
            ("hours", sa.Text()),
        ]:
            if name in _columns("tenant_sites"):
                op.drop_column("tenant_sites", name)
