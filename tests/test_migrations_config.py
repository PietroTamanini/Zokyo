import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from app import create_app


def test_flask_migrate_registrado():
    app = create_app("development")
    assert "migrate" in app.extensions


def test_producao_desabilita_create_all():
    os.environ["SECRET_KEY"] = "prod-secret-key"
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    app = create_app("production")
    assert app.config["DISABLE_CREATE_ALL"] is True
