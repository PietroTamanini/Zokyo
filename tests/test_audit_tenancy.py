from flask import g, session

from app import create_app
from app.extensions import db
from app.models import EventoLog, Organization, Usuario, registrar


def test_registrar_usa_tenant_do_contexto_autenticado():
    app = create_app("development")
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    with app.app_context():
        db.create_all()
        first = Organization(id=1, nome="Primeira", slug="primeira")
        second = Organization(id=2, nome="Segunda", slug="segunda")
        user = Usuario(id=42, organization_id=2, nome="Operador tenant 2", email="audit@test.local", nivel="admin")
        user.set_senha("Senha!123")
        db.session.add_all([first, second, user])
        db.session.commit()

    with app.test_request_context("/acao", method="POST"):
        g.organization_id = 2
        session["usuario_id"] = 42
        session["usuario_nome"] = "Operador tenant 2"
        registrar("edicao", "os", "OS atualizada")
        db.session.commit()

        event = EventoLog.query.execution_options(include_all_tenants=True).one()
        assert event.organization_id == 2
        assert event.usuario_id == 42
        assert event.usuario_nome == "Operador tenant 2"


def test_registrar_respeita_tenant_explicito_fora_de_requisicao():
    app = create_app("development")
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    with app.app_context():
        db.create_all()
        db.session.add_all([
            Organization(id=1, nome="Primeira", slug="primeira-explicita"),
            Organization(id=3, nome="Terceira", slug="terceira"),
        ])
        db.session.commit()

        registrar("sistema", "jobs", "Rotina concluida", organization_id=3)
        db.session.commit()

        event = EventoLog.query.execution_options(include_all_tenants=True).one()
        assert event.organization_id == 3
        assert event.usuario_nome == "Sistema"
