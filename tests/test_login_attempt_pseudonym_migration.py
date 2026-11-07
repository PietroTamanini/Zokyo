"""Existing login locks survive the IP pseudonym migration."""
import importlib

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text


def test_login_attempts_are_pseudonymized_without_losing_active_locks():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE login_attempts (
                ip TEXT PRIMARY KEY, falhas INTEGER,
                bloqueado_ate TEXT, ultima_falha TEXT
            )
        """))
        connection.execute(text("""
            INSERT INTO login_attempts VALUES
            ('192.0.2.10', 3, '2026-11-08 10:00:00', '2026-11-07 10:00:00'),
            ('192.0.2.11', 2, NULL, '2026-11-07 09:00:00'),
            ('lr:existing', 1, '2026-11-08 09:00:00', '2026-11-07 08:00:00')
        """))
        migration = importlib.import_module(
            "migrations.versions.20261107_0054_pseudonymize_login_attempts"
        )
        original_op, original_key = migration.op, migration._login_rate_key
        migration.op = Operations(MigrationContext.configure(connection))
        migration._login_rate_key = lambda ip: "lr:existing" if ip == "192.0.2.10" else "lr:second"
        try:
            migration.upgrade()
            migration.upgrade()  # safe after partial migration / repeated run
        finally:
            migration.op, migration._login_rate_key = original_op, original_key
        rows = connection.execute(text(
            "SELECT ip, falhas, bloqueado_ate, ultima_falha FROM login_attempts ORDER BY ip"
        )).all()
        assert rows == [
            ("lr:existing", 3, "2026-11-08 10:00:00", "2026-11-07 10:00:00"),
            ("lr:second", 2, None, "2026-11-07 09:00:00"),
        ]
    engine.dispose()
