"""A migration 0049 amplia campos cifrados sem inventar migração de dados legados."""
import importlib
import unittest

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text


class PrivacyFieldMigrationTests(unittest.TestCase):
    def test_legacy_rows_remain_readable_and_columns_allow_ciphertext(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            connection.execute(text("""
                CREATE TABLE data_subject_requests (
                    id INTEGER PRIMARY KEY, requester_name VARCHAR(160),
                    requester_email VARCHAR(254), identity_reference VARCHAR(200),
                    delivery_reference VARCHAR(200)
                )
            """))
            connection.execute(text(
                "CREATE INDEX ix_data_subject_requests_requester_email "
                "ON data_subject_requests (requester_email)"
            ))
            connection.execute(text("""
                CREATE TABLE privacy_incidents (
                    id INTEGER PRIMARY KEY, title VARCHAR(200) NOT NULL,
                    notification_reference VARCHAR(200)
                )
            """))
            connection.execute(text("""
                INSERT INTO data_subject_requests
                    (id, requester_name, requester_email)
                VALUES (1, 'Titular legado', 'legado@example.test')
            """))
            connection.execute(text("""
                INSERT INTO privacy_incidents (id, title)
                VALUES (1, 'Incidente legado')
            """))
            migration = importlib.import_module("migrations.versions.20261106_0049_encrypt_privacy_fields")
            original_op = migration.op
            migration.op = Operations(MigrationContext.configure(connection))
            try:
                migration.upgrade()
            finally:
                migration.op = original_op
            fields = {row.name: row.type for row in connection.execute(text(
                "PRAGMA table_info(data_subject_requests)"
            ))}
            self.assertEqual(fields["requester_name"], "TEXT")
            self.assertEqual(fields["requester_email"], "TEXT")
            self.assertEqual(fields["identity_reference"], "TEXT")
            self.assertEqual(fields["delivery_reference"], "TEXT")
            self.assertEqual(connection.execute(text(
                "SELECT requester_email FROM data_subject_requests WHERE id = 1"
            )).scalar_one(), "legado@example.test")
            self.assertEqual(connection.execute(text(
                "SELECT title FROM privacy_incidents WHERE id = 1"
            )).scalar_one(), "Incidente legado")
            self.assertFalse(connection.execute(text(
                "SELECT 1 FROM sqlite_master WHERE type='index' "
                "AND name='ix_data_subject_requests_requester_email'"
            )).first())
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
