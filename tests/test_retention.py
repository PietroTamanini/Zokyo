from datetime import datetime, timedelta, timezone

from app import create_app
from app.extensions import db
from app.models import Notification, Organization, RetentionPolicy
from app.services.retention import apply_policy, count_candidates


def test_retencao_remove_apenas_notificacoes_terminais_antigas_e_aprovadas():
    app = create_app("development")
    app.config.update(TESTING=True)
    with app.app_context():
        db.drop_all()
        db.create_all()
        db.session.add(Organization(id=1, nome="Teste", slug="teste"))
        old = datetime.now(timezone.utc) - timedelta(days=100)
        db.session.add_all([
            Notification(organization_id=1, recipient="1", event_type="test", idempotency_key="sent", payload={}, status="sent", created_at=old),
            Notification(organization_id=1, recipient="1", event_type="test", idempotency_key="pending", payload={}, status="pending", created_at=old),
        ])
        policy = RetentionPolicy(
            organization_id=1, category="notifications", retention_days=90,
            active=True, approved_at=datetime.now(timezone.utc),
        )
        db.session.add(policy)
        db.session.commit()
        assert count_candidates(policy) == 1
        assert apply_policy(policy) == 1
        assert Notification.query.count() == 1
        assert Notification.query.one().status == "pending"


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
