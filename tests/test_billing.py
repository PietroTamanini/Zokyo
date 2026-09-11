import hashlib
import hmac
import json

from app import create_app
from app.extensions import db
from app.models import BillingEvent, Organization, OrganizationSubscription, Plan, Usuario
from app.services.billing import assert_limit, assert_write_allowed, ensure_trial_subscription, process_asaas_event
from app.services.tenant_provisioning import provision_tenant


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


def test_painel_global_aceita_platform_admin_sem_allowlist(monkeypatch):
    app, admin_id = make_app()
    with app.app_context():
        admin = db.session.get(Usuario, admin_id)
        admin.is_platform_admin = True
        admin.organization_id = None
        db.session.commit()
    client = app.test_client()
    with client.session_transaction() as session:
        session["usuario_id"] = admin_id
        session["nivel"] = "admin"
        session["_last_active"] = 9999999999
    monkeypatch.delenv("PLATFORM_ADMIN_EMAILS", raising=False)
    assert client.get("/platform").status_code == 200
    assert client.get("/platform/subscription").status_code == 404


def test_platform_cria_empresa_dono_subdominio_e_trial(monkeypatch):
    app, admin_id = make_app()
    monkeypatch.setenv("PLATFORM_ADMIN_EMAILS", "global@example.com")
    client = app.test_client()
    with client.session_transaction() as session:
        session["usuario_id"] = admin_id
        session["nivel"] = "admin"
        session["_last_active"] = 9999999999
        session["_csrf_token"] = "csrf"
    response = client.post("/platform/organizations", data={
        "_csrf_token": "csrf",
        "name": "Loja A",
        "slug": "loja-a",
        "owner_name": "Dono Loja",
        "owner_email": "dono@loja.test",
        "owner_password": "Senha!123",
        "trial_days": "10",
        "active": "on",
    })
    assert response.status_code == 302
    with app.app_context():
        organization = Organization.query.execution_options(include_all_tenants=True).filter_by(slug="loja-a").one()
        owner = Usuario.query.execution_options(include_all_tenants=True).filter_by(email="dono@loja.test").one()
        subscription = OrganizationSubscription.query.filter_by(organization_id=organization.id).one()
        assert organization.custom_domain == "loja-a.tamanini.dev.br"
        assert organization.dns_status == "manual"
        assert owner.organization_id == organization.id
        assert owner.nivel == "admin"
        assert subscription.status == "trialing"


def test_resolve_tenant_por_subdominio_e_bloqueio_central():
    app, _admin_id = make_app()
    with app.app_context():
        organization, owner = provision_tenant(
            name="Tenant Host",
            slug="tenant-host",
            owner_name="Dono Host",
            owner_email="host-owner@test.local",
            owner_password="Senha!123",
            provision_dns=False,
        )
        subscription = OrganizationSubscription.query.filter_by(organization_id=organization.id).one()
        subscription.status = "suspended"
        db.session.commit()
        owner_id = owner.id

    client = app.test_client()
    response = client.get("/", headers={"Host": "tenant-host.tamanini.dev.br"})
    assert response.status_code in {200, 302}
    with client.session_transaction() as session:
        session["usuario_id"] = owner_id
        session["nivel"] = "admin"
        session["_last_active"] = 9999999999
        session["_csrf_token"] = "csrf"
    blocked = client.post(
        "/api/usuarios",
        json={"nome": "Bloqueado", "email": "blocked@test.local", "senha": "Senha!123", "nivel": "consulta"},
        headers={"X-CSRFToken": "csrf"},
    )
    assert blocked.status_code == 403
    assert "Assinatura" in blocked.get_json()["erro"]


def test_trial_automatico_e_webhook_asaas_idempotente(monkeypatch):
    app, _admin_id = make_app()
    with app.app_context():
        current = OrganizationSubscription.query.one()
        db.session.delete(current)
        db.session.commit()
        trial = ensure_trial_subscription(1)
        trial.provider = "asaas"
        trial.external_id = "sub_123"
        db.session.commit()
        assert trial.status == "trialing"
        assert trial.trial_fim is not None
        payload = {"id": "evt_asaas_1", "event": "PAYMENT_RECEIVED", "payment": {"subscription": "sub_123"}}
        event, processed = process_asaas_event(payload)
        db.session.commit()
        assert processed is True
        assert event.provider == "asaas"
        assert OrganizationSubscription.query.one().status == "active"
        _event, processed_again = process_asaas_event(payload)
        assert processed_again is False

    monkeypatch.setenv("ASAAS_WEBHOOK_TOKEN", "a" * 40)
    client = app.test_client()
    assert client.post("/platform/webhooks/asaas", json={}).status_code == 401
    duplicate = client.post(
        "/platform/webhooks/asaas", json=payload, headers={"asaas-access-token": "a" * 40},
    )
    assert duplicate.status_code == 200
    assert duplicate.json["processed"] is False
