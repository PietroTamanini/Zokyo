"""Existing subject requests gain empty export evidence columns."""
import importlib
import unittest

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text


class SubjectExportEvidenceMigrationTests(unittest.TestCase):
    def test_existing_request_does_not_get_fabricated_export_evidence(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE data_subject_requests (id INTEGER PRIMARY KEY)"))
            connection.execute(text("INSERT INTO data_subject_requests (id) VALUES (1)"))
            migration = importlib.import_module("migrations.versions.20261107_0050_subject_export_evidence")
            original_op = migration.op
            migration.op = Operations(MigrationContext.configure(connection))
            try:
                migration.upgrade()
            finally:
                migration.op = original_op
            row = connection.execute(text(
                "SELECT prepared_export_sha256, prepared_export_at FROM data_subject_requests WHERE id = 1"
            )).one()
            self.assertIsNone(row.prepared_export_sha256)
            self.assertIsNone(row.prepared_export_at)
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
