from datetime import datetime

from app import create_app
from app.extensions import db
from app.models import Cliente, EventoLog, Fornecedor, OrdemServico, Organization, Peca, Plan, Usuario
from app.services.cplus_firebird_importer import CPlusImportError


def _make_client():
    app = create_app("development")
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SECRET_KEY="route-edge-key",
        SERVER_NAME="example.test",
        WTF_CSRF_ENABLED=False,
    )
    with app.app_context():
        db.create_all()
        organization = Organization(id=1, nome="Rotas", slug="rotas")
        admin = Usuario(organization_id=1, nome="Admin", email="admin@routes.test", nivel="admin", ativo=True)
        admin.set_senha("Senha!123")
        client = Cliente(organization_id=1, nome="Cliente Base", telefone="47999999999")
        supplier = Fornecedor(organization_id=1, nome="Fornecedor Base", ativo=True)
        part = Peca(organization_id=1, nome="Peca Base", codigo="BASE", quantidade=5, custo=10)
        db.session.add_all([organization, admin, client, supplier, part])
        db.session.flush()
        order = OrdemServico(
            organization_id=1,
            cliente_id=client.id,
            usuario_id=admin.id,
            tipo_aparelho="Notebook",
            defeito_alegado="Nao liga",
        )
        db.session.add(order)
        db.session.commit()
        ids = {"admin": admin.id, "client": client.id, "supplier": supplier.id, "part": part.id, "order": order.id}
    browser = app.test_client()
    with browser.session_transaction() as session:
        session["usuario_id"] = ids["admin"]
        session["nivel"] = "admin"
        session["perfil"] = "admin"
        session["usuario_nome"] = "Admin"
        session["_csrf_token"] = "route-csrf"
        session["_last_active"] = 9999999999
    return app, browser, ids


def _json(browser, method, path, payload=None):
    return browser.open(path, method=method, json=payload or {}, headers={"X-CSRFToken": "route-csrf"})


def _form(browser, path, data):
    return browser.post(path, data={**data, "_csrf_token": "route-csrf"}, headers={"X-CSRFToken": "route-csrf"})


def test_rotas_crud_json_cobrem_validacoes_e_bordas(monkeypatch):
    app, browser, ids = _make_client()

    with app.app_context():
        admin = db.session.get(Usuario, ids["admin"])
        db.session.add(EventoLog(usuario_id=admin.id, tipo="criacao", modulo="testes", descricao="Evento edge"))
        db.session.commit()
    assert browser.get("/logs?data_ini=2026-01-01&data_fim=2026-12-31&usuario_id=abc&tipo=criacao&modulo=testes").status_code == 200
    logs = browser.get("/api/logs?data_ini=bad&data_fim=bad&usuario_id=abc&tipo=criacao&modulo=testes&per_page=500")
    assert logs.status_code == 200
    assert logs.get_json()["total"] >= 1

    assert _json(browser, "POST", "/api/clientes", {"nome": "A"}).status_code == 400
    assert _json(browser, "POST", "/api/clientes", {"nome": "Cliente Doc", "cpf": "111"}).status_code == 400
    assert _json(browser, "POST", "/api/clientes", {"nome": "Cliente Tel", "telefone": "123"}).status_code == 400
    assert _json(browser, "POST", "/api/clientes", {"nome": "Cliente Cep", "cep": "123"}).status_code == 400
    import app.routes.clientes as clientes_routes

    monkeypatch.setattr(clientes_routes, "_check_client_limit", lambda: (_ for _ in ()).throw(PermissionError("limite clientes")))
    assert _json(browser, "POST", "/api/clientes", {"nome": "Cliente Limite"}).status_code == 403
    assert _json(browser, "POST", "/api/clientes/quick-create", {"nome": "Cliente Limite Rapido"}).status_code == 403
    monkeypatch.setattr(clientes_routes, "_check_client_limit", lambda: None)
    created = _json(browser, "POST", "/api/clientes", {"nome": "Cliente Doc", "cpf": "52998224725", "telefone": "47988887777"})
    assert created.status_code == 201
    cliente_id = created.get_json()["id"]
    assert browser.get("/api/clientes?q=529.982").status_code == 200
    assert browser.get(f"/api/clientes/{cliente_id}").status_code == 200
    assert _json(browser, "POST", "/api/clientes/quick-create", {"nome": "Cliente Rapido Tel", "telefone": "123"}).status_code == 400
    assert _json(browser, "POST", "/api/clientes/quick-create", {"nome": "Cliente Doc", "cpf": "52998224725"}).status_code == 400
    quick = _json(browser, "POST", "/api/clientes/quick-create", {"nome": "Cliente Rapido", "cnpj": "04252011000110"})
    assert quick.status_code == 201
    assert _json(browser, "POST", "/api/clientes", {"nome": "Cliente CNPJ", "cnpj": "04252011000110"}).status_code == 400
    assert _json(browser, "PUT", f"/api/clientes/{cliente_id}", {}).status_code == 400
    assert _json(browser, "PUT", f"/api/clientes/{cliente_id}", {"uf": "XX"}).status_code == 400
    assert _json(browser, "PUT", f"/api/clientes/{cliente_id}", {"cnpj": "04252011000110"}).status_code == 400
    assert _json(browser, "PUT", f"/api/clientes/{cliente_id}", {"nome": "Cliente Atualizado", "ativo": "false"}).status_code == 200

    assert _json(browser, "POST", "/api/fornecedores", {}).status_code == 400
    assert browser.get("/api/fornecedores").status_code == 200
    assert _json(browser, "POST", "/api/fornecedores", {"nome": "A"}).status_code == 400
    assert _json(browser, "POST", "/api/fornecedores", {"nome": "Fornecedor X", "cnpj": "111"}).status_code == 400
    assert _json(browser, "POST", "/api/fornecedores", {"nome": "Fornecedor X", "telefone": "123"}).status_code == 400
    assert _json(browser, "POST", "/api/fornecedores", {"nome": "Fornecedor X", "cep": "123"}).status_code == 400
    supplier = _json(browser, "POST", "/api/fornecedores", {
        "nome": "Fornecedor X",
        "email": "x@example.com",
        "endereco": "Rua X",
    })
    assert supplier.status_code == 201
    supplier_id = supplier.get_json()["id"]
    assert browser.get(f"/api/fornecedores/{supplier_id}").status_code == 200
    assert _json(browser, "PUT", f"/api/fornecedores/{supplier_id}", {"email": "ruim"}).status_code == 400
    assert _json(browser, "PUT", f"/api/fornecedores/{supplier_id}", {"telefone": "123"}).status_code == 400
    assert _json(browser, "PUT", f"/api/fornecedores/{supplier_id}", {"cep": "123"}).status_code == 400
    assert _json(browser, "PUT", f"/api/fornecedores/{supplier_id}", {"ativo": "0", "cidade": "Joinville", "endereco": "Rua Y"}).status_code == 200
    assert _json(browser, "DELETE", f"/api/fornecedores/{supplier_id}").status_code == 200

    assert browser.get("/api/defeitos?q=%25&tipo_aparelho=note_").status_code == 200
    assert _json(browser, "POST", "/api/defeitos", {}).status_code == 400
    defect = _json(browser, "POST", "/api/defeitos", {"tipo_aparelho": "Notebook", "sintoma": "Sem video", "causa": "Fonte"})
    assert defect.status_code == 201
    defect_id = defect.get_json()["id"]
    assert _json(browser, "PUT", f"/api/defeitos/{defect_id}", {"solucao": "Trocar fonte"}).status_code == 200
    assert _json(browser, "DELETE", f"/api/defeitos/{defect_id}").status_code == 200

    for payload in (
        {"nome": "A"},
        {"nome": "Peca", "quantidade": "x"},
        {"nome": "Peca", "quantidade": -1},
        {"nome": "Peca", "custo": -1},
        {"nome": "Peca", "custo": 1_000_000},
        {"nome": "Peca", "margem": -1},
        {"nome": "Peca", "margem": 20_000},
        {"nome": "Peca", "fornecedor_id": 9999},
    ):
        assert _json(browser, "POST", "/api/pecas", payload).status_code == 400
    part = _json(browser, "POST", "/api/pecas", {"nome": "Peca Edge", "quantidade": 0, "custo": 10, "fornecedor_id": ids["supplier"]})
    assert part.status_code == 201
    part_id = part.get_json()["id"]
    assert browser.get("/api/pecas?q=Peca&baixo_estoque=10").status_code == 200
    assert browser.get(f"/api/pecas/{part_id}").status_code == 200
    assert _json(browser, "PUT", f"/api/pecas/{part_id}", {"nome": "A"}).status_code == 400
    assert _json(browser, "PUT", f"/api/pecas/{part_id}", {"custo": "x"}).status_code == 400
    assert _json(browser, "PUT", f"/api/pecas/{part_id}", {"custo": -1}).status_code == 400
    assert _json(browser, "PUT", f"/api/pecas/{part_id}", {"margem": 20_000}).status_code == 400
    assert _json(browser, "PUT", f"/api/pecas/{part_id}", {"fornecedor_id": 9999}).status_code == 400
    assert _json(browser, "PUT", f"/api/pecas/{part_id}", {
        "nome": "Peca Edge Atualizada",
        "codigo": "EDGE",
        "margem": 50,
        "fornecedor_id": ids["supplier"],
    }).status_code == 200
    assert _json(browser, "POST", f"/api/pecas/{part_id}/ajuste-estoque", {"delta": "x", "justificativa": "inventario"}).status_code == 400
    assert _json(browser, "POST", f"/api/pecas/{part_id}/ajuste-estoque", {"delta": -1, "justificativa": "inventario"}).status_code == 400
    assert _json(browser, "POST", f"/api/pecas/{part_id}/ajuste-estoque", {"delta": 1, "justificativa": "abc"}).status_code == 400
    assert _json(browser, "POST", f"/api/pecas/{part_id}/ajuste-estoque", {"delta": 1_000_000, "justificativa": "inventario"}).status_code == 400
    assert browser.get(f"/api/pecas/{part_id}/lotes").status_code == 200
    assert _json(browser, "POST", f"/api/pecas/{part_id}/lotes", {}).status_code == 400
    assert _json(browser, "POST", f"/api/pecas/{part_id}/lotes", {"codigo": "L", "quantidade": 1, "custo_unitario": 1, "fornecedor_id": 9999, "justificativa": "compra"}).status_code == 400
    assert _json(browser, "POST", f"/api/pecas/{part_id}/lotes", {"codigo": "L", "quantidade": 1, "custo_unitario": 1, "justificativa": "compra"}).status_code == 400
    assert _json(browser, "POST", f"/api/pecas/{part_id}/lotes", {"codigo": "L2", "quantidade": 1, "custo_unitario": 1, "validade": "ruim", "justificativa": "compra"}).status_code == 400
    assert _json(browser, "POST", f"/api/pecas/{part_id}/lotes", {"codigo": "L3", "quantidade": 1, "custo_unitario": 1, "justificativa": "abc"}).status_code == 400
    removable = _json(browser, "POST", "/api/pecas", {"nome": "Peca Removivel", "quantidade": 0, "custo": 1})
    assert removable.status_code == 201
    assert _json(browser, "DELETE", f"/api/pecas/{removable.get_json()['id']}").status_code == 200

    assert browser.get("/api/transacoes?tipo=bad").status_code == 400
    assert browser.get("/api/transacoes?status=bad").status_code == 400
    assert browser.get("/api/transacoes?mes=13&ano=2026").status_code == 400
    assert browser.get("/api/transacoes?mes=1&ano=1999").status_code == 400
    for payload in (
        {},
        {"tipo": "receita", "valor": "nan"},
        {"tipo": "receita", "valor": None},
        {"tipo": "receita", "valor": -1},
        {"tipo": "receita", "valor": 10_000_000},
        {"tipo": "receita", "valor": 1, "status": "bad"},
        {"tipo": "receita", "valor": 1, "os_id": "x"},
        {"tipo": "receita", "valor": 1, "os_id": 9999},
        {"tipo": "receita", "valor": 1, "comissao_usuario_id": 9999},
        {"tipo": "receita", "valor": 1, "recorrencia": "semanal"},
    ):
        assert _json(browser, "POST", "/api/transacoes", payload).status_code == 400
    tx = _json(browser, "POST", "/api/transacoes", {"tipo": "despesa", "valor": 33, "status": "pendente", "descricao": "=formula"})
    assert tx.status_code == 201
    tx_id = tx.get_json()["id"]
    multi = _json(browser, "POST", "/api/transacoes", {
        "tipo": "receita",
        "valor": 90,
        "status": "pendente",
        "descricao": "Parcelada",
        "parcelas": 3,
        "recorrencia": "mensal",
        "data_vencimento": datetime.now().isoformat(),
        "data_pagamento": "data-ruim",
    })
    assert multi.status_code == 201
    assert len(multi.get_json()["transactions"]) == 3
    assert browser.get(f"/api/transacoes?tipo=despesa&status=pendente&mes={datetime.now().month}&ano={datetime.now().year}").status_code == 200
    assert browser.get(f"/api/transacoes/{tx_id}").status_code == 200
    assert _json(browser, "PUT", f"/api/transacoes/{tx_id}", {"tipo": "bad"}).status_code == 400
    assert _json(browser, "PUT", f"/api/transacoes/{tx_id}", {"status": "bad"}).status_code == 400
    assert _json(browser, "PUT", f"/api/transacoes/{tx_id}", {"valor": "inf"}).status_code == 400
    assert _json(browser, "PUT", f"/api/transacoes/{tx_id}", {"valor": None}).status_code == 400
    assert _json(browser, "PUT", f"/api/transacoes/{tx_id}", {"os_id": "x"}).status_code == 400
    assert _json(browser, "PUT", f"/api/transacoes/{tx_id}", {
        "tipo": "receita",
        "status": "pago",
        "valor": 44.5,
        "categoria": "Despesa",
        "descricao": "-formula",
        "os_id": ids["order"],
        "data_vencimento": "data-ruim",
        "data_pagamento": datetime.now().isoformat(),
    }).status_code == 200
    assert browser.get("/api/transacoes/resumo?mes=0").status_code == 400
    assert browser.get("/api/transacoes/resumo?ano=1999").status_code == 400
    assert browser.get(f"/api/transacoes/resumo?mes={datetime.now().month}&ano={datetime.now().year}").status_code == 200
    assert _json(browser, "POST", f"/api/transacoes/{tx_id}/conciliar", {"referencia": "ab"}).status_code == 400
    assert _json(browser, "POST", f"/api/transacoes/{tx_id}/conciliar", {"referencia": "extrato-edge"}).status_code == 200
    assert _json(browser, "POST", f"/api/transacoes/{tx_id}/desconciliar").status_code == 200
    dre_expense = _json(browser, "POST", "/api/transacoes", {
        "tipo": "despesa",
        "valor": 25,
        "status": "pago",
        "descricao": "Despesa DRE",
        "data_pagamento": datetime.now().isoformat(),
    })
    assert dre_expense.status_code == 201
    assert browser.get("/api/transacoes/dre?inicio=2026-01-01&fim=2026-12-31").status_code == 200
    csv_response = browser.get("/api/transacoes/contabilidade.csv")
    assert csv_response.status_code == 200
    assert b"'-formula" in csv_response.data
    assert _json(browser, "DELETE", f"/api/transacoes/{tx_id}").status_code == 200

    with app.app_context():
        used_part = db.session.get(Peca, ids["part"])
        order = db.session.get(OrdemServico, ids["order"])
        order.pecas.append(used_part)
        db.session.commit()
    assert _json(browser, "DELETE", f"/api/pecas/{ids['part']}").status_code == 409


def test_rotas_usuarios_importacao_platform_privacidade_e_portal(monkeypatch):
    app, browser, ids = _make_client()

    assert browser.get("/api/permissoes").status_code == 200
    assert browser.get("/api/usuarios").status_code == 200
    assert browser.get(f"/api/usuarios/{ids['admin']}").status_code == 200
    for payload in (
        {},
        {"nome": "A", "email": "bad", "senha": "x", "nivel": "bad"},
        {"nome": "User", "email": "bad", "senha": "Senha!123", "nivel": "admin"},
        {"nome": "User", "email": "perfil@routes.test", "senha": "Senha!123", "nivel": "bad"},
        {"nome": "User", "email": "novo@routes.test", "senha": "fraca", "nivel": "admin"},
        {"nome": "User", "email": "novo@routes.test", "senha": "Senha!123", "nivel": "admin", "permissoes_extra": "x"},
        {"nome": "User", "email": "novo@routes.test", "senha": "Senha!123", "nivel": "admin", "permissoes_extra": ["bad.permission"]},
    ):
        assert _json(browser, "POST", "/api/usuarios", payload).status_code == 400
    monkeypatch.setattr("app.routes.usuarios.assert_write_allowed", lambda _organization_id: (_ for _ in ()).throw(PermissionError("bloqueado")))
    assert _json(browser, "POST", "/api/usuarios", {
        "nome": "Bloqueado",
        "email": "bloqueado@routes.test",
        "senha": "Senha!123",
        "nivel": "admin",
    }).status_code == 403
    monkeypatch.setattr("app.routes.usuarios.assert_write_allowed", lambda _organization_id: None)
    user = _json(browser, "POST", "/api/usuarios", {"nome": "User Edge", "email": "edge@routes.test", "senha": "Senha!123", "nivel": "operacional"})
    assert user.status_code == 201
    user_id = user.get_json()["id"]
    assert _json(browser, "POST", "/api/usuarios", {"nome": "Dup", "email": "edge@routes.test", "senha": "Senha!123", "nivel": "admin"}).status_code == 409
    assert _json(browser, "PUT", f"/api/usuarios/{user_id}", {"nome": "A"}).status_code == 400
    assert _json(browser, "PUT", f"/api/usuarios/{user_id}", {"email": "bad"}).status_code == 400
    assert _json(browser, "PUT", f"/api/usuarios/{user_id}", {"email": "admin@routes.test"}).status_code == 409
    assert _json(browser, "PUT", f"/api/usuarios/{user_id}", {"nivel": "bad"}).status_code == 400
    assert _json(browser, "PUT", f"/api/usuarios/{user_id}", {"senha": "fraca"}).status_code == 400
    assert _json(browser, "PUT", f"/api/usuarios/{user_id}", {"permissoes_extra": "bad"}).status_code == 400
    assert _json(browser, "PUT", f"/api/usuarios/{user_id}", {
        "nome": "User Edge Atualizado",
        "email": "edge2@routes.test",
        "nivel": "consulta",
        "senha": "Outra!123",
        "permissoes_extra": [],
    }).status_code == 200
    assert _json(browser, "PUT", f"/api/usuarios/{user_id}", {"ativo": "false", "permissoes_negadas": []}).status_code == 200
    assert _json(browser, "POST", f"/api/usuarios/{user_id}/revogar-sessoes").status_code == 200
    self_revoke = _json(browser, "POST", f"/api/usuarios/{ids['admin']}/revogar-sessoes")
    assert self_revoke.status_code == 200
    with browser.session_transaction() as session:
        session["usuario_id"] = ids["admin"]
        session["nivel"] = "admin"
        session["perfil"] = "admin"
        session["usuario_nome"] = "Admin"
        session["_csrf_token"] = "route-csrf"
        session["_last_active"] = 9999999999
    assert _json(browser, "DELETE", f"/api/usuarios/{ids['admin']}").status_code == 400
    assert _json(browser, "DELETE", f"/api/usuarios/{user_id}").status_code == 200
    assert _json(browser, "POST", "/api/usuarios/alterar-senha", {"senha_atual": "errada", "nova_senha": "Nova!123"}).status_code == 401
    assert _json(browser, "POST", "/api/usuarios/alterar-senha", {"senha_atual": "Senha!123", "nova_senha": "fraca"}).status_code == 400
    assert _json(browser, "POST", "/api/usuarios/alterar-senha", {"senha_atual": "Senha!123", "nova_senha": "Senha!123"}).status_code == 400
    assert _json(browser, "POST", "/api/usuarios/alterar-senha", {"senha_atual": "Senha!123", "nova_senha": "Nova!456"}).status_code == 200
    with browser.session_transaction() as session:
        session["usuario_id"] = ids["admin"]
        session["nivel"] = "admin"
        session["perfil"] = "admin"
        session["usuario_nome"] = "Admin"
        session["_csrf_token"] = "route-csrf"
        session["_last_active"] = 9999999999

    monkeypatch.setattr("app.utils.email_delivery.send_email", lambda *args, **kwargs: {"sent": True})
    assert _json(browser, "POST", "/api/usuarios/convites", {"email": "ruim", "nivel": "bad"}).status_code == 400
    assert _json(browser, "POST", "/api/usuarios/convites", {"email": "admin@routes.test", "nivel": "admin"}).status_code == 409
    monkeypatch.setattr("app.routes.usuarios.assert_write_allowed", lambda _organization_id: (_ for _ in ()).throw(PermissionError("bloqueado")))
    assert _json(browser, "POST", "/api/usuarios/convites", {"email": "blocked@routes.test", "nivel": "admin"}).status_code == 403
    monkeypatch.setattr("app.routes.usuarios.assert_write_allowed", lambda _organization_id: None)
    invite = _json(browser, "POST", "/api/usuarios/convites", {"email": "invite@routes.test", "nivel": "operacional"})
    assert invite.status_code == 201
    token = invite.get_json()["link"].rstrip("/").rsplit("/", 1)[-1]
    assert browser.get(f"/convite/{token}").status_code == 200
    assert _form(browser, f"/convite/{token}", {"nome": "A", "senha": "fraca"}).status_code == 200
    assert _form(browser, f"/convite/{token}", {"nome": "Convidado", "senha": "Senha!123"}).status_code == 302

    from app.services.user_invites import create_invite

    with app.app_context():
        _duplicate_invite, duplicate_token = create_invite(1, "admin@routes.test", "admin", ids["admin"])
        db.session.commit()
    assert _form(browser, f"/convite/{duplicate_token}", {"nome": "Admin Dup", "senha": "Senha!123"}).status_code == 409

    class FakeImporter:
        def __init__(self, creds):
            self.creds = creds

        def test_connection(self):
            if self.creds.database_path == "bad":
                raise CPlusImportError("falha")
            return {"success": True, "driver": "fake", "table_count": 1}

        def preview(self):
            if self.creds.database_path == "bad":
                raise CPlusImportError("falha")
            return {"success": True, "dry_run": True}

        def commit(self, admin_user=None, admin_user_id=None):
            if self.creds.database_path == "commit-bad.fdb":
                raise CPlusImportError("falha")
            return {"success": True, "created": {"clientes": 1}, "admin": admin_user, "admin_id": admin_user_id}

    import app.routes.importacao as importacao_routes

    monkeypatch.setattr(importacao_routes, "CPlusFirebirdImporter", FakeImporter)
    assert _json(browser, "POST", "/api/importacao/cplus/test", {"database_path": "bad"}).status_code == 400
    assert _json(browser, "POST", "/api/importacao/cplus/test", {"database_path": "ok.fdb"}).status_code == 200
    assert _json(browser, "POST", "/api/importacao/cplus/preview", {"database_path": "bad"}).status_code == 400
    assert _json(browser, "POST", "/api/importacao/cplus/commit", {"database_path": "ok.fdb", "confirm": True}).status_code == 400
    assert _json(browser, "POST", "/api/importacao/cplus/preview", {"database_path": "ok.fdb"}).status_code == 200
    assert _json(browser, "POST", "/api/importacao/cplus/commit", {"database_path": "other.fdb", "confirm": True}).status_code == 400
    assert _json(browser, "POST", "/api/importacao/cplus/preview", {"database_path": "commit-bad.fdb"}).status_code == 200
    assert _json(browser, "POST", "/api/importacao/cplus/commit", {"database_path": "commit-bad.fdb", "confirm": True}).status_code == 400
    assert _json(browser, "POST", "/api/importacao/cplus/preview", {"database_path": "ok.fdb"}).status_code == 200
    assert _json(browser, "POST", "/api/importacao/cplus/commit", {"database_path": "ok.fdb", "confirm": True}).status_code == 200

    monkeypatch.setenv("PLATFORM_ADMIN_EMAILS", "admin@routes.test")
    assert _form(browser, "/platform/plans", {"code": "", "nome": ""}).status_code == 400
    assert _form(browser, "/platform/plans", {"code": "Pro Plan", "nome": "Pro", "max_users": "5"}).status_code == 302
    assert _form(browser, "/platform/plans", {"code": "Pro Plan", "nome": "Pro"}).status_code == 400
    with app.app_context():
        plan_id = Plan.query.filter_by(code="pro-plan").one().id
    assert _form(browser, "/platform/subscriptions", {"organization_id": "999", "plan_id": str(plan_id)}).status_code == 400
    assert _form(browser, "/platform/subscriptions", {"organization_id": "1", "plan_id": str(plan_id)}).status_code == 302
    assert _form(browser, "/platform/subscriptions", {"organization_id": "1", "plan_id": str(plan_id)}).status_code == 302

    assert browser.get("/privacidade/retencao").status_code == 200
    assert _form(browser, "/privacidade/retencao", {"active_notifications": "on"}).status_code == 302
    assert _form(browser, "/privacidade/retencao", {"legal_approval": "yes", "days_notifications": "abc"}).status_code == 302
    assert _form(browser, "/privacidade/retencao", {"legal_approval": "yes", "days_notifications": "1"}).status_code == 302
    assert _form(browser, "/privacidade/retencao", {"legal_approval": "yes", "days_notifications": "90"}).status_code == 302
    assert browser.get(f"/privacidade/clientes/{ids['client']}").status_code == 200
    assert _form(browser, f"/privacidade/clientes/{ids['client']}/consent", {"purpose": "bad", "granted": "true"}).status_code == 302
    assert _form(browser, f"/privacidade/clientes/{ids['client']}/consent", {"purpose": "marketing", "granted": "true"}).status_code == 302
    export = browser.get(f"/privacidade/clientes/{ids['client']}/export")
    assert export.status_code == 200
    assert export.headers["Cache-Control"] == "no-store, private"
    with app.app_context():
        anon = Cliente(organization_id=1, nome="Cliente Anonimo")
        db.session.add(anon)
        db.session.commit()
        anon_id = anon.id
    assert _form(browser, f"/privacidade/clientes/{anon_id}/anonymize", {}).status_code == 302
    assert _form(browser, f"/privacidade/clientes/{ids['client']}/anonymize", {}).status_code == 302

    assert _form(browser, f"/os/{ids['order']}/portal-link", {"purpose": "bad"}).status_code == 400
    assert _form(browser, f"/os/{ids['order']}/portal-link", {"purpose": "tracking"}).status_code == 200
    assert browser.get("/portal/os/token-invalido").status_code == 404


def test_platform_redireciona_sem_usuario_e_bloqueia_fora_da_allowlist(monkeypatch):
    _app, browser, _ids = _make_client()
    monkeypatch.delenv("PLATFORM_ADMIN_EMAILS", raising=False)
    assert browser.get("/platform").status_code == 403
    public = _app.test_client()
    assert public.get("/platform").status_code == 302
