import hashlib

from app import create_app
from app.extensions import db
from app.models import Cliente, OrdemServico, Organization, OSHistorico, PortalToken, Usuario
from app.services.portal import criar_link_portal


def make_app():
    app = create_app("development")
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    with app.app_context():
        db.create_all()
    return app


def seed(app):
    with app.app_context():
        organization = Organization(id=1, nome="Portal Teste", slug="portal-teste")
        user = Usuario(nome="Admin", email="portal-admin@example.com", nivel="admin", ativo=True, organization_id=1)
        user.set_senha("Senha!123")
        client = Cliente(nome="Cliente Sigiloso", telefone="47999999999", organization_id=1)
        db.session.add_all([organization, user, client])
        db.session.flush()
        service_order = OrdemServico(
            organization_id=1, cliente_id=client.id, usuario_id=user.id,
            tipo_aparelho="Notebook", marca="Dell", modelo="XPS",
            numero_serie="SERIE-SECRETA", defeito_alegado="Nao liga",
            defeito_encontrado="DIAGNOSTICO INTERNO", valor_servico=200, valor_pecas=50,
            status="aguardando_aprovacao",
        )
        db.session.add(service_order)
        db.session.commit()
        return user.id, service_order.id


def test_portal_armazena_so_hash_e_nao_expoe_dados_internos():
    app = make_app()
    user_id, os_id = seed(app)
    with app.app_context():
        raw = criar_link_portal(db.session.get(OrdemServico, os_id), db.session.get(Usuario, user_id), "budget")
        db.session.commit()
        stored = PortalToken.query.one()
        assert stored.token_hash == hashlib.sha256(raw.encode()).hexdigest()
        assert raw not in stored.token_hash

    response = app.test_client().get(f"/portal/os/{raw}")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store, private"
    assert "R$ 250,00" in body
    assert "SERIE-SECRETA" not in body
    assert "DIAGNOSTICO INTERNO" not in body
    assert "Cliente Sigiloso" not in body


def test_aprovacao_e_idempotente_e_registra_transicao():
    app = make_app()
    user_id, os_id = seed(app)
    with app.app_context():
        raw = criar_link_portal(db.session.get(OrdemServico, os_id), db.session.get(Usuario, user_id), "budget")
        db.session.commit()

    client = app.test_client()
    with client.session_transaction() as session:
        session["_csrf_token"] = "portal-csrf"
    first = client.post(f"/portal/os/{raw}", data={"decisao": "approved", "_csrf_token": "portal-csrf"})
    assert first.status_code == 302
    second = client.post(f"/portal/os/{raw}", data={"decisao": "rejected", "_csrf_token": "portal-csrf"})
    assert second.status_code == 409
    with app.app_context():
        service_order = db.session.get(OrdemServico, os_id)
        token = PortalToken.query.one()
        assert service_order.orcamento_status == "approved"
        assert service_order.status == "em_reparo"
        assert token.usado_em is not None
        assert OSHistorico.query.filter_by(os_id=os_id, status_novo="em_reparo").count() == 1


def test_novo_link_revoga_o_anterior():
    app = make_app()
    user_id, os_id = seed(app)
    with app.app_context():
        user = db.session.get(Usuario, user_id)
        service_order = db.session.get(OrdemServico, os_id)
        old = criar_link_portal(service_order, user, "tracking")
        db.session.commit()
        new = criar_link_portal(service_order, user, "tracking")
        db.session.commit()

    client = app.test_client()
    assert client.get(f"/portal/os/{old}").status_code == 404
    assert client.get(f"/portal/os/{new}").status_code == 200
