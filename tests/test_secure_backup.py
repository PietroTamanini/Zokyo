"""Backup criptografado deve ser verificável e não publicar dump em claro."""
import base64
import gzip
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import backup_secure, restore_database


class SecureBackupTests(unittest.TestCase):
    def test_encrypted_backup_roundtrip_and_tamper_detection(self):
        key = base64.urlsafe_b64encode(b"k" * 32).decode()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)

            def fake_dump(_command, target, compress):
                self.assertTrue(compress)
                with gzip.open(target, "wb") as stream:
                    stream.write(b"CREATE TABLE privacy_test (id INT);\n")

            with patch.dict(os.environ, {"BACKUP_ENCRYPTION_KEY": key}):
                with patch.object(backup_secure.backup_database, "resolve_mysqldump", return_value="mysqldump"):
                    with patch.object(backup_secure.backup_database, "run_dump", side_effect=fake_dump):
                        encrypted = backup_secure.create_secure_database_backup(
                            "mysql+pymysql://user:pass@db/zokyo", output,
                        )
                self.assertTrue(encrypted.name.endswith(".sql.gz.enc"))
                self.assertEqual({path.name for path in output.iterdir()}, {
                    encrypted.name, encrypted.name + ".json",
                })
                metadata = restore_database.verify_backup(encrypted, Path(str(encrypted) + ".json"))
                with restore_database.prepared_backup(encrypted, metadata) as plaintext:
                    with gzip.open(plaintext, "rb") as stream:
                        self.assertEqual(stream.read(), b"CREATE TABLE privacy_test (id INT);\n")
                with patch.object(sys, "argv", ["restore_database.py", "--backup", str(encrypted), "--verify-only"]):
                    self.assertEqual(restore_database.main(), 0)
                env_file = output / "test.env"
                env_file.write_text("BACKUP_ENCRYPTION_KEY=" + key + "\n", encoding="utf-8")
                with patch.dict(os.environ, {"BACKUP_ENCRYPTION_KEY": ""}):
                    with patch.object(sys, "argv", ["restore_database.py", "--backup", str(encrypted), "--env-file", str(env_file), "--verify-only"]):
                        self.assertEqual(restore_database.main(), 0)
                with encrypted.open("r+b") as stream:
                    stream.seek(-1, 2)
                    stream.write(b"x")
                with self.assertRaisesRegex(ValueError, "SHA-256"):
                    restore_database.verify_backup(encrypted, Path(str(encrypted) + ".json"))


if __name__ == "__main__":
    unittest.main()
