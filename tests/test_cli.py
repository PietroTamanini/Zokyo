import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from app import create_app
from app.extensions import db
from app.models import Configuracao, Organization, Plan, Usuario


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
    with app.app_context():
        organization = Organization.query.filter_by(slug="empresa-nova").one()
        assert Usuario.query.filter_by(organization_id=organization.id, nivel="admin").count() == 1
        assert Configuracao.query.filter_by(organization_id=organization.id).count() == 1


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
