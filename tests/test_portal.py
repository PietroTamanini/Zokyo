import hashlib

from app import create_app
from app.extensions import db
from app.models import Cliente, OrdemServico, Organization, OSHistorico, PortalToken, Transacao, Usuario
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
    assert "Baixar comprovante" in body

    pdf = app.test_client().get(f"/portal/os/{raw}/pdf")
    assert pdf.status_code == 200
    assert pdf.mimetype == "application/pdf"
    assert pdf.data.startswith(b"%PDF")
    assert b"SERIE-SECRETA" not in pdf.data
    assert b"DIAGNOSTICO INTERNO" not in pdf.data


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


def test_api_client_usa_token_portal_e_isola_cliente():
    app = make_app()
    user_id, os_id = seed(app)
    with app.app_context():
        user = db.session.get(Usuario, user_id)
        service_order = db.session.get(OrdemServico, os_id)
        raw = criar_link_portal(service_order, user, "tracking")
        other_client = Cliente(nome="Outro Cliente", telefone="4711111111", organization_id=1)
        db.session.add(other_client)
        db.session.flush()
        other_order = OrdemServico(
            organization_id=1,
            cliente_id=other_client.id,
            usuario_id=user.id,
            tipo_aparelho="Celular",
            defeito_alegado="Tela quebrada",
            status="recepcao",
        )
        charge = Transacao(
            organization_id=1,
            os_id=service_order.id,
            tipo="receita",
            categoria="servico",
            descricao="OS portal",
            valor=250,
            status="pendente",
        )
        db.session.add_all([other_order, charge])
        db.session.commit()
        other_order_id = other_order.id

    client = app.test_client()
    assert client.get("/api/v1/client").status_code == 401
    auth = client.post("/api/v1/client/auth", json={"portal_token": raw})
    assert auth.status_code == 200
    assert auth.json["cliente"]["nome"] == "Cliente Sigiloso"

    headers = {"Authorization": f"Bearer {raw}"}
    orders = client.get("/api/v1/client/os", headers=headers)
    assert orders.status_code == 200
    assert [item["id"] for item in orders.json["result"]["Os"]] == [os_id]
    assert client.get(f"/api/v1/client/os/{other_order_id}", headers=headers).status_code == 404

    compras = client.get("/api/v1/client/compras", headers=headers)
    assert compras.status_code == 200
    assert compras.json["result"]["Compras"][0]["descricao"] == "OS portal"
    cobrancas = client.get("/api/v1/client/cobrancas", headers=headers)
    assert cobrancas.status_code == 200
    assert cobrancas.json["result"][0]["status"] == "pendente"

    created = client.post("/api/v1/client/os", headers=headers, json={
        "descricaoProduto": "Tablet",
        "defeito": "Nao carrega",
    })
    assert created.status_code == 201
    assert created.json["result"]["equipamento"] == "Tablet"
