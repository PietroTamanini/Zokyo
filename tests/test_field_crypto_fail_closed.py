"""Chave errada não pode transformar dado cifrado em campo vazio."""
import base64
import os
import unittest
from unittest.mock import patch

from flask import Flask

from app.utils.field_crypto import FieldDecryptionError, decrypt_value, encrypt_value
from app.utils.blind_index import blind_index_key


class FieldCryptoFailClosedTests(unittest.TestCase):
    def test_production_rejects_implicit_field_and_index_keys(self):
        app = Flask(__name__)
        app.config["SECRET_KEY"] = "s" * 40
        with app.app_context(), patch.dict(os.environ, {"FLASK_ENV": "production", "ENCRYPTION_SALT": "", "BLIND_INDEX_KEY": ""}):
            with self.assertRaisesRegex(RuntimeError, "ENCRYPTION_SALT"):
                encrypt_value("Rua Privada")
            with self.assertRaisesRegex(RuntimeError, "BLIND_INDEX_KEY"):
                blind_index_key()

    def test_wrong_salt_raises_and_original_key_recovers_value(self):
        app = Flask(__name__)
        app.config["SECRET_KEY"] = "s" * 40
        first = base64.b64encode(b"a" * 32).decode("ascii")
        second = base64.b64encode(b"b" * 32).decode("ascii")
        with app.app_context(), patch.dict(os.environ, {"ENCRYPTION_SALT": first}):
            encrypted = encrypt_value("Rua Privada, 123")
            with patch.dict(os.environ, {"ENCRYPTION_SALT": second}):
                with self.assertRaisesRegex(FieldDecryptionError, "ilegível"):
                    decrypt_value(encrypted)
            self.assertEqual(decrypt_value(encrypted), "Rua Privada, 123")


if __name__ == "__main__":
    unittest.main()
