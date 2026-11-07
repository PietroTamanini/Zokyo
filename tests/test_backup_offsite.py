import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

from scripts import backup_offsite
from scripts.audit_anchor import publish_anchor
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
    assert "*.audit-anchor.json" in command
    assert "--immutable" in command
    with pytest.raises(ValueError):
        build_rclone_command("rclone", tmp_path, "s3:destino\nmalicioso")


def test_copia_externa_exige_ancora_quando_configurada(tmp_path, monkeypatch):
    (tmp_path / "zokyo.sql.gz.enc").write_bytes(b"encrypted")
    calls = []
    monkeypatch.setattr(backup_offsite.shutil, "which", lambda _: "/usr/bin/rclone")
    monkeypatch.setattr(backup_offsite.subprocess, "run", lambda command, **_kwargs: calls.append(command))
    monkeypatch.setattr(backup_offsite, "notify_failure", lambda _message: False)
    monkeypatch.setattr(sys, "argv", [
        "backup_offsite.py", "--source", str(tmp_path), "--remote", "s3:zokyo",
        "--require-audit-anchor",
    ])
    assert backup_offsite.main() == 1
    assert calls == []
    publish_anchor(tmp_path, {
        "checked": 1, "legacy": 0, "errors": [],
        "head_hash": "a" * 64, "last_event_id": 1,
    })
    assert backup_offsite.main() == 0
    assert "*.audit-anchor.json" in calls[0]
