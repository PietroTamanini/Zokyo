import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from app import create_app
from app.extensions import db
from app.models import Configuracao, MessageTemplate, Organization
from app.services.message_templates import active_template, render_template, render_text


def _make_app():
    app = create_app("development")
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:", SECRET_KEY="config-secret")
    with app.app_context():
        db.drop_all()
        db.create_all()
        db.session.add(Organization(id=1, nome="Teste", slug="teste"))
        db.session.commit()
    return app


def test_configuracao_to_dict_nao_expoe_campos_de_gateway_legado():
    app = _make_app()
    with app.app_context():
        cfg = Configuracao(organization_id=1, nome_empresa="Teste")
        data = cfg.to_dict()
        assert data["nome_empresa"] == "Teste"
        assert "evolution_api_url" not in data
        assert "evolution_api_key" not in data
        assert "evolution_instance" not in data
        assert "wpp_server_url" not in data


def test_configuracao_get_cria_registro_padrao():
    app = _make_app()
    with app.app_context():
        cfg = Configuracao.get()
        assert cfg.id is not None
        assert Configuracao.query.count() == 1


def test_templates_de_mensagem_renderizam_variaveis_permitidas():
    assert render_text("Ola {{ cliente }} {{ senha }} {{os_id}}", {"cliente": "Ana", "os_id": "0001"}) == "Ola Ana  0001"

    app = _make_app()
    with app.app_context():
        assert render_template("evento", "email", {}, default_subject="S", default_body="B") == ("S", "B")
        db.session.add_all(
            [
                MessageTemplate(
                    organization_id=1,
                    event_type="os_status",
                    channel="email",
                    version=1,
                    subject="Antigo {{cliente}}",
                    body="Body antigo",
                    active=True,
                ),
                MessageTemplate(
                    organization_id=1,
                    event_type="os_status",
                    channel="email",
                    version=2,
                    subject="Atual {{cliente}}",
                    body="OS {{os_id}} {{status}}",
                    active=True,
                ),
            ]
        )
        db.session.commit()
        assert active_template("os_status", "email").version == 2
        assert render_template("os_status", "email", {"cliente": "Ana", "os_id": "0002", "status": "Pronto"}) == (
            "Atual Ana",
            "OS 0002 Pronto",
        )
