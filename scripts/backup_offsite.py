#!/usr/bin/env python3
"""Copia backups criptografados para storage externo e monitora sua idade."""
import argparse
import hashlib
import ipaddress
import json
import os
import shutil
import socket
import subprocess  # nosec B404
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

try:
    from scripts.audit_anchor import latest_anchor
except ModuleNotFoundError:  # execução direta a partir de scripts/
    from audit_anchor import latest_anchor


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


def check_backup_set(source: Path, max_age_hours: int, required_kinds: tuple[str, ...]) -> dict[str, Path]:
    """Rejeita pares ausentes/corrompidos e exige backup recente de cada tipo."""
    if max_age_hours <= 0:
        raise ValueError("Prazo máximo do backup deve ser positivo.")
    latest = {}
    archives = sorted(source.glob("*.enc"))
    if not archives:
        raise RuntimeError("Nenhum backup criptografado encontrado.")
    for archive in archives:
        if not archive.is_file() or archive.is_symlink():
            raise RuntimeError(f"Arquivo de backup inválido: {archive.name}")
        sidecar = Path(str(archive) + ".json")
        if not sidecar.is_file() or sidecar.is_symlink():
            raise RuntimeError(f"Metadata ausente para {archive.name}.")
        metadata = json.loads(sidecar.read_text(encoding="utf-8"))
        if (metadata.get("format") != "aes256-gcm" or metadata.get("output_file") != archive.name
                or metadata.get("output_size_bytes") != archive.stat().st_size):
            raise RuntimeError(f"Metadata inválido para {archive.name}.")
        digest = hashlib.sha256()
        with archive.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if metadata.get("output_sha256") != digest.hexdigest():
            raise RuntimeError(f"SHA-256 inválido para {archive.name}.")
        created = datetime.fromisoformat(metadata["created_at"])
        if created.tzinfo is None:
            raise RuntimeError(f"Horário sem fuso para {archive.name}.")
        if (created - datetime.now(timezone.utc)).total_seconds() > 300:
            raise RuntimeError(f"Horário futuro inválido para {archive.name}.")
        kind = metadata.get("kind")
        if kind not in {"database-backup", "private-storage-backup"}:
            raise RuntimeError(f"Tipo de backup desconhecido: {archive.name}.")
        if kind not in latest or created > latest[kind][0]:
            latest[kind] = (created, archive)
    now = datetime.now(timezone.utc)
    for kind in required_kinds:
        if kind not in latest:
            raise RuntimeError(f"Backup obrigatório ausente: {kind}.")
        if (now - latest[kind][0]).total_seconds() > max_age_hours * 3600:
            raise RuntimeError(f"Backup obrigatório excede {max_age_hours} horas: {kind}.")
    return {kind: archive for kind, (_, archive) in latest.items()}


def build_rclone_command(binary: str, source: Path, remote: str) -> list[str]:
    resolved = shutil.which(binary)
    if not resolved:
        raise FileNotFoundError("rclone nao encontrado.")
    if not remote or remote.startswith("-") or ":" not in remote or any(character in remote for character in "\r\n\0"):
        raise ValueError("Destino rclone invalido.")
    return [
        resolved, "copy", str(source.resolve()), remote,
        "--include", "*.enc", "--include", "*.enc.json",
        "--include", "*.audit-anchor.json", "--exclude", "*",
        "--checksum", "--immutable",
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
    parser.add_argument("--require-kind", action="append", choices=("database-backup", "private-storage-backup"), default=[])
    parser.add_argument("--require-audit-anchor", action="store_true",
                        help="Exige uma âncora de auditoria íntegra e recente antes da cópia.")
    parser.add_argument("--rclone", default="rclone")
    args = parser.parse_args()
    try:
        if args.require_kind:
            check_backup_set(args.source, args.max_age_hours, tuple(args.require_kind))
        else:
            check_backup_age(args.source, args.max_age_hours)
        if args.require_audit_anchor and latest_anchor(args.source, args.max_age_hours) is None:
            raise RuntimeError("Âncora de auditoria ausente.")
        command = build_rclone_command(args.rclone, args.source, args.remote)
        subprocess.run(command, check=True, timeout=3600)  # nosec B603
    except Exception as exc:
        try:
            notify_failure(str(exc))
        except requests.RequestException as notify_exc:
            print(f"Falha ao notificar alerta: {notify_exc}", file=sys.stderr)
        print(f"Falha no backup externo: {exc}", file=sys.stderr)
        return 1
    print(f"Backup externo sincronizado: {args.remote}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
