"""Add public branding fields to configuracoes."""

import sqlalchemy as sa
from alembic import op

revision = "20260729_0004"
down_revision = "20260729_0003"
branch_labels = None
depends_on = None


BRANDING_COLUMNS = {
    "subtitulo_empresa": sa.Column("subtitulo_empresa", sa.String(length=160), nullable=True),
    "logo_url": sa.Column("logo_url", sa.String(length=600), nullable=True),
    "site_url": sa.Column("site_url", sa.String(length=300), nullable=True),
    "instagram_url": sa.Column("instagram_url", sa.String(length=300), nullable=True),
    "whatsapp_publico": sa.Column("whatsapp_publico", sa.String(length=20), nullable=True),
}


def _existing_columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade():
    existing = _existing_columns("configuracoes")
    for name, column in BRANDING_COLUMNS.items():
        if name not in existing:
            op.add_column("configuracoes", column)


def downgrade():
    existing = _existing_columns("configuracoes")
    for name in reversed(BRANDING_COLUMNS):
        if name in existing:
            op.drop_column("configuracoes", name)
