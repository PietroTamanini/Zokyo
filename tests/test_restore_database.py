import gzip
import hashlib
import json

from scripts.restore_database import validate_portable_dump, verify_backup


def test_verificacao_de_backup_do_banco_detecta_integridade(tmp_path):
    backup = tmp_path / "zokyo_test.sql.gz"
    with gzip.open(backup, "wb") as handle:
        handle.write(b"CREATE DATABASE zokyo_test;\n")
    metadata = tmp_path / "zokyo_test.sql.gz.json"
    metadata.write_text(json.dumps({
        "application": "Zokyo",
        "kind": "database-backup",
        "output_file": backup.name,
        "output_size_bytes": backup.stat().st_size,
        "output_sha256": hashlib.sha256(backup.read_bytes()).hexdigest(),
    }), encoding="utf-8")
    assert verify_backup(backup, metadata)["kind"] == "database-backup"
    backup.write_bytes(backup.read_bytes() + b"corrompido")
    try:
        verify_backup(backup, metadata)
    except ValueError as exc:
        assert "Tamanho" in str(exc) or "SHA-256" in str(exc)
    else:
        raise AssertionError("Backup corrompido foi aceito")


def test_restore_rejeita_dump_que_seleciona_outro_banco(tmp_path):
    backup = tmp_path / "legado.sql.gz"
    with gzip.open(backup, "wb") as handle:
        handle.write(b"-- dump legado\nCREATE DATABASE `zokyo`;\nUSE `zokyo`;\n")
    try:
        validate_portable_dump(backup)
    except ValueError as exc:
        assert "nao portavel" in str(exc)
    else:
        raise AssertionError("Dump com troca de banco foi aceito")


def test_restore_aceita_dump_portavel(tmp_path):
    backup = tmp_path / "portavel.sql"
    backup.write_bytes(b"CREATE TABLE exemplo (id INT);\nINSERT INTO exemplo VALUES (1);\n")
    validate_portable_dump(backup)
