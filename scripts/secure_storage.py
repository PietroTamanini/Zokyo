"""Backup e restore cifrados dos uploads privados do Zokyo."""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

try:
    from scripts import backup_crypto, backup_database, backup_storage
    from scripts.backup_secure import file_sha256
except ModuleNotFoundError:  # execução direta a partir de scripts/
    import backup_crypto
    import backup_database
    import backup_storage
    from backup_secure import file_sha256


def _key_from_env_file(path: Path):
    values = backup_database.load_env_file(path)
    if not os.environ.get("BACKUP_ENCRYPTION_KEY") and values.get("BACKUP_ENCRYPTION_KEY"):
        os.environ["BACKUP_ENCRYPTION_KEY"] = values["BACKUP_ENCRYPTION_KEY"]
    return backup_crypto.key_from_env()


def create_encrypted_storage_backup(source: Path, output_dir: Path, key: bytes) -> Path:
    if source.is_symlink():
        raise ValueError("Origem dos uploads não pode ser um link simbólico.")
    source = source.resolve()
    output_dir = output_dir.resolve()
    if not source.is_dir():
        raise ValueError("Origem dos uploads deve ser um diretório existente e regular.")
    if any(path.is_symlink() for path in source.rglob("*")):
        raise ValueError("Uploads contêm link simbólico; backup incompleto seria inseguro.")
    if output_dir == source or output_dir.is_relative_to(source):
        raise ValueError("Destino do backup deve ficar fora dos uploads.")
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    encrypted = output_dir / f"zokyo_uploads_{stamp}.tar.gz.enc"
    if encrypted.exists():
        raise FileExistsError(f"Backup já existe: {encrypted.name}")
    with tempfile.TemporaryDirectory(prefix="zokyo-storage-backup-") as directory, \
            tempfile.TemporaryDirectory(prefix=".zokyo-storage-publish-", dir=output_dir) as publish_dir:
        temporary = Path(directory)
        publish = Path(publish_dir)
        plaintext = temporary / "storage.tar.gz"
        manifest = backup_storage.create_backup(source, plaintext)
        plaintext_hash = file_sha256(plaintext)
        encrypted_temp = publish / encrypted.name
        backup_crypto.encrypt_file(plaintext, encrypted_temp, key)
        encrypted_temp.chmod(0o600)
        roundtrip = temporary / "check.tar.gz"
        backup_crypto.decrypt_file(encrypted_temp, roundtrip, key)
        if file_sha256(roundtrip) != plaintext_hash:
            raise RuntimeError("Backup cifrado não reproduz o arquivo original.")
        checked = backup_storage.restore_backup(roundtrip, temporary / "verify", verify_only=True)
        if checked != manifest:
            raise RuntimeError("Manifesto dos uploads diverge após cifragem.")
        metadata = {
            "application": "Zokyo", "kind": "private-storage-backup", "format": "aes256-gcm",
            "output_file": encrypted.name,
            "output_size_bytes": encrypted_temp.stat().st_size,
            "output_sha256": file_sha256(encrypted_temp),
            "plaintext_sha256": plaintext_hash,
            "file_count": len(manifest["files"]),
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


def restore_encrypted_storage_backup(archive: Path, destination: Path, key: bytes, *,
                                     verify_only=False, confirm_in_place=False,
                                     active_source=Path("instance/uploads")) -> dict:
    archive = archive.resolve()
    metadata_path = Path(str(archive) + ".json")
    if not archive.name.endswith(".tar.gz.enc") or not archive.is_file() or not metadata_path.is_file():
        raise ValueError("Backup cifrado e metadata correspondente são obrigatórios.")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("kind") != "private-storage-backup" or metadata.get("format") != "aes256-gcm":
        raise ValueError("Metadata de storage inválido.")
    if metadata.get("output_file") != archive.name or metadata.get("output_size_bytes") != archive.stat().st_size:
        raise ValueError("Tamanho ou nome do backup diverge do metadata.")
    if metadata.get("output_sha256") != file_sha256(archive):
        raise ValueError("SHA-256 do backup cifrado inválido.")
    destination = destination.resolve()
    active_source = active_source.resolve()
    if not verify_only and not confirm_in_place:
        if destination == active_source or destination.is_relative_to(active_source):
            raise ValueError("Restore nos uploads ativos exige --confirm-in-place.")
        if destination.exists() and any(destination.iterdir()):
            raise ValueError("Destino de restore deve estar vazio ou exigir --confirm-in-place.")
    with tempfile.TemporaryDirectory(prefix="zokyo-storage-restore-") as directory:
        plaintext = Path(directory) / "storage.tar.gz"
        backup_crypto.decrypt_file(archive, plaintext, key)
        if metadata.get("plaintext_sha256") != file_sha256(plaintext):
            raise ValueError("SHA-256 do arquivo decriptado inválido.")
        checked = backup_storage.restore_backup(plaintext, destination, verify_only=True)
        if metadata.get("file_count") != len(checked["files"]):
            raise ValueError("Quantidade de arquivos diverge do metadata.")
        if verify_only:
            return checked
        manifest = backup_storage.restore_backup(plaintext, destination, verify_only=verify_only)
        if manifest != checked:
            raise RuntimeError("Manifesto mudou durante o restore.")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=".env")
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("--source", default="instance/uploads")
    create.add_argument("--output-dir", default="backups")
    restore = subparsers.add_parser("restore")
    restore.add_argument("--archive", required=True)
    restore.add_argument("--destination")
    restore.add_argument("--verify-only", action="store_true")
    restore.add_argument("--confirm-in-place", action="store_true")
    restore.add_argument("--active-source", default="instance/uploads")
    args = parser.parse_args()
    key = _key_from_env_file(Path(args.env_file))
    if args.command == "create":
        result = create_encrypted_storage_backup(Path(args.source), Path(args.output_dir), key)
        print(f"Backup cifrado dos uploads criado: {result}")
    else:
        if not args.verify_only and not args.destination:
            raise ValueError("Informe --destination para restaurar os uploads.")
        destination = Path(args.destination or tempfile.gettempdir())
        manifest = restore_encrypted_storage_backup(
            Path(args.archive), destination, key, verify_only=args.verify_only,
            confirm_in_place=args.confirm_in_place,
            active_source=Path(args.active_source),
        )
        print(f"Uploads {'verificados' if args.verify_only else 'restaurados'}: {len(manifest['files'])} arquivo(s).")


if __name__ == "__main__":
    main()
