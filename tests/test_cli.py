import base64
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from app import create_app
from app.extensions import db
from app.models import Configuracao, Organization, Plan, Usuario


def _production_check_env():
    return {
        "FLASK_ENV": "production",
        "SECRET_KEY": "s" * 32,  # pragma: allowlist secret
        "DATABASE_URL": "mysql+pymysql://zokyo:" + "senha" + "@db:3306/zokyo",
        "ENCRYPTION_SALT": base64.b64encode(b"0" * 32).decode("ascii"),
        "BLIND_INDEX_KEY": base64.urlsafe_b64encode(b"2" * 32).decode("ascii"),
        "REQUIRE_ADMIN_2FA": "true",
        "PUBLIC_BASE_URL": "https://zokyo.example.com",
        "METRICS_TOKEN": "m" * 32,
        "BACKUP_ENCRYPTION_KEY": base64.urlsafe_b64encode(b"1" * 32).decode("ascii"),
        "REPORTS_UPLOAD_FOLDER": "/var/lib/zokyo/uploads/reports",
        "REDIS_URL": "redis://redis:6379/0",
        "ALERT_EMAIL": "ops@example.com",
        "SMTP_HOST": "smtp.example.com",
        "MAIL_FROM": "no-reply@example.com",
        "WHATSAPP_CLOUD_API_TOKEN": "meta-token",
        "WHATSAPP_CLOUD_PHONE_NUMBER_ID": "1234567890",
        "WHATSAPP_CLOUD_API_VERSION": "v23.0",
    }


def test_production_check_cli_aprova_env_completo():
    app = create_app("development")
    result = app.test_cli_runner().invoke(
        args=["production-check", "--strict-integrations"],
        env=_production_check_env(),
    )

    assert result.exit_code == 0, result.output
    assert "Prontidao de producao aprovada." in result.output


def test_production_check_cli_reprova_env_incompleto():
    app = create_app("development")
    result = app.test_cli_runner().invoke(args=["production-check"], env={"FLASK_ENV": "production"})

    assert result.exit_code != 0
    assert "Prontidao de producao reprovada." in result.output


def test_cli_provisiona_organizacao_admin_e_configuracao():
    app = create_app("development")
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    with app.app_context():
        db.create_all()
    result = app.test_cli_runner().invoke(args=[
        "create-organization", "--name", "Empresa Nova", "--slug", "empresa-nova",
        "--admin-name", "Administrador", "--admin-email", "admin@nova.example",
        "--password", "Senha!Forte123", "--password", "Senha!Forte123",
    ])
    assert result.exit_code == 0, result.output
    assert "empresa-nova.tamanini.dev.br" in result.output
    with app.app_context():
        organization = Organization.query.filter_by(slug="empresa-nova").one()
        assert organization.subdomain == "empresa-nova"
        assert organization.custom_domain == "empresa-nova.tamanini.dev.br"
        assert organization.dns_status == "manual"
        assert Usuario.query.filter_by(organization_id=organization.id, nivel="admin").count() == 1
        assert Configuracao.query.filter_by(organization_id=organization.id).count() == 1


def test_cli_create_organization_rejeita_entradas_invalidas():
    app = create_app("development")
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    with app.app_context():
        db.create_all()
        org = Organization(nome="Existente", slug="existente")
        user = Usuario(nome="Admin", email="admin@existente.example", nivel="admin", ativo=True)
        user.set_senha("Senha!123")
        db.session.add_all([org, user])
        db.session.commit()
    runner = app.test_cli_runner()
    base = [
        "create-organization", "--name", "Empresa", "--admin-name", "Administrador",
        "--password", "Senha!Forte123", "--password", "Senha!Forte123",
    ]
    cases = (
        [*base, "--slug", "!!!", "--admin-email", "novo@example.com"],
        [*base, "--slug", "nova-empresa", "--admin-email", "email-ruim"],
        [*base[:-4], "--password", "fraca", "--password", "fraca", "--slug", "nova-empresa", "--admin-email", "novo@example.com"],
        [*base, "--slug", "existente", "--admin-email", "novo@example.com"],
        [*base, "--slug", "outra-empresa", "--admin-email", "admin@existente.example"],
    )
    for args in cases:
        assert runner.invoke(args=args).exit_code != 0


def test_cli_create_organization_aceita_subdominio_curto():
    app = create_app("development")
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    with app.app_context():
        db.create_all()
    result = app.test_cli_runner().invoke(args=[
        "create-organization", "--name", "A", "--slug", "a",
        "--admin-name", "Administrador", "--admin-email", "admin@a.example",
        "--password", "Senha!Forte123", "--password", "Senha!Forte123",
    ])
    assert result.exit_code == 0, result.output
    with app.app_context():
        assert Organization.query.filter_by(custom_domain="a.tamanini.dev.br").count() == 1


def test_seed_system_e_idempotente():
    app = create_app("development")
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    with app.app_context():
        db.drop_all()
        db.create_all()
    runner = app.test_cli_runner()
    assert runner.invoke(args=["seed-system"]).exit_code == 0
    assert runner.invoke(args=["seed-system"]).exit_code == 0
    with app.app_context():
        assert Plan.query.count() == 3
        assert Plan.query.filter_by(code="professional").one().limites["max_users"] == 10
