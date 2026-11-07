"""Keep append-only snapshots of privacy incident decisions.

Revision ID: 20261106_0045
Revises: 20261106_0044
"""
import json
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "20261106_0045"
down_revision = "20261106_0044"
branch_labels = None
depends_on = None

_SNAPSHOT_FIELDS = (
    "title", "description", "status", "severity", "affected_data",
    "affected_subjects", "known_at", "anpd_notified_at", "subjects_notified_at",
    "notification_reference", "notification_decision", "corrective_actions", "closed_at",
)


def upgrade():
    table = op.create_table(
        "privacy_incident_revisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("incident_id", sa.Integer(), sa.ForeignKey("privacy_incidents.id"), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=True),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.Column("snapshot", sa.Text(), nullable=False),
    )
    op.create_index("ix_privacy_incident_revisions_incident_id", "privacy_incident_revisions", ["incident_id"])
    connection = op.get_bind()
    columns = ", ".join(("id", "reported_by_id", *_SNAPSHOT_FIELDS))
    rows = connection.execute(sa.text(f"SELECT {columns} FROM privacy_incidents ORDER BY id")).mappings()
    for row in rows:
        connection.execute(table.insert().values(
            incident_id=row["id"], actor_id=row["reported_by_id"],
            action="baseline", recorded_at=datetime.now(timezone.utc),
            snapshot=json.dumps({field: row[field] for field in _SNAPSHOT_FIELDS}, default=str, ensure_ascii=False),
        ))
    dialect = connection.dialect.name
    if dialect in {"mysql", "mariadb"}:
        for action in ("update", "delete"):
            op.execute(f"DROP TRIGGER IF EXISTS trg_incident_revision_no_{action}")
            op.execute(
                f"CREATE TRIGGER trg_incident_revision_no_{action} BEFORE {action.upper()} "
                "ON privacy_incident_revisions FOR EACH ROW SIGNAL SQLSTATE '45000' "
                "SET MESSAGE_TEXT = 'Incident revisions are append-only'"
            )
    elif dialect == "sqlite":
        for action in ("update", "delete"):
            op.execute(f"DROP TRIGGER IF EXISTS trg_incident_revision_no_{action}")
            op.execute(
                f"CREATE TRIGGER trg_incident_revision_no_{action} BEFORE {action.upper()} "
                "ON privacy_incident_revisions BEGIN SELECT RAISE(ABORT, 'Incident revisions are append-only'); END"
            )
    else:
        raise RuntimeError(f"Dialect {dialect} needs an append-only trigger implementation.")


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS trg_incident_revision_no_delete")
    op.execute("DROP TRIGGER IF EXISTS trg_incident_revision_no_update")
    op.drop_index("ix_privacy_incident_revisions_incident_id", table_name="privacy_incident_revisions")
    op.drop_table("privacy_incident_revisions")
