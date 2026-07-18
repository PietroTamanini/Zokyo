import base64
import gzip
import io
import json
import os
import tarfile
from argparse import Namespace
from datetime import datetime, timedelta, timezone

import pytest

from scripts import backup_crypto, backup_database, backup_offsite, backup_storage, restore_database


class FakeProcess:
    def __init__(self, stdout=b"dump", stderr=b"", return_code=0):
        self.stdout = io.BytesIO(stdout)
        self.stderr = io.BytesIO(stderr)
        self.stdin = io.BytesIO()
        self._return_code = return_code

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def wait(self):
        return self._return_code


def _metadata_for(backup):
    return {
        "application": "Zokyo",
        "kind": "database-backup",
        "output_file": backup.name,
        "output_size_bytes": backup.stat().st_size,
        "output_sha256": restore_database.sha256_file(backup),
    }


def test_backup_database_funcoes_e_main_cobrem_sucesso_e_falhas(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join([
            "# comentario",
            "DATABASE_URL='mysql+pymysql://user:pass@localhost:3307/zokyo'",
            "IGNORAR",
        ]),
        encoding="utf-8",
    )
    assert backup_database.load_env_file(tmp_path / "missing.env") == {}
    assert backup_database.get_env("DATABASE_URL", backup_database.load_env_file(env_file)).endswith("/zokyo")
    with pytest.raises(ValueError, match="Unsupported"):
        backup_database.parse_database_url("sqlite:///x.db")
    with pytest.raises(ValueError, match="database name"):
        backup_database.parse_database_url("mysql://user:pass@localhost/")
    with pytest.raises(ValueError, match="username"):
        backup_database.parse_database_url("mysql://localhost/zokyo")

    db_config = backup_database.parse_database_url("mysql://user:p%40ss@db.local/zokyo")
    defaults = backup_database.write_defaults_file(db_config)
    try:
        assert "password=p@ss" in defaults.read_text(encoding="utf-8")
        command = backup_database.build_dump_command("/usr/bin/mysqldump", defaults, db_config, ["--where=1=1"])
        assert command[0] == "/usr/bin/mysqldump"
        assert "--where=1=1" in command
    finally:
        defaults.unlink(missing_ok=True)

    binary = tmp_path / "mysqldump.exe"
    binary.write_text("", encoding="utf-8")
    monkeypatch.setattr(backup_database.shutil, "which", lambda _binary: "C:/mysql/mysqldump.exe")
    assert backup_database.resolve_mysqldump("mysqldump") == "C:/mysql/mysqldump.exe"
    monkeypatch.setattr(backup_database.shutil, "which", lambda _binary: None)
    assert backup_database.resolve_mysqldump(str(binary)) == str(binary)
    with pytest.raises(FileNotFoundError):
        backup_database.resolve_mysqldump(str(tmp_path / "missing-mysqldump"))
    monkeypatch.setattr(
        backup_database.Path,
        "chmod",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("chmod")),
    )
    defaults_no_chmod = backup_database.write_defaults_file(db_config)
    defaults_no_chmod.unlink(missing_ok=True)

    monkeypatch.setattr(backup_database.subprocess, "Popen", lambda *args, **kwargs: FakeProcess(stdout=b"SQL", return_code=0))
    output = tmp_path / "backup.sql"
    backup_database.run_dump(["mysqldump"], output, compress=False)
    assert output.read_bytes() == b"SQL"
    compressed = tmp_path / "backup.sql.gz"
    backup_database.run_dump(["mysqldump"], compressed, compress=True)
    with gzip.open(compressed, "rb") as handle:
        assert handle.read() == b"SQL"
    monkeypatch.setattr(
        backup_database.subprocess,
        "Popen",
        lambda *args, **kwargs: type("BadPipes", (), {
            "__enter__": lambda self: self,
            "__exit__": lambda self, exc_type, exc, tb: False,
            "stdout": None,
            "stderr": io.BytesIO(),
        })(),
    )
    with pytest.raises(RuntimeError, match="pipes"):
        backup_database.run_dump(["mysqldump"], tmp_path / "bad.sql", compress=False)
    monkeypatch.setattr(backup_database.subprocess, "Popen", lambda *args, **kwargs: FakeProcess(stdout=b"SQL", return_code=0))
    metadata = tmp_path / "backup.sql.json"
    backup_database.write_metadata(metadata, db_config, output, datetime.now(timezone.utc), datetime.now(timezone.utc))
    assert json.loads(metadata.read_text(encoding="utf-8"))["output_sha256"]

    old = tmp_path / "zokyo_old.sql"
    old.write_text("old", encoding="utf-8")
    (tmp_path / "zokyo_dir.sql").mkdir()
    old_time = datetime.now(timezone.utc) - timedelta(days=30)
    os.utime(old, (old_time.timestamp(), old_time.timestamp()))
    assert backup_database.prune_old_backups(tmp_path, 14) == [old]
    assert backup_database.prune_old_backups(tmp_path, 0) == []
    monkeypatch.setattr("sys.argv", ["backup_database.py", "--keep-days", "3", "--extra-mysqldump-arg=--no-tablespaces"])
    parsed = backup_database.parse_args()
    assert parsed.keep_days == 3
    assert parsed.extra_mysqldump_arg == ["--no-tablespaces"]

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    old_in_out = out_dir / "zokyo_old.sql"
    old_in_out.write_text("old", encoding="utf-8")
    os.utime(old_in_out, (old_time.timestamp(), old_time.timestamp()))
    monkeypatch.setattr(backup_database, "parse_args", lambda: Namespace(
        env_file=str(env_file),
        output_dir=str(out_dir),
        keep_days=1,
        mysqldump=str(binary),
        no_compress=True,
        extra_mysqldump_arg=[],
    ))
    assert backup_database.main() == 0
    created_output = capsys.readouterr().out
    assert "Backup created" in created_output
    assert "Removed old backup files: 1" in created_output

    monkeypatch.setattr(backup_database, "parse_args", lambda: Namespace(
        env_file=str(tmp_path / "empty.env"),
        output_dir=str(tmp_path / "out"),
        keep_days=14,
        mysqldump=str(binary),
        no_compress=False,
        extra_mysqldump_arg=[],
    ))
    assert backup_database.main() == 2

    invalid_env = tmp_path / "invalid.env"
    invalid_env.write_text("DATABASE_URL=sqlite:///local.db", encoding="utf-8")
    monkeypatch.setattr(backup_database, "parse_args", lambda: Namespace(
        env_file=str(invalid_env),
        output_dir=str(tmp_path / "out-invalid"),
        keep_days=14,
        mysqldump=str(binary),
        no_compress=False,
        extra_mysqldump_arg=[],
    ))
    assert backup_database.main() == 2

    monkeypatch.setattr(backup_database, "parse_args", lambda: Namespace(
        env_file=str(env_file),
        output_dir=str(tmp_path / "out2"),
        keep_days=14,
        mysqldump=str(binary),
        no_compress=False,
        extra_mysqldump_arg=[],
    ))
    monkeypatch.setattr(backup_database.subprocess, "Popen", lambda *args, **kwargs: FakeProcess(stderr=b"boom", return_code=7))
    assert backup_database.main() == 1


def test_restore_database_verificacao_restore_e_main(monkeypatch, tmp_path, capsys):
    backup = tmp_path / "zokyo.sql"
    backup.write_bytes(b"CREATE TABLE t (id INT);\n")
    metadata = tmp_path / "zokyo.sql.json"
    metadata.write_text(json.dumps(_metadata_for(backup)), encoding="utf-8")
    assert restore_database.verify_backup(backup, metadata)["output_file"] == backup.name

    with pytest.raises(FileNotFoundError):
        restore_database.verify_backup(tmp_path / "missing.sql", metadata)
    wrong = tmp_path / "wrong.json"
    wrong.write_text(json.dumps({**_metadata_for(backup), "kind": "other"}), encoding="utf-8")
    with pytest.raises(ValueError, match="Metadata"):
        restore_database.verify_backup(backup, wrong)
    wrong.write_text(json.dumps({**_metadata_for(backup), "kind": "database-backup", "output_file": "other.sql"}), encoding="utf-8")
    with pytest.raises(ValueError, match="outro"):
        restore_database.verify_backup(backup, wrong)
    wrong.write_text(json.dumps({**_metadata_for(backup), "output_sha256": "bad"}), encoding="utf-8")
    with pytest.raises(ValueError, match="SHA"):
        restore_database.verify_backup(backup, wrong)

    mysql = tmp_path / "mysql.exe"
    mysql.write_text("", encoding="utf-8")
    monkeypatch.setattr(restore_database.shutil, "which", lambda binary: None)
    monkeypatch.setattr(restore_database.subprocess, "Popen", lambda *args, **kwargs: FakeProcess(stdout=b"", stderr=b"", return_code=0))
    restore_database.restore(backup, "mysql://user:pass@localhost/zokyo", str(mysql))
    monkeypatch.setattr(restore_database.subprocess, "Popen", lambda *args, **kwargs: FakeProcess(stdout=b"", stderr=b"erro mysql", return_code=2))
    with pytest.raises(RuntimeError, match="erro mysql"):
        restore_database.restore(backup, "mysql://user:pass@localhost/zokyo", str(mysql))
    with pytest.raises(FileNotFoundError):
        restore_database.restore(backup, "mysql://user:pass@localhost/zokyo", str(tmp_path / "missing-mysql"))
    monkeypatch.setattr(
        restore_database.subprocess,
        "Popen",
        lambda *args, **kwargs: type("NoStdin", (), {
            "stdin": None,
            "stdout": io.BytesIO(),
            "stderr": io.BytesIO(),
        })(),
    )
    with pytest.raises(RuntimeError, match="pipe de entrada"):
        restore_database.restore(backup, "mysql://user:pass@localhost/zokyo", str(mysql))

    monkeypatch.setattr("sys.argv", ["restore_database.py", "--backup", str(backup), "--metadata", str(metadata), "--verify-only"])
    assert restore_database.main() == 0
    assert "Backup valido" in capsys.readouterr().out
    env_file = tmp_path / ".env.restore"
    env_file.write_text("DATABASE_URL=mysql://user:pass@localhost/zokyo", encoding="utf-8")
    monkeypatch.setenv("DATABASE_URL", "mysql://user:pass@localhost/zokyo")
    monkeypatch.setattr(restore_database.subprocess, "Popen", lambda *args, **kwargs: FakeProcess(stdout=b"", stderr=b"", return_code=0))
    monkeypatch.setattr("sys.argv", ["restore_database.py", "--backup", str(backup), "--metadata", str(metadata), "--env-file", str(env_file), "--mysql", str(mysql)])
    assert restore_database.main() == 0
    assert "Restore concluido" in capsys.readouterr().out
    monkeypatch.setattr("sys.argv", ["restore_database.py", "--backup", str(backup), "--metadata", str(metadata), "--env-file", str(tmp_path / "empty.env"), "--mysql", str(mysql)])
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert restore_database.main() == 1


def test_backup_crypto_chaves_erros_e_main(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("BACKUP_ENCRYPTION_KEY", "not-base64")
    with pytest.raises(ValueError, match="base64"):
        backup_crypto.key_from_env()
    monkeypatch.setenv("BACKUP_ENCRYPTION_KEY", base64.urlsafe_b64encode(b"short").decode())
    with pytest.raises(ValueError, match="32 bytes"):
        backup_crypto.key_from_env()
    key = b"k" * 32
    monkeypatch.setenv("BACKUP_ENCRYPTION_KEY", base64.urlsafe_b64encode(key).decode())
    assert backup_crypto.key_from_env() == key

    source = tmp_path / "plain.txt"
    source.write_text("dados", encoding="utf-8")
    with pytest.raises(ValueError, match="diferentes"):
        backup_crypto.encrypt_file(source, source, key)
    encrypted = tmp_path / "plain.enc"
    decrypted = tmp_path / "plain.out"
    monkeypatch.setattr("sys.argv", ["backup_crypto.py", "encrypt", str(source), str(encrypted)])
    assert backup_crypto.main() == 0
    monkeypatch.setattr("sys.argv", ["backup_crypto.py", "decrypt", str(encrypted), str(decrypted)])
    assert backup_crypto.main() == 0
    assert decrypted.read_text(encoding="utf-8") == "dados"
    assert "Arquivo decrypt concluido" in capsys.readouterr().out
    monkeypatch.setattr(
        backup_crypto.Path,
        "replace",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("replace")),
    )
    with pytest.raises(OSError, match="replace"):
        backup_crypto.encrypt_file(source, tmp_path / "replace-fail.enc", key)

    bad = tmp_path / "bad.enc"
    bad.write_bytes(b"BAD")
    with pytest.raises(ValueError, match="Formato"):
        backup_crypto.decrypt_file(bad, tmp_path / "bad.out", key)
    bad.write_bytes(backup_crypto.MAGIC + b"\x00")
    with pytest.raises(ValueError, match="truncado"):
        backup_crypto.decrypt_file(bad, tmp_path / "bad2.out", key)
    bad.write_bytes(backup_crypto.MAGIC + (1).to_bytes(4, "big") + b"short")
    with pytest.raises(ValueError, match="truncado"):
        backup_crypto.decrypt_file(bad, tmp_path / "bad3.out", key)
    bad.write_bytes(backup_crypto.MAGIC + (0).to_bytes(4, "big") + b"x")
    with pytest.raises(ValueError, match="extras"):
        backup_crypto.decrypt_file(bad, tmp_path / "bad4.out", key)
    bad.write_bytes(backup_crypto.MAGIC + (backup_crypto.CHUNK_SIZE + 17).to_bytes(4, "big"))
    with pytest.raises(ValueError, match="excede"):
        backup_crypto.decrypt_file(bad, tmp_path / "bad5.out", key)


def test_backup_storage_erros_integridade_e_main(tmp_path, monkeypatch, capsys):
    source = tmp_path / "uploads"
    source.mkdir()
    (source / "a.txt").write_text("A", encoding="utf-8")
    archive = tmp_path / "storage.tar.gz"
    backup_storage.create_backup(source, archive)

    no_manifest = tmp_path / "no-manifest.tar.gz"
    with tarfile.open(no_manifest, "w:gz") as tar:
        info = tarfile.TarInfo("a.txt")
        payload = b"A"
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    with pytest.raises(ValueError, match="Manifesto"):
        backup_storage.restore_backup(no_manifest, tmp_path / "restore")

    unsafe = tmp_path / "unsafe.tar.gz"
    with tarfile.open(unsafe, "w:gz") as tar:
        info = tarfile.TarInfo("../escape.txt")
        payload = b"x"
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    with pytest.raises(ValueError, match="insegura"):
        backup_storage.restore_backup(unsafe, tmp_path / "restore")

    corrupt = tmp_path / "corrupt.tar.gz"
    manifest = {
        "files": [{"path": "missing.txt", "size": 1, "sha256": "bad"}],
    }
    manifest_bytes = json.dumps(manifest).encode()
    with tarfile.open(corrupt, "w:gz") as tar:
        info = tarfile.TarInfo(backup_storage.MANIFEST_NAME)
        info.size = len(manifest_bytes)
        tar.addfile(info, io.BytesIO(manifest_bytes))
    with pytest.raises(ValueError, match="ausente"):
        backup_storage.restore_backup(corrupt, tmp_path / "restore")
    mismatch = tmp_path / "mismatch.tar.gz"
    file_payload = b"A"
    manifest = {
        "files": [{"path": "a.txt", "size": len(file_payload), "sha256": "bad"}],
    }
    manifest_bytes = json.dumps(manifest).encode()
    with tarfile.open(mismatch, "w:gz") as tar:
        info = tarfile.TarInfo(backup_storage.MANIFEST_NAME)
        info.size = len(manifest_bytes)
        tar.addfile(info, io.BytesIO(manifest_bytes))
        info = tarfile.TarInfo("a.txt")
        info.size = len(file_payload)
        tar.addfile(info, io.BytesIO(file_payload))
    with pytest.raises(ValueError, match="integridade"):
        backup_storage.restore_backup(mismatch, tmp_path / "restore")

    monkeypatch.setattr("sys.argv", ["backup_storage.py", "create", "--source", str(source), "--output", str(tmp_path / "main.tar.gz")])
    assert backup_storage.main() == 0
    monkeypatch.setattr("sys.argv", ["backup_storage.py", "restore", "--archive", str(archive), "--destination", str(tmp_path / "main-restore"), "--verify-only"])
    assert backup_storage.main() == 0
    assert "Backup verificado" in capsys.readouterr().out


def test_backup_offsite_webhook_main_e_erros(monkeypatch, tmp_path, capsys):
    assert backup_offsite.newest_encrypted_backup(tmp_path) is None
    encrypted = tmp_path / "b.enc"
    encrypted.write_text("enc", encoding="utf-8")
    assert backup_offsite.newest_encrypted_backup(tmp_path) == encrypted
    monkeypatch.setattr(backup_offsite.shutil, "which", lambda binary: None)
    with pytest.raises(FileNotFoundError):
        backup_offsite.build_rclone_command("rclone", tmp_path, "s3:bucket")

    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)
    assert backup_offsite.notify_failure("x") is False
    monkeypatch.setenv("ALERT_WEBHOOK_ALLOWED_HOSTS", "alerts.example.com")
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://alerts.example.com/hook")
    monkeypatch.setattr(backup_offsite.socket, "getaddrinfo", lambda *args, **kwargs: [(None, None, None, None, ("8.8.8.8", 443))])

    posted = []

    class FakeResponse:
        def raise_for_status(self):
            posted.append("ok")

    monkeypatch.setattr(backup_offsite.requests, "post", lambda *args, **kwargs: FakeResponse())
    assert backup_offsite._safe_webhook("https://alerts.example.com/hook") is True
    monkeypatch.setattr(backup_offsite.socket, "getaddrinfo", lambda *args, **kwargs: [(None, None, None, None, ("127.0.0.1", 443))])
    assert backup_offsite._safe_webhook("https://alerts.example.com/hook") is False
    monkeypatch.setattr(backup_offsite.socket, "getaddrinfo", lambda *args, **kwargs: (_ for _ in ()).throw(backup_offsite.socket.gaierror()))
    assert backup_offsite._safe_webhook("https://alerts.example.com/hook") is False
    monkeypatch.setattr(backup_offsite.socket, "getaddrinfo", lambda *args, **kwargs: [(None, None, None, None, ("8.8.8.8", 443))])
    assert backup_offsite._safe_webhook("http://alerts.example.com/hook") is False
    assert backup_offsite._safe_webhook("https://user:pass@alerts.example.com/hook#frag") is False
    assert backup_offsite.notify_failure("falha") is True
    assert posted == ["ok"]

    monkeypatch.setattr(backup_offsite.shutil, "which", lambda binary: "/usr/bin/rclone")
    monkeypatch.setattr(backup_offsite.subprocess, "run", lambda *args, **kwargs: None)
    monkeypatch.setattr("sys.argv", ["backup_offsite.py", "--source", str(tmp_path), "--remote", "s3:zokyo"])
    assert backup_offsite.main() == 0
    assert "Backup externo sincronizado" in capsys.readouterr().out

    class BrokenRequests:
        class RequestException(Exception):
            pass

    def broken_notify(message):
        raise backup_offsite.requests.RequestException("sem webhook")

    monkeypatch.setattr(backup_offsite, "check_backup_age", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("velho")))
    monkeypatch.setattr(backup_offsite, "notify_failure", broken_notify)
    assert backup_offsite.main() == 1
