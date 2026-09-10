import os

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from flask import g

from app import create_app
from app.extensions import db
from app.models import Configuracao, Organization, Peca


def test_escopo_central_isola_configuracao_e_estoque():
    app = create_app("development")
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    with app.app_context():
        db.create_all()
        db.session.add_all([
            Organization(id=1, nome="Um", slug="um"),
            Organization(id=2, nome="Dois", slug="dois"),
            Configuracao(organization_id=1, nome_empresa="Empresa Um"),
            Configuracao(organization_id=2, nome_empresa="Empresa Dois"),
            Peca(organization_id=1, nome="Peca Um"),
            Peca(organization_id=2, nome="Peca Dois"),
        ])
        db.session.commit()

        with app.test_request_context("/"):
            g.organization_id = 2
            assert Configuracao.get().nome_empresa == "Empresa Dois"
            assert [item.nome for item in Peca.query.all()] == ["Peca Dois"]
            nova = Peca(nome="Nova no tenant")
            db.session.add(nova)
            db.session.flush()
            assert nova.organization_id == 2


def test_escopo_central_bloqueia_mutacao_de_outro_tenant():
    app = create_app("development")
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    with app.app_context():
        db.create_all()
        db.session.add_all([
            Organization(id=1, nome="Um", slug="um-mutacao"),
            Organization(id=2, nome="Dois", slug="dois-mutacao"),
            Peca(organization_id=1, nome="Peca protegida"),
        ])
        db.session.commit()

        with app.test_request_context("/"):
            g.organization_id = 2
            foreign_part = (
                Peca.query.execution_options(include_all_tenants=True)
                .filter_by(nome="Peca protegida")
                .one()
            )
            foreign_part.nome = "Tentativa indevida"
            with pytest.raises(ValueError, match="Operacao entre tenants bloqueada"):
                db.session.flush()
            db.session.rollback()
