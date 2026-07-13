import hashlib
import hmac
import json

from app import create_app
from app.extensions import db
from app.models import BillingEvent, Organization, OrganizationSubscription, Plan, Usuario
from app.services.billing import assert_limit, assert_write_allowed


def make_app():
    app = create_app("development")
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    with app.app_context():
        db.create_all()
        organization = Organization(id=1, nome="Billing", slug="billing")
        admin = Usuario(nome="Global", email="global@example.com", nivel="admin", ativo=True, organization_id=1)
        admin.set_senha("Senha!123")
        plan = Plan(code="sandbox-basic", nome="Sandbox Basic", limites={"max_users": 1})
        db.session.add_all([organization, admin, plan])
        db.session.flush()
        db.session.add(OrganizationSubscription(
            organization_id=1, plan_id=plan.id, provider="sandbox", status="trialing",
        ))
        db.session.commit()
        return app, admin.id


def sign(payload, secret):
    return "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def test_webhook_sandbox_exige_hmac_e_e_idempotente(monkeypatch):
    app, _admin_id = make_app()
    monkeypatch.setenv("BILLING_SANDBOX_SECRET", "sandbox-secret")
    raw = json.dumps({
        "event_id": "evt-1", "type": "subscription.activated", "organization_id": 1,
    }, separators=(",", ":")).encode()
    client = app.test_client()
    assert client.post("/platform/webhooks/sandbox", data=raw, content_type="application/json").status_code == 400
    headers = {"X-Zokyo-Signature": sign(raw, "sandbox-secret")}
    first = client.post("/platform/webhooks/sandbox", data=raw, content_type="application/json", headers=headers)
    second = client.post("/platform/webhooks/sandbox", data=raw, content_type="application/json", headers=headers)
    assert first.json["processed"] is True
    assert second.json["processed"] is False
    with app.app_context():
        assert BillingEvent.query.count() == 1
        assert OrganizationSubscription.query.one().status == "active"


def test_limites_e_inadimplencia_sao_aplicados():
    app, _admin_id = make_app()
    with app.app_context():
        try:
            assert_limit(1, "max_users", 1)
        except PermissionError as exc:
            assert "max_users" in str(exc)
        else:
            raise AssertionError("Limite do plano nao foi aplicado")
        subscription = OrganizationSubscription.query.one()
        subscription.status = "past_due"
        db.session.commit()
        try:
            assert_write_allowed(1)
        except PermissionError:
            pass
        else:
            raise AssertionError("Inadimplencia nao bloqueou nova operacao")


def test_painel_global_usa_allowlist_de_email(monkeypatch):
    app, admin_id = make_app()
    client = app.test_client()
    with client.session_transaction() as session:
        session["usuario_id"] = admin_id
        session["nivel"] = "admin"
        session["_last_active"] = 9999999999
    monkeypatch.delenv("PLATFORM_ADMIN_EMAILS", raising=False)
    assert client.get("/platform").status_code == 403
    monkeypatch.setenv("PLATFORM_ADMIN_EMAILS", "global@example.com")
    assert client.get("/platform").status_code == 200
