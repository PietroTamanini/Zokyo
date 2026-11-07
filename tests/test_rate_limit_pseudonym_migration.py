"""The one-time upgrade removes existing plaintext API rate keys."""
import importlib

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text


def test_upgrade_clears_legacy_counters_and_keeps_login_locks():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE api_rate_limits (id INTEGER PRIMARY KEY, ip TEXT)"))
        connection.execute(text("CREATE TABLE login_attempts (ip TEXT PRIMARY KEY)"))
        connection.execute(text("INSERT INTO api_rate_limits (id, ip) VALUES (1, '192.0.2.10')"))
        connection.execute(text("INSERT INTO login_attempts (ip) VALUES ('192.0.2.10')"))
        migration = importlib.import_module("migrations.versions.20261107_0053_clear_legacy_rate_keys")
        original_op = migration.op
        migration.op = Operations(MigrationContext.configure(connection))
        try:
            migration.upgrade()
        finally:
            migration.op = original_op
        assert connection.scalar(text("SELECT COUNT(*) FROM api_rate_limits")) == 0
        assert connection.scalar(text("SELECT COUNT(*) FROM login_attempts")) == 1
    engine.dispose()
