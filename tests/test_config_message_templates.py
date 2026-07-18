import os

import pytest
from cryptography.fernet import InvalidToken

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from app import create_app
from app.extensions import db
from app.models import Configuracao, MessageTemplate, Organization
from app.models import configuracao as configuracao_model
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


def test_configuracao_criptografa_segredos_e_to_dict_oculta_valores():
    app = _make_app()
    with app.app_context():
        cfg = Configuracao(organization_id=1, nome_empresa="Teste")
        cfg.set_evolution_api_url("https://api.example.com")
        cfg.set_evolution_api_key("chave-secreta")
        assert cfg._evolution_api_url_enc != "https://api.example.com"
        assert cfg._evolution_api_key_enc != "chave-secreta"
        assert cfg.get_evolution_api_url() == "https://api.example.com"
        assert cfg.get_evolution_api_key() == "chave-secreta"
        cfg.set_evolution_api_url(None)
        cfg.set_evolution_api_key(None)
        assert cfg.get_evolution_api_url() is None
        assert cfg.get_evolution_api_key() is None
        cfg._evolution_api_url_enc = "token"
        data = cfg.to_dict()
        assert data["evolution_api_url_set"] is True
        assert "evolution_api_url" not in data


def test_configuracao_falha_explicitamente_sem_fernet(monkeypatch):
    monkeypatch.setattr(configuracao_model, "_get_fernet", lambda: None)
    assert configuracao_model._encrypt("") == ""
    with pytest.raises(RuntimeError, match="Fernet indisponivel|Fernet indispon"):
        configuracao_model._encrypt("segredo")
    assert configuracao_model._decrypt("token") is None


def test_configuracao_get_fernet_sem_secret_ou_com_erro(monkeypatch):
    app = _make_app()
    with app.app_context():
        app.config["SECRET_KEY"] = ""
        assert configuracao_model._get_fernet() is None

        class BrokenKdf:
            def __init__(self, *args, **kwargs):
                raise RuntimeError("kdf falhou")

        monkeypatch.setattr(configuracao_model, "PBKDF2HMAC", BrokenKdf)
        app.config["SECRET_KEY"] = "secret"
        assert configuracao_model._get_fernet() is None


def test_configuracao_trata_erros_de_criptografia(monkeypatch):
    class BrokenEncrypt:
        def encrypt(self, _value):
            raise RuntimeError("falhou")

    class InvalidDecrypt:
        def decrypt(self, _value):
            raise InvalidToken()

    class BrokenDecrypt:
        def decrypt(self, _value):
            raise RuntimeError("falhou")

    monkeypatch.setattr(configuracao_model, "_get_fernet", lambda: BrokenEncrypt())
    with pytest.raises(RuntimeError, match="Erro ao criptografar segredo"):
        configuracao_model._encrypt("segredo")

    monkeypatch.setattr(configuracao_model, "_get_fernet", lambda: InvalidDecrypt())
    assert configuracao_model._decrypt("token") is None
    monkeypatch.setattr(configuracao_model, "_get_fernet", lambda: BrokenDecrypt())
    assert configuracao_model._decrypt("token") is None


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
