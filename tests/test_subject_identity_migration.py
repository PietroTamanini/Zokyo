"""A migração preserva pedidos antigos sem inventar prova de identidade."""
import importlib
import unittest

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text


class SubjectIdentityMigrationTests(unittest.TestCase):
    def test_existing_verification_has_unknown_method_and_reference(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE data_subject_requests (id INTEGER PRIMARY KEY, identity_verified BOOLEAN NOT NULL)"))
            connection.execute(text("INSERT INTO data_subject_requests (id, identity_verified) VALUES (1, 1)"))
            migration = importlib.import_module("migrations.versions.20261106_0047_subject_identity_evidence")
            original_op = migration.op
            migration.op = Operations(MigrationContext.configure(connection))
            try:
                migration.upgrade()
            finally:
                migration.op = original_op
            row = connection.execute(text(
                "SELECT identity_verified, identity_method, identity_reference, identity_verified_at "
                "FROM data_subject_requests WHERE id = 1"
            )).one()
            self.assertEqual(row.identity_verified, 1)
            self.assertIsNone(row.identity_method)
            self.assertIsNone(row.identity_reference)
            self.assertIsNone(row.identity_verified_at)
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
