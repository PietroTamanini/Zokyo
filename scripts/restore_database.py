#!/usr/bin/env python3
"""Verifica e restaura backups MySQL/MariaDB gerados pelo Zokyo."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess  # nosec B404
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

try:
    from scripts.backup_database import load_env_file, parse_database_url, write_defaults_file
except ModuleNotFoundError:  # pragma: no cover - direct script bootstrap.
    from backup_database import load_env_file, parse_database_url, write_defaults_file

try:
    from scripts import backup_crypto
except ModuleNotFoundError:  # pragma: no cover - direct script bootstrap.
    import backup_crypto


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_backup(backup: Path, metadata: Path) -> dict:
    if not backup.is_file() or not metadata.is_file():
        raise FileNotFoundError("Backup ou metadata sidecar nao encontrado.")
    payload = json.loads(metadata.read_text(encoding="utf-8"))
    if payload.get("kind") != "database-backup":
        raise ValueError("Metadata nao pertence a um backup de banco Zokyo.")
    if payload.get("output_file") != backup.name:
        raise ValueError("Metadata aponta para outro arquivo de backup.")
    if payload.get("output_size_bytes") != backup.stat().st_size:
        raise ValueError("Tamanho do backup diverge do metadata.")
    expected = payload.get("output_sha256")
    if not expected or not secrets_compare(expected, sha256_file(backup)):
        raise ValueError("SHA-256 do backup invalido.")
    return payload


def secrets_compare(left: str, right: str) -> bool:
    import secrets
    return secrets.compare_digest(left, right)


@contextmanager
def prepared_backup(backup: Path, metadata: dict):
    """Disponibiliza dump em claro apenas em diretório temporário privado."""
    if not backup.name.endswith(".enc"):
        if metadata.get("format") == "aes256-gcm":
            raise ValueError("Metadata criptografado aponta para arquivo sem .enc.")
        yield backup
        return
    if metadata.get("format") != "aes256-gcm" or not metadata.get("plaintext_sha256"):
        raise ValueError("Metadata do backup criptografado incompleto.")
    key = backup_crypto.key_from_env()
    with tempfile.TemporaryDirectory(prefix="zokyo-restore-") as directory:
        plaintext = Path(directory) / backup.name[:-4]
        backup_crypto.decrypt_file(backup, plaintext, key)
        if not secrets_compare(metadata["plaintext_sha256"], sha256_file(plaintext)):
            raise ValueError("SHA-256 do dump decriptado invalido.")
        yield plaintext


def validate_portable_dump(backup: Path):
    """Impede que o dump selecione ou altere bancos fora do destino configurado."""
    opener = gzip.open if backup.name.endswith(".gz") else open
    forbidden = re.compile(rb"(?im)^\s*(?:CREATE|DROP)\s+DATABASE\b|^\s*USE\s+[`\w-]+\s*;")
    with opener(backup, "rb") as source:
        for line in source:
            if forbidden.search(line):
                raise ValueError("Backup nao portavel contem CREATE/DROP DATABASE ou USE explicito.")


def restore(backup: Path, database_url: str, mysql_binary: str = "mysql"):
    validate_portable_dump(backup)
    binary = shutil.which(mysql_binary) or (mysql_binary if Path(mysql_binary).is_file() else None)
    if not binary:
        raise FileNotFoundError("Cliente mysql/mariadb nao encontrado.")
    database = parse_database_url(database_url)
    defaults = write_defaults_file(database)
    command = [binary, f"--defaults-extra-file={defaults}", database.database]
    opener = gzip.open if backup.name.endswith(".gz") else open
    try:
        with opener(backup, "rb") as source:
            # O executavel vem de shutil.which/configuracao local e os argumentos sao uma lista, sem shell.
            process = subprocess.Popen(  # nosec B603
                command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            if process.stdin is None:
                raise RuntimeError("Nao foi possivel abrir o pipe de entrada do cliente MariaDB.")
            pipe_error = None
            try:
                shutil.copyfileobj(source, process.stdin, length=1024 * 1024)
            except BrokenPipeError as exc:
                pipe_error = exc
            finally:
                try:
                    process.stdin.close()
                except BrokenPipeError as exc:
                    pipe_error = pipe_error or exc
            stdout = process.stdout.read() if process.stdout else b""
            stderr = process.stderr.read() if process.stderr else b""
            return_code = process.wait()
        if return_code:
            detail = stderr.decode("utf-8", errors="replace").strip() or stdout.decode("utf-8", errors="replace").strip()
            raise RuntimeError(detail)
            if pipe_error:
                raise RuntimeError("Cliente MariaDB encerrou o pipe durante o restore.") from pipe_error
    finally:
        defaults.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", required=True)
    parser.add_argument("--metadata")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--mysql", default="mysql")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument(
        "--confirm-in-place", action="store_true",
        help="Autoriza explicitamente restaurar no banco principal ou em destino com o mesmo nome.",
    )
    args = parser.parse_args()
    backup = Path(args.backup).resolve()
    metadata = Path(args.metadata).resolve() if args.metadata else Path(str(backup) + ".json")
    try:
        env_values = load_env_file(Path(args.env_file))
        if not os.environ.get("BACKUP_ENCRYPTION_KEY") and env_values.get("BACKUP_ENCRYPTION_KEY"):
            os.environ["BACKUP_ENCRYPTION_KEY"] = env_values["BACKUP_ENCRYPTION_KEY"]
        payload = verify_backup(backup, metadata)
        if args.verify_only:
            with prepared_backup(backup, payload):
                print(f"Backup valido: {payload['output_file']}")
            return 0
        env = {**env_values, **os.environ}
        source_url = env.get("DATABASE_URL")
        target_url = env.get("RESTORE_DATABASE_URL")
        if not target_url and not args.confirm_in_place:
            raise ValueError("Defina RESTORE_DATABASE_URL para um banco descartavel ou use --confirm-in-place.")
        database_url = target_url or source_url
        if not database_url:
            raise ValueError("DATABASE_URL/RESTORE_DATABASE_URL nao configurada.")
        target = parse_database_url(database_url)
        original_name = str(payload.get("database") or "").lower()
        if original_name and target.database.lower() == original_name and not args.confirm_in_place:
            raise ValueError("Destino tem o mesmo nome do banco de origem; use --confirm-in-place se isso for intencional.")
        with prepared_backup(backup, payload) as prepared:
            restore(prepared, database_url, args.mysql)
        print("Restore concluido. Execute healthcheck e verificacoes funcionais antes de liberar o ambiente.")
        return 0
    except Exception as exc:
        print(f"Restore falhou: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
