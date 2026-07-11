import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from app import create_app
from app.extensions import db
from app.models import Usuario


def make_app():
    app = create_app("development")
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    return app


def test_healthz_funciona_sem_usuario():
    app = make_app()
    with app.app_context():
        db.drop_all()
        db.create_all()

    response = app.test_client().get("/healthz")

    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


def test_readyz_verifica_banco():
    app = make_app()
    with app.app_context():
        db.drop_all()
        db.create_all()

    response = app.test_client().get("/readyz")

    assert response.status_code == 200
    assert response.get_json()["database"] == "ok"


def test_erros_api_json_e_html_separados():
    app = make_app()
    with app.app_context():
        db.drop_all()
        db.create_all()
        usuario = Usuario(nome="Admin", email="admin@example.com", nivel="admin", ativo=True)
        usuario.set_senha("Senha!123")
        db.session.add(usuario)
        db.session.commit()

    client = app.test_client()
    api_response = client.get("/api/rota-inexistente", headers={"Accept": "application/json"})
    html_response = client.get("/rota-inexistente", headers={"Accept": "text/html"})

    assert api_response.status_code == 404
    assert api_response.is_json
    assert html_response.status_code == 404
    assert b"Pagina nao encontrada" in html_response.data
