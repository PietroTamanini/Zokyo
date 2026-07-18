from datetime import datetime, timezone

from app import create_app
from app.extensions import db
from app.models import Cliente, Notification, OrdemServico, Organization, SavedReport, Transacao, Usuario
from app.services.scheduled_reports import process_scheduled_reports


def make_app():
    app = create_app("development")
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    with app.app_context():
        db.create_all()
        org1 = Organization(id=1, nome="Um", slug="um")
        org2 = Organization(id=2, nome="Dois", slug="dois")
        finance = Usuario(nome="Financeiro", email="fin@example.com", nivel="financeiro", ativo=True, organization_id=1)
        operation = Usuario(nome="Operacao", email="op@example.com", nivel="operacional", ativo=True, organization_id=1)
        other = Usuario(nome="Outro", email="other@example.com", nivel="admin", ativo=True, organization_id=2)
        for user in (finance, operation, other):
            user.set_senha("Senha!123")
        visible_client = Cliente(nome="=CLIENTE VISIVEL", telefone="47999999999", organization_id=1)
        hidden_client = Cliente(nome="CLIENTE OCULTO", telefone="47999999998", organization_id=2)
        db.session.add_all([org1, org2, finance, operation, other, visible_client, hidden_client])
        db.session.flush()
        now = datetime.now(timezone.utc)
        db.session.add_all([
            OrdemServico(
                organization_id=1, cliente_id=visible_client.id, usuario_id=finance.id,
                tipo_aparelho="Notebook", marca="Dell", modelo="XPS", status="recepcao",
                valor_servico=100, data_entrada=now,
            ),
            OrdemServico(
                organization_id=2, cliente_id=hidden_client.id, usuario_id=other.id,
                tipo_aparelho="Oculto", marca="Oculta", modelo="Oculto", status="recepcao",
                valor_servico=900, data_entrada=now,
            ),
            Transacao(organization_id=1, tipo="receita", valor=100, status="pago", criado_em=now),
            Transacao(organization_id=2, tipo="receita", valor=900, status="pago", criado_em=now),
        ])
        db.session.commit()
        return app, finance.id, operation.id


def login(client, user_id, role):
    with client.session_transaction() as session:
        session["usuario_id"] = user_id
        session["nivel"] = role
        session["_last_active"] = 9999999999


def test_relatorio_e_exportacoes_respeitam_tenant():
    app, finance_id, _operation_id = make_app()
    client = app.test_client()
    login(client, finance_id, "financeiro")
    current_day = datetime.now(timezone.utc).date().isoformat()
    period = f"?inicio={current_day}&fim={current_day}"

    page = client.get(f"/relatorios{period}")
    csv_response = client.get(f"/relatorios/ordens.csv{period}")
    xlsx = client.get(f"/relatorios/gerencial.xlsx{period}")
    pdf = client.get(f"/relatorios/gerencial.pdf{period}")

    assert page.status_code == 200
    assert "CLIENTE OCULTO" not in page.get_data(as_text=True)
    assert "R$ 100,00" in page.get_data(as_text=True)
    csv_text = csv_response.data.decode("utf-8-sig")
    assert "'=CLIENTE VISIVEL" in csv_text
    assert "CLIENTE OCULTO" not in csv_text
    assert xlsx.data.startswith(b"PK")
    assert pdf.data.startswith(b"%PDF")


def test_relatorio_normaliza_periodos_invalidos_invertidos_e_longos():
    app, finance_id, _operation_id = make_app()
    client = app.test_client()
    login(client, finance_id, "financeiro")

    assert client.get("/relatorios?inicio=invalido&fim=invalido").status_code == 200
    assert client.get("/relatorios?inicio=2026-12-31&fim=2026-01-01").status_code == 200
    assert client.get("/relatorios?inicio=2020-01-01&fim=2026-12-31").status_code == 200


def test_operacional_sem_permissao_nao_acessa_relatorios():
    app, _finance_id, operation_id = make_app()
    client = app.test_client()
    login(client, operation_id, "operacional")
    assert client.get("/relatorios").status_code == 403
    assert client.get("/relatorios/ordens.csv").status_code == 403


def test_filtro_salvo_e_relatorio_agendado_entram_na_fila():
    app, finance_id, _ = make_app()
    client = app.test_client()
    login(client, finance_id, "financeiro")
    with client.session_transaction() as current:
        current["_csrf_token"] = "report-csrf"
    response = client.post("/relatorios/salvos", data={
        "_csrf_token": "report-csrf", "nome": "Resumo diario", "inicio": "2026-01-01",
        "fim": "2026-12-31", "frequencia": "daily", "destinatario": "gestor@example.com",
    })
    assert response.status_code == 302
    with app.app_context():
        report = SavedReport.query.one()
        report.next_run_at = datetime.now(timezone.utc)
        report_id = report.id
        db.session.commit()
        assert process_scheduled_reports() == 1
        notification = Notification.query.filter_by(event_type="scheduled_report").one()
        assert notification.recipient == "gestor@example.com"
        assert report.last_run_at is not None

    invalid_name = client.post("/relatorios/salvos", data={
        "_csrf_token": "report-csrf", "nome": "", "frequencia": "daily", "destinatario": "gestor@example.com",
    })
    invalid_frequency = client.post("/relatorios/salvos", data={
        "_csrf_token": "report-csrf", "nome": "Ruim", "frequencia": "yearly", "destinatario": "gestor@example.com",
    })
    invalid_email = client.post("/relatorios/salvos", data={
        "_csrf_token": "report-csrf", "nome": "Ruim", "frequencia": "weekly", "destinatario": "email-ruim",
    })
    delete_response = client.post(f"/relatorios/salvos/{report_id}/excluir", data={"_csrf_token": "report-csrf"})

    assert invalid_name.status_code == 302
    assert invalid_frequency.status_code == 302
    assert invalid_email.status_code == 302
    assert delete_response.status_code == 302
