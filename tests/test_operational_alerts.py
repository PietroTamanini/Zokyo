import pytest
import requests
from datetime import datetime, timedelta, timezone

from app import create_app
from app.extensions import db
from app.models import EventoLog, OperationalAlert, OperationalHeartbeat, Organization, registrar
from app.admin.operations import _job_stale, operations_context
from app.services.audit_integrity import assert_event_chain, verify_event_chain, verify_saved_anchor
from scripts.audit_anchor import latest_anchor
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


def test_daily_audit_records_verified_head_without_personal_data():
    app = _app()
    with app.app_context():
        registrar("sistema", "teste", "Evento de teste", organization_id=1)
        db.session.commit()
        original = EventoLog.query.one()
        result = assert_event_chain(record_success=True)
        assert result["checked"] == 1
        assert result["head_hash"] == original.integrity_hash
        verified = EventoLog.query.filter_by(modulo="audit_integrity").one()
        assert verified.organization_id is None
        assert verified.descricao == f"eventos=1;ultimo_id={original.id};hash_ponta={original.integrity_hash}"
        assert verify_event_chain()["checked"] == 2
        assert verify_event_chain()["errors"] == []


def test_audit_anchor_is_published_only_after_verified_check(tmp_path):
    app = _app()
    with app.app_context():
        registrar("sistema", "teste", "Primeiro", organization_id=1)
        db.session.commit()
        original = EventoLog.query.one()
        result = assert_event_chain(record_success=True, anchor_dir=tmp_path)
        path, saved = latest_anchor(tmp_path, 1)
        assert saved["head_hash"] == original.integrity_hash == result["head_hash"]
        assert saved["last_event_id"] == original.id
        assert verify_saved_anchor(tmp_path) == path
        count = EventoLog.query.count()
        db.session.execute(
            EventoLog.__table__.update().where(EventoLog.id == original.id).values(integrity_hash="0" * 64)
        )
        db.session.commit()
        with pytest.raises(RuntimeError, match="diverge"):
            verify_saved_anchor(tmp_path)
        with pytest.raises(RuntimeError, match="inconsistente"):
            assert_event_chain(record_success=True, anchor_dir=tmp_path)
        assert EventoLog.query.count() == count


def test_operations_uses_each_job_interval_and_flags_missing_audit():
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    daily = OperationalHeartbeat(job_name="verificar_auditoria", last_success_at=now - timedelta(hours=2))
    minute = OperationalHeartbeat(job_name="processar_notificacoes", last_success_at=now - timedelta(minutes=2))
    assert not _job_stale(daily, now)
    assert not _job_stale(minute, now)
    daily.last_success_at = now - timedelta(hours=31)
    minute.last_success_at = now - timedelta(minutes=6)
    assert _job_stale(daily, now)
    assert _job_stale(minute, now)

    app = _app()
    with app.app_context():
        assert operations_context()["audit_unverified"] is True


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
