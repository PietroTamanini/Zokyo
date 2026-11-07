"""Exercita o backfill e os bloqueios físicos da migration 0046."""
import importlib
import json
import unittest

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DatabaseError


class SubjectRequestMigrationTests(unittest.TestCase):
    def test_existing_request_gets_protected_baseline(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE usuarios (id INTEGER PRIMARY KEY)"))
            connection.execute(text("""
                CREATE TABLE data_subject_requests (
                    id INTEGER PRIMARY KEY,
                    solicitado_por_id INTEGER,
                    request_type VARCHAR(40) NOT NULL,
                    status VARCHAR(30) NOT NULL,
                    identity_verified BOOLEAN NOT NULL,
                    due_at DATETIME,
                    response_notes TEXT,
                    concluido_em DATETIME
                )
            """))
            connection.execute(text("INSERT INTO usuarios (id) VALUES (7)"))
            connection.execute(text("""
                INSERT INTO data_subject_requests
                    (id, solicitado_por_id, request_type, status, identity_verified, response_notes)
                VALUES (5, 7, 'access', 'completed', 1, 'Resposta antiga')
            """))
            migration = importlib.import_module("migrations.versions.20261106_0046_subject_request_history")
            original_op = migration.op
            migration.op = Operations(MigrationContext.configure(connection))
            try:
                migration.upgrade()
            finally:
                migration.op = original_op
            row = connection.execute(text(
                "SELECT request_id, actor_id, action, snapshot FROM data_subject_request_revisions"
            )).one()
            self.assertEqual((row.request_id, row.actor_id, row.action), (5, 7, "baseline"))
            snapshot = json.loads(row.snapshot)
            self.assertEqual(snapshot["status"], "completed")
            self.assertEqual(snapshot["response_notes"], "Resposta antiga")
            self.assertIsNone(snapshot["delivery_reference"])
            with self.assertRaises(DatabaseError):
                connection.execute(text("UPDATE data_subject_request_revisions SET action = 'tampered' WHERE request_id = 5"))
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
