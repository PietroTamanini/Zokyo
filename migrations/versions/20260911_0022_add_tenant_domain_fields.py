"""add tenant domain fields

Revision ID: 20260911_0022
Revises: 20260911_0021
Create Date: 2026-09-11 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = "20260911_0022"
down_revision = "20260911_0021"
branch_labels = None
depends_on = None


def _columns(table):
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table)}


def _unique_constraints(table):
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {constraint["name"] for constraint in inspector.get_unique_constraints(table)}


def upgrade():
    existing = _columns("organizations")
    with op.batch_alter_table("organizations") as batch:
        if "subdomain" not in existing:
            batch.add_column(sa.Column("subdomain", sa.String(length=80), nullable=True))
        if "custom_domain" not in existing:
            batch.add_column(sa.Column("custom_domain", sa.String(length=255), nullable=True))
        if "dns_status" not in existing:
            batch.add_column(sa.Column("dns_status", sa.String(length=30), nullable=False, server_default="pending"))
        if "dns_last_error" not in existing:
            batch.add_column(sa.Column("dns_last_error", sa.String(length=500), nullable=True))

    constraints = _unique_constraints("organizations")
    with op.batch_alter_table("organizations") as batch:
        if "uq_organizations_subdomain" not in constraints:
            batch.create_unique_constraint("uq_organizations_subdomain", ["subdomain"])
        if "uq_organizations_custom_domain" not in constraints:
            batch.create_unique_constraint("uq_organizations_custom_domain", ["custom_domain"])

    op.execute("UPDATE organizations SET subdomain = slug WHERE subdomain IS NULL")
    bind = op.get_bind()
    base_domain = "tamanini.dev.br"
    if bind.dialect.name == "mysql":
        op.execute(
            "UPDATE organizations SET custom_domain = CONCAT(subdomain, '.%s') "
            "WHERE custom_domain IS NULL AND subdomain IS NOT NULL" % base_domain
        )
    else:
        op.execute(
            "UPDATE organizations SET custom_domain = subdomain || '.%s' "
            "WHERE custom_domain IS NULL AND subdomain IS NOT NULL" % base_domain
        )


def downgrade():
    constraints = _unique_constraints("organizations")
    with op.batch_alter_table("organizations") as batch:
        if "uq_organizations_custom_domain" in constraints:
            batch.drop_constraint("uq_organizations_custom_domain", type_="unique")
        if "uq_organizations_subdomain" in constraints:
            batch.drop_constraint("uq_organizations_subdomain", type_="unique")
    existing = _columns("organizations")
    with op.batch_alter_table("organizations") as batch:
        for column in ("dns_last_error", "dns_status", "custom_domain", "subdomain"):
            if column in existing:
                batch.drop_column(column)
