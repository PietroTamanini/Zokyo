import os

import pytest
from cryptography.exceptions import InvalidTag

from scripts.backup_crypto import decrypt_file, encrypt_file


def test_backup_criptografado_restaura_byte_a_byte(tmp_path):
    key = os.urandom(32)
    source = tmp_path / "database.sql.gz"
    encrypted = tmp_path / "database.sql.gz.enc"
    restored = tmp_path / "restored.sql.gz"
    source.write_bytes(os.urandom(1024 * 1024 + 123))

    encrypt_file(source, encrypted, key)
    decrypt_file(encrypted, restored, key)

    assert encrypted.read_bytes() != source.read_bytes()
    assert restored.read_bytes() == source.read_bytes()


def test_backup_criptografado_rejeita_adulteracao_sem_criar_destino(tmp_path):
    source = tmp_path / "storage.tar.gz"
    encrypted = tmp_path / "storage.enc"
    restored = tmp_path / "restored.tar.gz"
    source.write_bytes(b"conteudo confidencial")
    key = os.urandom(32)
    encrypt_file(source, encrypted, key)
    payload = bytearray(encrypted.read_bytes())
    payload[-8] ^= 1
    encrypted.write_bytes(payload)

    with pytest.raises((InvalidTag, ValueError)):
        decrypt_file(encrypted, restored, key)
    assert not restored.exists()
