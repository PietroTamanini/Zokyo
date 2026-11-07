"""Prevent direct updates and deletes of audit events.

Revision ID: 20261106_0044
Revises: 20261106_0043
"""
from alembic import op

revision = "20261106_0044"
down_revision = "20261106_0043"
branch_labels = None
depends_on = None


def upgrade():
    dialect = op.get_bind().dialect.name
    if dialect in {"mysql", "mariadb"}:
        op.execute("DROP TRIGGER IF EXISTS trg_eventos_log_no_update")
        op.execute("DROP TRIGGER IF EXISTS trg_eventos_log_no_delete")
        op.execute(
            "CREATE TRIGGER trg_eventos_log_no_update BEFORE UPDATE ON eventos_log "
            "FOR EACH ROW SIGNAL SQLSTATE '45000' "
            "SET MESSAGE_TEXT = 'Audit events are append-only'"
        )
        op.execute(
            "CREATE TRIGGER trg_eventos_log_no_delete BEFORE DELETE ON eventos_log "
            "FOR EACH ROW SIGNAL SQLSTATE '45000' "
            "SET MESSAGE_TEXT = 'Audit events are append-only'"
        )
    elif dialect == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS trg_eventos_log_no_update")
        op.execute("DROP TRIGGER IF EXISTS trg_eventos_log_no_delete")
        op.execute(
            "CREATE TRIGGER trg_eventos_log_no_update BEFORE UPDATE ON eventos_log "
            "BEGIN SELECT RAISE(ABORT, 'Audit events are append-only'); END"
        )
        op.execute(
            "CREATE TRIGGER trg_eventos_log_no_delete BEFORE DELETE ON eventos_log "
            "BEGIN SELECT RAISE(ABORT, 'Audit events are append-only'); END"
        )
    else:
        raise RuntimeError(f"Dialect {dialect} needs an append-only trigger implementation.")


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS trg_eventos_log_no_delete")
    op.execute("DROP TRIGGER IF EXISTS trg_eventos_log_no_update")
