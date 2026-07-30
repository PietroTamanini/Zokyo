import builtins
import logging
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Flask

from app import create_app
from app.extensions import db
from app.models import Notification, OperationalAlert, OperationalHeartbeat, Organization, Usuario
from app.utils import email_delivery, logging_config, observability, operational_metrics, rate_limit
from app.utils.rate_limit import (
    ApiRateLimit,
    LoginAttempt,
    check_lock,
    clear_fails,
    limpar_rate_limit_antigos,
    rate_limit_route,
    register_fail,
)


def test_email_delivery_testing_simulacao_smtp_e_fallback(monkeypatch):
    testing_app = Flask(__name__)
    testing_app.testing = True
    with testing_app.app_context():
        result = email_delivery.send_email("user@example.com", "Assunto", "Corpo")
        assert result == {"sucesso": True, "modo": "testing"}
        assert testing_app.extensions["email_outbox"][0]["to"] == "user@example.com"

    app = Flask(__name__)
    app.testing = False
    with app.app_context():
        assert email_delivery.send_email("user@example.com", "Assunto", "Corpo") == {
            "sucesso": False,
            "modo": "simulacao",
            "aviso": "SMTP não configurado",
        }

    class FakeSMTP:
        sent_subject = None
        logged_in = False
        started_tls = False

        def __init__(self, host, port, timeout):
            assert (host, port, timeout) == ("smtp.example.com", 2525, 15)

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def starttls(self):
            type(self).started_tls = True

        def login(self, username, password):
            type(self).logged_in = (username, password) == ("usuario", "senha")

        def send_message(self, message):
            type(self).sent_subject = message["Subject"]

    monkeypatch.setattr(email_delivery.smtplib, "SMTP", FakeSMTP)
    app.config.update(
        SMTP_HOST="smtp.example.com",
        SMTP_PORT=2525,
        SMTP_STARTTLS=True,
        SMTP_USERNAME="usuario",
        SMTP_PASSWORD="senha",
        MAIL_FROM="noreply@example.com",
    )
    with app.app_context():
        result = email_delivery.send_email("user@example.com", "S" * 250, "Corpo")
        assert result == {"sucesso": True, "modo": "smtp"}
        assert FakeSMTP.started_tls is True
        assert FakeSMTP.logged_in is True
        assert len(FakeSMTP.sent_subject) == 200

    class BrokenSMTP(FakeSMTP):
        def __enter__(self):
            raise OSError("fora")

    monkeypatch.setattr(email_delivery.smtplib, "SMTP", BrokenSMTP)
    with app.app_context():
        assert email_delivery.send_email("user@example.com", "Assunto", "Corpo") == {
            "sucesso": False,
            "modo": "fallback",
                "erro": "Falha temporária de e-mail",
        }


def test_observability_start_observe_e_sentry(monkeypatch):
    app = Flask(__name__)

    @app.route("/ok")
    def ok():
        observability.start_request_metrics()
        return observability.observe_response(app.response_class("ok", status=201))

    response = app.test_client().get("/ok")
    assert response.status_code == 201
    assert observability.init_sentry(app) is False

    sentry_module = types.ModuleType("sentry_sdk")
    captured = {}

    def fake_init(**kwargs):
        captured.update(kwargs)

    sentry_module.init = fake_init
    integrations_module = types.ModuleType("sentry_sdk.integrations")
    flask_module = types.ModuleType("sentry_sdk.integrations.flask")

    class FlaskIntegration:
        pass

    flask_module.FlaskIntegration = FlaskIntegration
    monkeypatch.setitem(sys.modules, "sentry_sdk", sentry_module)
    monkeypatch.setitem(sys.modules, "sentry_sdk.integrations", integrations_module)
    monkeypatch.setitem(sys.modules, "sentry_sdk.integrations.flask", flask_module)
    app.config.update(SENTRY_DSN="https://example.invalid/1", SENTRY_TRACES_SAMPLE_RATE=0.25, ENV="test")
    assert observability.init_sentry(app) is True
    assert captured["dsn"] == "https://example.invalid/1"
    assert captured["traces_sample_rate"] == 0.25
    assert captured["send_default_pii"] is False

    real_import = builtins.__import__

    def block_sentry_import(name, *args, **kwargs):
        if name.startswith("sentry_sdk"):
            raise ImportError("sem sentry")
        return real_import(name, *args, **kwargs)

    missing_app = Flask("missing-sentry")
    missing_app.config["SENTRY_DSN"] = "https://example.invalid/2"
    monkeypatch.setattr(builtins, "__import__", block_sentry_import)
    assert observability.init_sentry(missing_app) is False


def test_logging_mask_formatter_e_configuracao(tmp_path, monkeypatch):
    masked = logging_config._mask(
        "senha=abcdef token=123456 Bearer abcd1234 user@example.com "
        "123.456.789-00 12.345.678/0001-99 X-Forwarded-For: 10.20.30.40"
    )
    assert "senha=abc***" in masked
    assert "token=123***" in masked
    assert "Bearer abcd***" in masked
    assert "u***@example.com" in masked
    assert "123.***.***-00" in masked
    assert "12.***.***/****-99" in masked
    assert "X-Forwarded-For: 10.20.***.***" in masked

    record = logging.LogRecord("test", logging.ERROR, __file__, 1, "msg %s", ("token=abcdef",), None)
    assert logging_config.MaskingFilter().filter(record) is True
    assert record.args == ("token=abc***",)
    formatted = logging_config.JsonFormatter().format(record)
    assert '"level": "ERROR"' in formatted
    assert "token=abc***" in formatted
    try:
        raise RuntimeError("falha")
    except RuntimeError:
        exc_record = logging.LogRecord("test", logging.ERROR, __file__, 1, "com excecao", (), sys.exc_info())
    assert "exception" in logging_config.JsonFormatter().format(exc_record)

    app = Flask(__name__)
    app.config["DEBUG"] = False
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    logging_config.configure_logging(app)
    assert app.logger.level == logging.INFO
    assert (tmp_path / "zokyo.log").exists()

    dev_app = Flask("dev")
    dev_app.config["DEBUG"] = True
    logging_config.configure_logging(dev_app)
    assert dev_app.logger.level == logging.DEBUG

    class BrokenRotatingFileHandler:
        def __init__(self, *_args, **_kwargs):
            raise OSError("sem permissao")

    monkeypatch.setattr(logging_config.logging.handlers, "RotatingFileHandler", BrokenRotatingFileHandler)
    broken_app = Flask("broken-log")
    broken_app.config["DEBUG"] = False
    logging_config.configure_logging(broken_app)
    assert broken_app.logger.level == logging.INFO


def _make_rate_limit_app():
    app = create_app("development")
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    with app.app_context():
        db.drop_all()
        db.create_all()
        db.session.add(Organization(id=1, nome="Teste", slug="teste"))
        user = Usuario(organization_id=1, nome="Admin", email="admin@example.com", nivel="admin", ativo=True)
        user.set_senha("Senha!123")
        db.session.add(user)
        db.session.commit()

    @app.route("/limited")
    @rate_limit_route(max_hits=2, window_seconds=60)
    def limited():
        return {"ok": True}

    @app.route("/limited-abort")
    @rate_limit_route(max_hits=1, window_seconds=60, abort_code=403)
    def limited_abort():
        return {"ok": True}

    return app


def test_rate_limit_login_api_e_limpeza():
    app = _make_rate_limit_app()
    with app.app_context():
        assert check_lock("1.2.3.4") == (False, 0)
        assert register_fail("1.2.3.4", max_fails=2, lock_seconds=30) == 0
        assert register_fail("1.2.3.4", max_fails=2, lock_seconds=30) == 30
        blocked, remaining = check_lock("1.2.3.4")
        assert blocked is True
        assert remaining <= 30
        clear_fails("1.2.3.4")
        assert check_lock("1.2.3.4") == (False, 0)

        old = datetime.now(timezone.utc) - timedelta(minutes=10)
        attempt = db.session.get(LoginAttempt, "1.2.3.4")
        attempt.falhas = 3
        attempt.ultima_falha = old
        attempt.bloqueado_ate = old
        db.session.commit()
        assert check_lock("1.2.3.4", window_minutes=5) == (False, 0)
        assert db.session.get(LoginAttempt, "1.2.3.4").falhas == 0

    client = app.test_client()
    assert client.get("/limited").status_code == 200
    assert client.get("/limited").status_code == 200
    too_many = client.get("/limited")
    assert too_many.status_code == 429
    assert "Retry-After" in too_many.headers
    assert client.get("/limited-abort").status_code == 200
    assert client.get("/limited-abort").status_code == 403

    with app.app_context():
        rec = ApiRateLimit.query.filter_by(endpoint="limited").one()
        rec.janela_inicio = datetime.now(timezone.utc) - timedelta(seconds=120)
        db.session.commit()
    assert client.get("/limited").status_code == 200

    with app.app_context():
        old_cutoff = datetime.now(timezone.utc) - timedelta(days=8)
        db.session.add(LoginAttempt(ip="old", falhas=1, ultima_falha=old_cutoff))
        db.session.add(ApiRateLimit(ip="old", endpoint="old", hits=1, janela_inicio=old_cutoff))
        db.session.commit()
        limpar_rate_limit_antigos()
        assert db.session.get(LoginAttempt, "old") is None
        assert ApiRateLimit.query.filter_by(ip="old").count() == 0


def test_rate_limit_mysql_atomic_branch(monkeypatch):
    class Dialect:
        name = "mysql"

    class Bind:
        dialect = Dialect()

    record = types.SimpleNamespace(falhas=5, bloqueado_ate=None)
    executed = []
    commits = []
    monkeypatch.setattr(rate_limit.db.session, "get_bind", lambda: Bind())
    monkeypatch.setattr(rate_limit.db.session, "execute", lambda statement, params: executed.append((statement, params)))
    monkeypatch.setattr(rate_limit.db.session, "commit", lambda: commits.append(True))
    monkeypatch.setattr(rate_limit.db.session, "get", lambda _model, _ip: record)

    assert rate_limit.register_fail("10.0.0.1", max_fails=5, lock_seconds=30) == 30
    assert record.falhas == 0
    record.falhas = 1
    assert rate_limit.register_fail("10.0.0.1", max_fails=5, lock_seconds=30) == 0
    assert executed
    assert commits


def test_operational_metrics_network_e_coleta(monkeypatch, tmp_path):
    class FakePath:
        def __init__(self, _value):
            pass

        def exists(self):
            return True

        def read_text(self, encoding):
            assert encoding == "utf-8"
            return "header\nheader\nsem-dois-pontos\neth0: 10 0 0 0 0 0 0 0 20 0 0 0 0 0 0 0\n"

    monkeypatch.setattr(operational_metrics, "Path", FakePath)
    assert operational_metrics._network_totals() == (10, 20)
    monkeypatch.setattr(operational_metrics, "Path", Path)
    assert operational_metrics._existing_path_for_disk_usage(tmp_path / "a" / "b") == tmp_path

    app = create_app("development")
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    with app.app_context():
        db.drop_all()
        db.create_all()
        db.session.add(Organization(id=1, nome="Teste", slug="teste"))
        db.session.add(
            Notification(
                organization_id=1,
                channel="email",
                recipient="a@b.com",
                event_type="teste",
                idempotency_key="notif-1",
                payload={"body": "x"},
                status="pending",
            )
        )
        db.session.add(OperationalHeartbeat(job_name="job", last_success_at=datetime.now(timezone.utc)))
        db.session.add(OperationalAlert(source="job", severity="critical", message="erro", fingerprint="abc"))
        db.session.commit()
        pool = db.engine.pool
        monkeypatch.setattr(pool, "checkedout", lambda: 1, raising=False)
        monkeypatch.setattr(pool, "checkedin", lambda: 2, raising=False)
        monkeypatch.setattr(pool, "overflow", lambda: 3, raising=False)
        monkeypatch.setattr(operational_metrics.os, "getloadavg", lambda: (1.0, 2.0, 3.0), raising=False)
        monkeypatch.setattr(operational_metrics, "_network_totals", lambda: (1, 2))
        operational_metrics.collect_operational_metrics()
        monkeypatch.setattr(
            operational_metrics.os,
            "getloadavg",
            lambda: (_ for _ in ()).throw(OSError()),
            raising=False,
        )
        monkeypatch.setattr(operational_metrics, "_network_totals", lambda: (1, 2))
        operational_metrics.collect_operational_metrics()
