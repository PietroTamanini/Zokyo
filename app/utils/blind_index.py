"""Deterministic HMAC blind indexes for exact-match searches on sensitive fields."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
from functools import lru_cache

from flask import current_app


def digits_only(value) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def normalize_email(value) -> str:
    return str(value or "").strip().lower()


def normalize_text(value) -> str:
    return " ".join(str(value or "").strip().lower().split())


def normalize_for_index(value, kind: str) -> str:
    if kind in {"cpf", "cnpj", "telefone", "phone", "document"}:
        return digits_only(value)
    if kind == "email":
        return normalize_email(value)
    return normalize_text(value)


@lru_cache(maxsize=16)
def _key_from_material(material: str) -> bytes:
    return hashlib.sha256(material.encode("utf-8")).digest()


def blind_index_key() -> bytes:
    configured = os.environ.get("BLIND_INDEX_KEY", "").strip()
    if configured:
        try:
            decoded = base64.urlsafe_b64decode(configured.encode("ascii"))
        except Exception as exc:
            raise RuntimeError("BLIND_INDEX_KEY invalido; use base64 URL-safe de 32 bytes.") from exc
        if len(decoded) != 32:
            raise RuntimeError("BLIND_INDEX_KEY deve decodificar exatamente 32 bytes.")
        return decoded

    secret = str(current_app.config.get("SECRET_KEY") or "").strip()
    if len(secret) < 32 and not (current_app.testing or current_app.debug):
        raise RuntimeError("BLIND_INDEX_KEY ou SECRET_KEY forte e obrigatoria para indice cego.")
    return _key_from_material("zokyo-blind-index-v1:" + secret)


def blind_index(value, kind: str = "text") -> str | None:
    normalized = normalize_for_index(value, kind)
    if not normalized:
        return None
    return hmac.new(blind_index_key(), normalized.encode("utf-8"), hashlib.sha256).hexdigest()
