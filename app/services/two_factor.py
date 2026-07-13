"""Autenticacao TOTP e codigos de recuperacao para administradores."""
import base64
import hashlib
import io
import os
import secrets

import pyotp
import qrcode
from cryptography.fernet import Fernet, InvalidToken
from flask import current_app


def _fernet() -> Fernet:
    secret = current_app.config["SECRET_KEY"]
    salt = os.environ.get("ENCRYPTION_SALT", "zokyo-development-only")
    key = hashlib.sha256(f"{secret}|{salt}|totp".encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode("ascii")).decode("ascii")


def decrypt_secret(encrypted: str) -> str | None:
    try:
        return _fernet().decrypt(encrypted.encode("ascii")).decode("ascii")
    except (InvalidToken, ValueError, TypeError):
        return None


def new_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, email: str) -> str:
    issuer = current_app.config.get("APP_NAME", "Zokyo")
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=issuer)


def qr_data_uri(uri: str) -> str:
    image = qrcode.make(uri)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")


def verify_totp(secret: str, code: str) -> bool:
    normalized = "".join(char for char in (code or "") if char.isdigit())
    return len(normalized) == 6 and pyotp.TOTP(secret).verify(normalized, valid_window=1)


def generate_recovery_codes(count: int = 8) -> tuple[list[str], list[str]]:
    codes = [f"{secrets.token_hex(2)}-{secrets.token_hex(2)}" for _ in range(count)]
    return codes, [hashlib.sha256(code.encode("ascii")).hexdigest() for code in codes]


def consume_recovery_code(user, code: str) -> bool:
    digest = hashlib.sha256((code or "").strip().lower().encode("ascii", errors="ignore")).hexdigest()
    hashes = list(user.recovery_codes_hash or [])
    match = next((item for item in hashes if secrets.compare_digest(item, digest)), None)
    if not match:
        return False
    hashes.remove(match)
    user.recovery_codes_hash = hashes
    return True
