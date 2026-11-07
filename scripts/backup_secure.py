"""Gera backup MariaDB criptografado sem publicar o dump em claro."""
import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

try:
    from scripts import backup_crypto, backup_database
except ModuleNotFoundError:  # execução direta a partir de scripts/
    import backup_crypto
    import backup_database


def file_sha256(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_secure_database_backup(database_url: str, output_dir: Path, *, mysqldump="mysqldump",
                                  extra_args=()):
    key = backup_crypto.key_from_env()
    db = backup_database.parse_database_url(database_url)
    binary = backup_database.resolve_mysqldump(mysqldump)
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    encrypted = output_dir / f"zokyo_{db.database}_{stamp}.sql.gz.enc"
    if encrypted.exists():
        raise FileExistsError(f"Backup já existe: {encrypted.name}")
    with tempfile.TemporaryDirectory(prefix="zokyo-backup-") as directory, \
            tempfile.TemporaryDirectory(prefix=".zokyo-backup-publish-", dir=output_dir) as publish_dir:
        temporary = Path(directory)
        publish = Path(publish_dir)
        plaintext = temporary / "dump.sql.gz"
        defaults = backup_database.write_defaults_file(db)
        try:
            command = backup_database.build_dump_command(binary, defaults, db, extra_args)
            backup_database.run_dump(command, plaintext, compress=True)
        finally:
            defaults.unlink(missing_ok=True)
        plaintext_hash = file_sha256(plaintext)
        encrypted_temp = publish / encrypted.name
        backup_crypto.encrypt_file(plaintext, encrypted_temp, key)
        encrypted_temp.chmod(0o600)
        roundtrip = temporary / "check.sql.gz"
        backup_crypto.decrypt_file(encrypted_temp, roundtrip, key)
        if file_sha256(roundtrip) != plaintext_hash:
            raise RuntimeError("Backup criptografado não reproduz o dump original.")
        metadata = {
            "application": "Zokyo", "kind": "database-backup", "format": "aes256-gcm",
            "database": db.database, "host": db.host,
            "output_file": encrypted.name,
            "output_size_bytes": encrypted_temp.stat().st_size,
            "output_sha256": file_sha256(encrypted_temp),
            "plaintext_sha256": plaintext_hash,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        metadata_temp = publish / (encrypted.name + ".json")
        metadata_temp.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        metadata_temp.chmod(0o600)
        encrypted_temp.replace(encrypted)
        try:
            metadata_temp.replace(Path(str(encrypted) + ".json"))
        except Exception:
            encrypted.unlink(missing_ok=True)
            raise
    return encrypted


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="backups")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--mysqldump", default="mysqldump")
    parser.add_argument("--extra-mysqldump-arg", action="append", default=[])
    args = parser.parse_args()
    values = backup_database.load_env_file(Path(args.env_file))
    database_url = os.environ.get("DATABASE_URL") or values.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL não configurada.")
    if not os.environ.get("BACKUP_ENCRYPTION_KEY") and values.get("BACKUP_ENCRYPTION_KEY"):
        os.environ["BACKUP_ENCRYPTION_KEY"] = values["BACKUP_ENCRYPTION_KEY"]
    result = create_secure_database_backup(
        database_url, Path(args.output_dir),
        mysqldump=args.mysqldump, extra_args=args.extra_mysqldump_arg,
    )
    print(f"Backup criptografado criado: {result}")


if __name__ == "__main__":
    main()
