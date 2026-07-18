import os
from datetime import datetime, timedelta
from io import BytesIO

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from werkzeug.datastructures import FileStorage

from app import create_app
from app.extensions import db
from app.models import (
    Cliente,
    ColetaAgendada,
    Configuracao,
    Fornecedor,
    InventoryMovement,
    OrdemServico,
    Organization,
    OSFoto,
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
        config = Configuracao(organization_id=1, nome_empresa="Empresa Teste", cnpj="04252011000110")
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


def _post(client, path, data):
    payload = {"_csrf_token": "csrf-pages"}
    payload.update(data)
    return client.post(path, data=payload)


def test_paginas_principais_autenticadas_renderizam_sem_erro(monkeypatch, tmp_path):
    monkeypatch.setenv("PLATFORM_ADMIN_EMAILS", "admin.pages@example.com")
    _app, client, ordem_id = _make_pages_client(tmp_path)
    paths = [
        "/",
        "/ajuda",
        "/clientes",
        "/os",
        "/os/nova",
        f"/os/{ordem_id}",
        f"/os/{ordem_id}/editar",
        "/estoque",
        "/estoque/movimentacoes",
        "/fornecedores",
        "/financeiro",
        "/coleta",
        "/relatorios",
        "/usuarios",
        "/configuracoes",
        "/configuracoes/notificacoes",
        "/logs",
        "/importacao/cplus",
        "/platform",
        "/privacidade/retencao",
        "/laudos/",
        "/laudos/novo",
        "/laudos/templates",
    ]

    for path in paths:
        response = client.get(path)
        assert response.status_code == 200, f"{path}: {response.status_code} {response.get_data(as_text=True)[:300]}"


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
        "status": "entregue",
        "prio": "normal",
    }).status_code == 302
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
