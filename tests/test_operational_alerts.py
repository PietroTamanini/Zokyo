import pytest
import requests

from app import create_app
from app.extensions import db
from app.models import OperationalAlert, OperationalHeartbeat, Organization
from app.services.operational_alerts import _safe_webhook, emit_alert, run_job


def _app():
    app = create_app("development")
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:", ALERT_EMAIL=None, ALERT_WEBHOOK_URL=None)
    with app.app_context():
        db.create_all()
        db.session.add(Organization(id=1, nome="Teste", slug="teste"))
        db.session.commit()
    return app


def test_job_registra_sucesso_e_falha_deduplicada():
    app = _app()
    with app.app_context():
        assert run_job("teste", lambda: 42) == 42
        heartbeat = OperationalHeartbeat.query.filter_by(job_name="teste").one()
        assert heartbeat.last_success_at is not None
        assert heartbeat.consecutive_failures == 0

        for _ in range(2):
            with pytest.raises(RuntimeError):
                run_job("teste", lambda: (_ for _ in ()).throw(RuntimeError("indisponivel")))
        heartbeat = OperationalHeartbeat.query.filter_by(job_name="teste").one()
        assert heartbeat.consecutive_failures == 2
        alert = OperationalAlert.query.one()
        assert alert.occurrences == 2
        assert alert.severity == "warning"


def test_alerta_deduplica_fingerprint():
    app = _app()
    with app.app_context():
        emit_alert("critical", "backup", "Backup atrasado")
        emit_alert("critical", "backup", "Backup atrasado")
        assert OperationalAlert.query.one().occurrences == 2


def test_webhook_exige_https_allowlist_e_ip_publico(monkeypatch):
    monkeypatch.setenv("ALERT_WEBHOOK_ALLOWED_HOSTS", "alerts.example")
    monkeypatch.setattr("app.services.operational_alerts.socket.getaddrinfo", lambda *_: [(None, None, None, None, ("8.8.8.8", 443))])
    assert _safe_webhook("https://alerts.example/hook")
    monkeypatch.setattr("app.services.operational_alerts.socket.getaddrinfo", lambda *_: [(None, None, None, None, ("127.0.0.1", 443))])
    assert not _safe_webhook("https://alerts.example/hook")
    monkeypatch.setattr(
        "app.services.operational_alerts.socket.getaddrinfo",
        lambda *_: (_ for _ in ()).throw(ValueError("dns")),
    )
    assert not _safe_webhook("https://alerts.example/hook")
    assert not _safe_webhook("http://alerts.example/hook")
    assert not _safe_webhook("https://other.example/hook")


def test_alerta_entrega_email_e_tenta_webhook_seguro(monkeypatch):
    app = _app()
    app.config.update(ALERT_EMAIL="ops@example.test", ALERT_WEBHOOK_URL="https://alerts.example/hook")
    sent = []

    def fake_post(*_args, **_kwargs):
        raise requests.RequestException("fora")

    monkeypatch.setattr("app.services.operational_alerts.send_email", lambda *args: sent.append(args))
    monkeypatch.setattr("app.services.operational_alerts._safe_webhook", lambda _url: True)
    monkeypatch.setattr("app.services.operational_alerts.requests.post", fake_post)
    with app.app_context():
        emit_alert("critical", "webhook", "Falha\ncom quebra")
    assert sent[0][0] == "ops@example.test"
