"""Storage privado com cache local e backend S3 compatível opcional."""
from __future__ import annotations

from pathlib import Path, PurePosixPath
from uuid import uuid4

from flask import current_app


def enabled() -> bool:
    return bool(current_app.config.get("S3_BUCKET"))


def _safe_key(key: str) -> str:
    path = PurePosixPath(key)
    if path.is_absolute() or ".." in path.parts or not key:
        raise ValueError("Chave de storage inválida.")
    return path.as_posix()


def _client():
    import boto3
    return boto3.client(
        "s3",
        endpoint_url=current_app.config.get("S3_ENDPOINT_URL"),
        region_name=current_app.config.get("S3_REGION"),
        aws_access_key_id=current_app.config.get("S3_ACCESS_KEY_ID"),
        aws_secret_access_key=current_app.config.get("S3_SECRET_ACCESS_KEY"),
    )


def put(key: str, data: bytes, content_type="application/octet-stream") -> None:
    if not enabled():
        return
    _client().put_object(
        Bucket=current_app.config["S3_BUCKET"], Key=_safe_key(key), Body=data,
        ContentType=content_type, ServerSideEncryption=current_app.config.get("S3_SSE") or "AES256",
    )


def hydrate(key: str, local_target: Path) -> Path:
    if local_target.exists() or not enabled():
        return local_target
    local_target.parent.mkdir(parents=True, exist_ok=True)
    temporary = local_target.with_name(f".{local_target.name}.{uuid4().hex}.download")
    try:
        _client().download_file(current_app.config["S3_BUCKET"], _safe_key(key), str(temporary))
        temporary.replace(local_target)
    finally:
        temporary.unlink(missing_ok=True)
    return local_target


def delete(key: str) -> None:
    if enabled():
        _client().delete_object(Bucket=current_app.config["S3_BUCKET"], Key=_safe_key(key))
