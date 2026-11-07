"""Evita restauração acidental sobre o banco operacional."""
import json
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import restore_database


class RestoreGuardTests(unittest.TestCase):
    def test_broken_pipe_reports_database_client_error(self):
        class BrokenStdin(io.BytesIO):
            def write(self, _data):
                raise BrokenPipeError()

        class FailedClient:
            stdin = BrokenStdin()
            stdout = io.BytesIO()
            stderr = io.BytesIO(b"Access denied for restore target")

            def wait(self):
                return 1

        with tempfile.TemporaryDirectory() as directory:
            backup = Path(directory) / "dump.sql"
            backup.write_bytes(b"CREATE TABLE smoke_test (id INT);\n")
            with patch.object(restore_database.shutil, "which", return_value="mysql"):
                with patch.object(restore_database.subprocess, "Popen", return_value=FailedClient()):
                    with self.assertRaisesRegex(RuntimeError, "Access denied for restore target"):
                        restore_database.restore(backup, "mysql://user:pass@localhost/disposable")

    def test_explicit_disposable_target_or_in_place_confirmation_required(self):
        with tempfile.TemporaryDirectory() as directory:
            backup = Path(directory) / "zokyo.sql"
            backup.write_bytes(b"CREATE TABLE smoke_test (id INT);\n")
            metadata = Path(str(backup) + ".json")
            metadata.write_text(json.dumps({
                "kind": "database-backup", "database": "zokyo", "host": "db",
                "output_file": backup.name, "output_size_bytes": backup.stat().st_size,
                "output_sha256": restore_database.sha256_file(backup),
            }), encoding="utf-8")
            arguments = ["restore_database.py", "--backup", str(backup)]
            source = "mysql+pymysql://user:pass@db/zokyo"
            disposable = "mysql+pymysql://user:pass@db/zokyo_disposable"
            with patch.object(sys, "argv", arguments), patch.object(restore_database, "restore") as restore:
                with patch.dict(os.environ, {"DATABASE_URL": source, "RESTORE_DATABASE_URL": ""}):
                    self.assertEqual(restore_database.main(), 1)
                with patch.dict(os.environ, {"DATABASE_URL": source, "RESTORE_DATABASE_URL": source}):
                    self.assertEqual(restore_database.main(), 1)
                restore.assert_not_called()
                with patch.dict(os.environ, {"DATABASE_URL": source, "RESTORE_DATABASE_URL": disposable}):
                    self.assertEqual(restore_database.main(), 0)
                restore.assert_called_once_with(backup.resolve(), disposable, "mysql")
                with patch.object(sys, "argv", arguments + ["--confirm-in-place"]):
                    with patch.dict(os.environ, {"DATABASE_URL": source, "RESTORE_DATABASE_URL": source}):
                        self.assertEqual(restore_database.main(), 0)


if __name__ == "__main__":
    unittest.main()
