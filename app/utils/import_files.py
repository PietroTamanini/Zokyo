"""Ciclo de vida dos arquivos temporários de importação externa."""
from __future__ import annotations

import re
import time
from pathlib import Path

IMPORT_UPLOAD_TTL_SECONDS = 24 * 60 * 60
_UPLOAD_NAME = re.compile(r"^[0-9a-f]{32}_[A-Za-z0-9_.-]+$")


def delete_import_file(folder: Path, file_path: str | Path) -> bool:
    """Apaga somente um arquivo regular criado nesta pasta pelo endpoint de upload."""
    candidate = Path(file_path)
    if not _UPLOAD_NAME.fullmatch(candidate.name) or candidate.is_symlink():
        return False
    if candidate.parent.resolve() != folder.resolve() or not candidate.is_file():
        return False
    candidate.unlink()
    return True


def cleanup_expired_imports(folder: Path, *, now: float | None = None) -> int:
    if not folder.is_dir():
        return 0
    threshold = (time.time() if now is None else now) - IMPORT_UPLOAD_TTL_SECONDS
    deleted = 0
    for candidate in folder.iterdir():
        try:
            if (candidate.is_file() and not candidate.is_symlink()
                    and candidate.stat().st_mtime < threshold
                    and delete_import_file(folder, candidate)):
                deleted += 1
        except FileNotFoundError:
            continue
    return deleted
