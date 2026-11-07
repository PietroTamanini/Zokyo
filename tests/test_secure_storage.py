"""Recuperação real dos uploads, integridade e bloqueio de destinos inseguros."""
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path

from scripts.secure_storage import (
    create_encrypted_storage_backup,
    restore_encrypted_storage_backup,
)
from scripts import backup_storage


class SecureStorageTests(unittest.TestCase):
    def test_roundtrip_and_guards(self):
        key = b"s" * 32
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            uploads = root / "uploads"
            (uploads / "reports").mkdir(parents=True)
            (uploads / "reports" / "laudo.pdf").write_bytes(b"%PDF-private-test\n")
            (uploads / "foto.jpg").write_bytes(b"\xff\xd8private\xff\xd9")
            backups = root / "backups"
            archive = create_encrypted_storage_backup(uploads, backups, key)
            self.assertEqual({p.name for p in backups.iterdir()}, {archive.name, archive.name + ".json"})
            self.assertNotIn(b"private-test", archive.read_bytes())

            scratch = root / "restore"
            checked = restore_encrypted_storage_backup(archive, scratch, key, verify_only=True, active_source=uploads)
            self.assertEqual(len(checked["files"]), 2)
            self.assertFalse(scratch.exists())
            with self.assertRaisesRegex(ValueError, "uploads ativos"):
                restore_encrypted_storage_backup(archive, uploads, key, active_source=uploads)
            scratch.mkdir()
            (scratch / "existing.txt").write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "vazio"):
                restore_encrypted_storage_backup(archive, scratch, key, active_source=uploads)
            (scratch / "existing.txt").unlink()
            restored = restore_encrypted_storage_backup(archive, scratch, key, active_source=uploads)
            self.assertEqual(restored, checked)
            self.assertEqual((scratch / "reports" / "laudo.pdf").read_bytes(), (uploads / "reports" / "laudo.pdf").read_bytes())
            self.assertEqual((scratch / "foto.jpg").read_bytes(), (uploads / "foto.jpg").read_bytes())

            with archive.open("r+b") as stream:
                stream.seek(-1, 2)
                stream.write(b"x")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                restore_encrypted_storage_backup(archive, scratch, key, verify_only=True, active_source=uploads)

    def test_rejects_symlink_before_publishing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            uploads = root / "uploads"
            uploads.mkdir()
            try:
                (uploads / "linked").symlink_to(root, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("Ambiente não permite links simbólicos")
            with self.assertRaisesRegex(ValueError, "link simbólico"):
                create_encrypted_storage_backup(uploads, root / "backups", b"s" * 32)
            self.assertFalse((root / "backups").exists())

    def test_manifest_rejects_unlisted_archive_member(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive_path = root / "unlisted.tar.gz"
            manifest = json.dumps({"files": []}).encode()
            with tarfile.open(archive_path, "w:gz") as archive:
                entry = tarfile.TarInfo(backup_storage.MANIFEST_NAME)
                entry.size = len(manifest)
                archive.addfile(entry, io.BytesIO(manifest))
                entry = tarfile.TarInfo("unlisted.txt")
                entry.size = 7
                archive.addfile(entry, io.BytesIO(b"private"))
            destination = root / "restored"
            with self.assertRaisesRegex(ValueError, "divergem"):
                backup_storage.restore_backup(archive_path, destination)
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
