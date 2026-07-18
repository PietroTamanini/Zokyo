import os
from datetime import datetime

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from app import create_app
from app.extensions import db
from app.models import (
    Cliente,
    Fornecedor,
    InventoryMovement,
    OrdemServico,
    Organization,
    StockReservation,
    Transacao,
    Usuario,
)


def make_client():
    app = create_app("development")
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    with app.app_context():
        db.create_all()
        organization = Organization(id=1, nome="Teste", slug="test")
        admin = Usuario(organization_id=1, nome="Admin", email="admin@api.test", nivel="admin", ativo=True)
        admin.set_senha("Senha!123")
        db.session.add_all([organization, admin])
        db.session.commit()
        admin_id = admin.id
    client = app.test_client()
    with client.session_transaction() as session:
        session["usuario_id"] = admin_id
        session["nivel"] = "admin"
        session["perfil"] = "admin"
        session["usuario_nome"] = "Admin"
        session["_last_active"] = 9999999999
        session["_csrf_token"] = "csrf-api"
    return app, client


def request_json(client, method, path, payload=None):
    return client.open(
        path,
        method=method,
        json=payload,
        headers={"X-CSRFToken": "csrf-api"},
    )


def test_convite_publico_invalido_nao_e_redirecionado_pelo_primeiro_acesso():
    app = create_app("development")
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    with app.app_context():
        db.drop_all()
        db.create_all()

    response = app.test_client().get("/convite/token-invalido")

    assert response.status_code == 410


def test_fluxo_crud_central_integrado():
    _app, client = make_client()
    response = request_json(client, "POST", "/api/clientes", {
        "nome": "Cliente Integrado", "telefone": "47999999999", "uf": "SC",
    })
    assert response.status_code == 201, response.get_data(as_text=True)
    cliente_id = response.get_json()["id"]

    response = request_json(client, "POST", "/api/fornecedores", {"nome": "Fornecedor Integrado"})
    assert response.status_code == 201
    fornecedor_id = response.get_json()["id"]

    response = request_json(client, "POST", "/api/pecas", {
        "nome": "Fonte Integrada", "quantidade": 3, "custo": 100, "margem": 20,
        "fornecedor_id": fornecedor_id,
    })
    assert response.status_code == 201
    peca_id = response.get_json()["id"]

    response = request_json(client, "POST", "/api/os", {
        "cliente_id": cliente_id, "tipo_aparelho": "Notebook", "defeito_alegado": "Nao liga",
        "valor_servico": 150, "prio": "urgente",
    })
    assert response.status_code == 201, response.get_data(as_text=True)
    os_id = response.get_json()["id"]

    reservation = request_json(client, "POST", f"/api/os/{os_id}/reservas", {
        "peca_id": peca_id, "quantidade": 1,
    })
    assert reservation.status_code == 201

    assert request_json(client, "POST", f"/api/os/{os_id}/pecas", {
        "peca_id": peca_id, "quantidade": 1, "valor_unitario": 120,
    }).status_code == 200

    response = request_json(client, "POST", "/api/transacoes", {
        "os_id": os_id, "tipo": "receita", "valor": 270, "status": "pago",
        "descricao": "Pagamento integrado",
    })
    assert response.status_code == 201
    now = datetime.now()
    resumo = client.get(f"/api/transacoes/resumo?mes={now.month}&ano={now.year}")
    assert resumo.status_code == 200
    assert resumo.get_json()["receitas"] == 270

    os_payload = client.get(f"/api/os/{os_id}").get_json()
    assert os_payload["valor_pecas"] == 120
    assert os_payload["pecas"][0]["quantidade"] == 1

    response = request_json(client, "DELETE", f"/api/clientes/{cliente_id}")
    assert response.status_code == 200
    with _app.app_context():
        assert db.session.get(Cliente, cliente_id).ativo is False
        assert db.session.get(OrdemServico, os_id) is not None
        assert Transacao.query.filter_by(os_id=os_id).count() == 1
        assert InventoryMovement.query.filter_by(part_id=peca_id).count() == 2
        assert StockReservation.query.filter_by(part_id=peca_id, status="consumed").count() == 1


def test_ajuste_de_estoque_exige_justificativa_e_gera_livro():
    app, client = make_client()
    response = request_json(client, "POST", "/api/pecas", {"nome": "Memoria", "quantidade": 2})
    part_id = response.get_json()["id"]
    assert request_json(client, "POST", f"/api/pecas/{part_id}/ajuste-estoque", {"delta": 1}).status_code == 400
    response = request_json(client, "POST", f"/api/pecas/{part_id}/ajuste-estoque", {
        "delta": 3, "justificativa": "Contagem de inventario",
    })
    assert response.status_code == 200
    assert response.get_json()["quantidade"] == 5
    with app.app_context():
        movement = InventoryMovement.query.filter_by(part_id=part_id, movement_type="adjustment").one()
        assert (movement.quantity_before, movement.quantity_after) == (2, 5)


def test_entrada_por_lote_calcula_custo_medio_e_registra_validade():
    app, client = make_client()
    part = request_json(client, "POST", "/api/pecas", {
        "nome": "SSD", "quantidade": 10, "custo": 10,
    }).get_json()
    response = request_json(client, "POST", f"/api/pecas/{part['id']}/lotes", {
        "codigo": "LOTE-2026-01", "quantidade": 10, "custo_unitario": 20,
        "localizacao": "A-01", "validade": "2027-12-31", "justificativa": "Compra fornecedor",
    })
    assert response.status_code == 201
    payload = response.get_json()
    assert payload["peca"]["quantidade"] == 20
    assert payload["peca"]["custo"] == 15
    assert payload["lote"]["codigo"] == "LOTE-2026-01"
    assert payload["lote"]["validade"].startswith("2027-12-31")
    with app.app_context():
        movement = InventoryMovement.query.filter_by(movement_type="lot_receipt").one()
        assert movement.lot_id == payload["lote"]["id"]


def test_financeiro_parcela_concilia_calcula_dre_e_exporta():
    app, client = make_client()
    response = request_json(client, "POST", "/api/transacoes", {
        "tipo": "receita", "valor": 100, "status": "pago", "descricao": "Contrato",
        "parcelas": 3, "recorrencia": "mensal", "comissao_percentual": 10,
        "data_pagamento": datetime.now().isoformat(),
    })
    assert response.status_code == 201
    transactions = response.get_json()["transactions"]
    assert len(transactions) == 3
    assert round(sum(item["valor"] for item in transactions), 2) == 100
    first_id = transactions[0]["id"]
    reconciled = request_json(client, "POST", f"/api/transacoes/{first_id}/conciliar", {
        "referencia": "extrato-001",
    })
    assert reconciled.status_code == 200
    assert reconciled.get_json()["conciliacao_ref"] == "extrato-001"
    dre = client.get("/api/transacoes/dre").get_json()
    assert dre["receita_bruta"] == 100
    assert dre["comissoes"] == 10
    export = client.get("/api/transacoes/contabilidade.csv")
    assert export.status_code == 200
    assert b"extrato-001" in export.data


def test_checklist_versionado_snapshot_e_aceite_da_os():
    app, client = make_client()
    template = request_json(client, "POST", "/api/checklists", {
        "categoria": "Notebook", "itens": ["Carcaca sem avarias", "Fonte recebida"],
    })
    assert template.status_code == 201
    customer = request_json(client, "POST", "/api/clientes", {"nome": "Cliente Checklist"}).get_json()
    order = request_json(client, "POST", "/api/os", {
        "cliente_id": customer["id"], "tipo_aparelho": "Notebook", "defeito_alegado": "Nao liga",
    }).get_json()
    assert order["checklist_snapshot"] == ["Carcaca sem avarias", "Fonte recebida"]
    result = request_json(client, "PUT", f"/api/os/{order['id']}/checklist", {
        "respostas": {"Carcaca sem avarias": True, "Fonte recebida": False},
    })
    assert result.status_code == 200
    accepted = request_json(client, "POST", f"/api/os/{order['id']}/autorizacao", {
        "aceito": True, "aceito_por": "Cliente Checklist",
    })
    assert accepted.status_code == 200
    assert accepted.get_json()["authorization_accepted_at"]
    with app.app_context():
        stored = db.session.get(OrdemServico, order["id"])
        assert stored.checklist_answers["Carcaca sem avarias"] is True


def test_template_de_mensagem_e_versionado_por_evento_e_canal():
    _app, client = make_client()
    first = request_json(client, "POST", "/api/message-templates", {
        "event_type": "os_status_pronto", "channel": "email",
        "subject": "OS {{os_id}} pronta", "body": "Ola {{cliente}}, seu {{equipamento}} esta pronto.",
    })
    second = request_json(client, "POST", "/api/message-templates", {
        "event_type": "os_status_pronto", "channel": "email",
        "subject": "Atualizacao {{os_id}}", "body": "Novo texto para {{cliente}}.",
    })
    assert first.status_code == second.status_code == 201
    assert first.get_json()["version"] == 1
    assert second.get_json()["version"] == 2
    templates = client.get("/api/message-templates").get_json()
    assert sum(item["active"] for item in templates) == 1


def test_convite_e_uso_unico_com_token_armazenado_por_hash():
    app, client = make_client()
    response = request_json(client, "POST", "/api/usuarios/convites", {
        "email": "convidado@example.com", "nivel": "operacional",
    })
    assert response.status_code == 201
    link = response.get_json()["link"]
    token = link.rsplit("/", 1)[-1]
    with app.app_context():
        from app.models import UserInvite
        stored_invite = UserInvite.query.one()
        assert stored_invite.token_hash != token
        assert len(stored_invite.token_hash) == 64
    invited = app.test_client()
    with invited.session_transaction() as current:
        current["_csrf_token"] = "invite-csrf"
    accepted = invited.post(f"/convite/{token}", data={
        "nome": "Usuario Convidado", "senha": "Senha!123", "_csrf_token": "invite-csrf",
    })
    assert accepted.status_code == 302
    with app.app_context():
        user = Usuario.query.filter_by(email="convidado@example.com").one()
        assert user.organization_id == 1
        assert user.nivel == "operacional"
    assert invited.get(f"/convite/{token}").status_code == 410


def test_branding_por_organizacao_valida_cores():
    app, client = make_client()
    response = client.post("/configuracoes/salvar", data={
        "_csrf_token": "csrf-api", "nome_empresa": "Marca Tenant",
        "primary_color": "#123456", "accent_color": "#abcdef",
    })
    assert response.status_code == 302
    with app.app_context():
        from app.models import Configuracao
        config = Configuracao.query.one()
        assert config.primary_color == "#123456"
        assert config.accent_color == "#abcdef"


def test_chaves_estrangeiras_de_outro_tenant_sao_rejeitadas():
    app, client = make_client()
    with app.app_context():
        other = Organization(id=2, nome="Outro", slug="outro")
        db.session.add(other)
        db.session.flush()
        supplier = Fornecedor(organization_id=2, nome="Fornecedor externo")
        db.session.add(supplier)
        db.session.commit()
        supplier_id = supplier.id
    response = request_json(client, "POST", "/api/pecas", {
        "nome": "Peca invalida", "quantidade": 1, "custo": 1,
        "margem": 1, "fornecedor_id": supplier_id,
    })
    assert response.status_code == 400


def test_perfil_consulta_nao_executa_mutacoes_operacionais():
    app, client = make_client()
    with app.app_context():
        user = Usuario.query.filter_by(email="admin@api.test").one()
        user.nivel = "consulta"
        db.session.commit()
    with client.session_transaction() as session:
        session["nivel"] = "consulta"
        session["perfil"] = "consulta"
    assert request_json(client, "POST", "/api/clientes", {"nome": "Bloqueado"}).status_code == 403
    assert request_json(client, "POST", "/api/os", {"cliente_id": 1}).status_code == 403
    assert request_json(client, "POST", "/api/whatsapp/teste", {"numero": "47999999999"}).status_code == 403
