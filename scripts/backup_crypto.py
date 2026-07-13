#!/usr/bin/env python3
"""Criptografia autenticada em fluxo para backups do Zokyo."""
from __future__ import annotations

import argparse
import base64
import os
import struct
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"ZOKYOENC1"
CHUNK_SIZE = 1024 * 1024


def key_from_env() -> bytes:
    encoded = os.environ.get("BACKUP_ENCRYPTION_KEY", "").strip()
    try:
        key = base64.urlsafe_b64decode(encoded)
    except Exception as exc:
        raise ValueError("BACKUP_ENCRYPTION_KEY deve ser base64 URL-safe.") from exc
    if len(key) != 32:
        raise ValueError("BACKUP_ENCRYPTION_KEY deve representar exatamente 32 bytes.")
    return key


def encrypt_file(source: Path, destination: Path, key: bytes) -> None:
    source, destination = source.resolve(), destination.resolve()
    if source == destination:
        raise ValueError("Origem e destino devem ser diferentes.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    cipher = AESGCM(key)
    with source.open("rb") as src, tempfile.NamedTemporaryFile("wb", dir=destination.parent, delete=False) as tmp:
        temporary = Path(tmp.name)
        tmp.write(MAGIC)
        counter = 0
        while chunk := src.read(CHUNK_SIZE):
            nonce = os.urandom(12)
            encrypted = cipher.encrypt(nonce, chunk, MAGIC + counter.to_bytes(8, "big"))
            tmp.write(struct.pack(">I", len(encrypted)))
            tmp.write(nonce)
            tmp.write(encrypted)
            counter += 1
        tmp.write(struct.pack(">I", 0))
    try:
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def decrypt_file(source: Path, destination: Path, key: bytes) -> None:
    source, destination = source.resolve(), destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    cipher = AESGCM(key)
    temporary = None
    try:
        with source.open("rb") as src, tempfile.NamedTemporaryFile("wb", dir=destination.parent, delete=False) as tmp:
            temporary = Path(tmp.name)
            if src.read(len(MAGIC)) != MAGIC:
                raise ValueError("Formato de backup criptografado invalido.")
            counter = 0
            while True:
                raw_size = src.read(4)
                if len(raw_size) != 4:
                    raise ValueError("Backup criptografado truncado.")
                size = struct.unpack(">I", raw_size)[0]
                if size == 0:
                    if src.read(1):
                        raise ValueError("Dados extras apos o fim do backup.")
                    break
                if size > CHUNK_SIZE + 16:
                    raise ValueError("Bloco criptografado excede o limite.")
                nonce = src.read(12)
                payload = src.read(size)
                if len(nonce) != 12 or len(payload) != size:
                    raise ValueError("Backup criptografado truncado.")
                tmp.write(cipher.decrypt(nonce, payload, MAGIC + counter.to_bytes(8, "big")))
                counter += 1
        temporary.replace(destination)
    except Exception:
        if temporary:
            temporary.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("encrypt", "decrypt"))
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    key = key_from_env()
    operation = encrypt_file if args.command == "encrypt" else decrypt_file
    operation(args.source, args.destination, key)
    print(f"Arquivo {args.command} concluido: {args.destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
