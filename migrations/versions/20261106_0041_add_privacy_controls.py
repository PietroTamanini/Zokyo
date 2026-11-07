"""add privacy request, incident and audit integrity controls

Revision ID: 20261106_0041
Revises: 20261106_0040
"""
import sqlalchemy as sa
from alembic import op

revision = "20261106_0041"
down_revision = "20261106_0040"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("eventos_log") as batch:
        batch.add_column(sa.Column("previous_hash", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("integrity_hash", sa.String(length=64), nullable=True))
        batch.create_unique_constraint("uq_eventos_log_integrity_hash", ["integrity_hash"])

    with op.batch_alter_table("data_subject_requests") as batch:
        batch.alter_column("organization_id", existing_type=sa.Integer(), nullable=True)
        batch.alter_column("cliente_id", existing_type=sa.Integer(), nullable=True)
        batch.alter_column("solicitado_por_id", existing_type=sa.Integer(), nullable=True)
        batch.add_column(sa.Column("requester_name", sa.String(length=160), nullable=True))
        batch.add_column(sa.Column("requester_email", sa.String(length=254), nullable=True))
        batch.add_column(sa.Column("channel", sa.String(length=30), nullable=False, server_default="admin"))
        batch.add_column(sa.Column("identity_verified", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("due_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("response_notes", sa.Text(), nullable=True))
        batch.create_index("ix_data_subject_requests_requester_email", ["requester_email"], unique=False)

    op.create_table(
        "privacy_incidents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("reported_by_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="open"),
        sa.Column("severity", sa.String(length=20), nullable=False, server_default="medium"),
        sa.Column("detected_at", sa.DateTime(), nullable=False),
        sa.Column("reported_at", sa.DateTime(), nullable=False),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("affected_data", sa.Text(), nullable=True),
        sa.Column("affected_subjects", sa.Integer(), nullable=True),
        sa.Column("notification_decision", sa.Text(), nullable=True),
        sa.Column("corrective_actions", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["reported_by_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_privacy_incidents_organization_id", "privacy_incidents", ["organization_id"])


def downgrade():
    op.drop_index("ix_privacy_incidents_organization_id", table_name="privacy_incidents")
    op.drop_table("privacy_incidents")
    with op.batch_alter_table("data_subject_requests") as batch:
        batch.drop_index("ix_data_subject_requests_requester_email")
        batch.drop_column("response_notes")
        batch.drop_column("due_at")
        batch.drop_column("identity_verified")
        batch.drop_column("channel")
        batch.drop_column("requester_email")
        batch.drop_column("requester_name")
        batch.alter_column("solicitado_por_id", existing_type=sa.Integer(), nullable=False)
        batch.alter_column("cliente_id", existing_type=sa.Integer(), nullable=False)
        batch.alter_column("organization_id", existing_type=sa.Integer(), nullable=False)
    with op.batch_alter_table("eventos_log") as batch:
        batch.drop_constraint("uq_eventos_log_integrity_hash", type_="unique")
        batch.drop_column("integrity_hash")
        batch.drop_column("previous_hash")
