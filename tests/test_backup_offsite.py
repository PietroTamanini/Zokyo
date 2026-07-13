import os
from datetime import datetime, timedelta, timezone

import pytest

from scripts.backup_offsite import build_rclone_command, check_backup_age


def test_backup_externo_exige_artefato_criptografado_recente(tmp_path, monkeypatch):
    with pytest.raises(RuntimeError):
        check_backup_age(tmp_path, 26)
    backup = tmp_path / "zokyo.sql.gz.enc"
    backup.write_bytes(b"encrypted")
    assert check_backup_age(tmp_path, 26) == backup
    old = datetime.now(timezone.utc) - timedelta(hours=30)
    os.utime(backup, (old.timestamp(), old.timestamp()))
    with pytest.raises(RuntimeError, match="excede"):
        check_backup_age(tmp_path, 26)


def test_comando_rclone_nao_usa_shell_e_filtra_criptografados(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.backup_offsite.shutil.which", lambda _: "/usr/bin/rclone")
    command = build_rclone_command("rclone", tmp_path, "s3:zokyo/producao")
    assert command[:2] == ["/usr/bin/rclone", "copy"]
    assert "*.enc" in command
    assert "--immutable" in command
    with pytest.raises(ValueError):
        build_rclone_command("rclone", tmp_path, "s3:destino\nmalicioso")
