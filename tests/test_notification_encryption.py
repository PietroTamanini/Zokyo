"""Notification content remains readable through the ORM but encrypted on disk."""
import json
import importlib

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from flask import Flask
from sqlalchemy import create_engine, text

from app import create_app
from app.extensions import db
from app.models import Notification, Organization
from app.services.privacy_encryption_audit import scan_privacy_encryption
from app.utils.field_crypto import FieldDecryptionError, PREFIX, decrypt_value


def test_new_notification_content_is_encrypted_and_fails_closed():
    app = create_app("development")
    app.config.update(TESTING=True)
    with app.app_context():
        db.drop_all()
        db.create_all()
        db.session.add(Organization(id=1, nome="Teste", slug="teste"))
        db.session.add(Notification(
            organization_id=1, recipient="cliente@example.test", event_type="test",
            idempotency_key="test-1", payload={"message": "Mensagem privada"},
            status="failed", last_error="Resposta privada do provedor",
        ))
        db.session.commit()
        raw = db.session.execute(text(
            "SELECT recipient, payload, last_error FROM notifications WHERE id=1"
        )).one()
        for value in raw:
            assert value.startswith(PREFIX)
            assert "privada" not in value
        item = db.session.get(Notification, 1)
        assert item.recipient == "cliente@example.test"
        assert item.payload == {"message": "Mensagem privada"}
        assert item.last_error == "Resposta privada do provedor"
        audit = scan_privacy_encryption()
        assert audit["plaintext"]["notifications.payload"] == 0
        assert audit["unreadable"]["notifications.payload"] == 0
        db.session.expunge(item)
        db.session.execute(text("UPDATE notifications SET payload=:value WHERE id=1"), {
            "value": PREFIX + "ciphertext-invalido",
        })
        db.session.commit()
        assert scan_privacy_encryption()["unreadable"]["notifications.payload"] == 1
        with pytest.raises(FieldDecryptionError):
            db.session.get(Notification, 1)


def test_legacy_notification_migration_encrypts_existing_rows():
    engine = create_engine("sqlite:///:memory:")
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY="notification-migration-test-only")
    with app.app_context(), engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE notifications (id INTEGER PRIMARY KEY, recipient VARCHAR(80) NOT NULL, "
            "payload JSON NOT NULL, last_error TEXT)"
        ))
        connection.execute(text(
            "INSERT INTO notifications (id, recipient, payload, last_error) "
            "VALUES (1, :recipient, :payload, :error), (2, '', '{}', NULL)"
        ), {"recipient": "legacy@example.test", "payload": json.dumps({"message": "Mensagem antiga"}),
            "error": "Falha antiga"})
        migration = importlib.import_module("migrations.versions.20261107_0052_encrypt_notifications")
        original_op = migration.op
        migration.op = Operations(MigrationContext.configure(connection))
        try:
            migration.upgrade()
        finally:
            migration.op = original_op
        rows = connection.execute(text(
            "SELECT id, recipient, payload, last_error FROM notifications ORDER BY id"
        )).all()
        assert rows[0].recipient.startswith(PREFIX)
        assert rows[0].payload.startswith(PREFIX)
        assert rows[0].last_error.startswith(PREFIX)
        assert decrypt_value(rows[0].recipient) == "legacy@example.test"
        assert json.loads(decrypt_value(rows[0].payload)) == {"message": "Mensagem antiga"}
        assert decrypt_value(rows[0].last_error) == "Falha antiga"
        assert rows[1].recipient == ""
        assert json.loads(decrypt_value(rows[1].payload)) == {}
    engine.dispose()
