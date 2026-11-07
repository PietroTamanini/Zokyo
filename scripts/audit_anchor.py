"""Small, non-personal audit-chain anchors for independent backup copies."""
from __future__ import annotations

import json
import os
import re
import secrets
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

SUFFIX = ".audit-anchor.json"
_HASH = re.compile(r"[0-9a-f]{64}\Z")


def read_anchor(path: Path) -> dict:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 4096:
        raise ValueError("Arquivo de âncora inválido.")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        created = datetime.fromisoformat(value["created_at"])
        last_id = value["last_event_id"]
        checked = value["checked"]
        chain_hash = value["head_hash"]
    except (ValueError, TypeError, KeyError, UnicodeError) as exc:
        raise ValueError("Formato de âncora inválido.") from exc
    if (value.get("kind") != "audit-chain-anchor" or created.tzinfo is None
            or type(checked) is not int or checked < 0
            or (last_id is not None and (type(last_id) is not int or last_id < 1))
            or not isinstance(chain_hash, str)
            or (last_id is None and (checked != 0 or chain_hash != "GENESIS"))
            or (last_id is not None and (checked > last_id or not _HASH.fullmatch(chain_hash)))
            or (created - datetime.now(timezone.utc)).total_seconds() > 300):
        raise ValueError("Conteúdo de âncora inválido.")
    return value


def publish_anchor(directory: Path, result: dict) -> Path:
    if result["errors"] or result["legacy"]:
        raise ValueError("Não é permitido ancorar uma cadeia inconsistente.")
    directory = Path(directory)
    if directory.is_symlink():
        raise ValueError("Diretório de âncoras não pode ser link simbólico.")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    created = datetime.now(timezone.utc)
    name = f"audit-{created.strftime('%Y%m%dT%H%M%S%fZ')}-{secrets.token_hex(6)}{SUFFIX}"
    anchor = directory / name
    payload = {
        "kind": "audit-chain-anchor", "created_at": created.isoformat(),
        "checked": result["checked"], "last_event_id": result["last_event_id"],
        "head_hash": result["head_hash"],
    }
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=directory, prefix=".audit-anchor-", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=False, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o600)
        read_anchor(temporary)
        temporary.replace(anchor)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return anchor


def latest_anchor(directory: Path, max_age_hours: int | None = None) -> tuple[Path, dict] | None:
    if max_age_hours is not None and max_age_hours <= 0:
        raise ValueError("Prazo máximo da âncora deve ser positivo.")
    anchors = []
    for path in Path(directory).glob(f"*{SUFFIX}"):
        data = read_anchor(path)
        anchors.append((datetime.fromisoformat(data["created_at"]), path, data))
    if not anchors:
        return None
    created, path, data = max(anchors, key=lambda item: item[0])
    if max_age_hours is not None and datetime.now(timezone.utc) - created > timedelta(hours=max_age_hours):
        raise RuntimeError(f"Âncora de auditoria excede {max_age_hours} horas.")
    return path, data
