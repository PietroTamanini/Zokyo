"""Pseudonymize stored login lock IPs while retaining active counters.

Revision ID: 20261107_0054
Revises: 20261107_0053
"""
import sqlalchemy as sa
from alembic import op

from app.utils.rate_limit import _login_rate_key

revision = "20261107_0054"
down_revision = "20261107_0053"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    rows = connection.execute(sa.text(
        "SELECT ip, falhas, bloqueado_ate, ultima_falha FROM login_attempts"
    )).mappings().all()
    for row in rows:
        original = row["ip"]
        if original.startswith("lr:"):
            continue  # Safe to rerun after a partially applied MySQL migration.
        pseudonym = _login_rate_key(original)
        existing = connection.execute(sa.text(
            "SELECT falhas, bloqueado_ate, ultima_falha FROM login_attempts WHERE ip = :ip"
        ), {"ip": pseudonym}).mappings().first()
        if existing:
            # A newer worker may already have created the pseudonymous row.
            connection.execute(sa.text("""
                UPDATE login_attempts
                   SET falhas = :falhas, bloqueado_ate = :blocked,
                       ultima_falha = :last_failure
                 WHERE ip = :ip
            """), {
                "ip": pseudonym,
                "falhas": max(row["falhas"] or 0, existing["falhas"] or 0),
                "blocked": max(filter(None, (row["bloqueado_ate"], existing["bloqueado_ate"])), default=None),
                "last_failure": max(filter(None, (row["ultima_falha"], existing["ultima_falha"])), default=None),
            })
            connection.execute(sa.text("DELETE FROM login_attempts WHERE ip = :ip"), {"ip": original})
        else:
            connection.execute(sa.text(
                "UPDATE login_attempts SET ip = :new_ip WHERE ip = :old_ip"
            ), {"new_ip": pseudonym, "old_ip": original})


def downgrade():
    # Original IP addresses cannot be reconstructed from HMAC pseudonyms.
    pass
