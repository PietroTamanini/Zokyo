import os
import time

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

import pyotp

import app as app_module
from app import create_app
from app.extensions import db
from app.models import EventoLog, Organization, UserSession, Usuario
from app.services.two_factor import consume_recovery_code, decrypt_secret, encrypt_secret, generate_recovery_codes


def make_app():
    app = create_app("development")
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    with app.app_context():
        db.create_all()
        db.session.add(Organization(id=1, nome="Teste", slug="test"))
        ativo = Usuario(nome="Ativo", email="ativo@example.com", nivel="admin", ativo=True)
        ativo.set_senha("Senha!123")
        inativo = Usuario(nome="Inativo", email="inativo@example.com", nivel="admin", ativo=False)
        inativo.set_senha("Senha!123")
        db.session.add_all([ativo, inativo])
        db.session.commit()
    return app


def csrf(client):
    with client.session_transaction() as session:
        session["_csrf_token"] = "csrf-token"
    return "csrf-token"


def test_primeiro_acesso_cria_admin_da_plataforma():
    app_module._tem_usuarios = False
    app = create_app("development")
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    with app.app_context():
        db.create_all()
    client = app.test_client()
    response = client.post("/primeiro-acesso", data={
        "_csrf_token": csrf(client),
        "nome": "Admin Plataforma",
        "email": "platform@example.com",
        "senha": "Senha!123",
        "confirmar_senha": "Senha!123",
    })
    assert response.status_code == 302
    with app.app_context():
        admin = Usuario.query.filter_by(email="platform@example.com").one()
        assert admin.is_platform_admin is True
        assert admin.organization_id is None
        assert Organization.query.count() == 0
    response = client.post("/login", data={
        "_csrf_token": csrf(client),
        "email": "platform@example.com",
        "senha": "Senha!123",
    })
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/platform")
    assert client.get("/").status_code == 404
    assert client.get("/platform").status_code == 200
    with app.app_context():
        session_record = UserSession.query.one()
        assert session_record.organization_id is None
        login_event = EventoLog.query.filter_by(tipo="login").one()
        assert login_event.organization_id is None


def test_login_logout_e_csrf():
    app = make_app()
    client = app.test_client()
    assert client.post("/login", data={"email": "ativo@example.com", "senha": "Senha!123"}).status_code == 400
    response = client.post("/login", data={
        "email": "ativo@example.com", "senha": "Senha!123", "_csrf_token": csrf(client),
    })
    assert response.status_code == 302
    with client.session_transaction() as session:
        assert session["nivel"] == "admin"
        assert session["session_token"]
        session["_last_active"] = time.time()
    with app.app_context():
        assert UserSession.query.filter_by(revoked_at=None).count() == 1
    response = client.post("/logout", data={"_csrf_token": csrf(client)})
    assert response.status_code == 302
    with client.session_transaction() as session:
        assert "usuario_id" not in session
    with app.app_context():
        assert UserSession.query.filter(UserSession.revoked_at.is_not(None)).count() == 1


def test_usuario_lista_e_revoga_sessao_secundaria():
    app = make_app()
    first = app.test_client()
    second = app.test_client()
    for client in (first, second):
        client.post("/login", data={
            "email": "ativo@example.com", "senha": "Senha!123", "_csrf_token": csrf(client),
        })
    page = first.get("/seguranca/sessoes")
    assert page.status_code == 200
    assert "Sessões e dispositivos".encode("utf-8") in page.data
    with app.app_context():
        second_record_id = UserSession.query.order_by(UserSession.id.desc()).first().id
    assert first.post(
        f"/seguranca/sessoes/{second_record_id}/revogar",
        data={"_csrf_token": csrf(first)},
    ).status_code == 302
    response = first.post("/seguranca/sessoes/revogar-outras", data={"_csrf_token": csrf(first)})
    assert response.status_code == 302
    assert second.get("/").status_code == 302


def test_admin_revoga_todas_as_proprias_sessoes():
    app = make_app()
    client = app.test_client()
    client.post("/login", data={
        "email": "ativo@example.com", "senha": "Senha!123", "_csrf_token": csrf(client),
    })
    with app.app_context():
        user_id = Usuario.query.filter_by(email="ativo@example.com").one().id
    response = client.post(
        f"/api/usuarios/{user_id}/revogar-sessoes",
        headers={"X-CSRFToken": csrf(client)},
    )
    assert response.status_code == 200
    with client.session_transaction() as current:
        assert "usuario_id" not in current


def test_usuario_inativo_nao_autentica():
    app = make_app()
    client = app.test_client()
    response = client.post("/login", data={
        "email": "inativo@example.com", "senha": "Senha!123", "_csrf_token": csrf(client),
    })
    assert response.status_code == 200
    with client.session_transaction() as session:
        assert "usuario_id" not in session


def test_novo_usuario_recebe_onboarding_e_pode_concluir():
    app = make_app()
    with app.app_context():
        usuario = Usuario.query.filter_by(email="ativo@example.com").one()
        usuario.onboarding_completed = False
        db.session.commit()
    client = app.test_client()
    response = client.post("/login", data={
        "email": "ativo@example.com", "senha": "Senha!123", "_csrf_token": csrf(client),
    })
    assert "/ajuda?onboarding=1" in response.headers["Location"]
    assert client.get(response.headers["Location"]).status_code == 200
    response = client.post("/ajuda/concluir", data={"_csrf_token": csrf(client)})
    assert response.status_code == 302
    with app.app_context():
        assert Usuario.query.filter_by(email="ativo@example.com").one().onboarding_completed is True


def test_admin_com_2fa_so_autentica_apos_totp():
    app = make_app()
    secret = pyotp.random_base32()
    with app.app_context():
        usuario = Usuario.query.filter_by(email="ativo@example.com").one()
        usuario.totp_secret_encrypted = encrypt_secret(secret)
        usuario.totp_enabled = True
        db.session.commit()
        user_id = usuario.id

    client = app.test_client()
    response = client.post("/login", data={
        "email": "ativo@example.com", "senha": "Senha!123", "_csrf_token": csrf(client),
    })
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/2fa")
    with client.session_transaction() as session:
        assert "usuario_id" not in session
        assert session["2fa_user_id"] == user_id

    response = client.post("/2fa", data={
        "codigo": pyotp.TOTP(secret).now(), "_csrf_token": csrf(client),
    })
    assert response.status_code == 302
    with client.session_transaction() as session:
        assert session["usuario_id"] == user_id
        assert "2fa_user_id" not in session


def test_codigo_de_recuperacao_e_consumido_uma_vez():
    app = make_app()
    with app.app_context():
        usuario = Usuario.query.filter_by(email="ativo@example.com").one()
        codes, hashes = generate_recovery_codes(1)
        usuario.recovery_codes_hash = hashes
        assert consume_recovery_code(usuario, codes[0]) is True
        assert consume_recovery_code(usuario, codes[0]) is False


def test_admin_ativa_2fa_com_confirmacao_totp():
    app = make_app()
    client = app.test_client()
    client.post("/login", data={
        "email": "ativo@example.com", "senha": "Senha!123", "_csrf_token": csrf(client),
    })
    response = client.get("/seguranca/2fa")
    assert response.status_code == 200
    assert b"QR Code" in response.data
    with app.app_context():
        usuario = Usuario.query.filter_by(email="ativo@example.com").one()
        secret = decrypt_secret(usuario.totp_secret_encrypted)
        assert usuario.totp_enabled is False
    response = client.post("/seguranca/2fa", data={
        "codigo": pyotp.TOTP(secret).now(), "_csrf_token": csrf(client),
    })
    assert response.status_code == 200
    assert "Códigos de recuperação".encode("utf-8") in response.data
    with app.app_context():
        usuario = Usuario.query.filter_by(email="ativo@example.com").one()
        assert usuario.totp_enabled is True
        assert len(usuario.recovery_codes_hash) == 8
