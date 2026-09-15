import os
from urllib.parse import urlparse

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from app import create_app
from app.extensions import db
from app.models import EventoLog, PasswordResetToken, Usuario


def make_app():
    app = create_app("development")
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:", WTF_CSRF_ENABLED=False)
    return app


def post_csrf(client, path, data):
    with client.session_transaction() as session:
        session["_csrf_token"] = "csrf-test-token"
    return client.post(path, data={**data, "_csrf_token": "csrf-test-token"})


def test_recuperacao_nao_enumera_email():
    app = make_app()
    with app.app_context():
        db.create_all()
    response = post_csrf(app.test_client(), "/recuperar-senha", {"email": "inexistente@example.com"})
    assert response.status_code == 302
    assert not app.extensions.get("password_reset_outbox")


def test_token_redefine_senha_uma_unica_vez():
    app = make_app()
    with app.app_context():
        db.create_all()
        usuario = Usuario(nome="Admin", email="admin@example.com", nivel="admin", ativo=True)
        usuario.set_senha("Senha!123")
        db.session.add(usuario)
        db.session.commit()

    client = app.test_client()
    response = post_csrf(client, "/recuperar-senha", {"email": "admin@example.com"})
    assert response.status_code == 302
    link = app.extensions["password_reset_outbox"][0]["link"]
    path = urlparse(link).path
    raw_token = path.rsplit("/", 1)[-1]

    with app.app_context():
        stored = PasswordResetToken.query.one()
        assert raw_token not in stored.token_hash
        assert stored.usado_em is None

    response = post_csrf(client, path, {"senha": "Nova!Senha123", "confirmar_senha": "Nova!Senha123"})
    assert response.status_code == 302
    with app.app_context():
        usuario = Usuario.query.filter_by(email="admin@example.com").one()
        stored = PasswordResetToken.query.one()
        assert usuario.check_senha("Nova!Senha123")
        assert not usuario.check_senha("Senha!123")
        assert stored.usado_em is not None
        events = EventoLog.query.filter_by(modulo="usuarios", tipo="senha").order_by(EventoLog.id).all()
        assert [event.operacao for event in events] == [
            "Recuperacao de senha solicitada.",
            "Senha redefinida por token de recuperacao.",
        ]
        combined = " ".join(f"{event.operacao or ''} {event.descricao or ''}" for event in events)
        assert "admin@example.com" not in combined
        assert raw_token not in combined

    response = client.get(path)
    assert response.status_code == 302
