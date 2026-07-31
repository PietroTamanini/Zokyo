import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from app import create_app
from app.extensions import db
from app.models import Notification, OperationalAlert, OperationalHeartbeat, Organization, Usuario
from app.utils.exceptions import ValidationError


def make_app():
    app = create_app("development")
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    return app


def _seed_admin_and_login(app, client):
    with app.app_context():
        org = Organization(id=1, nome="Erros", slug="erros")
        usuario = Usuario(organization_id=1, nome="Admin", email="admin-errors@example.com", nivel="admin", ativo=True)
        usuario.set_senha("Senha!123")
        db.session.add_all([org, usuario])
        db.session.commit()
        user_id = usuario.id
    with client.session_transaction() as session:
        session["usuario_id"] = user_id
        session["nivel"] = "admin"
        session["perfil"] = "admin"
        session["_last_active"] = 9999999999


def test_healthz_funciona_sem_usuario():
    app = make_app()
    with app.app_context():
        db.drop_all()
        db.create_all()

    response = app.test_client().get("/healthz")

    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"
    assert len(response.headers["X-Request-ID"]) == 32


def test_request_id_valido_e_propagado():
    app = make_app()
    with app.app_context():
        db.create_all()
    response = app.test_client().get("/healthz", headers={"X-Request-ID": "trace-123"})
    assert response.headers["X-Request-ID"] == "trace-123"
    csp = response.headers["Content-Security-Policy"]
    assert "cdn.jsdelivr.net" not in csp
    assert "fonts.googleapis.com" not in csp


def test_metricas_exigem_autorizacao_e_exportam_prometheus():
    app = make_app()
    app.config["METRICS_TOKEN"] = "metrics-secret"
    with app.app_context():
        db.create_all()
    client = app.test_client()
    assert client.get("/metrics").status_code == 403
    response = client.get("/metrics", headers={"Authorization": "Bearer metrics-secret"})
    assert response.status_code == 200
    assert b"zokyo_http_requests_total" in response.data


def test_readyz_verifica_banco():
    app = make_app()
    with app.app_context():
        db.drop_all()
        db.create_all()

    response = app.test_client().get("/readyz")

    assert response.status_code == 200
    assert response.get_json()["database"] == "ok"


def test_readyz_reporta_falha_do_banco(monkeypatch):
    app = make_app()
    with app.app_context():
        db.drop_all()
        db.create_all()

    def raise_db_error(*_args, **_kwargs):
        raise RuntimeError("db fora")

    monkeypatch.setattr(db.session, "execute", raise_db_error)
    response = app.test_client().get("/readyz")

    assert response.status_code == 503
    assert response.get_json()["database"] == "error"


def test_operations_status_lista_heartbeats_alertas_e_notificacoes():
    app = make_app()
    with app.app_context():
        db.drop_all()
        db.create_all()
        org = Organization(id=1, nome="Ops", slug="ops")
        usuario = Usuario(organization_id=1, nome="Admin", email="ops@example.com", nivel="admin", ativo=True)
        usuario.set_senha("Senha!123")
        heartbeat = OperationalHeartbeat(job_name="backup", consecutive_failures=2, last_error="falhou")
        alert = OperationalAlert(severity="critical", source="backup", message="Falhou", fingerprint="ops-alert")
        notification = Notification(
            organization_id=1,
            channel="email",
            recipient="ops@example.com",
            event_type="ops",
            idempotency_key="ops-1",
            payload={},
            status="failed",
        )
        db.session.add_all([org, usuario, heartbeat, alert, notification])
        db.session.commit()
        user_id = usuario.id

    client = app.test_client()
    with client.session_transaction() as session:
        session["usuario_id"] = user_id
        session["nivel"] = "admin"
        session["perfil"] = "admin"
        session["_last_active"] = 9999999999
        session["_csrf_token"] = "ops-csrf"

    response = client.get("/api/operations/status")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["heartbeats"][0]["job"] == "backup"
    assert payload["alerts"][0]["source"] == "backup"
    assert payload["failed_notifications"] == 1


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
    assert "Página não encontrada".encode("utf-8") in html_response.data


def test_erros_estruturados_incluem_codigo_e_request_id():
    app = make_app()

    def invalid_payload():
        raise ValidationError("Campo inválido.", {"nome": "Obrigatório"})

    app.add_url_rule("/api/test-validation", view_func=invalid_payload)
    with app.app_context():
        db.create_all()
    client = app.test_client()
    _seed_admin_and_login(app, client)

    response = client.get(
        "/api/test-validation",
        headers={"Accept": "application/json", "X-Request-ID": "validation-test"},
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "success": False,
        "erro": "Campo inválido.",
        "errors": {"nome": "Obrigatório"},
        "code": 400,
        "request_id": "validation-test",
    }


def test_erro_429_html_usa_tela_generica_acessivel():
    from flask import abort

    app = make_app()
    app.add_url_rule("/test-rate-limit", view_func=lambda: abort(429))
    with app.app_context():
        db.create_all()
    client = app.test_client()
    _seed_admin_and_login(app, client)

    response = client.get("/test-rate-limit", headers={"Accept": "text/html"})

    assert response.status_code == 429
    assert b"N\xc3\xa3o foi poss\xc3\xadvel concluir" in response.data
    assert b"Muitas tentativas" in response.data
