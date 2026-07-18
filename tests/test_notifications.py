from datetime import datetime, timedelta, timezone

from app import create_app
from app.extensions import db
from app.models import Notification, Organization
from app.services import notifications


def _app():
    app = create_app("development")
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        db.session.add(Organization(id=1, nome="Teste", slug="teste"))
        db.session.commit()
    return app


def test_enqueue_whatsapp_e_idempotente():
    app = _app()
    with app.app_context():
        first, created = notifications.enqueue_whatsapp(1, "47999999999", "Oi", "test", "same-key")
        second, created_again = notifications.enqueue_whatsapp(1, "47999999999", "Oi", "test", "same-key")
        assert created is True
        assert created_again is False
        assert first.id == second.id
        assert Notification.query.count() == 1


def test_enqueue_notification_cobre_colisao_de_idempotencia(monkeypatch):
    app = _app()
    with app.app_context():
        existing = Notification(
            organization_id=1,
            channel="email",
            recipient="cliente@example.test",
            event_type="test",
            idempotency_key="race",
            payload={"message": "existente"},
        )

        class FakeQuery:
            def execution_options(self, **_kwargs):
                return self

            def filter_by(self, **_kwargs):
                return self

            def first(self):
                return None

            def one(self):
                return existing

        monkeypatch.setattr(notifications.Notification, "query", FakeQuery(), raising=False)
        monkeypatch.setattr(
            notifications.db.session,
            "commit",
            lambda: (_ for _ in ()).throw(notifications.IntegrityError("insert", {}, Exception("duplicate"))),
        )
        monkeypatch.setattr(notifications.db.session, "rollback", lambda: None)
        item, created = notifications.enqueue_notification(1, "email", "cliente@example.test", {}, "test", "race")
        assert item is existing
        assert created is False


def test_process_notification_registra_sucesso(monkeypatch):
    app = _app()
    monkeypatch.setattr(notifications, "enviar_whatsapp", lambda *_: {"sucesso": True, "modo": "gateway"})
    with app.app_context():
        item, _ = notifications.enqueue_whatsapp(1, "47999999999", "Oi", "test", "success")
        result = notifications.process_notification(item.id)
        assert result.status == "sent"
        assert result.attempts == 1
        assert result.sent_at is not None


def test_process_notification_retries_e_falha_no_limite(monkeypatch):
    app = _app()
    monkeypatch.setattr(notifications, "enviar_whatsapp", lambda *_: {
        "sucesso": False, "modo": "fallback", "erro": "offline", "link": "https://wa.me/1"
    })
    with app.app_context():
        item, _ = notifications.enqueue_whatsapp(1, "47999999999", "Oi", "test", "retry")
        first = notifications.process_notification(item.id)
        assert first.status == "retry"
        assert first.next_attempt_at > datetime.now(timezone.utc).replace(tzinfo=None)
        first.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.session.commit()
        notifications.process_pending_notifications()
        item = db.session.get(Notification, item.id)
        assert item.attempts == 2
        item.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.session.commit()
        notifications.process_pending_notifications()
        assert db.session.get(Notification, item.id).status == "failed"


def test_simulacao_exige_envio_manual_sem_repetir(monkeypatch):
    app = _app()
    monkeypatch.setattr(notifications, "enviar_whatsapp", lambda *_: {
        "sucesso": False, "modo": "simulacao", "aviso": "sem servidor", "link": "https://wa.me/1"
    })
    with app.app_context():
        item, _ = notifications.enqueue_whatsapp(1, "47999999999", "Oi", "test", "manual")
        assert notifications.process_notification(item.id).status == "manual_required"
        assert notifications.process_notification(item.id).attempts == 1


def test_retry_manual_reinicia_estado_e_respeita_tenant():
    app = _app()
    with app.app_context():
        item, _ = notifications.enqueue_whatsapp(1, "47999999999", "Oi", "test", "reset")
        item.status = "failed"
        item.attempts = 3
        item.last_error = "offline"
        db.session.commit()
        reset = notifications.retry_notification(item.id, 1)
        assert reset.status == "pending"
        assert reset.attempts == 0
        assert reset.last_error is None
        try:
            notifications.retry_notification(item.id, 999)
        except LookupError:
            pass
        else:
            raise AssertionError("retry entre tenants deveria falhar")
        item.status = "sent"
        db.session.commit()
        try:
            notifications.retry_notification(item.id, 1)
        except ValueError:
            pass
        else:
            raise AssertionError("retry de notificacao entregue deveria falhar")


def test_email_transacional_usa_mesma_fila_auditavel():
    app = _app()
    with app.app_context():
        item, created = notifications.enqueue_email(
            1, "cliente@example.com", "OS pronta", "Seu equipamento esta pronto.",
            "os_ready", "email-ready-1",
        )
        assert created is True
        result = notifications.process_notification(item.id)
        assert result.channel == "email"
        assert result.status == "sent"
        assert app.extensions["email_outbox"][0]["to"] == "cliente@example.com"
