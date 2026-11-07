from datetime import datetime, timedelta, timezone

from app import create_app
from app.extensions import db
from app.models import EventoLog, Notification, Organization, PlatformRetentionPolicy, RetentionPolicy, UserSession, Usuario
from app.services.retention import apply_active_policies, apply_platform_policy, apply_policy, count_candidates, count_platform_candidates
from app.services.notifications import enqueue_email


def test_retencao_remove_apenas_notificacoes_terminais_antigas_e_aprovadas():
    app = create_app("development")
    app.config.update(TESTING=True)
    with app.app_context():
        db.drop_all()
        db.create_all()
        db.session.add(Organization(id=1, nome="Teste", slug="teste"))
        db.session.add(Organization(id=2, nome="Outra", slug="outra"))
        old = datetime.now(timezone.utc) - timedelta(days=100)
        db.session.add_all([
            Notification(organization_id=1, recipient="pessoa@example.test", event_type="test", idempotency_key="sent", payload={"message": "Olá, pessoa"}, status="sent", created_at=old),
            Notification(organization_id=1, recipient="1", event_type="test", idempotency_key="pending", payload={}, status="pending", created_at=old),
            Notification(organization_id=1, recipient="2", event_type="test", idempotency_key="manual", payload={"message": "Enviar"}, status="manual_required", created_at=old),
            Notification(organization_id=1, recipient="3", event_type="test", idempotency_key="failed", payload={"message": "Reenviar"}, status="failed", created_at=old),
            Notification(organization_id=2, recipient="other@example.test", event_type="test", idempotency_key="other-sent", payload={"message": "Outra empresa"}, status="sent", created_at=old),
        ])
        policy = RetentionPolicy(
            organization_id=1, category="notifications", retention_days=90,
            active=True, approved_at=datetime.now(timezone.utc),
        )
        db.session.add(policy)
        db.session.commit()
        assert count_candidates(policy) == 1
        assert apply_policy(policy) == 1
        assert count_candidates(policy) == 0
        assert apply_policy(policy) == 0
        assert Notification.query.count() == 5
        sent = Notification.query.filter_by(idempotency_key="sent").one()
        assert sent.status == "sent"
        assert sent.recipient == ""
        assert sent.payload == {}
        assert sent.redacted_at is not None
        assert Notification.query.filter_by(idempotency_key="manual").one().recipient == "2"
        assert Notification.query.filter_by(idempotency_key="failed").one().recipient == "3"
        assert Notification.query.filter_by(organization_id=2).one().recipient == "other@example.test"
        same, created = enqueue_email(1, "pessoa@example.test", "Assunto", "Corpo", "test", "sent")
        assert not created
        assert same.id == sent.id
        assert EventoLog.query.filter_by(modulo="privacy", tipo="retencao").count() == 1


def test_retencao_inativa_nunca_exclui():
    app = create_app("development")
    app.config.update(TESTING=True)
    with app.app_context():
        db.drop_all()
        db.create_all()
        db.session.add(Organization(id=1, nome="Teste", slug="teste"))
        db.session.add(Notification(
            organization_id=1, recipient="1", event_type="test", idempotency_key="keep",
            payload={}, status="failed", created_at=datetime.now(timezone.utc) - timedelta(days=100),
        ))
        policy = RetentionPolicy(organization_id=1, category="notifications", retention_days=90, active=False)
        db.session.add(policy)
        db.session.commit()
        assert apply_policy(policy) == 0
        assert Notification.query.count() == 1


def test_retencao_de_sessoes_preserva_ativas_e_outras_empresas():
    app = create_app("development")
    app.config.update(TESTING=True)
    with app.app_context():
        db.drop_all()
        db.create_all()
        db.session.add_all((
            Organization(id=1, nome="Teste", slug="teste"),
            Organization(id=2, nome="Outra", slug="outra"),
        ))
        user1 = Usuario(organization_id=1, nome="Um", email="um@example.test", nivel="admin")
        user2 = Usuario(organization_id=2, nome="Dois", email="dois@example.test", nivel="admin")
        user1.set_senha("Senha!123")
        user2.set_senha("Senha!123")
        db.session.add_all((user1, user2))
        db.session.flush()
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=120)
        future = now + timedelta(days=1)
        db.session.add_all((
            UserSession(organization_id=1, user_id=user1.id, token_hash="a" * 64,
                        security_version=1, expires_at=old),
            UserSession(organization_id=1, user_id=user1.id, token_hash="b" * 64,
                        security_version=1, expires_at=future, revoked_at=old),
            UserSession(organization_id=1, user_id=user1.id, token_hash="c" * 64,
                        security_version=1, expires_at=future),
            UserSession(organization_id=2, user_id=user2.id, token_hash="d" * 64,
                        security_version=1, expires_at=old),
        ))
        policy = RetentionPolicy(
            organization_id=1, category="user_sessions", retention_days=90, active=False,
        )
        db.session.add(policy)
        db.session.commit()
        assert count_candidates(policy, now) == 2
        assert apply_policy(policy, now) == 0
        policy.active = True
        policy.approved_at = now
        db.session.commit()
        assert apply_policy(policy, now) == 2
        assert count_candidates(policy, now) == 0
        remaining = {row.token_hash for row in UserSession.query.execution_options(
            include_all_tenants=True
        ).all()}
        assert remaining == {"c" * 64, "d" * 64}
        event = EventoLog.query.filter_by(modulo="privacy", tipo="retencao").one()
        assert event.organization_id == 1


def test_retencao_global_exige_aprovacao_e_preserva_sessoes_das_empresas():
    app = create_app("development")
    app.config.update(TESTING=True)
    with app.app_context():
        db.drop_all()
        db.create_all()
        db.session.add(Organization(id=1, nome="Assistência", slug="assistencia"))
        admin = Usuario(organization_id=None, nome="Plataforma", email="plataforma@example.test",
                        nivel="admin", is_platform_admin=True)
        tenant = Usuario(organization_id=1, nome="Empresa", email="empresa@example.test", nivel="admin")
        admin.set_senha("Senha!123")
        tenant.set_senha("Senha!123")
        db.session.add_all((admin, tenant))
        db.session.flush()
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=120)
        future = now + timedelta(days=1)
        db.session.add_all((
            UserSession(user_id=admin.id, organization_id=None, token_hash="e" * 64,
                        security_version=1, expires_at=old),
            UserSession(user_id=admin.id, organization_id=None, token_hash="f" * 64,
                        security_version=1, expires_at=future, revoked_at=old),
            UserSession(user_id=admin.id, organization_id=None, token_hash="g" * 64,
                        security_version=1, expires_at=future),
            UserSession(user_id=tenant.id, organization_id=1, token_hash="h" * 64,
                        security_version=1, expires_at=old),
        ))
        policy = PlatformRetentionPolicy(category="user_sessions", retention_days=90, active=True)
        db.session.add(policy)
        db.session.commit()
        assert count_platform_candidates(policy, now) == 2
        assert apply_platform_policy(policy, now) == 0
        policy.approved_by_id = admin.id
        policy.approved_at = now
        policy.approval_reference = "PRIV-2026-001"
        db.session.commit()
        assert apply_active_policies() == 2
        assert count_platform_candidates(policy, now) == 0
        remaining = {row.token_hash for row in UserSession.query.execution_options(
            include_all_tenants=True
        ).all()}
        assert remaining == {"g" * 64, "h" * 64}
        event = EventoLog.query.filter_by(modulo="privacy", tipo="retencao").one()
        assert event.organization_id is None
