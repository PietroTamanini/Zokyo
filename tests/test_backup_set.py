"""A cópia externa deve exigir os dois backups recentes e íntegros."""
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.backup_offsite import check_backup_set
from scripts.audit_anchor import latest_anchor, publish_anchor


class BackupSetTests(unittest.TestCase):
    def test_audit_anchor_is_validated_for_external_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertIsNone(latest_anchor(root, 26))
            anchor = publish_anchor(root, {
                "checked": 1, "legacy": 0, "errors": [],
                "head_hash": "a" * 64, "last_event_id": 1,
            })
            self.assertEqual(latest_anchor(root, 26)[0], anchor)
            anchor.write_text('{"kind":"invalid"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                latest_anchor(root, 26)

    def test_missing_stale_and_corrupt_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def add(name, kind, created):
                archive = root / name
                archive.write_bytes(b"encrypted-" + name.encode())
                metadata = {
                    "kind": kind, "format": "aes256-gcm", "output_file": name,
                    "output_size_bytes": archive.stat().st_size,
                    "output_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                    "created_at": created.isoformat(),
                }
                Path(str(archive) + ".json").write_text(json.dumps(metadata), encoding="utf-8")
                return archive

            now = datetime.now(timezone.utc)
            database = add("db.sql.gz.enc", "database-backup", now)
            with self.assertRaisesRegex(RuntimeError, "private-storage-backup"):
                check_backup_set(root, 26, ("database-backup", "private-storage-backup"))
            storage = add("uploads.tar.gz.enc", "private-storage-backup", now - timedelta(hours=30))
            with self.assertRaisesRegex(RuntimeError, "excede"):
                check_backup_set(root, 26, ("database-backup", "private-storage-backup"))
            sidecar = Path(str(storage) + ".json")
            metadata = json.loads(sidecar.read_text(encoding="utf-8"))
            metadata["created_at"] = now.isoformat()
            sidecar.write_text(json.dumps(metadata), encoding="utf-8")
            result = check_backup_set(root, 26, ("database-backup", "private-storage-backup"))
            self.assertEqual(result, {"database-backup": database, "private-storage-backup": storage})
            storage.write_bytes(b"altered")
            with self.assertRaisesRegex(RuntimeError, "Metadata inválido|SHA-256 inválido"):
                check_backup_set(root, 26, ("database-backup", "private-storage-backup"))


if __name__ == "__main__":
    unittest.main()
