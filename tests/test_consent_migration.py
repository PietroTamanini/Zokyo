"""Registros antigos não ganham evidência fictícia e o ledger resiste a mutações."""
import importlib
import unittest

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DatabaseError


class ConsentMigrationTests(unittest.TestCase):
    def test_legacy_record_is_unknown_and_update_delete_are_blocked(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE consent_records (id INTEGER PRIMARY KEY, granted BOOLEAN NOT NULL)"))
            connection.execute(text("INSERT INTO consent_records (id, granted) VALUES (1, 1)"))
            migration = importlib.import_module("migrations.versions.20261106_0048_consent_evidence")
            original_op = migration.op
            migration.op = Operations(MigrationContext.configure(connection))
            try:
                migration.upgrade()
            finally:
                migration.op = original_op
            row = connection.execute(text(
                "SELECT policy_version, evidence_reference FROM consent_records WHERE id = 1"
            )).one()
            self.assertEqual(tuple(row), (None, None))
            with self.assertRaises(DatabaseError):
                connection.execute(text("UPDATE consent_records SET granted = 0 WHERE id = 1"))
            with self.assertRaises(DatabaseError):
                connection.execute(text("DELETE FROM consent_records WHERE id = 1"))
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
