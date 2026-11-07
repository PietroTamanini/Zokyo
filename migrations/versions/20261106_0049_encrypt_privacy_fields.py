"""Allow encrypted personal fields in privacy requests and incidents.

Existing plaintext rows remain readable and must be re-encrypted separately
under an approved operational procedure. This migration only widens columns.

Revision ID: 20261106_0049
Revises: 20261106_0048
"""
import sqlalchemy as sa
from alembic import op

revision = "20261106_0049"
down_revision = "20261106_0048"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("data_subject_requests") as batch:
        batch.drop_index("ix_data_subject_requests_requester_email")
        for column, length in (
            ("requester_name", 160),
            ("requester_email", 254),
            ("identity_reference", 200),
            ("delivery_reference", 200),
        ):
            batch.alter_column(
                column, existing_type=sa.String(length=length),
                type_=sa.Text(), existing_nullable=True,
            )

    with op.batch_alter_table("privacy_incidents") as batch:
        for column in ("title", "notification_reference"):
            batch.alter_column(
                column, existing_type=sa.String(length=200), type_=sa.Text(),
                existing_nullable=column != "title",
            )


def downgrade():
    raise RuntimeError(
        "Downgrade de campos cifrados pode truncar dados. "
        "Restaure um backup validado ou faça uma migração explícita com revisão dos dados."
    )
