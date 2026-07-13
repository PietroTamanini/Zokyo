"""Consentimentos e solicitacoes de titulares.

Revision ID: 20260712_0011
Revises: 20260712_0010
"""
from alembic import op
import sqlalchemy as sa


revision = "20260712_0011"
down_revision = "20260712_0010"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "consent_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("cliente_id", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(length=60), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(length=60), nullable=False, server_default="admin"),
        sa.Column("registrado_por_id", sa.Integer(), nullable=False),
        sa.Column("registrado_em", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_consent_organization"),
        sa.ForeignKeyConstraint(["cliente_id"], ["clientes.id"], name="fk_consent_cliente"),
        sa.ForeignKeyConstraint(["registrado_por_id"], ["usuarios.id"], name="fk_consent_usuario"),
    )
    op.create_index("ix_consent_records_organization_id", "consent_records", ["organization_id"])
    op.create_index("ix_consent_records_cliente_id", "consent_records", ["cliente_id"])
    op.create_table(
        "data_subject_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("cliente_id", sa.Integer(), nullable=False),
        sa.Column("request_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="open"),
        sa.Column("solicitado_por_id", sa.Integer(), nullable=False),
        sa.Column("solicitado_em", sa.DateTime(), nullable=False),
        sa.Column("concluido_em", sa.DateTime()),
        sa.Column("observacoes", sa.Text()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_dsr_organization"),
        sa.ForeignKeyConstraint(["cliente_id"], ["clientes.id"], name="fk_dsr_cliente"),
        sa.ForeignKeyConstraint(["solicitado_por_id"], ["usuarios.id"], name="fk_dsr_usuario"),
    )
    op.create_index("ix_data_subject_requests_organization_id", "data_subject_requests", ["organization_id"])
    op.create_index("ix_data_subject_requests_cliente_id", "data_subject_requests", ["cliente_id"])


def downgrade():
    op.drop_index("ix_data_subject_requests_cliente_id", table_name="data_subject_requests")
    op.drop_index("ix_data_subject_requests_organization_id", table_name="data_subject_requests")
    op.drop_table("data_subject_requests")
    op.drop_index("ix_consent_records_cliente_id", table_name="consent_records")
    op.drop_index("ix_consent_records_organization_id", table_name="consent_records")
    op.drop_table("consent_records")
