import os
import sys
import time
import types

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

import pytest
from flask import abort, session

import app as app_module
from app import _run_with_context, create_app
from app.extensions import db
from app.models import Configuracao, Organization, Usuario
from app.utils.exceptions import ValidationError
from config import DevelopmentConfig


def _factory_app():
    app_module._tem_usuarios = False
    app = create_app("development")
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    with app.app_context():
        db.drop_all()
        db.create_all()
    return app


def _before(app, name):
    return next(func for func in app.before_request_funcs[None] if func.__name__ == name)


def _seed_user(app, *, ativo=True, org_ativo=True, nivel="admin", totp_enabled=False):
    with app.app_context():
        org = Organization(id=1, nome="Factory", slug="factory", ativo=org_ativo)
        user = Usuario(
            organization_id=1,
            nome="Admin",
            email="admin.factory@example.com",
            nivel=nivel,
            ativo=ativo,
            totp_enabled=totp_enabled,
        )
        user.set_senha("Senha!123")
        db.session.add_all([org, user, Configuracao(organization_id=1, nome_empresa="Factory")])
        db.session.commit()
        return user.id, user.security_version


def test_context_processors_e_filtros_toleram_falhas(monkeypatch):
    app = _factory_app()
    processors = {func.__name__: func for func in app.template_context_processors[None]}

    def raise_error(*_args, **_kwargs):
        raise RuntimeError("falha planejada")

    monkeypatch.setattr(Configuracao, "get", raise_error)
    assert processors["inject_branding"]()["APP_NAME"] == "Zokyo"

    with app.test_request_context("/"):
        session["usuario_id"] = 1
        session["nivel"] = "admin"
        monkeypatch.setattr(db.session, "get", raise_error)
        context = processors["inject_globals"]()
    assert context["current_user"] is None
    assert context["cfg"] is None
    assert context["is_admin"] is True

    with app.app_context():
        assert processors["inject_csp_nonce"]()["csp_nonce"] == ""

    with app.test_request_context("/"):
        token = processors["inject_csrf_token"]()["csrf_token"]()
        assert token == session["_csrf_token"]

    assert app.jinja_env.filters["moeda"](object()) == "R$ 0,00"
    assert app.jinja_env.filters["fmtdata"](None) == "—"

    class BadDate:
        def strftime(self, _fmt):
            raise ValueError("data ruim")

        def __str__(self):
            return "bad-date"

    assert app.jinja_env.filters["fmtdata"](BadDate()) == "bad-date"
    assert app.jinja_env.filters["fmtdata"]("2026-07-18") == "18/07/2026"
    assert app.jinja_env.filters["fmtdata"]("abc") == "abc"


def test_before_requests_cobrem_sessoes_invalidas_e_2fa(monkeypatch):
    app = _factory_app()
    user_id, security_version = _seed_user(app)
    verificar_usuario = _before(app, "verificar_usuario_ativo")

    with app.test_request_context("/qualquer"):
        session["usuario_id"] = 999
        response = verificar_usuario()
    assert response.status_code == 302
    assert response.location == "/login"

    def raise_session_get(*_args, **_kwargs):
        raise RuntimeError("db indisponivel")

    monkeypatch.setattr(db.session, "get", raise_session_get)
    with app.test_request_context("/qualquer"):
        session["usuario_id"] = user_id
        assert verificar_usuario() is None
    monkeypatch.undo()
    app = _factory_app()
    user_id, security_version = _seed_user(app)
    verificar_usuario = _before(app, "verificar_usuario_ativo")

    inactive_app = _factory_app()
    inactive_id, _inactive_version = _seed_user(inactive_app, ativo=False)
    with inactive_app.test_request_context("/qualquer"):
        session["usuario_id"] = inactive_id
        response = _before(inactive_app, "verificar_usuario_ativo")()
    assert response.status_code == 302

    org_app = _factory_app()
    org_user_id, _org_version = _seed_user(org_app, org_ativo=False)
    with org_app.test_request_context("/qualquer"):
        session["usuario_id"] = org_user_id
        response = _before(org_app, "verificar_usuario_ativo")()
    assert response.status_code == 302

    with app.test_request_context("/qualquer"):
        session["usuario_id"] = user_id
        session["security_version"] = security_version + 1
        response = verificar_usuario()
    assert response.status_code == 302

    app.config["ALLOW_LEGACY_SESSIONS"] = False
    with app.test_request_context("/qualquer"):
        session["usuario_id"] = user_id
        session["security_version"] = security_version
        response = verificar_usuario()
    assert response.status_code == 302

    monkeypatch.setattr("app.services.user_sessions.validate_session_record", lambda _user: False)
    with app.test_request_context("/qualquer"):
        session["usuario_id"] = user_id
        session["security_version"] = security_version
        session["session_token"] = "token"
        response = verificar_usuario()
    assert response.status_code == 302

    app.config["ALLOW_LEGACY_SESSIONS"] = True
    app.config["REQUIRE_ADMIN_2FA"] = True
    with app.test_request_context("/qualquer"):
        session["usuario_id"] = user_id
        session["security_version"] = security_version
        response = verificar_usuario()
    assert response.status_code == 302
    assert response.location == "/seguranca/2fa"


def test_normalizacao_inatividade_csrf_primeiro_acesso_e_headers():
    app = _factory_app()
    user_id, _security_version = _seed_user(app)

    with app.test_request_context("/"):
        session["usuario_id"] = user_id
        session["perfil"] = "admin"
        _before(app, "normalizar_sessao")()
        assert session["nivel"] == "admin"
        session.pop("perfil")
        _before(app, "normalizar_sessao")()
        assert session["perfil"] == "admin"

    with app.test_request_context("/"):
        session["usuario_id"] = user_id
        session["_last_active"] = time.time() - 3600
        response = _before(app, "verificar_inatividade")()
    assert response.status_code == 302
    assert response.location == "/login"

    with app.test_request_context("/", method="POST"):
        with pytest.raises(Exception):
            _before(app, "protect_csrf")()

    first_app = _factory_app()
    with first_app.test_request_context("/"):
        response = _before(first_app, "primeiro_acesso_redirect")()
    assert response.status_code == 302
    assert response.location == "/primeiro-acesso"

    app.config["SESSION_COOKIE_SECURE"] = True
    response = app.test_client().get("/healthz")
    assert "Strict-Transport-Security" in response.headers
    assert "upgrade-insecure-requests" in response.headers["Content-Security-Policy"]


def test_rate_limit_global_cobre_rotas_dinamicas_e_poupa_healthcheck():
    app = _factory_app()
    app_module._tem_usuarios = True
    user_id, _security_version = _seed_user(app)
    app.config.update(
        RATE_LIMIT_GLOBAL_GET=50,
        RATE_LIMIT_GLOBAL_API=50,
        RATE_LIMIT_ENDPOINT_GET=2,
        RATE_LIMIT_ENDPOINT_API=1,
        RATE_LIMIT_WINDOW_SECONDS=60,
    )
    app.add_url_rule("/global-limited", endpoint="global_limited", view_func=lambda: "ok")
    app.add_url_rule("/api/global-limited", endpoint="api_global_limited", view_func=lambda: {"ok": True})
    client = app.test_client()
    with client.session_transaction() as session:
        session["usuario_id"] = user_id
        session["nivel"] = "admin"
        session["_last_active"] = time.time()

    assert client.get("/global-limited").status_code == 200
    assert client.get("/global-limited").status_code == 200
    blocked = client.get("/global-limited")
    assert blocked.status_code == 429

    assert client.get("/api/global-limited").status_code == 200
    api_blocked = client.get("/api/global-limited", headers={"Accept": "application/json"})
    assert api_blocked.status_code == 429
    assert api_blocked.get_json()["retry_after"] >= 1
    assert "Retry-After" in api_blocked.headers

    assert client.get("/healthz").status_code == 200
    assert client.get("/healthz").status_code == 200


def test_primeiro_acesso_e_rollback_toleram_excecoes(monkeypatch):
    app = _factory_app()
    primeiro_acesso = _before(app, "primeiro_acesso_redirect")

    class QueryFalha:
        def first(self):
            raise RuntimeError("db fora")

    with app.app_context():
        monkeypatch.setattr(Usuario, "query", QueryFalha())
    with app.test_request_context("/"):
        assert primeiro_acesso() is None

    teardown = next(func for func in app.teardown_request_funcs[None] if func.__name__ == "rollback_on_error")
    monkeypatch.setattr(db.session, "rollback", lambda: (_ for _ in ()).throw(RuntimeError("rollback falhou")))
    teardown(RuntimeError("erro request"))


def test_handlers_globais_e_scheduler_command(monkeypatch):
    app = _factory_app()
    app_module._tem_usuarios = True
    user_id, _security_version = _seed_user(app)
    app.config["PROPAGATE_EXCEPTIONS"] = False
    app.add_url_rule("/e401", endpoint="e401", view_func=lambda: abort(401))
    app.add_url_rule("/e403", endpoint="e403", view_func=lambda: abort(403))
    app.add_url_rule("/e422", endpoint="e422", view_func=lambda: abort(422))
    app.add_url_rule("/e503", endpoint="e503", view_func=lambda: abort(503))
    app.add_url_rule(
        "/html-app-error",
        endpoint="html_app_error",
        view_func=lambda: (_ for _ in ()).throw(ValidationError("Erro HTML")),
    )
    app.add_url_rule("/boom", endpoint="boom", view_func=lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    app.add_url_rule("/post-only", methods=["POST"], view_func=lambda: "ok")
    client = app.test_client()
    with client.session_transaction() as session:
        session["usuario_id"] = user_id
        session["nivel"] = "admin"
        session["_last_active"] = time.time()

    assert client.get("/e401").status_code == 401
    assert client.get("/e403").status_code == 403
    assert client.get("/e422").status_code == 422
    assert client.get("/e503").status_code == 503
    assert client.get("/post-only").status_code == 405
    assert client.get("/html-app-error", headers={"Accept": "text/html"}).status_code == 400
    assert client.get("/boom").status_code == 500

    disabled = app.test_cli_runner().invoke(args=["run-scheduler"])
    assert isinstance(disabled.exception, RuntimeError)

    app.config["SCHEDULER_ENABLED"] = True
    monkeypatch.setattr(time, "sleep", lambda _seconds: (_ for _ in ()).throw(KeyboardInterrupt()))
    interrupted = app.test_cli_runner().invoke(args=["run-scheduler"])
    assert isinstance(interrupted.exception, SystemExit)
    assert interrupted.exit_code == 1


def test_scheduler_start_import_error_e_start_error(monkeypatch):
    starts = []

    class FakeScheduler:
        def __init__(self, daemon=True):
            self.daemon = daemon

        def add_job(self, **_kwargs):
            return None

        def start(self):
            starts.append("start")

    fake_module = types.ModuleType("apscheduler.schedulers.background")
    fake_module.BackgroundScheduler = FakeScheduler
    monkeypatch.setitem(sys.modules, "apscheduler.schedulers.background", fake_module)
    monkeypatch.setattr(DevelopmentConfig, "SCHEDULER_ENABLED", True)
    app = create_app("development")
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    assert starts == ["start"]

    real_import = __import__

    def import_sem_scheduler(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "apscheduler.schedulers.background":
            raise ImportError("sem apscheduler")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", import_sem_scheduler)
    monkeypatch.setattr(DevelopmentConfig, "SCHEDULER_ENABLED", False)
    create_app("development")

    class BrokenScheduler(FakeScheduler):
        def add_job(self, **_kwargs):
            raise RuntimeError("scheduler quebrou")

    broken_module = types.ModuleType("apscheduler.schedulers.background")
    broken_module.BackgroundScheduler = BrokenScheduler
    monkeypatch.setattr("builtins.__import__", real_import)
    monkeypatch.setitem(sys.modules, "apscheduler.schedulers.background", broken_module)
    create_app("development")


def test_run_with_context_registra_sucesso_e_falha(monkeypatch):
    app = _factory_app()
    calls = []

    def fake_run_job(name, func):
        calls.append(name)
        func()

    monkeypatch.setattr("app.services.operational_alerts.run_job", fake_run_job)
    _run_with_context(app, "ok", lambda: calls.append("func"))
    assert calls == ["ok", "func"]

    def raising_run_job(_name, _func):
        raise RuntimeError("falha")

    monkeypatch.setattr("app.services.operational_alerts.run_job", raising_run_job)
    _run_with_context(app, "erro", lambda: None)
