"""Legacy notifications get no fabricated redaction timestamp."""
import importlib
import unittest

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text


class NotificationRedactionMigrationTests(unittest.TestCase):
    def test_existing_notification_has_null_redacted_at(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE notifications (id INTEGER PRIMARY KEY)"))
            connection.execute(text("INSERT INTO notifications (id) VALUES (1)"))
            migration = importlib.import_module("migrations.versions.20261107_0051_notification_redaction")
            original_op = migration.op
            migration.op = Operations(MigrationContext.configure(connection))
            try:
                migration.upgrade()
            finally:
                migration.op = original_op
            row = connection.execute(text("SELECT redacted_at FROM notifications WHERE id = 1")).one()
            self.assertIsNone(row.redacted_at)
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
