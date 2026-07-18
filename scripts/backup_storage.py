#!/usr/bin/env python3
"""Backup e restauracao verificavel do storage privado do Zokyo."""
from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
from datetime import datetime, timezone
from pathlib import Path

MANIFEST_NAME = "zokyo-storage-manifest.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def list_files(source: Path) -> list[Path]:
    return sorted(path for path in source.rglob("*") if path.is_file() and not path.is_symlink())


def create_backup(source: Path, destination: Path) -> dict:
    source = source.resolve()
    destination = destination.resolve()
    files = list_files(source)
    manifest = {
        "application": "Zokyo",
        "kind": "private-storage-backup",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "files": [
            {
                "path": path.relative_to(source).as_posix(),
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in files
        ],
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    manifest_bytes = (json.dumps(manifest, ensure_ascii=True, indent=2) + "\n").encode("utf-8")
    import io
    with tarfile.open(destination, "w:gz") as archive:
        info = tarfile.TarInfo(MANIFEST_NAME)
        info.size = len(manifest_bytes)
        info.mtime = int(datetime.now(timezone.utc).timestamp())
        archive.addfile(info, io.BytesIO(manifest_bytes))
        for path in files:
            archive.add(path, arcname=path.relative_to(source).as_posix(), recursive=False)
    return manifest


def _safe_members(archive: tarfile.TarFile, destination: Path):
    destination = destination.resolve()
    for member in archive.getmembers():
        target = (destination / member.name).resolve()
        if not target.is_relative_to(destination) or member.issym() or member.islnk():
            raise ValueError(f"Entrada insegura no backup: {member.name}")
        yield member


def restore_backup(archive_path: Path, destination: Path, verify_only: bool = False) -> dict:
    destination = destination.resolve()
    with tarfile.open(archive_path.resolve(), "r:gz") as archive:
        members = list(_safe_members(archive, destination))
        manifest_member = next((item for item in members if item.name == MANIFEST_NAME), None)
        if not manifest_member:
            raise ValueError("Manifesto ausente no backup.")
        extracted = archive.extractfile(manifest_member)
        if not extracted:  # pragma: no cover - tarfile returns None only for malformed members.
            raise ValueError("Manifesto invalido.")
        manifest = json.loads(extracted.read().decode("utf-8"))
        member_map = {item.name: item for item in members}
        for entry in manifest.get("files", []):
            member = member_map.get(entry["path"])
            if not member:
                raise ValueError(f"Arquivo ausente no backup: {entry['path']}")
            stream = archive.extractfile(member)
            digest = hashlib.sha256(stream.read()).hexdigest() if stream else ""
            if digest != entry["sha256"] or member.size != entry["size"]:
                raise ValueError(f"Falha de integridade: {entry['path']}")
        if not verify_only:
            destination.mkdir(parents=True, exist_ok=True)
            for member in members:
                if member.name != MANIFEST_NAME:
                    archive.extract(member, destination, filter="data")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("--source", default="instance/uploads")
    create.add_argument("--output", required=True)
    restore = subparsers.add_parser("restore")
    restore.add_argument("--archive", required=True)
    restore.add_argument("--destination", default="instance/uploads")
    restore.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.command == "create":
        manifest = create_backup(Path(args.source), Path(args.output))
        print(f"Backup criado com {len(manifest['files'])} arquivo(s): {args.output}")
    else:
        manifest = restore_backup(Path(args.archive), Path(args.destination), args.verify_only)
        action = "verificado" if args.verify_only else "restaurado"
        print(f"Backup {action}: {len(manifest['files'])} arquivo(s).")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
