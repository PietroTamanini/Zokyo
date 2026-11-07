"""Session and signature metadata is encrypted without changing ORM reads."""
import importlib
from datetime import datetime, timedelta, timezone

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from flask import Flask
from sqlalchemy import create_engine, text

from app import create_app
from app.extensions import db
from app.models import OrderSignature, Organization, UserSession, Usuario
from app.services.privacy_encryption_audit import scan_privacy_encryption
from app.utils.field_crypto import FieldDecryptionError, PREFIX, decrypt_value, encrypt_value


def test_new_session_and_signature_metadata_is_encrypted_and_readable():
    app = create_app("development")
    app.config.update(TESTING=True)
    with app.app_context():
        db.drop_all()
        db.create_all()
        db.session.add(Organization(id=1, nome="Teste", slug="teste"))
        user = Usuario(organization_id=1, nome="Operador", email="operador@example.test", nivel="admin")
        user.set_senha("Senha!123")
        db.session.add(user)
        db.session.flush()
        session_record = UserSession(
            organization_id=1, user_id=user.id, token_hash="a" * 64,
            security_version=1, ip_address="192.0.2.10", user_agent="Navegador de teste",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        signature = OrderSignature(
            organization_id=1, order_id=1, captured_by_id=user.id,
            signer_name="Cliente Teste", storage_key="1/teste.png",
            size_bytes=10, sha256="b" * 64, ip_address="2001:db8::1",
        )
        db.session.add_all((session_record, signature))
        db.session.commit()
        raw_session = db.session.execute(text(
            "SELECT ip_address, user_agent FROM user_sessions WHERE id=:id"
        ), {"id": session_record.id}).one()
        raw_signature = db.session.execute(text(
            "SELECT signer_name, ip_address FROM order_signatures WHERE id=:id"
        ), {"id": signature.id}).one()
        for raw in (*raw_session, *raw_signature):
            assert raw.startswith(PREFIX)
        db.session.expire_all()
        assert db.session.get(UserSession, session_record.id).ip_address == "192.0.2.10"
        assert db.session.get(UserSession, session_record.id).user_agent == "Navegador de teste"
        assert db.session.get(OrderSignature, signature.id).signer_name == "Cliente Teste"
        assert db.session.get(OrderSignature, signature.id).ip_address == "2001:db8::1"
        audit = scan_privacy_encryption()
        assert all(audit["plaintext"][f"{table}.{column}"] == 0 for table, column in (
            ("user_sessions", "ip_address"), ("user_sessions", "user_agent"),
            ("order_signatures", "signer_name"), ("order_signatures", "ip_address"),
        ))
        db.session.execute(text(
            "UPDATE user_sessions SET ip_address=:bad WHERE id=:id"
        ), {"bad": PREFIX + "invalid", "id": session_record.id})
        db.session.commit()
        assert scan_privacy_encryption()["unreadable"]["user_sessions.ip_address"] == 1
        db.session.expire_all()
        with pytest.raises(FieldDecryptionError):
            db.session.get(UserSession, session_record.id)


def test_legacy_session_and_signature_rows_are_encrypted_by_migration():
    engine = create_engine("sqlite:///:memory:")
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY="session-signature-migration-test")
    with app.app_context(), engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE user_sessions (id INTEGER PRIMARY KEY, ip_address VARCHAR(45), user_agent VARCHAR(300))"
        ))
        connection.execute(text(
            "CREATE TABLE order_signatures (id INTEGER PRIMARY KEY, signer_name VARCHAR(120) NOT NULL, "
            "ip_address VARCHAR(45))"
        ))
        connection.execute(text(
            "INSERT INTO user_sessions (id, ip_address, user_agent) VALUES "
            "(1, '192.0.2.20', 'Navegador legado'), (2, NULL, NULL)"
        ))
        connection.execute(text(
            "INSERT INTO order_signatures (id, signer_name, ip_address) VALUES "
            "(1, 'Cliente legado', '2001:db8::2'), (2, 'Cliente cifrado', NULL)"
        ))
        connection.execute(text(
            "UPDATE order_signatures SET signer_name=:encrypted WHERE id=2"
        ), {"encrypted": encrypt_value("Cliente cifrado")})
        migration = importlib.import_module(
            "migrations.versions.20261107_0055_encrypt_session_signature_metadata"
        )
        original_op = migration.op
        migration.op = Operations(MigrationContext.configure(connection))
        try:
            migration.upgrade()
        finally:
            migration.op = original_op
        session_row = connection.execute(text(
            "SELECT ip_address, user_agent FROM user_sessions WHERE id=1"
        )).one()
        signature_row = connection.execute(text(
            "SELECT signer_name, ip_address FROM order_signatures WHERE id=1"
        )).one()
        assert [decrypt_value(value) for value in session_row] == ["192.0.2.20", "Navegador legado"]
        assert [decrypt_value(value) for value in signature_row] == ["Cliente legado", "2001:db8::2"]
        assert all(value.startswith(PREFIX) for value in (*session_row, *signature_row))
        assert connection.scalar(text("SELECT signer_name FROM order_signatures WHERE id=2")).startswith(PREFIX)
        assert connection.execute(text(
            "SELECT ip_address, user_agent FROM user_sessions WHERE id=2"
        )).one() == (None, None)
    engine.dispose()
