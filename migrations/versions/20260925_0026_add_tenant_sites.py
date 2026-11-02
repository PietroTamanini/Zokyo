"""add tenant sites table

Revision ID: 20260925_0026
Revises: 20260924_0025
Create Date: 2026-09-25 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = "20260925_0026"
down_revision = "20260924_0025"
branch_labels = None
depends_on = None


def _columns(table):
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table)}


def _indexes(table):
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {idx["name"] for idx in inspector.get_indexes(table)}


def _unique_constraints(table):
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {constraint["name"] for constraint in inspector.get_unique_constraints(table)}


def upgrade():
    # Criar tabela tenant_sites se nao existir
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "tenant_sites" not in tables:
        op.create_table(
            "tenant_sites",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column(
                "organization_id",
                sa.Integer(),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("site_enabled", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("site_title", sa.String(length=200), nullable=True),
            sa.Column("site_subtitle", sa.String(length=300), nullable=True),
            sa.Column("site_description", sa.Text(), nullable=True),
            sa.Column("primary_color", sa.String(length=7), nullable=True),
            sa.Column("accent_color", sa.String(length=7), nullable=True),
            sa.Column("logo_url", sa.String(length=600), nullable=True),
            sa.Column("favicon_url", sa.String(length=600), nullable=True),
            sa.Column("custom_domain", sa.String(length=255), nullable=True),
            sa.Column(
                "custom_domain_validated",
                sa.Boolean(),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_tenant_sites_organization_id",
            "tenant_sites",
            ["organization_id"],
            unique=True,
        )
        op.create_index(
            "ix_tenant_sites_custom_domain",
            "tenant_sites",
            ["custom_domain"],
            unique=True,
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "tenant_sites" in tables:
        op.drop_index("ix_tenant_sites_custom_domain", table_name="tenant_sites")
        op.drop_index("ix_tenant_sites_organization_id", table_name="tenant_sites")
        op.drop_table("tenant_sites")
