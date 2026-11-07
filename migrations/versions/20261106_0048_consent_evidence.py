"""Version and protect the consent decision ledger.

Revision ID: 20261106_0048
Revises: 20261106_0047
"""
import sqlalchemy as sa
from alembic import op

revision = "20261106_0048"
down_revision = "20261106_0047"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("consent_records", sa.Column("policy_version", sa.String(length=40), nullable=True))
    op.add_column("consent_records", sa.Column("evidence_reference", sa.String(length=200), nullable=True))
    dialect = op.get_bind().dialect.name
    if dialect in {"mysql", "mariadb"}:
        for action in ("update", "delete"):
            op.execute(f"DROP TRIGGER IF EXISTS trg_consent_no_{action}")
            op.execute(
                f"CREATE TRIGGER trg_consent_no_{action} BEFORE {action.upper()} "
                "ON consent_records FOR EACH ROW SIGNAL SQLSTATE '45000' "
                "SET MESSAGE_TEXT = 'Consent decisions are append-only'"
            )
    elif dialect == "sqlite":
        for action in ("update", "delete"):
            op.execute(f"DROP TRIGGER IF EXISTS trg_consent_no_{action}")
            op.execute(
                f"CREATE TRIGGER trg_consent_no_{action} BEFORE {action.upper()} "
                "ON consent_records BEGIN SELECT RAISE(ABORT, 'Consent decisions are append-only'); END"
            )
    else:
        raise RuntimeError(f"Dialect {dialect} needs append-only consent triggers.")


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS trg_consent_no_delete")
    op.execute("DROP TRIGGER IF EXISTS trg_consent_no_update")
    op.drop_column("consent_records", "evidence_reference")
    op.drop_column("consent_records", "policy_version")
