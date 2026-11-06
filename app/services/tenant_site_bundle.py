"""Upload e leitura segura de sites estaticos publicados por tenant."""
from __future__ import annotations

import shutil
import stat
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from flask import current_app, send_from_directory

from app.extensions import db
from app.models import TenantSite


class SiteBundleError(ValueError):
    pass


def _root() -> Path:
    configured = current_app.config.get("SITES_UPLOAD_FOLDER")
    root = Path(configured) if configured else Path(current_app.instance_path) / "uploads" / "sites"
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _safe_member(name: str) -> str:
    normalized = name.replace("\\", "/").strip("/")
    path = PurePosixPath(normalized)
    if not normalized or path.is_absolute() or ".." in path.parts:
        raise SiteBundleError("O ZIP possui um caminho de arquivo inválido.")
    if any(part in {".git", "__pycache__"} or part.startswith(".") for part in path.parts):
        raise SiteBundleError("O ZIP não pode conter arquivos ocultos ou .git.")
    if path.name.lower() in {".env", "id_rsa", "id_rsa.pub"}:
        raise SiteBundleError("O ZIP não pode conter arquivos de ambiente ou chaves.")
    return "/".join(path.parts)


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    return stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK


def publish_bundle(site: TenantSite, uploaded_file) -> dict:
    """Extrai ZIP em area isolada e publica atomicamente a nova versao."""
    if not uploaded_file or not uploaded_file.filename:
        raise SiteBundleError("Selecione um arquivo ZIP do site.")
    if not uploaded_file.filename.lower().endswith(".zip"):
        raise SiteBundleError("Envie um arquivo .zip com o index.html e os assets do site.")

    max_bytes = int(current_app.config.get("SITES_MAX_BUNDLE_MB", 50)) * 1024 * 1024
    max_files = int(current_app.config.get("SITES_MAX_FILES", 2000))
    root = _root()
    tenant_root = (root / str(site.organization_id)).resolve()
    tenant_root.mkdir(parents=True, exist_ok=True)
    version = uuid.uuid4().hex
    final_dir = tenant_root / version
    temp_dir = Path(tempfile.mkdtemp(prefix=f".{version}-", dir=tenant_root))

    try:
        uploaded_file.stream.seek(0)
        with zipfile.ZipFile(uploaded_file.stream) as archive:
            members = [item for item in archive.infolist() if not item.is_dir()]
            if len(members) > max_files:
                raise SiteBundleError(f"O site excede o limite de {max_files} arquivos.")
            total_size = sum(item.file_size for item in members)
            if total_size > max_bytes:
                raise SiteBundleError(f"O site excede o limite de {max_bytes // (1024 * 1024)} MB.")
            names = [_safe_member(item.filename) for item in members]
            if any(_is_symlink(item) for item in members):
                raise SiteBundleError("O ZIP não pode conter links simbólicos.")
            entrypoint = next((name for name in names if name.lower() == "index.html"), None)
            if not entrypoint:
                # Aceita ZIP contendo uma pasta raiz (ex.: site/dist/index.html).
                prefixes = {name.split("/", 1)[0] for name in names if "/" in name}
                if len(prefixes) == 1:
                    prefix = next(iter(prefixes)) + "/"
                    entrypoint = next((name[len(prefix):] for name in names if name.startswith(prefix) and name[len(prefix):].lower() == "index.html"), None)
                    if entrypoint:
                        names = [name[len(prefix):] if name.startswith(prefix) else name for name in names]
                        members = [item for item in members if _safe_member(item.filename).startswith(prefix)]
                if not entrypoint:
                    raise SiteBundleError("O ZIP precisa conter um index.html na raiz.")

            for item, name in zip(members, names):
                target = (temp_dir / name).resolve()
                if temp_dir.resolve() not in target.parents:
                    raise SiteBundleError("Caminho de arquivo fora da pasta do site.")
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(item) as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination, length=1024 * 1024)
        temp_dir.rename(final_dir)
        site.site_mode = "upload"
        site.site_bundle_version = version
        site.site_bundle_entrypoint = entrypoint or "index.html"
        site.site_bundle_uploaded_at = datetime.now(timezone.utc)
        site.site_bundle_file_count = len(names)
        site.site_bundle_size_bytes = sum(item.file_size for item in members)
        db.session.flush()
        return {"version": version, "files": len(names), "size_bytes": site.site_bundle_size_bytes}
    except zipfile.BadZipFile as exc:
        raise SiteBundleError("O arquivo enviado não é um ZIP válido.") from exc
    except Exception:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        if final_dir.exists():
            shutil.rmtree(final_dir, ignore_errors=True)
        raise


def bundle_directory(site: TenantSite) -> Path | None:
    if site.site_mode != "upload" or not site.site_bundle_version:
        return None
    directory = (_root() / str(site.organization_id) / site.site_bundle_version).resolve()
    if not directory.is_dir() or _root() not in directory.parents:
        return None
    return directory


def send_bundle_file(site: TenantSite, path: str):
    directory = bundle_directory(site)
    if not directory:
        return None
    clean = (path or "").strip("/") or site.site_bundle_entrypoint or "index.html"
    candidate = (directory / clean).resolve()
    if directory not in candidate.parents and candidate != directory:
        return None
    if not candidate.is_file():
        if "." not in Path(clean).name:
            clean = site.site_bundle_entrypoint or "index.html"
        else:
            return None
    cache_seconds = 0 if clean.lower().endswith((".html", ".htm")) else 3600
    return send_from_directory(directory, clean, conditional=True, max_age=cache_seconds)


def unpublish_bundle(site: TenantSite) -> bool:
    """Remove a versao ativa e deixa o site sem conteudo publicado."""
    directory = bundle_directory(site)
    if directory:
        shutil.rmtree(directory, ignore_errors=True)
    site.site_mode = "builder"
    site.site_bundle_version = None
    site.site_bundle_entrypoint = "index.html"
    site.site_bundle_uploaded_at = None
    site.site_bundle_file_count = None
    site.site_bundle_size_bytes = None
    db.session.flush()
    return bool(directory)
