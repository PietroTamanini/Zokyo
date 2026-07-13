from scripts.backup_storage import create_backup, restore_backup


def test_backup_storage_verifica_e_restaura(tmp_path):
    source = tmp_path / "uploads"
    source.mkdir()
    (source / "reports").mkdir()
    (source / "reports" / "laudo.pdf").write_bytes(b"%PDF-backup-test")
    (source / "foto.jpg").write_bytes(b"jpeg-test")
    archive = tmp_path / "storage.tar.gz"

    manifest = create_backup(source, archive)
    assert len(manifest["files"]) == 2
    assert archive.exists()
    restore_backup(archive, tmp_path / "verify", verify_only=True)

    restored = tmp_path / "restored"
    restore_backup(archive, restored)
    assert (restored / "reports" / "laudo.pdf").read_bytes() == b"%PDF-backup-test"
    assert (restored / "foto.jpg").read_bytes() == b"jpeg-test"
