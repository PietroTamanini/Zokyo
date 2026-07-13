#!/usr/bin/env python3
"""Copia backups criptografados para storage externo e monitora sua idade."""
import argparse
import ipaddress
import json
import os
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests


def _safe_webhook(url):
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    allowed = {item.strip().lower() for item in os.environ.get("ALERT_WEBHOOK_ALLOWED_HOSTS", "").split(",") if item.strip()}
    if parsed.scheme != "https" or hostname not in allowed or parsed.username or parsed.password or parsed.fragment:
        return False
    try:
        for result in socket.getaddrinfo(hostname, 443):
            address = ipaddress.ip_address(result[4][0])
            if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
                return False
    except (socket.gaierror, ValueError):
        return False
    return True


def newest_encrypted_backup(source: Path) -> Path | None:
    files = [path for path in source.glob("*.enc") if path.is_file() and not path.is_symlink()]
    return max(files, key=lambda path: path.stat().st_mtime, default=None)


def check_backup_age(source: Path, max_age_hours: int) -> Path:
    newest = newest_encrypted_backup(source)
    if not newest:
        raise RuntimeError("Nenhum backup criptografado encontrado.")
    age_seconds = datetime.now(timezone.utc).timestamp() - newest.stat().st_mtime
    if age_seconds > max_age_hours * 3600:
        raise RuntimeError(f"Backup mais recente excede {max_age_hours} horas.")
    return newest


def build_rclone_command(binary: str, source: Path, remote: str) -> list[str]:
    resolved = shutil.which(binary)
    if not resolved:
        raise FileNotFoundError("rclone nao encontrado.")
    if not remote or any(character in remote for character in "\r\n\0"):
        raise ValueError("Destino rclone invalido.")
    return [
        resolved, "copy", str(source.resolve()), remote,
        "--include", "*.enc", "--include", "*.json", "--checksum", "--immutable",
        "--retries", "3", "--low-level-retries", "5",
    ]


def notify_failure(message: str):
    webhook = os.environ.get("ALERT_WEBHOOK_URL", "").strip()
    if not webhook or not _safe_webhook(webhook):
        return False
    requests.post(
        webhook,
        data=json.dumps({"severity": "critical", "source": "backup", "message": message[:500]}),
        headers={"Content-Type": "application/json"}, timeout=5, allow_redirects=False,
    ).raise_for_status()
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("backups"))
    parser.add_argument("--remote", required=True, help="Destino configurado no rclone, por exemplo: s3:zokyo/producao")
    parser.add_argument("--max-age-hours", type=int, default=26)
    parser.add_argument("--rclone", default="rclone")
    args = parser.parse_args()
    try:
        check_backup_age(args.source, args.max_age_hours)
        command = build_rclone_command(args.rclone, args.source, args.remote)
        subprocess.run(command, check=True, timeout=3600)  # nosec B603
    except Exception as exc:
        try:
            notify_failure(str(exc))
        except requests.RequestException:
            pass
        print(f"Falha no backup externo: {exc}", file=sys.stderr)
        return 1
    print(f"Backup externo sincronizado: {args.remote}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
