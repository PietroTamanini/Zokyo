import os
from datetime import datetime, timedelta
from io import BytesIO
from urllib.parse import quote_plus

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from werkzeug.datastructures import FileStorage

from app import create_app
from app.extensions import db
from app.models import (
    Cliente,
    ColetaAgendada,
    Configuracao,
    DefeitoPadrao,
    EventoLog,
    Fornecedor,
    InventoryMovement,
    LaudoTecnico,
    Notification,
    OrdemServico,
    Organization,
    OSFoto,
    OSHistorico,
    Peca,
    Transacao,
    Usuario,
)


def _make_pages_client(instance_path=None):
    app = create_app("development")
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    if instance_path is not None:
        app.instance_path = str(instance_path)
    with app.app_context():
        db.drop_all()
        db.create_all()
        organization = Organization(id=1, nome="Teste", slug="teste")
        admin = Usuario(
            organization_id=1,
            nome="Admin",
            email="admin.pages@example.com",
            nivel="admin",
            ativo=True,
            onboarding_completed=True,
        )
        admin.set_senha("Senha!123")
        config = Configuracao(
            organization_id=1,
            nome_empresa="Empresa Teste",
            cnpj="04252011000110",
            cidade="Joinville",
            pix_chave="financeiro@example.com",
        )
        cliente = Cliente(
            organization_id=1,
            nome="Cliente Paginas",
            telefone="47999999999",
            email="cliente@example.com",
            cidade="Joinville",
            uf="SC",
        )
        fornecedor = Fornecedor(organization_id=1, nome="Fornecedor Paginas", telefone="4733333333")
        peca = Peca(
            organization_id=1,
            nome="Peca Paginas",
            codigo="PAG-1",
            quantidade=5,
            estoque_minimo=2,
            custo=10,
            margem=50,
        )
        db.session.add_all([organization, admin, config, cliente, fornecedor, peca])
        db.session.flush()
        ordem = OrdemServico(
            organization_id=1,
            numero=1,
            cliente_id=cliente.id,
            usuario_id=admin.id,
            tipo_aparelho="Notebook",
            marca="Marca",
            modelo="Modelo",
            defeito_alegado="Nao liga",
            valor_servico=100,
            status="recepcao",
            data_prev=datetime.now() + timedelta(days=2),
        )
        transacao = Transacao(
            organization_id=1,
            os_id=None,
            tipo="receita",
            categoria="servico",
            descricao="Entrada",
            valor=100,
            status="pendente",
            data_vencimento=datetime.now() + timedelta(days=1),
        )
        db.session.add_all([ordem, transacao])
        db.session.commit()
        user_id = admin.id
        ordem_id = ordem.id
    client = app.test_client()
    with client.session_transaction() as session:
        session["usuario_id"] = user_id
        session["nivel"] = "admin"
        session["perfil"] = "admin"
        session["usuario_nome"] = "Admin"
        session["_last_active"] = 9999999999
        session["_csrf_token"] = "csrf-pages"
    return app, client, ordem_id


def test_os_baixada_some_da_lista_principal_e_pode_restaurar(tmp_path):
    app, client, ordem_id = _make_pages_client(tmp_path)

    lista_ativa = client.get("/os")
    assert lista_ativa.status_code == 200
    assert b"#0001" in lista_ativa.data

    response = _post(client, f"/os/{ordem_id}/baixar", {"observacao": "Concluida e arquivada"})
    assert response.status_code == 302
    with app.app_context():
        ordem = db.session.get(OrdemServico, ordem_id)
        assert ordem.baixada is True
        assert ordem.baixa_observacao == "Concluida e arquivada"

    lista_ativa = client.get("/os")
    assert b"#0001" not in lista_ativa.data
    baixadas = client.get("/os/baixadas")
    assert baixadas.status_code == 200
    assert b"#0001" in baixadas.data

    api_ativa = _json(client, "get", "/api/v1/os").get_json()
    assert api_ativa["total"] == 0
    api_baixadas = _json(client, "get", "/api/v1/os?baixadas=1").get_json()
    assert api_baixadas["total"] == 1
    assert api_baixadas["items"][0]["codigo_os"] == "0001"

    response = _post(client, f"/os/{ordem_id}/restaurar", {})
    assert response.status_code == 302
    with app.app_context():
        ordem = db.session.get(OrdemServico, ordem_id)
        assert ordem.baixada is False
    assert b"#0001" in client.get("/os").data


def test_os_so_entrega_quando_pagamento_estiver_completo(tmp_path):
    app, client, ordem_id = _make_pages_client(tmp_path)

    edicao_bloqueada = _post(client, f"/os/{ordem_id}/editar", {
        "tipo_aparelho": "Notebook",
        "marca": "Marca",
        "modelo": "Modelo",
        "defeito_alegado": "Nao liga",
        "valor_servico": "100",
        "desconto": "0",
        "horas_trabalho": "0",
        "custo_hora": "0",
        "garantia_dias": "90",
        "status": "entregue",
        "prio": "normal",
        "tipo_atendimento": "balcao",
    })
    assert edicao_bloqueada.status_code == 400
    assert "saldo em aberto" in edicao_bloqueada.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(OrdemServico, ordem_id).status == "recepcao"
        assert Transacao.query.filter_by(os_id=ordem_id).count() == 0

    parcial = _post(client, f"/os/{ordem_id}/pagamento-parcial", {
        "valor": "40",
        "forma_pagamento": "PIX",
    })
    assert parcial.status_code == 302
    detalhe = client.get(f"/os/{ordem_id}").get_data(as_text=True)
    assert "Pago" in detalhe
    assert "R$ 40,00" in detalhe
    assert "R$ 60,00" in detalhe

    bloqueada = _post(client, f"/os/{ordem_id}/status", {
        "status": "entregue",
    })
    assert bloqueada.status_code == 302
    with app.app_context():
        ordem = db.session.get(OrdemServico, ordem_id)
        assert ordem.status == "recepcao"
        assert Transacao.query.filter_by(os_id=ordem_id, tipo="receita", status="pago").count() == 1

    api_bloqueada = _json(client, "put", f"/api/v1/os/{ordem_id}", {
        "status": "entregue",
    })
    assert api_bloqueada.status_code == 400
    assert "saldo em aberto" in api_bloqueada.json["erro"]
    with app.app_context():
        assert db.session.get(OrdemServico, ordem_id).status == "recepcao"

    restante = _post(client, f"/os/{ordem_id}/pagamento-parcial", {
        "valor": "60",
        "forma_pagamento": "Dinheiro",
    })
    assert restante.status_code == 302

    entrega = _post(client, f"/os/{ordem_id}/status", {
        "status": "entregue",
    })
    assert entrega.status_code == 302
    with app.app_context():
        receitas = Transacao.query.filter_by(os_id=ordem_id, tipo="receita", status="pago").order_by(Transacao.id).all()
        assert [float(item.valor) for item in receitas] == [40.0, 60.0]
        assert sum(float(item.valor) for item in receitas) == 100.0
        assert db.session.get(OrdemServico, ordem_id).status == "entregue"

    with app.app_context():
        db.session.get(OrdemServico, ordem_id).status = "recepcao"
        db.session.commit()
    api_entrega = _json(client, "put", f"/api/v1/os/{ordem_id}", {
        "status": "entregue",
    })
    assert api_entrega.status_code == 200
    with app.app_context():
        assert db.session.get(OrdemServico, ordem_id).status == "entregue"


def _post(client, path, data):
    payload = {"_csrf_token": "csrf-pages"}
    payload.update(data)
    return client.post(path, data=payload)


def _json(client, method, path, payload=None):
    return getattr(client, method)(
        path,
        json={**(payload or {}), "_csrf_token": "csrf-pages"},
        headers={"X-CSRFToken": "csrf-pages"},
    )


def test_paginas_principais_autenticadas_renderizam_sem_erro(monkeypatch, tmp_path):
    monkeypatch.setenv("PLATFORM_ADMIN_EMAILS", "admin.pages@example.com")
    _app, client, ordem_id = _make_pages_client(tmp_path)
    paths = [
        "/",
        "/ajuda",
        "/clientes",
        "/os",
        "/os/kanban",
        "/os/nova",
        f"/os/{ordem_id}",
        f"/os/{ordem_id}/imprimir",
        f"/os/{ordem_id}/editar",
        "/agenda",
        "/estoque",
        "/estoque/movimentacoes",
        "/compras-pecas",
        "/fornecedores",
        "/financeiro",
        "/coleta",
        "/coletas/rota",
        "/bancada",
        "/checklists",
        "/relatorios",
        "/produtividade",
        "/usuarios",
        "/configuracoes",
        "/configuracoes/notificacoes",
        "/configurar",
        "/emitente",
        "/backup",
        "/minhaConta",
        "/alterarSenha",
        "/pesquisar?termo=Cliente",
        "/logs",
        "/importacao/bancos",
        "/platform",
        "/privacidade/retencao",
        "/laudos/",
        "/laudos/novo",
        "/laudos/templates",
    ]

    for path in paths:
        response = client.get(path, follow_redirects=path in {"/minhaConta", "/alterarSenha"})
        assert response.status_code == 200, f"{path}: {response.status_code} {response.get_data(as_text=True)[:300]}"


def test_frontend_nao_regride_logout_e_scripts_globais(tmp_path):
    _app, client, _ordem_id = _make_pages_client(tmp_path)
    dashboard = client.get("/").get_data(as_text=True)
    assert 'action="/logout"' in dashboard
    assert 'href="/login/sair"' not in dashboard

    for path in ("/clientes/adicionar", "/fornecedores/adicionar", "/configurar"):
        html = client.get(path).get_data(as_text=True)
        assert html.count("/static/js/masks.js") == 1


def test_pesquisa_global_encontra_fluxos_principais(tmp_path):
    app, client, ordem_id = _make_pages_client(tmp_path)
    with app.app_context():
        ordem = db.session.get(OrdemServico, ordem_id)
        ordem.numero_serie = "SERIAL-TOP-9988"
        ordem.defeito_encontrado = "Placa oxidada"
        fornecedor = Fornecedor.query.filter_by(nome="Fornecedor Paginas").one()
        fornecedor.cidade = "Joinville"
        servico = DefeitoPadrao(
            organization_id=1,
            tipo_aparelho="Notebook",
            sintoma="Troca de conector de carga",
            solucao="Substituição e teste de carregamento",
        )
        laudo = LaudoTecnico(
            organization_id=1,
            os_id=ordem.id,
            cliente_id=ordem.cliente_id,
            criado_por_id=ordem.usuario_id,
            numero="LT-OS-0001",
            status="draft",
            diagnostico_tecnico="Oxidação no setor de alimentação",
        )
        db.session.add_all([servico, laudo])
        db.session.commit()

    checks = [
        ("SERIAL-TOP-9988", "OS0001"),
        ("Joinville", "Fornecedor Paginas"),
        ("conector de carga", "Troca de conector de carga"),
        ("LT-OS-0001", "Laudo"),
    ]
    for termo, esperado in checks:
        html = client.get(f"/pesquisar?termo={quote_plus(termo)}").get_data(as_text=True)
        assert esperado in html


def test_logout_legado_exige_post_para_encerrar_sessao(tmp_path):
    _app, client, _ordem_id = _make_pages_client(tmp_path)

    response = client.get("/login/sair")
    assert response.status_code == 200
    with client.session_transaction() as session:
        assert session["usuario_id"]

    response = _post(client, "/login/sair", {})
    assert response.status_code == 302
    with client.session_transaction() as session:
        assert "usuario_id" not in session


def test_rotas_mutaveis_nao_aceitam_visitante_sem_autenticacao():
    app = create_app("development")
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    with app.app_context():
        db.drop_all()
        db.create_all()
        organization = Organization(id=1, nome="Audit", slug="audit")
        admin = Usuario(id=1, organization_id=1, nome="Admin", email="admin.audit@example.com", nivel="admin", ativo=True)
        admin.set_senha("Senha!123")
        db.session.add_all([organization, admin])
        db.session.commit()

    client = app.test_client()
    samples = {
        "id": 1,
        "os_id": 1,
        "ordem_id": 1,
        "cliente_id": 1,
        "client_id": 1,
        "peca_id": 1,
        "servico_id": 1,
        "usuario_id": 1,
        "fornecedor_id": 1,
        "transacao_id": 1,
        "foto_id": 1,
        "template_id": 1,
        "report_id": 1,
        "record_id": 1,
        "notification_id": 1,
        "reservation_id": 1,
        "anexo_id": 1,
        "anotacao_id": 1,
        "token": "invalid-token-audit",
    }
    allowed_public_prefixes = (
        "/login",
        "/2fa",
        "/recuperar-senha",
        "/redefinir-senha/",
        "/primeiro-acesso",
        "/convite/",
        "/portal/os/",
        "/platform/webhooks/sandbox",
    )
    issues = []
    for rule in app.url_map.iter_rules():
        methods = sorted((rule.methods - {"HEAD", "OPTIONS"}) & {"POST", "PUT", "PATCH", "DELETE"})
        if not methods or any(arg not in samples for arg in rule.arguments):
            continue
        values = {arg: samples[arg] for arg in rule.arguments}
        with app.test_request_context():
            path = rule.build(values)[1]
        if path.startswith(allowed_public_prefixes):
            continue
        for method in methods:
            response = getattr(client, method.lower())(path, data={})
            if response.status_code < 300:
                issues.append((method, path, response.status_code, rule.endpoint))
    assert issues == []


def test_rotas_get_privadas_nao_vazam_para_visitante():
    app = create_app("development")
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    with app.app_context():
        db.drop_all()
        db.create_all()
        organization = Organization(id=1, nome="Audit", slug="audit")
        admin = Usuario(id=1, organization_id=1, nome="Admin", email="admin.audit@example.com", nivel="admin", ativo=True)
        admin.set_senha("Senha!123")
        db.session.add_all([organization, admin])
        db.session.commit()

    client = app.test_client()
    samples = {
        "id": 1,
        "os_id": 1,
        "ordem_id": 1,
        "cliente_id": 1,
        "client_id": 1,
        "peca_id": 1,
        "servico_id": 1,
        "usuario_id": 1,
        "fornecedor_id": 1,
        "transacao_id": 1,
        "foto_id": 1,
        "template_id": 1,
        "report_id": 1,
        "record_id": 1,
        "notification_id": 1,
        "reservation_id": 1,
        "anexo_id": 1,
        "anotacao_id": 1,
        "token": "invalid-token-audit",
        "filename": "missing.txt",
        "path": "missing.txt",
    }
    public_prefixes = (
        "/login",
        "/register",
        "/primeiro-acesso",
        "/recuperar-senha",
        "/redefinir-senha/",
        "/convite/",
        "/portal/os/",
        "/healthz",
        "/readyz",
        "/metrics",
        "/service-worker.js",
        "/pwa-start",
        "/laudos/verificar/",
    )
    public_exact = {"/api/v1"}
    issues = []
    for rule in app.url_map.iter_rules():
        if "GET" not in (rule.methods - {"HEAD", "OPTIONS"}) or rule.rule.startswith("/static/"):
            continue
        if any(arg not in samples for arg in rule.arguments):
            continue
        values = {arg: samples[arg] for arg in rule.arguments}
        with app.test_request_context():
            path = rule.build(values)[1]
        if path in public_exact or path.startswith(public_prefixes):
            continue
        response = client.get(path, follow_redirects=False)
        if response.status_code < 300:
            issues.append((path, response.status_code, rule.endpoint))
    assert issues == []


def test_rotas_mutaveis_logadas_exigem_csrf_quando_nao_exentas(tmp_path):
    app, client, ordem_id = _make_pages_client(tmp_path)
    samples = {
        "id": 1,
        "os_id": ordem_id,
        "ordem_id": ordem_id,
        "cliente_id": 1,
        "client_id": 1,
        "peca_id": 1,
        "servico_id": 1,
        "usuario_id": 1,
        "fornecedor_id": 1,
        "transacao_id": 1,
        "foto_id": 1,
        "template_id": 1,
        "report_id": 1,
        "record_id": 1,
        "notification_id": 1,
        "reservation_id": 1,
        "anexo_id": 1,
        "anotacao_id": 1,
        "token": "invalid-token-audit",
    }
    allowed_prefixes = ("/api/v1/login", "/api/v1/client/auth", "/platform/webhooks/sandbox")
    allowed_statuses = {400, 401, 403, 404, 405}
    csrf_exempt = set(app.config.get("CSRF_EXEMPT_ENDPOINTS", set()))
    issues = []
    for rule in app.url_map.iter_rules():
        methods = sorted((rule.methods - {"HEAD", "OPTIONS"}) & {"POST", "PUT", "PATCH", "DELETE"})
        if not methods or rule.endpoint in csrf_exempt or any(arg not in samples for arg in rule.arguments):
            continue
        values = {arg: samples[arg] for arg in rule.arguments}
        with app.test_request_context():
            path = rule.build(values)[1]
        if path.startswith(allowed_prefixes):
            continue
        for method in methods:
            response = getattr(client, method.lower())(path, data={})
            if response.status_code not in allowed_statuses and not (300 <= response.status_code < 400):
                issues.append((method, path, response.status_code, rule.endpoint))
    assert issues == []


def test_api_v1_mutavel_nao_aceita_bearer_invalido():
    app = create_app("development")
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    with app.app_context():
        db.drop_all()
        db.create_all()
        organization = Organization(id=1, nome="Audit", slug="audit")
        admin = Usuario(id=1, organization_id=1, nome="Admin", email="admin.audit@example.com", nivel="admin", ativo=True)
        admin.set_senha("Senha!123")
        db.session.add_all([organization, admin])
        db.session.commit()

    client = app.test_client()
    samples = {
        "id": 1,
        "os_id": 1,
        "ordem_id": 1,
        "cliente_id": 1,
        "client_id": 1,
        "peca_id": 1,
        "servico_id": 1,
        "usuario_id": 1,
        "fornecedor_id": 1,
        "transacao_id": 1,
        "foto_id": 1,
        "template_id": 1,
        "report_id": 1,
        "record_id": 1,
        "notification_id": 1,
        "reservation_id": 1,
        "anexo_id": 1,
        "anotacao_id": 1,
        "token": "invalid-token-audit",
    }
    issues = []
    for rule in app.url_map.iter_rules():
        methods = sorted((rule.methods - {"HEAD", "OPTIONS"}) & {"POST", "PUT", "PATCH", "DELETE"})
        if not methods or not rule.rule.startswith("/api/v1/"):
            continue
        if rule.rule in {"/api/v1/login", "/api/v1/client/auth"}:
            continue
        if any(arg not in samples for arg in rule.arguments):
            continue
        values = {arg: samples[arg] for arg in rule.arguments}
        with app.test_request_context():
            path = rule.build(values)[1]
        for method in methods:
            response = getattr(client, method.lower())(
                path,
                json={},
                headers={"Authorization": "Bearer token-invalido"},
            )
            if response.status_code < 400:
                issues.append((method, path, response.status_code, rule.endpoint))
    assert issues == []


def test_respostas_principais_mantem_headers_de_seguranca(tmp_path):
    _app, client, _ordem_id = _make_pages_client(tmp_path)
    required = {
        "X-Content-Type-Options",
        "X-Frame-Options",
        "Referrer-Policy",
        "Permissions-Policy",
        "Content-Security-Policy",
    }
    for path in ("/", "/clientes", "/api/v1"):
        response = client.get(path)
        missing = [name for name in required if not response.headers.get(name)]
        assert missing == [], f"{path} sem headers: {missing}"
        assert "'unsafe-inline'" not in response.headers["Content-Security-Policy"]


def test_formularios_zokyo_criam_e_editam_registros(tmp_path):
    app, client, _ordem_id = _make_pages_client(tmp_path)

    produto = _post(client, "/produtos/adicionar", {
        "nome": "Tela LCD 15",
        "codigo": "LCD-15",
        "categoria": "Tela",
        "localizacao": "A1",
        "quantidade": "3",
        "estoque_minimo": "1",
        "custo": "120.50",
        "margem": "35",
    })
    fornecedor = _post(client, "/fornecedores/adicionar", {
        "nome": "Fornecedor Novo",
        "telefone": "47988887777",
        "email": "novo.fornecedor@example.com",
        "cidade": "Joinville",
    })
    servico = _post(client, "/servicos/adicionar", {
        "nome": "Troca de tela",
        "tipo_aparelho": "Notebook",
        "causa": "Tela quebrada",
        "descricao": "Substituir display",
    })
    transacao = _post(client, "/financeiro/adicionar", {
        "tipo": "despesa",
        "categoria": "fornecedor",
        "descricao": "Compra de tela",
        "valor": "120.50",
        "data_vencimento": "2026-07-30",
        "status": "pendente",
        "forma_pagamento": "PIX",
        "parcelas": "1",
        "comissao_percentual": "0",
    })
    assert produto.status_code == 302
    assert fornecedor.status_code == 302
    assert servico.status_code == 302
    assert transacao.status_code == 302

    with app.app_context():
        peca = Peca.query.filter_by(codigo="LCD-15").one()
        fornecedor_obj = Fornecedor.query.filter_by(nome="Fornecedor Novo").one()
        servico_obj = DefeitoPadrao.query.filter_by(sintoma="Troca de tela").one()
        transacao_obj = Transacao.query.filter_by(descricao="Compra de tela").one()
        assert peca.quantidade == 3
        assert fornecedor_obj.email == "novo.fornecedor@example.com"
        assert servico_obj.solucao == "Substituir display"
        assert transacao_obj.tipo == "despesa"

        peca_id = peca.id
        fornecedor_id = fornecedor_obj.id
        servico_id = servico_obj.id
        transacao_id = transacao_obj.id

    assert _post(client, f"/produtos/editar/{peca_id}", {
        "nome": "Tela LCD 15 Slim",
        "codigo": "LCD-15S",
        "categoria": "Tela",
        "localizacao": "A2",
        "estoque_minimo": "2",
        "custo": "130",
        "margem": "40",
    }).status_code == 302
    assert _post(client, f"/fornecedores/editar/{fornecedor_id}", {
        "nome": "Fornecedor Editado",
        "telefone": "47977776666",
        "email": "editado.fornecedor@example.com",
        "cidade": "Blumenau",
    }).status_code == 302
    assert _post(client, f"/servicos/editar/{servico_id}", {
        "nome": "Troca de tela premium",
        "tipo_aparelho": "Notebook",
        "causa": "Tela sem imagem",
        "descricao": "Substituir display e testar",
    }).status_code == 302
    assert _post(client, f"/financeiro/editar/{transacao_id}", {
        "tipo": "despesa",
        "categoria": "fornecedor",
        "descricao": "Compra de tela editada",
        "valor": "130",
        "data_vencimento": "2026-07-31",
        "status": "pago",
        "forma_pagamento": "PIX",
        "comissao_percentual": "0",
    }).status_code == 302

    with app.app_context():
        assert db.session.get(Peca, peca_id).codigo == "LCD-15S"
        assert db.session.get(Fornecedor, fornecedor_id).nome == "Fornecedor Editado"
        assert db.session.get(DefeitoPadrao, servico_id).sintoma == "Troca de tela premium"
        assert db.session.get(Transacao, transacao_id).status == "pago"


def test_api_v1_aliases_preservam_fluxos_centrais(tmp_path):
    app, client, ordem_id = _make_pages_client(tmp_path)
    with app.app_context():
        peca_id = Peca.query.filter_by(codigo="PAG-1").one().id
        cliente_id = Cliente.query.filter_by(nome="Cliente Paginas").one().id
        servico = DefeitoPadrao(
            organization_id=1,
            tipo_aparelho="Notebook",
            sintoma="Servico API",
            solucao="Execucao via API",
        )
        db.session.add(servico)
        db.session.commit()
        servico_id = servico.id

    assert client.get("/api/v1/clientes").status_code == 200
    assert client.get(f"/api/v1/clientes/{cliente_id}").status_code == 200
    assert client.get("/api/v1/produtos").status_code == 200
    assert client.get(f"/api/v1/produtos/{peca_id}").status_code == 200
    assert client.get("/api/v1/pecas").status_code == 200
    assert client.get("/api/v1/servicos").status_code == 200
    assert client.get("/api/v1/os").status_code == 200
    assert client.get(f"/api/v1/os/{ordem_id}").status_code == 200
    assert client.get("/api/v1/usuarios").status_code == 200
    assert client.get("/api/v1/conta").status_code == 200
    api_index = client.get("/api/v1")
    assert api_index.status_code == 200
    assert "calendario" in api_index.json["resources"]
    audit = client.get("/api/v1/audit")
    assert audit.status_code == 200
    assert "items" in audit.json
    calendario = client.get("/api/v1/calendario")
    assert calendario.status_code == 200
    assert any(item["id"] == ordem_id for item in calendario.json)
    emitente = client.get("/api/v1/emitente")
    assert emitente.status_code == 200
    assert emitente.json["nome_empresa"] == "Empresa Teste"
    assert "site_url" in emitente.json
    assert "instagram_url" in emitente.json
    assert "whatsapp_publico" in emitente.json
    assert "logo_url" in emitente.json
    assert "evolution_api_key" not in emitente.json
    assert "evolution_api_url" not in emitente.json

    novo_cliente = _json(client, "post", "/api/v1/clientes", {
        "nome": "Cliente API V1",
        "telefone": "47977776666",
        "email": "cliente.api@example.com",
    })
    assert novo_cliente.status_code == 201
    produto_os = _json(client, "post", f"/api/v1/os/{ordem_id}/pecas", {
        "peca_id": peca_id,
        "quantidade": 1,
        "valor_unitario": 20,
    })
    assert produto_os.status_code == 200
    produto_alias = _json(client, "post", f"/api/v1/os/{ordem_id}/produtos", {
        "produto_id": peca_id,
        "quantidade": 1,
        "preco": 30,
    })
    assert produto_alias.status_code == 200
    desconto_alias = _json(client, "post", f"/api/v1/os/{ordem_id}/desconto", {"desconto": 5})
    assert desconto_alias.status_code == 200
    assert desconto_alias.json["desconto"] == 5
    servico_alias = _json(client, "post", f"/api/v1/os/{ordem_id}/servicos", {
        "servico_id": servico_id,
        "quantidade": 1,
        "preco": 15,
    })
    assert servico_alias.status_code == 200
    anotacao_alias = _json(client, "post", f"/api/v1/os/{ordem_id}/anotacoes", {"anotacao": "Cliente avisado"})
    assert anotacao_alias.status_code == 200
    assert "Cliente avisado" in anotacao_alias.json["observacoes"]
    assert client.get(f"/api/v1/os/{ordem_id}/anexos").status_code == 200
    remove_produto_os = _json(client, "delete", f"/api/v1/os/{ordem_id}/produtos/{peca_id}")
    assert remove_produto_os.status_code == 200


def test_api_v1_login_e_regeneracao_token_bearer(tmp_path):
    app, _client, _ordem_id = _make_pages_client(tmp_path)
    api = app.test_client()
    login = api.post("/api/v1/login", json={"email": "admin.pages@example.com", "password": "Senha!123"})
    assert login.status_code == 200
    token = login.json["token"]

    bearer = {"Authorization": f"Bearer {token}"}
    conta = app.test_client().get("/api/v1/conta", headers=bearer)
    assert conta.status_code == 200
    assert conta.json["email"] == "admin.pages@example.com"

    regen = app.test_client().post("/api/v1/reGenToken", headers=bearer)
    assert regen.status_code == 200
    new_token = regen.json["token"]
    assert new_token != token

    assert app.test_client().get("/api/v1/conta", headers=bearer).status_code == 401
    assert app.test_client().get("/api/v1/conta", headers={"Authorization": f"Bearer {new_token}"}).status_code == 200
    with app.app_context():
        token_event = EventoLog.query.filter_by(modulo="sessoes", tipo="seguranca").one()
        assert token_event.organization_id == 1
        assert token_event.operacao.startswith("Token API regenerado para usuario #")
        combined = f"{token_event.operacao or ''} {token_event.descricao or ''}"
        assert token not in combined
        assert new_token not in combined


def test_formularios_html_principais_executam_fluxos_de_mutacao(tmp_path):
    app, client, ordem_id = _make_pages_client(tmp_path)

    assert _post(client, "/clientes/novo", {"nome": ""}).status_code == 400
    assert _post(client, "/clientes/novo", {
        "nome": "Cliente Form",
        "telefone": "47988887777",
        "email": "cliente.form@example.com",
        "cidade": "Joinville",
        "uf": "SC",
    }).status_code == 302
    with app.app_context():
        cliente = Cliente.query.filter_by(nome="Cliente Form").one()
        cliente_id = cliente.id
    assert _post(client, f"/clientes/{cliente_id}/editar", {
        "nome": "Cliente Form Editado",
        "telefone": "47988887777",
        "email": "cliente.editado@example.com",
        "cidade": "Joinville",
        "uf": "SC",
    }).status_code == 302
    assert _post(client, f"/clientes/{cliente_id}/deletar", {}).status_code == 302

    assert _post(client, "/fornecedores/novo", {"nome": ""}).status_code == 302
    assert _post(client, "/fornecedores/novo", {
        "nome": "Fornecedor Form",
        "telefone": "4733333333",
        "email": "fornecedor@example.com",
        "cep": "89000000",
        "cidade": "Joinville",
    }).status_code == 302
    with app.app_context():
        fornecedor_id = Fornecedor.query.filter_by(nome="Fornecedor Form").one().id
    assert _post(client, f"/fornecedores/{fornecedor_id}/editar", {
        "nome": "Fornecedor Form Editado",
        "telefone": "4733333333",
        "email": "fornecedor.editado@example.com",
        "cep": "89000000",
        "cidade": "Joinville",
    }).status_code == 302
    assert _post(client, f"/fornecedores/{fornecedor_id}/deletar", {}).status_code == 302

    assert _post(client, "/estoque/nova", {"nome": "A"}).status_code == 302
    assert _post(client, "/estoque/nova", {
        "nome": "Peca Form",
        "codigo": "PF-1",
        "categoria": "Teste",
        "localizacao": "A1",
        "quantidade": "3",
        "estoque_minimo": "1",
        "custo": "10",
        "margem": "25",
    }).status_code == 302
    with app.app_context():
        peca_id = Peca.query.filter_by(nome="Peca Form").one().id
    assert _post(client, f"/estoque/{peca_id}/movimentacao", {
        "tipo": "entrada",
        "quantidade": "2",
        "justificativa": "Compra inicial",
    }).status_code == 302
    assert _post(client, f"/estoque/{peca_id}/movimentacao", {
        "tipo": "saida",
        "quantidade": "1",
        "justificativa": "Uso teste",
    }).status_code == 302
    assert _post(client, f"/estoque/{peca_id}/movimentacao", {
        "tipo": "ajuste",
        "quantidade": "4",
        "justificativa": "Contagem teste",
    }).status_code == 302
    assert _post(client, f"/estoque/{peca_id}/deletar", {}).status_code == 302

    assert _post(client, "/financeiro/nova", {"valor": "abc"}).status_code == 302
    assert _post(client, "/financeiro/nova", {
        "tipo": "receita",
        "categoria": "servico",
        "descricao": "Transacao Form",
        "valor": "120",
        "status": "pendente",
        "parcelas": "1",
        "data_vencimento": datetime.now().date().isoformat(),
    }).status_code == 302
    with app.app_context():
        transacao_id = Transacao.query.filter_by(descricao="Transacao Form").one().id
    assert _post(client, f"/financeiro/{transacao_id}/conciliar", {"referencia": "extrato-1"}).status_code == 302
    assert _post(client, f"/financeiro/{transacao_id}/pagar", {}).status_code == 302
    assert _post(client, f"/financeiro/{transacao_id}/deletar", {}).status_code == 302

    assert _post(client, "/os/nova", {"cliente_id": ""}).status_code == 400
    with app.app_context():
        cliente_base_id = Cliente.query.filter_by(nome="Cliente Paginas").one().id
    response = _post(client, "/os/nova", {
        "cliente_id": str(cliente_base_id),
        "tipo_aparelho": "Desktop",
        "marca": "Marca",
        "modelo": "Modelo",
        "defeito_alegado": "Liga e desliga",
        "valor_servico": "150",
        "desconto": "0",
        "garantia_dias": "90",
        "prio": "urgente",
        "status": "recepcao",
    })
    assert response.status_code == 302
    with app.app_context():
        nova_os_id = OrdemServico.query.filter_by(tipo_aparelho="Desktop").one().id
    assert _post(client, f"/os/{nova_os_id}/editar", {
        "tipo_aparelho": "Desktop",
        "marca": "Marca Editada",
        "modelo": "Modelo",
        "defeito_alegado": "Atualizado",
        "valor_servico": "180",
        "desconto": "10",
        "garantia_dias": "120",
        "status": "pronto",
        "prio": "normal",
    }).status_code == 302
    with app.app_context():
        assert OSHistorico.query.filter_by(
            os_id=nova_os_id,
            status_anterior="recepcao",
            status_novo="pronto",
        ).count() == 1
        assert Notification.query.filter_by(
            event_type="os_status_pronto",
            organization_id=1,
        ).count() >= 1
    assert _post(client, f"/os/{nova_os_id}/status", {"status": "status-invalido"}).status_code == 302
    assert _post(client, f"/os/{ordem_id}/deletar", {}).status_code == 302

    assert _post(client, "/coleta/agendar", {"nome": ""}).status_code == 400
    assert _post(client, "/coleta/agendar", {
        "nome": "Cliente Coleta",
        "telefone": "47977776666",
        "endereco": "Rua Teste",
        "numero_casa": "10",
        "cidade": "Joinville",
        "uf": "SC",
        "observacoes": "Buscar na recepcao",
    }).status_code == 302
    with app.app_context():
        coleta_id = ColetaAgendada.query.join(Cliente).filter(Cliente.nome == "Cliente Coleta").one().id
    assert client.get(f"/coletas/{coleta_id}/concluir").status_code == 200
    assert _post(client, f"/coletas/{coleta_id}/concluir", {
        "tipo_aparelho": "Notebook",
        "marca": "Marca",
        "modelo": "Modelo",
        "defeito_alegado": "Nao carrega",
        "garantia_dias": "90",
        "fotos": (BytesIO(b"fake-image"), "foto.png"),
    }).status_code == 302


def test_pwa_e_guardas_de_login_cobrem_fluxos_publicos_e_primeiro_acesso(tmp_path):
    app, client, _ordem_id = _make_pages_client(tmp_path)

    service_worker = client.get("/service-worker.js")
    assert service_worker.status_code == 200
    assert service_worker.headers["Service-Worker-Allowed"] == "/"

    anon = app.test_client()
    assert anon.get("/pwa-start").status_code == 200
    assert anon.get("/").status_code == 302

    empty_app = create_app("development")
    empty_app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    with empty_app.app_context():
        db.drop_all()
        db.create_all()
        from flask import session as flask_session

        from app.routes.pages import login_required

        with empty_app.test_request_context("/"):
            flask_session["usuario_id"] = 999
            response = login_required(lambda: "ok")()
    assert response.status_code == 302
    assert "/primeiro-acesso" in response.location


def test_aliases_zokyo_renderizam_ou_redirecionam_sem_erro(tmp_path):
    app, client, ordem_id = _make_pages_client(tmp_path)
    with app.app_context():
        cliente_id = Cliente.query.filter_by(nome="Cliente Paginas").one().id
        fornecedor_id = Fornecedor.query.filter_by(nome="Fornecedor Paginas").one().id
        peca_id = Peca.query.filter_by(codigo="PAG-1").one().id
        transacao_id = Transacao.query.filter_by(descricao="Entrada").one().id
        admin_id = Usuario.query.filter_by(email="admin.pages@example.com").one().id
        evento = EventoLog(
            organization_id=1,
            usuario_id=admin_id,
            usuario_nome="Admin",
            tipo="edicao",
            modulo="teste",
            operacao="Evento Zokyo",
            descricao="Auditoria Zokyo",
        )
        servico = DefeitoPadrao(
            organization_id=1,
            tipo_aparelho="Notebook",
            sintoma="Limpeza preventiva",
            solucao="Limpeza interna e troca de pasta termica",
        )
        db.session.add_all([evento, servico])
        db.session.commit()
        servico_id = servico.id
        evento_id = evento.id

    paths = [
        "/zokyo",
        "/home",
        "/zokyo/pesquisar?termo=Cliente",
        "/login/verificarLogin",
        "/zokyo/minhaConta",
        "/zokyo/alterarSenha",
        "/mine",
        "/mine/painel",
        "/mine/conta",
        "/mine/editarDados",
        "/mine/os",
        "/mine/minha_ordem_de_servico",
        f"/mine/visualizarOs/{ordem_id}",
        f"/mine/detalhesOs/{ordem_id}",
        f"/mine/imprimirOs/{ordem_id}",
        f"/mine/imprimirCompra/{transacao_id}",
        "/mine/adicionarOs",
        "/mine/compras",
        f"/mine/visualizarCompra/{transacao_id}",
        "/mine/cobrancas",
        f"/mine/atualizarcobranca/{transacao_id}",
        "/mine/cadastrar",
        "/mine/resetarSenha",
        "/zokyo/configurar",
        "/zokyo/emitente",
        "/zokyo/cadastrarEmitente",
        "/zokyo/editarEmitente",
        "/zokyo/editarLogo",
        "/zokyo/atualizarBanco",
        "/zokyo/atualizarZokyo",
        "/zokyo/emails",
        "/zokyo/excluirEmail",
        "/zokyo/backup",
        "/permissoes",
        "/auditoria",
        "/relatorios/clientes",
        "/relatorios/produtos",
        "/relatorios/servicos",
        "/relatorios/os",
        "/relatorios/vendas",
        "/relatorios/financeiro",
        "/relatorios/sku",
        "/relatorios/receitasBrutasMei",
        "/clientes/",
        "/clientes/adicionar",
        f"/clientes/editar/{cliente_id}",
        f"/clientes/visualizar/{cliente_id}",
        "/fornecedores/adicionar",
        f"/fornecedores/editar/{fornecedor_id}",
        f"/fornecedores/visualizar/{fornecedor_id}",
        "/produtos/",
        "/produtos/adicionar",
        f"/produtos/editar/{peca_id}",
        f"/produtos/visualizar/{peca_id}",
        "/servicos/",
        "/servicos/index",
        "/servicos/adicionar",
        f"/servicos/editar/{servico_id}",
        f"/servicos/visualizar/{servico_id}",
        "/vendas/",
        "/vendas/index",
        "/vendas/adicionar",
        "/financeiro/",
        "/financeiro/lancamentos/",
        "/lancamentos/",
        "/financeiro/adicionar",
        "/financeiro/adicionarReceita",
        "/financeiro/adicionarDespesa",
        "/financeiro/adicionarReceita_parc",
        "/lancamentos/adicionar",
        f"/lancamentos/visualizar/{transacao_id}",
        f"/lancamentos/editar/{transacao_id}",
        "/cobrancas/",
        "/cobrancas/cobrancas",
        "/cobrancas/adicionar",
        f"/cobrancas/visualizar/{transacao_id}",
        "/garantias/",
        "/garantias/index",
        "/garantias/adicionar",
        f"/garantias/editar/{ordem_id}",
        f"/garantias/visualizar/{ordem_id}",
        f"/garantias/imprimir/{ordem_id}",
        f"/garantias/imprimirGarantiaOs/{ordem_id}",
        "/arquivos/",
        "/arquivos/adicionar",
        "/arquivos/download/1",
        "/os/",
        "/os/adicionar",
        f"/os/imprimir/{ordem_id}",
        f"/os/imprimirTermica/{ordem_id}",
        f"/os/visualizar/{ordem_id}",
        f"/os/editar/{ordem_id}",
    ]
    for path in paths:
        response = client.get(path, follow_redirects=True)
        assert response.status_code == 200, f"{path}: {response.status_code} {response.get_data(as_text=True)[:300]}"

    assert client.get("/auditoria/clean").status_code == 405
    assert _post(client, "/auditoria/clean", {}).status_code == 302

    relatorio_clientes = client.get("/relatorios/clientes")
    assert relatorio_clientes.status_code == 200
    assert relatorio_clientes.mimetype == "text/csv"
    assert b"Cliente Paginas" in relatorio_clientes.data
    relatorio_produtos_rapid = client.get("/relatorios/produtosRapid")
    assert relatorio_produtos_rapid.status_code == 200
    assert relatorio_produtos_rapid.mimetype == "text/csv"
    assert b"Peca Paginas" in relatorio_produtos_rapid.data

    produto_novo = client.get("/produtos/adicionar")
    assert produto_novo.status_code == 200
    assert b"Adicionar Produto" in produto_novo.data

    produto_editar = client.get(f"/produtos/editar/{peca_id}")
    assert produto_editar.status_code == 200
    assert b"Editar Produto" in produto_editar.data

    produto_ver = client.get(f"/produtos/visualizar/{peca_id}")
    assert produto_ver.status_code == 200
    assert b"Visualizar Produto" in produto_ver.data
    assert b"Peca Paginas" in produto_ver.data

    adiciona_produto_os = _post(client, "/os/adicionarProduto", {
        "idOsProduto": str(ordem_id),
        "idProduto": str(peca_id),
        "quantidade": "2",
        "preco": "25.50",
    })
    assert adiciona_produto_os.status_code == 302
    with app.app_context():
        ordem = db.session.get(OrdemServico, ordem_id)
        peca = db.session.get(Peca, peca_id)
        assert float(ordem.valor_pecas) == 51
        assert peca.quantidade == 3

    adiciona_servico_os = _post(client, "/os/adicionarServico", {
        "idOsServico": str(ordem_id),
        "idServico": str(servico_id),
        "quantidade": "1",
        "preco": "40",
    })
    assert adiciona_servico_os.status_code == 302
    with app.app_context():
        ordem = db.session.get(OrdemServico, ordem_id)
        assert float(ordem.valor_servico) == 140
        assert "Limpeza preventiva" in (ordem.observacoes or "")

    desconto_os = _post(client, "/os/adicionarDesconto", {
        "idOs": str(ordem_id),
        "tipoDesconto": "valor",
        "desconto": "10",
    })
    assert desconto_os.status_code == 302
    faturar_os = _post(client, "/os/faturar", {
        "idOs": str(ordem_id),
        "status": "pago",
        "forma_pagamento": "PIX",
        "vencimento": "2026-07-30",
        "recebimento": "2026-07-30",
    })
    assert faturar_os.status_code == 302
    with app.app_context():
        ordem = db.session.get(OrdemServico, ordem_id)
        receita = Transacao.query.filter_by(os_id=ordem_id, tipo="receita").one()
        receita_os_id = receita.id
        assert float(ordem.desconto) == 10
        assert float(receita.valor) == ordem.valor_total
        assert receita.status == "pago"

    remove_produto_os = _post(client, "/os/excluirProduto", {
        "idOs": str(ordem_id),
        "idProduto": str(peca_id),
    })
    assert remove_produto_os.status_code == 302
    with app.app_context():
        ordem = db.session.get(OrdemServico, ordem_id)
        peca = db.session.get(Peca, peca_id)
        assert float(ordem.valor_pecas) == 0
        assert peca.quantidade == 5

    cliente_novo = client.get("/clientes/adicionar")
    assert cliente_novo.status_code == 200
    assert b"Adicionar Cliente" in cliente_novo.data

    cliente_editar = client.get(f"/clientes/editar/{cliente_id}")
    assert cliente_editar.status_code == 200
    assert b"Editar Cliente" in cliente_editar.data

    cliente_ver = client.get(f"/clientes/visualizar/{cliente_id}")
    assert cliente_ver.status_code == 200
    assert b"Visualizar Cliente" in cliente_ver.data
    assert b"Cliente Paginas" in cliente_ver.data

    fornecedor_novo = client.get("/fornecedores/adicionar")
    assert fornecedor_novo.status_code == 200
    assert b"Adicionar Fornecedor" in fornecedor_novo.data

    fornecedor_editar = client.get(f"/fornecedores/editar/{fornecedor_id}")
    assert fornecedor_editar.status_code == 200
    assert b"Editar Fornecedor" in fornecedor_editar.data

    fornecedor_ver = client.get(f"/fornecedores/visualizar/{fornecedor_id}")
    assert fornecedor_ver.status_code == 200
    assert b"Visualizar Fornecedor" in fornecedor_ver.data
    assert b"Fornecedor Paginas" in fornecedor_ver.data

    lancamento_novo = client.get("/financeiro/adicionar")
    assert lancamento_novo.status_code == 200
    assert "Adicionar Lançamento".encode("utf-8") in lancamento_novo.data

    lancamento_editar = client.get(f"/lancamentos/editar/{transacao_id}")
    assert lancamento_editar.status_code == 200
    assert "Editar Lançamento".encode("utf-8") in lancamento_editar.data

    lancamento_ver = client.get(f"/lancamentos/visualizar/{transacao_id}")
    assert lancamento_ver.status_code == 200
    assert "Visualizar Lançamento".encode("utf-8") in lancamento_ver.data
    assert b"Entrada" in lancamento_ver.data

    venda_nova = client.get("/vendas/adicionar")
    assert venda_nova.status_code == 200
    assert b"Adicionar Venda" in venda_nova.data

    venda_editar = client.get(f"/vendas/editar/{transacao_id}")
    assert venda_editar.status_code == 200
    assert b"Editar Venda" in venda_editar.data

    venda_ver = client.get(f"/vendas/visualizar/{transacao_id}")
    assert venda_ver.status_code == 200
    assert b"Visualizar Venda" in venda_ver.data
    assert client.get(f"/vendas/imprimir/{transacao_id}").mimetype == "application/pdf"
    assert client.get(f"/vendas/imprimirVendaOrcamento/{transacao_id}").mimetype == "application/pdf"
    venda_termica = client.get(f"/vendas/imprimirTermica/{transacao_id}")
    assert venda_termica.status_code == 200
    assert venda_termica.mimetype == "text/plain"
    assert b"COMPROVANTE DE VENDA" in venda_termica.data

    cobranca_ver = client.get(f"/cobrancas/visualizar/{transacao_id}")
    assert cobranca_ver.status_code == 200
    assert "Visualizar Cobrança".encode("utf-8") in cobranca_ver.data

    cobranca_atualizar = _post(client, "/cobrancas/atualizar", {
        "id": str(transacao_id),
        "descricao": "Cobranca Atualizada",
        "valor": "200.50",
        "status": "pendente",
        "vencimento": "2026-07-31",
        "forma_pagamento": "Boleto",
    })
    assert cobranca_atualizar.status_code == 302
    assert _post(client, "/cobrancas/confirmarPagamento", {"id": str(transacao_id), "recebimento": "2026-08-01"}).status_code == 302
    with app.app_context():
        cobranca = db.session.get(Transacao, transacao_id)
        assert cobranca.descricao == "Cobranca Atualizada"
        assert float(cobranca.valor) == 200.5
        assert cobranca.status == "pago"
    assert _post(client, "/cobrancas/enviarEmail", {"id": str(receita_os_id)}).status_code == 302
    with app.app_context():
        notification = Notification.query.filter_by(event_type="billing_charge").one()
        assert notification.recipient == "cliente@example.com"
        assert "Cobrança" in notification.payload["subject"]

    with app.app_context():
        cobranca = db.session.get(Transacao, receita_os_id)
        cobranca.status = "pendente"
        db.session.commit()
    pagamento = _json(client, "post", f"/api/v1/cobrancas/{receita_os_id}/pagamento", {
        "gateway": "asaas",
        "metodo": "pix",
        "dias": 10,
    })
    assert pagamento.status_code == 200
    payload = pagamento.get_json()
    assert payload["payment"]["payment_gateway"] == "pix"
    assert payload["payment"]["payment_method"] == "pix"
    assert payload["payment"]["payload"].startswith("000201")
    assert payload["payment"]["barcode"]
    detalhe_pagamento = _json(client, "get", f"/api/v1/cobrancas/{receita_os_id}/pagamento")
    assert detalhe_pagamento.status_code == 200
    assert detalhe_pagamento.get_json()["payment"]["payload"] == payload["payment"]["payload"]

    assert _post(client, "/cobrancas/cancelar", {"id": str(transacao_id)}).status_code == 302
    with app.app_context():
        assert db.session.get(Transacao, transacao_id).status == "cancelado"

    garantia_nova = client.get("/garantias/adicionar")
    assert garantia_nova.status_code == 200
    assert b"Adicionar Garantia" in garantia_nova.data

    garantia_editar = client.get(f"/garantias/editar/{ordem_id}")
    assert garantia_editar.status_code == 200
    assert b"Editar Garantia" in garantia_editar.data

    garantia_post = _post(client, "/garantias/adicionar", {
        "os_id": str(ordem_id),
        "data_saida": "2026-07-28",
        "garantia_dias": "120",
        "observacoes": "Garantia Zokyo",
    })
    assert garantia_post.status_code == 302

    garantia_ver = client.get(f"/garantias/visualizar/{ordem_id}")
    assert garantia_ver.status_code == 200
    assert b"Visualizar Garantia" in garantia_ver.data
    assert b"120 dias" in garantia_ver.data

    permissoes_page = client.get("/permissoes")
    assert permissoes_page.status_code == 200
    assert "Permissões".encode("utf-8") in permissoes_page.data

    permissoes_post = _post(client, f"/permissoes/editar/{admin_id}", {
        "permissoes_extra": "logs.view",
    })
    assert permissoes_post.status_code == 302
    with app.app_context():
        admin = db.session.get(Usuario, admin_id)
        assert "logs.view" in (admin.permissoes_extra or [])

    auditoria_page = client.get("/auditoria?modulo=teste")
    assert auditoria_page.status_code == 200
    assert b"Auditoria" in auditoria_page.data
    assert b"Auditoria Zokyo" in auditoria_page.data
    assert client.post("/auditoria/clean", data={"_csrf_token": "csrf-pages"}).status_code == 302
    with app.app_context():
        assert db.session.get(EventoLog, evento_id) is not None

    configurar_page = client.get("/zokyo/configurar")
    assert configurar_page.status_code == 200
    assert b"Configurar Sistema" in configurar_page.data

    emitente_page = client.get("/zokyo/emitente")
    assert emitente_page.status_code == 200
    assert b"Emitente" in emitente_page.data

    backup_page = client.get("/zokyo/backup")
    assert backup_page.status_code == 200
    assert b"Backup" in backup_page.data
    assert b"clientes" in backup_page.data

    arquivo_novo = client.get("/arquivos/adicionar")
    assert arquivo_novo.status_code == 200
    assert b"Adicionar Arquivo" in arquivo_novo.data

    upload = client.post(
        "/arquivos/adicionar",
        data={
            "_csrf_token": "csrf-pages",
            "os_id": str(ordem_id),
            "descricao": "Foto teste Zokyo",
            "fotos": (BytesIO(b"fake-image"), "zokyo-test.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert upload.status_code == 302
    with app.app_context():
        foto_id = OSFoto.query.filter_by(original_filename="zokyo-test.png").one().id

    arquivo_ver = client.get(f"/arquivos/visualizar/{foto_id}")
    assert arquivo_ver.status_code == 200
    assert b"Visualizar Arquivo" in arquivo_ver.data
    assert b"zokyo-test.png" in arquivo_ver.data

    assert _post(client, f"/lancamentos/editar/{transacao_id}", {
        "tipo": "receita",
        "categoria": "servico",
        "descricao": "Entrada Editada",
        "valor": "150.25",
        "status": "pendente",
        "data_vencimento": "2026-07-30",
        "forma_pagamento": "PIX",
        "comissao_percentual": "0",
    }).status_code == 302


def test_paginas_html_cobrem_filtros_alertas_e_consultas(tmp_path):
    app, client, ordem_id = _make_pages_client(tmp_path)
    with app.app_context():
        cfg = Configuracao.get()
        cfg.alerta_caixa_minimo = 500
        cfg.meta_receita_mensal = 100
        cfg.alerta_vencimento_dias = 10
        cliente = Cliente.query.filter_by(nome="Cliente Paginas").one()
        cliente.ativo = False
        peca = Peca.query.filter_by(codigo="PAG-1").one()
        peca.categoria = "Filtro"
        peca.quantidade = 1
        peca.estoque_minimo = 5
        ordem = db.session.get(OrdemServico, ordem_id)
        ordem.status = "pronto"
        ordem.prio = "urgente"
        ordem.data_prev = datetime.now() - timedelta(days=2)
        atrasada = OrdemServico(
            organization_id=1,
            cliente_id=cliente.id,
            usuario_id=ordem.usuario_id,
            tipo_aparelho="Tablet",
            marca="BuscaEspecial",
            modelo="Modelo_%_Busca",
            defeito_alegado="Tela",
            status="em_reparo",
            prio="normal",
            data_prev=datetime.now() - timedelta(days=3),
        )
        receita_paga = Transacao(
            organization_id=1,
            tipo="receita",
            categoria="servico",
            descricao="Receita paga",
            valor=80,
            status="pago",
            data_vencimento=datetime.now(),
            data_pagamento=datetime.now(),
        )
        despesa_paga = Transacao(
            organization_id=1,
            tipo="despesa",
            categoria="compra",
            descricao="Despesa paga",
            valor=120,
            status="pago",
            data_vencimento=datetime.now(),
            data_pagamento=datetime.now(),
        )
        db.session.add_all([atrasada, receita_paga, despesa_paga])
        db.session.commit()

    assert client.get("/").status_code == 200
    assert client.get("/os?q=Busca%25_&status=em_reparo&prio=normal&page=1").status_code == 200
    assert client.get("/clientes?q=47999999999&ativo=0").status_code == 200
    assert client.get("/estoque?q=PAG%25&cat=Filtro&critico=1&page=1").status_code == 200
    assert client.get("/fornecedores?q=Fornecedor%25").status_code == 200
    assert client.get("/financeiro?preset=semana&tipo=receita&status=pendente").status_code == 200
    assert client.get("/financeiro?preset=ano").status_code == 200
    assert client.get("/financeiro?data_ini=invalida&data_fim=invalida").status_code == 200
    assert client.get("/pwa-start").status_code == 200


def test_coleta_html_cobre_cancelamento_e_erros_de_conclusao(tmp_path):
    app, client, ordem_id = _make_pages_client(tmp_path)
    with app.app_context():
        cliente = Cliente.query.filter_by(nome="Cliente Paginas").one()
        admin = Usuario.query.filter_by(email="admin.pages@example.com").one()
        coleta_agendada = ColetaAgendada(
            organization_id=1,
            cliente_id=cliente.id,
            usuario_id=admin.id,
            status="agendada",
            observacoes="Buscar no balcao",
            endereco="Rua A",
            numero_casa="10",
            cidade="Joinville",
            uf="SC",
        )
        coleta_concluida = ColetaAgendada(
            organization_id=1,
            cliente_id=cliente.id,
            usuario_id=admin.id,
            status="concluida",
            os_id=ordem_id,
        )
        coleta_cancelada = ColetaAgendada(
            organization_id=1,
            cliente_id=cliente.id,
            usuario_id=admin.id,
            status="cancelada",
        )
        db.session.add_all([coleta_agendada, coleta_concluida, coleta_cancelada])
        db.session.commit()
        agendada_id = coleta_agendada.id
        concluida_id = coleta_concluida.id
        cancelada_id = coleta_cancelada.id

    assert _post(client, f"/coletas/{agendada_id}/cancelar", {}).status_code == 302
    assert _post(client, f"/coletas/{concluida_id}/cancelar", {}).status_code == 302
    assert client.get(f"/coletas/{concluida_id}/concluir").status_code == 302
    assert _post(client, f"/coletas/{concluida_id}/concluir", {}).status_code == 302
    assert _post(client, f"/coletas/{cancelada_id}/concluir", {}).status_code == 302

    with app.app_context():
        cliente = Cliente.query.filter_by(nome="Cliente Paginas").one()
        admin = Usuario.query.filter_by(email="admin.pages@example.com").one()
        coleta_erro = ColetaAgendada(organization_id=1, cliente_id=cliente.id, usuario_id=admin.id)
        coleta_upload = ColetaAgendada(organization_id=1, cliente_id=cliente.id, usuario_id=admin.id)
        coleta_garantia = ColetaAgendada(organization_id=1, cliente_id=cliente.id, usuario_id=admin.id)
        db.session.add_all([coleta_erro, coleta_upload, coleta_garantia])
        db.session.commit()
        erro_id = coleta_erro.id
        upload_id = coleta_upload.id
        garantia_id = coleta_garantia.id

    assert _post(client, f"/coletas/{erro_id}/concluir", {
        "tipo_aparelho": "",
        "marca": "",
        "modelo": "",
        "defeito_alegado": "",
    }).status_code == 400
    assert _post(client, f"/coletas/{upload_id}/concluir", {
        "tipo_aparelho": "Notebook",
        "marca": "Marca",
        "modelo": "Modelo",
        "defeito_alegado": "Falha",
        "fotos": (BytesIO(b"texto"), "foto.txt"),
    }).status_code == 400
    assert _post(client, f"/coletas/{garantia_id}/concluir", {
        "tipo_aparelho": "Notebook",
        "marca": "Marca",
        "modelo": "Modelo",
        "defeito_alegado": "Falha",
        "garantia_dias": "abc",
    }).status_code == 400


def test_os_html_cobre_validacoes_status_pdf_foto_e_devolucao_estoque(monkeypatch, tmp_path):
    app, client, ordem_id = _make_pages_client(tmp_path)
    with app.app_context():
        cliente_id = Cliente.query.filter_by(nome="Cliente Paginas").one().id
        peca = Peca.query.filter_by(codigo="PAG-1").one()
        peca.quantidade = 4
        db.session.execute(
            db.text("INSERT INTO os_pecas (os_id, peca_id, quantidade, valor_unitario) VALUES (:os, :peca, 2, 10)"),
            {"os": ordem_id, "peca": peca.id},
        )
        db.session.commit()

    assert _post(client, "/os/nova", {"cliente_id": "999999"}).status_code == 400
    assert _post(client, "/os/nova", {
        "cliente_id": str(cliente_id),
        "valor_servico": "abc",
    }).status_code == 400
    assert _post(client, "/os/nova", {
        "cliente_id": str(cliente_id),
        "valor_servico": "-1",
        "desconto": "0",
        "garantia_dias": "90",
    }).status_code == 400
    assert _post(client, "/os/nova", {
        "cliente_id": str(cliente_id),
        "valor_servico": "10",
        "desconto": "20",
        "garantia_dias": "90",
    }).status_code == 400
    response = _post(client, "/os/nova", {
        "cliente_id": str(cliente_id),
        "tipo_aparelho": "Monitor",
        "marca": "Marca",
        "modelo": "Modelo",
        "defeito_alegado": "Imagem",
        "valor_servico": "20",
        "desconto": "0",
        "garantia_dias": "30",
        "status": "fora-da-lista",
        "prio": "fora-da-lista",
    })
    assert response.status_code == 302

    base_update = {
        "tipo_aparelho": "Notebook",
        "marca": "Marca",
        "modelo": "Modelo",
        "defeito_alegado": "Falha",
        "valor_servico": "100",
        "desconto": "0",
        "garantia_dias": "90",
        "status": "recepcao",
        "prio": "normal",
    }
    for extra in (
        {"valor_servico": "abc"},
        {"valor_servico": "-1"},
        {"desconto": "200"},
        {"data_entrada": "data-ruim"},
        {"data_saida": "data-ruim"},
        {"data_prev": "data-ruim"},
    ):
        payload = {**base_update, **extra}
        assert _post(client, f"/os/{ordem_id}/editar", payload).status_code == 400

    fake_notification = type("NotificationStub", (), {"id": 1, "payload": {"last_result": {"sucesso": True}}})()
    monkeypatch.setattr("app.services.notifications.enqueue_email", lambda *args, **kwargs: (fake_notification, True))
    monkeypatch.setattr("app.services.notifications.enqueue_whatsapp", lambda *args, **kwargs: (fake_notification, True))
    monkeypatch.setattr("app.services.notifications.process_notification", lambda *_args, **_kwargs: fake_notification)
    monkeypatch.setattr("app.services.message_templates.render_template", lambda *args, **kwargs: ("Assunto", "Corpo"))
    assert _post(client, f"/os/{ordem_id}/status", {"status": "pronto"}).status_code == 302
    assert _post(client, f"/os/{ordem_id}/status", {"status": "cancelado"}).status_code == 302

    monkeypatch.setattr("app.utils.pdf_gen.gerar_pdf_os", lambda _os: (_ for _ in ()).throw(RuntimeError("sem pdf")))
    assert client.get(f"/os/{ordem_id}/pdf").status_code == 302

    with app.app_context():
        admin = Usuario.query.filter_by(email="admin.pages@example.com").one()
        foto = OSFoto(
            organization_id=1,
            os_id=ordem_id,
            usuario_id=admin.id,
            filename="os_fotos/inexistente.png",
            original_filename="inexistente.png",
            mime_type="image/png",
        )
        db.session.add(foto)
        db.session.commit()
        foto_id = foto.id
    assert client.get(f"/uploads/os-fotos/{foto_id}").status_code == 404


def test_estoque_fornecedores_clientes_e_financeiro_cobrem_erros_restantes(tmp_path):
    app, client, _ordem_id = _make_pages_client(tmp_path)

    assert _post(client, "/estoque/nova", {
        "nome": "Peca Invalida",
        "quantidade": "abc",
    }).status_code == 302
    assert _post(client, "/estoque/nova", {
        "nome": "Peca Negativa",
        "quantidade": "-1",
        "estoque_minimo": "1",
        "custo": "0",
        "margem": "0",
    }).status_code == 302
    with app.app_context():
        admin = Usuario.query.filter_by(email="admin.pages@example.com").one()
        peca_sem_historico = Peca(organization_id=1, nome="Peca Sem Historico", quantidade=0, estoque_minimo=1)
        peca_movimento = Peca(organization_id=1, nome="Peca Movimento", quantidade=1, estoque_minimo=1)
        db.session.add_all([peca_sem_historico, peca_movimento])
        db.session.flush()
        movimento = InventoryMovement(
            organization_id=1,
            part_id=peca_movimento.id,
            user_id=admin.id,
            movement_type="entrada",
            quantity_delta=1,
            quantity_before=0,
            quantity_after=1,
            reason="Historico",
        )
        db.session.add(movimento)
        db.session.commit()
        sem_historico_id = peca_sem_historico.id
        movimento_id = peca_movimento.id

    assert _post(client, f"/estoque/{movimento_id}/movimentacao", {"tipo": "x"}).status_code == 302
    assert _post(client, f"/estoque/{movimento_id}/movimentacao", {
        "tipo": "entrada",
        "quantidade": "abc",
    }).status_code == 302
    assert _post(client, f"/estoque/{movimento_id}/movimentacao", {
        "tipo": "entrada",
        "quantidade": "-1",
    }).status_code == 302
    assert _post(client, f"/estoque/{movimento_id}/movimentacao", {
        "tipo": "entrada",
        "quantidade": "1000000",
    }).status_code == 302
    assert _post(client, f"/estoque/{movimento_id}/movimentacao", {
        "tipo": "entrada",
        "quantidade": "1",
        "justificativa": "abc",
    }).status_code == 302
    assert _post(client, f"/estoque/{movimento_id}/movimentacao", {
        "tipo": "saida",
        "quantidade": "999",
        "justificativa": "Teste estoque",
    }).status_code == 302
    assert _post(client, f"/estoque/{movimento_id}/deletar", {}).status_code == 302
    assert _post(client, f"/estoque/{sem_historico_id}/deletar", {}).status_code == 302

    assert _post(client, "/fornecedores/novo", {"nome": "Fornecedor X", "cnpj": "111"}).status_code == 302
    assert _post(client, "/fornecedores/novo", {
        "nome": "Fornecedor X",
        "email": "email-invalido",
    }).status_code == 302
    assert _post(client, "/fornecedores/novo", {
        "nome": "Fornecedor X",
        "cep": "123",
    }).status_code == 302
    with app.app_context():
        fornecedor_id = Fornecedor.query.filter_by(nome="Fornecedor Paginas").one().id
    assert _post(client, f"/fornecedores/{fornecedor_id}/editar", {"nome": ""}).status_code == 302
    assert _post(client, f"/fornecedores/{fornecedor_id}/editar", {
        "nome": "Fornecedor Paginas",
        "cnpj": "111",
    }).status_code == 302
    assert _post(client, f"/fornecedores/{fornecedor_id}/editar", {
        "nome": "Fornecedor Paginas",
        "email": "email-invalido",
    }).status_code == 302
    assert _post(client, f"/fornecedores/{fornecedor_id}/editar", {
        "nome": "Fornecedor Paginas",
        "cep": "123",
    }).status_code == 302

    assert _post(client, "/clientes/novo", {
        "nome": "Cliente Paginas",
        "telefone": "47999999999",
    }).status_code == 400
    with app.app_context():
        cliente_id = Cliente.query.filter_by(nome="Cliente Paginas").one().id
        outro = Cliente(organization_id=1, nome="Outro Cliente", telefone="47999999999")
        db.session.add(outro)
        db.session.commit()
        outro_id = outro.id
    assert _post(client, f"/clientes/{outro_id}/editar", {
        "nome": "Cliente Paginas",
        "telefone": "47999999999",
    }).status_code == 400
    assert client.get("/clientes?ativo=1").status_code == 200
    assert _post(client, f"/clientes/{cliente_id}/deletar", {}).status_code == 302

    assert _post(client, "/financeiro/nova", {"valor": "-1"}).status_code == 302
    assert _post(client, "/financeiro/nova", {"valor": "10", "tipo": "invalido"}).status_code == 302
    assert _post(client, "/financeiro/nova", {
        "valor": "10",
        "tipo": "receita",
        "descricao": "",
    }).status_code == 302
    assert _post(client, "/financeiro/nova", {
        "valor": "10000000",
        "tipo": "receita",
        "descricao": "Valor alto",
    }).status_code == 302
    assert _post(client, "/financeiro/nova", {
        "valor": "10",
        "tipo": "receita",
        "descricao": "Comissao invalida",
        "comissao_usuario_id": "999999",
    }).status_code == 302
    assert _post(client, "/financeiro/nova", {
        "valor": "10",
        "tipo": "receita",
        "descricao": "Status fallback",
        "status": "fora",
        "parcelas": "1",
    }).status_code == 302
    with app.app_context():
        transacao_id = Transacao.query.filter_by(descricao="Status fallback").one().id
    assert _post(client, f"/financeiro/{transacao_id}/conciliar", {"referencia": "ab"}).status_code == 302


def test_pages_cobre_bordas_restantes_de_coleta_os_pdf_foto_e_notificacao(monkeypatch, tmp_path):
    app, client, ordem_id = _make_pages_client(tmp_path)

    from app.routes.pages import _date_trunc_day, _date_trunc_month, _validar_fotos

    class _Dialect:
        name = "mysql"

    class _Bind:
        dialect = _Dialect()

    monkeypatch.setattr("app.routes.pages.db.session.get_bind", lambda: _Bind())
    assert "date_format" in str(_date_trunc_month(Transacao.criado_em)).lower()
    assert "date_format" in str(_date_trunc_day(Transacao.criado_em)).lower()
    fotos_demais = [
        FileStorage(stream=BytesIO(b"png"), filename=f"foto-{idx}.png", content_type="image/png")
        for idx in range(13)
    ]
    assert _validar_fotos(fotos_demais)[1] == ["Envie no maximo 12 fotos por coleta."]

    assert _post(client, "/coleta/agendar", {
        "nome": "Cliente Invalido",
        "cpf_cnpj": "111",
        "telefone": "123",
        "cep": "123",
        "uf": "XX",
        "data_agendada": "data-ruim",
    }).status_code == 400

    with app.app_context():
        admin = Usuario.query.filter_by(email="admin.pages@example.com").one()
        admin_id = admin.id
        cliente_cpf = Cliente(
            organization_id=1,
            nome="Cliente CPF",
            cpf="52998224725",
            telefone=None,
            cep=None,
            endereco=None,
            numero_casa=None,
            cidade=None,
            uf=None,
        )
        cliente_cnpj = Cliente(organization_id=1, nome="Cliente CNPJ", cnpj="04252011000110")
        db.session.add_all([cliente_cpf, cliente_cnpj])
        db.session.commit()

    assert _post(client, "/coleta/agendar", {
        "nome": "Cliente CPF",
        "cpf_cnpj": "52998224725",
        "telefone": "47911112222",
        "cep": "89201000",
        "endereco": "Rua Atualizada",
        "numero_casa": "100",
        "cidade": "Joinville",
        "uf": "SC",
    }).status_code == 302
    assert _post(client, "/coleta/agendar", {
        "nome": "Cliente CNPJ",
        "cpf_cnpj": "04252011000110",
    }).status_code == 302

    with app.app_context():
        cliente = Cliente.query.filter_by(nome="Cliente Paginas").one()
        coleta = ColetaAgendada(organization_id=1, cliente_id=cliente.id, usuario_id=admin_id, observacoes="Obs")
        coleta_limite = ColetaAgendada(organization_id=1, cliente_id=cliente.id, usuario_id=admin_id)
        db.session.add_all([coleta, coleta_limite])
        db.session.commit()
        coleta_id = coleta.id
        coleta_limite_id = coleta_limite.id
        cliente_id = cliente.id

    monkeypatch.setattr("app.routes.pages._check_order_limit", lambda: (_ for _ in ()).throw(PermissionError("limite")))
    assert _post(client, f"/coletas/{coleta_limite_id}/concluir", {
        "tipo_aparelho": "Notebook",
        "marca": "Marca",
        "modelo": "Modelo",
        "defeito_alegado": "Falha",
        "garantia_dias": "90",
        "fotos": (BytesIO(b"fake-image"), "foto.png"),
    }).status_code == 302
    assert _post(client, "/os/nova", {"cliente_id": str(cliente_id)}).status_code == 400
    monkeypatch.setattr("app.routes.pages._check_order_limit", lambda: None)

    assert _post(client, f"/coletas/{coleta_id}/concluir", {
        "tipo_aparelho": "Notebook",
        "marca": "Marca",
        "modelo": "Modelo",
        "defeito_alegado": "Falha",
        "garantia_dias": "abc",
        "fotos": (BytesIO(b"fake-image"), "foto.png"),
    }).status_code == 400
    assert _post(client, f"/coletas/{coleta_id}/concluir", {
        "tipo_aparelho": "Notebook",
        "marca": "Marca",
        "modelo": "Modelo",
        "defeito_alegado": "Falha",
        "prio": "fora",
        "garantia_dias": "90",
        "fotos": (BytesIO(b"fake-image"), "foto.png"),
    }).status_code == 302

    assert client.get("/os?q=47999999999").status_code == 200
    assert _post(client, f"/os/{ordem_id}/editar", {
        "tipo_aparelho": "Notebook",
        "marca": "Marca",
        "modelo": "Modelo",
        "defeito_alegado": "Falha",
        "valor_servico": "120",
        "desconto": "10",
        "garantia_dias": "90",
        "status": "recepcao",
        "prio": "normal",
        "data_entrada": "2026-01-01",
        "data_saida": "2026-01-02",
        "data_prev": "2026-01-03",
    }).status_code == 302

    fake_notification = type("NotificationStub", (), {"id": 1, "payload": {"last_result": {"sucesso": False, "modo": "simulacao", "link": "https://wa.me/1"}}})()
    monkeypatch.setattr("app.services.notifications.enqueue_email", lambda *args, **kwargs: (fake_notification, True))
    monkeypatch.setattr("app.services.notifications.enqueue_whatsapp", lambda *args, **kwargs: (fake_notification, True))
    monkeypatch.setattr("app.services.notifications.process_notification", lambda *_args, **_kwargs: fake_notification)
    monkeypatch.setattr("app.services.message_templates.render_template", lambda *args, **kwargs: ("Assunto", "Corpo"))
    assert _post(client, f"/os/{ordem_id}/status", {"status": "pronto"}).status_code == 302

    with app.app_context():
        cliente_sem_fone = Cliente(organization_id=1, nome="Sem Fone", email="")
        db.session.add(cliente_sem_fone)
        db.session.flush()
        sem_fone = OrdemServico(
            organization_id=1,
            cliente_id=cliente_sem_fone.id,
            usuario_id=admin_id,
            tipo_aparelho="Desktop",
            defeito_alegado="Falha",
            status="recepcao",
            valor_servico=50,
        )
        falha_wpp = OrdemServico(
            organization_id=1,
            cliente_id=cliente_id,
            usuario_id=admin_id,
            tipo_aparelho="Desktop",
            defeito_alegado="Falha",
            status="recepcao",
            valor_servico=60,
        )
        entrega = OrdemServico(
            organization_id=1,
            cliente_id=cliente_id,
            usuario_id=admin_id,
            tipo_aparelho="Desktop",
            defeito_alegado="Falha",
            status="recepcao",
            valor_servico=70,
        )
        db.session.add_all([sem_fone, falha_wpp, entrega])
        db.session.commit()
        sem_fone_id = sem_fone.id
        falha_wpp_id = falha_wpp.id
        entrega_id = entrega.id

    assert _post(client, f"/os/{sem_fone_id}/status", {"status": "pronto"}).status_code == 302
    fake_notification.payload["last_result"] = {"sucesso": False, "erro": "fora", "link": "https://wa.me/1"}
    assert _post(client, f"/os/{falha_wpp_id}/status", {"status": "pronto"}).status_code == 302
    assert _post(client, f"/os/{entrega_id}/status", {"status": "entregue"}).status_code == 302

    monkeypatch.setattr("app.utils.pdf_gen.gerar_pdf_os", lambda _os: b"%PDF-pages")
    pdf_response = client.get(f"/os/{entrega_id}/pdf")
    assert pdf_response.status_code == 200
    assert pdf_response.mimetype == "application/pdf"

    with app.app_context():
        photo_path = tmp_path / "uploads" / "os_fotos" / "ok.png"
        photo_path.parent.mkdir(parents=True, exist_ok=True)
        photo_path.write_bytes(b"png")
        foto = OSFoto(
            organization_id=1,
            os_id=entrega_id,
            usuario_id=admin_id,
            filename="os_fotos/ok.png",
            original_filename="ok.png",
            mime_type="image/png",
        )
        db.session.add(foto)
        db.session.execute(
            db.text("INSERT INTO os_pecas (os_id, peca_id, quantidade, valor_unitario) VALUES (:os, :peca, 1, 10)"),
            {"os": entrega_id, "peca": Peca.query.filter_by(codigo="PAG-1").one().id},
        )
        db.session.commit()
        foto_id = foto.id

    assert client.get(f"/uploads/os-fotos/{foto_id}").status_code == 200
    assert _post(client, f"/os/{entrega_id}/deletar", {}).status_code == 302

    with app.app_context():
        from flask import session as flask_session

        from app.routes.pages import os_deletar

        with app.test_request_context(f"/os/{ordem_id}/deletar", method="POST"):
            flask_session["usuario_id"] = admin_id
            flask_session["nivel"] = "operacional"
            flask_session["_csrf_token"] = "csrf-pages"
            response = os_deletar.__wrapped__(ordem_id)
    assert response.status_code == 302

    with app.app_context():
        outro = Cliente(organization_id=1, nome="Cliente Outro", telefone="47911112222")
        db.session.add(outro)
        db.session.commit()
        outro_id = outro.id
    assert _post(client, f"/clientes/{outro_id}/editar", {
        "nome": "Cliente CPF",
        "telefone": "47911112222",
    }).status_code == 400
    assert _post(client, f"/clientes/{outro_id}/editar", {
        "nome": "A",
        "telefone": "123",
        "cep": "123",
    }).status_code == 400
