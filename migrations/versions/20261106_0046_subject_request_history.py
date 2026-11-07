"""Preserve subject request decisions and documented response delivery.

Revision ID: 20261106_0046
Revises: 20261106_0045
"""
import json
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "20261106_0046"
down_revision = "20261106_0045"
branch_labels = None
depends_on = None

_FIELDS = (
    "request_type", "status", "identity_verified", "due_at", "response_notes",
    "response_channel", "delivery_reference", "delivered_at", "concluido_em",
)


def upgrade():
    op.add_column("data_subject_requests", sa.Column("response_channel", sa.String(length=30), nullable=True))
    op.add_column("data_subject_requests", sa.Column("delivery_reference", sa.String(length=200), nullable=True))
    op.add_column("data_subject_requests", sa.Column("delivered_at", sa.DateTime(), nullable=True))
    revisions = op.create_table(
        "data_subject_request_revisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.Integer(), sa.ForeignKey("data_subject_requests.id"), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=True),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.Column("snapshot", sa.Text(), nullable=False),
    )
    op.create_index("ix_data_subject_request_revisions_request_id", "data_subject_request_revisions", ["request_id"])
    connection = op.get_bind()
    columns = ", ".join(("id", "solicitado_por_id", *_FIELDS))
    rows = connection.execute(sa.text(f"SELECT {columns} FROM data_subject_requests ORDER BY id")).mappings()
    for row in rows:
        connection.execute(revisions.insert().values(
            request_id=row["id"], actor_id=row["solicitado_por_id"],
            action="baseline", recorded_at=datetime.now(timezone.utc),
            snapshot=json.dumps({field: row[field] for field in _FIELDS}, default=str, ensure_ascii=False),
        ))
    dialect = connection.dialect.name
    if dialect in {"mysql", "mariadb"}:
        for action in ("update", "delete"):
            op.execute(f"DROP TRIGGER IF EXISTS trg_request_revision_no_{action}")
            op.execute(
                f"CREATE TRIGGER trg_request_revision_no_{action} BEFORE {action.upper()} "
                "ON data_subject_request_revisions FOR EACH ROW SIGNAL SQLSTATE '45000' "
                "SET MESSAGE_TEXT = 'Subject request revisions are append-only'"
            )
    elif dialect == "sqlite":
        for action in ("update", "delete"):
            op.execute(f"DROP TRIGGER IF EXISTS trg_request_revision_no_{action}")
            op.execute(
                f"CREATE TRIGGER trg_request_revision_no_{action} BEFORE {action.upper()} "
                "ON data_subject_request_revisions BEGIN SELECT RAISE(ABORT, 'Subject request revisions are append-only'); END"
            )
    else:
        raise RuntimeError(f"Dialect {dialect} needs an append-only trigger implementation.")


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS trg_request_revision_no_delete")
    op.execute("DROP TRIGGER IF EXISTS trg_request_revision_no_update")
    op.drop_index("ix_data_subject_request_revisions_request_id", table_name="data_subject_request_revisions")
    op.drop_table("data_subject_request_revisions")
    op.drop_column("data_subject_requests", "delivered_at")
    op.drop_column("data_subject_requests", "delivery_reference")
    op.drop_column("data_subject_requests", "response_channel")
