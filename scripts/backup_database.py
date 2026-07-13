#!/usr/bin/env python3
"""
Zokyo database backup utility.

Creates a MySQL/MariaDB dump from DATABASE_URL, compresses it by default,
stores a metadata sidecar, and optionally removes old local backups.

The script intentionally avoids putting the database password in the process
arguments. It passes credentials to mysqldump through a temporary defaults file.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote, urlparse

SUPPORTED_SCHEMES = {
    "mysql",
    "mysql+pymysql",
    "mysql+mysqldb",
    "mariadb",
    "mariadb+pymysql",
}


@dataclass(frozen=True)
class DatabaseConfig:
    scheme: str
    username: str
    password: str
    host: str
    port: int
    database: str


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def get_env(name: str, env_file_values: dict[str, str]) -> str | None:
    return os.environ.get(name) or env_file_values.get(name)


def parse_database_url(database_url: str) -> DatabaseConfig:
    parsed = urlparse(database_url)

    if parsed.scheme not in SUPPORTED_SCHEMES:
        supported = ", ".join(sorted(SUPPORTED_SCHEMES))
        raise ValueError(f"Unsupported DATABASE_URL scheme '{parsed.scheme}'. Supported: {supported}.")

    database = parsed.path.lstrip("/")
    if not database:
        raise ValueError("DATABASE_URL must include a database name.")

    if not parsed.username:
        raise ValueError("DATABASE_URL must include a username.")

    return DatabaseConfig(
        scheme=parsed.scheme,
        username=unquote(parsed.username),
        password=unquote(parsed.password or ""),
        host=parsed.hostname or "localhost",
        port=parsed.port or 3306,
        database=unquote(database),
    )


def resolve_mysqldump(binary: str) -> str:
    found = shutil.which(binary)
    if found:
        return found
    candidate = Path(binary)
    if candidate.exists():
        return str(candidate)
    raise FileNotFoundError(
        f"mysqldump binary not found: {binary}. Install MySQL/MariaDB client tools "
        "or pass --mysqldump with the full path."
    )


def write_defaults_file(db: DatabaseConfig) -> Path:
    fd, name = tempfile.mkstemp(prefix="zokyo-mysqldump-", suffix=".cnf")
    path = Path(name)
    content = "\n".join(
        [
            "[client]",
            f"user={db.username}",
            f"password={db.password}",
            f"host={db.host}",
            f"port={db.port}",
            "default-character-set=utf8mb4",
            "",
        ]
    )
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(content)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def build_dump_command(mysqldump: str, defaults_file: Path, db: DatabaseConfig, extra_args: Iterable[str]) -> list[str]:
    return [
        mysqldump,
        f"--defaults-extra-file={defaults_file}",
        "--single-transaction",
        "--quick",
        "--routines",
        "--triggers",
        "--events",
        "--hex-blob",
        db.database,
        *extra_args,
    ]


def run_dump(command: list[str], output_path: Path, compress: bool) -> None:
    # O executavel vem de shutil.which/configuracao local e os argumentos sao uma lista, sem shell.
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as proc:  # nosec B603
        if proc.stdout is None or proc.stderr is None:
            raise RuntimeError("Nao foi possivel abrir os pipes do mysqldump.")

        if compress:
            with gzip.open(output_path, "wb", compresslevel=6) as out:
                shutil.copyfileobj(proc.stdout, out)
        else:
            with output_path.open("wb") as out:
                shutil.copyfileobj(proc.stdout, out)

        stderr = proc.stderr.read().decode("utf-8", errors="replace").strip()
        return_code = proc.wait()

    if return_code != 0:
        output_path.unlink(missing_ok=True)
        raise RuntimeError(f"mysqldump failed with exit code {return_code}: {stderr}")


def write_metadata(path: Path, db: DatabaseConfig, output_path: Path, started_at: datetime, finished_at: datetime) -> None:
    digest = hashlib.sha256()
    with output_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    metadata = {
        "application": "Zokyo",
        "kind": "database-backup",
        "database": db.database,
        "host": db.host,
        "port": db.port,
        "scheme": db.scheme,
        "output_file": output_path.name,
        "output_size_bytes": output_path.stat().st_size,
        "output_sha256": digest.hexdigest(),
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": round((finished_at - started_at).total_seconds(), 3),
    }
    path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def prune_old_backups(output_dir: Path, keep_days: int) -> list[Path]:
    if keep_days <= 0:
        return []

    now = datetime.now(timezone.utc).timestamp()
    max_age = keep_days * 24 * 60 * 60
    removed: list[Path] = []

    for pattern in ("zokyo_*.sql", "zokyo_*.sql.gz", "zokyo_*.json"):
        for path in output_dir.glob(pattern):
            if not path.is_file():
                continue
            age = now - path.stat().st_mtime
            if age > max_age:
                path.unlink()
                removed.append(path)
    return removed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a Zokyo MySQL/MariaDB backup.")
    parser.add_argument("--env-file", default=".env", help="Path to the .env file. Default: .env")
    parser.add_argument("--output-dir", default="backups", help="Backup destination directory. Default: backups")
    parser.add_argument("--keep-days", type=int, default=14, help="Remove local backups older than N days. Use 0 to disable. Default: 14")
    parser.add_argument("--mysqldump", default="mysqldump", help="mysqldump binary name or full path. Default: mysqldump")
    parser.add_argument("--no-compress", action="store_true", help="Write plain .sql instead of .sql.gz")
    parser.add_argument(
        "--extra-mysqldump-arg",
        action="append",
        default=[],
        help="Additional mysqldump argument. Can be repeated.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    env_values = load_env_file(Path(args.env_file))
    database_url = get_env("DATABASE_URL", env_values)
    if not database_url:
        print("DATABASE_URL not found in environment or env file.", file=sys.stderr)
        return 2

    try:
        db = parse_database_url(database_url)
        mysqldump = resolve_mysqldump(args.mysqldump)
    except Exception as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    started_at = datetime.now(timezone.utc)
    timestamp = started_at.strftime("%Y%m%d_%H%M%S")
    suffix = ".sql" if args.no_compress else ".sql.gz"
    output_path = output_dir / f"zokyo_{db.database}_{timestamp}{suffix}"
    metadata_path = output_path.with_suffix(output_path.suffix + ".json")

    defaults_file = write_defaults_file(db)
    command = build_dump_command(mysqldump, defaults_file, db, args.extra_mysqldump_arg)

    try:
        run_dump(command, output_path, compress=not args.no_compress)
        finished_at = datetime.now(timezone.utc)
        write_metadata(metadata_path, db, output_path, started_at, finished_at)
        removed = prune_old_backups(output_dir, args.keep_days)
    except Exception as exc:
        print(f"Backup failed: {exc}", file=sys.stderr)
        return 1
    finally:
        defaults_file.unlink(missing_ok=True)

    print(f"Backup created: {output_path}")
    print(f"Metadata: {metadata_path}")
    if removed:
        print(f"Removed old backup files: {len(removed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
