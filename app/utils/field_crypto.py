"""Transparent field encryption for sensitive database columns."""
from __future__ import annotations

import base64
import logging
import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from flask import current_app
from sqlalchemy.types import Text, TypeDecorator

logger = logging.getLogger(__name__)

PREFIX = "zokyo-fernet:v1:"
LEGACY_SALT = b"zokyo-config-encryption-v1"


def _salt() -> bytes:
    raw = os.environ.get("ENCRYPTION_SALT", "").strip()
    if not raw:
        return LEGACY_SALT
    try:
        decoded = base64.b64decode(raw)
    except Exception as exc:
        raise RuntimeError("ENCRYPTION_SALT invalido para criptografia de campos.") from exc
    if len(decoded) < 16:
        raise RuntimeError("ENCRYPTION_SALT deve ter pelo menos 16 bytes apos base64.")
    return decoded


@lru_cache(maxsize=16)
def _derive_key(secret: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=210_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(secret.encode("utf-8")))


def get_fernet() -> Fernet:
    secret = str(current_app.config.get("SECRET_KEY") or "").strip()
    if len(secret) < 32 and not (current_app.testing or current_app.debug):
        raise RuntimeError("SECRET_KEY forte e fixa e obrigatoria para criptografia.")
    return Fernet(_derive_key(secret, _salt()))


def encrypt_value(value: str | None) -> str | None:
    if value is None or value == "":
        return value
    text = str(value)
    if text.startswith(PREFIX):
        return text
    token = get_fernet().encrypt(text.encode("utf-8")).decode("ascii")
    return PREFIX + token


def decrypt_value(value: str | None) -> str | None:
    if value is None or value == "":
        return value
    text = str(value)
    for _ in range(3):
        if not text.startswith(PREFIX):
            return text
        token = text[len(PREFIX):]
        try:
            text = get_fernet().decrypt(token.encode("ascii")).decode("utf-8")
        except InvalidToken:
            logger.warning("Campo criptografado nao pode ser descriptografado; chave ou salt mudou.")
            return None
    return text


def is_encrypted(value: str | None) -> bool:
    return bool(value and str(value).startswith(PREFIX))


class EncryptedText(TypeDecorator):
    """Stores encrypted text while exposing plaintext to the application."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return encrypt_value(value)

    def process_result_value(self, value, dialect):
        return decrypt_value(value)
