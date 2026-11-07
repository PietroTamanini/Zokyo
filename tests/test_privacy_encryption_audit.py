"""The privacy encryption inventory reports counts without leaking values."""
import os
import unittest

from sqlalchemy import text

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "privacy-encryption-audit-tests-only")
os.environ["REDIS_URL"] = ""
os.environ["SCHEDULER_ENABLED"] = "false"

from app import create_app
from app.extensions import db
from app.models import DataSubjectRequest, PrivacyIncident
from app.services.privacy_encryption_audit import count_privacy_plaintext
from app.utils.field_crypto import encrypt_value


class PrivacyEncryptionAuditTests(unittest.TestCase):
    def test_cli_counts_legacy_plaintext_without_exposing_it(self):
        app = create_app("development")
        app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
        with app.app_context():
            db.create_all()
            db.session.add(DataSubjectRequest(request_type="access", status="open"))
            db.session.add(PrivacyIncident(title="Incidente teste", description="Descrição teste"))
            db.session.commit()
            db.session.execute(text(
                "UPDATE data_subject_requests SET requester_email = 'legado@example.test'"
            ))
            db.session.execute(text(
                "UPDATE privacy_incidents SET title = 'Título legado'"
            ))
            db.session.execute(text(
                "UPDATE data_subject_request_revisions SET snapshot = '{\"status\":\"open\"}'"
            ))
            db.session.commit()
            counts = count_privacy_plaintext()
            self.assertEqual(counts["data_subject_requests.requester_email"], 1)
            self.assertEqual(counts["privacy_incidents.title"], 1)
            self.assertEqual(counts["data_subject_request_revisions.snapshot"], 1)

        result = app.test_cli_runner().invoke(args=["privacy-encryption-audit", "--strict"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Total de valores legados em claro: 3", result.output)
        self.assertNotIn("legado@example.test", result.output)
        self.assertNotIn("Título legado", result.output)

        with app.app_context():
            db.session.execute(text(
                "UPDATE data_subject_requests SET requester_email = :encrypted"
            ), {"encrypted": encrypt_value("legado@example.test")})
            db.session.execute(text(
                "UPDATE privacy_incidents SET title = :encrypted"
            ), {"encrypted": encrypt_value("Título legado")})
            db.session.execute(text(
                "UPDATE data_subject_request_revisions SET snapshot = :encrypted"
            ), {"encrypted": encrypt_value('{"status":"open"}')})
            db.session.commit()
            self.assertEqual(sum(count_privacy_plaintext().values()), 0)
        result = app.test_cli_runner().invoke(args=["privacy-encryption-audit", "--strict"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Total de ciphertexts ilegíveis: 0", result.output)
        with app.app_context():
            db.session.execute(text(
                "UPDATE data_subject_requests SET requester_email = 'ZOKYO-FERNET:v1:marcador-falso'"
            ))
            db.session.commit()
        result = app.test_cli_runner().invoke(args=["privacy-encryption-audit", "--strict"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Total de valores legados em claro: 1", result.output)
        with app.app_context():
            db.session.execute(text(
                "UPDATE data_subject_requests SET requester_email = :encrypted"
            ), {"encrypted": encrypt_value("legado@example.test")})
            db.session.commit()
        with app.app_context():
            db.session.execute(text(
                "UPDATE privacy_incidents SET description = 'zokyo-fernet:v1:token-corrompido'"
            ))
            db.session.commit()
        result = app.test_cli_runner().invoke(args=["privacy-encryption-audit"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Total de ciphertexts ilegíveis: 1", result.output)
        self.assertNotIn("token-corrompido", result.output)
        with app.app_context():
            db.session.remove()
            db.drop_all()
        result = app.test_cli_runner().invoke(args=["privacy-encryption-audit", "--strict"])
        self.assertNotEqual(result.exit_code, 0)  # banco descartado: falha fechada
        self.assertNotIn("legado@example.test", result.output)
        with app.app_context():
            db.session.remove()
            db.engine.dispose()


if __name__ == "__main__":
    unittest.main()
