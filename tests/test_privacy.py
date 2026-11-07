import json
import zipfile

from app import create_app
from app.extensions import db
from app.models import Cliente, ColetaAgendada, ConsentRecord, DataSubjectRequest, EventoLog, OrdemServico, Organization, Usuario
from app.services.privacy import anonymize_client, export_subject_data, has_active_consent, register_consent


def make_app():
    app = create_app("development")
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    with app.app_context():
        db.create_all()
        organization = Organization(id=1, nome="Privacy", slug="privacy")
        user = Usuario(nome="Admin", email="privacy@example.com", nivel="admin", ativo=True, organization_id=1)
        user.set_senha("Senha!123")
        client = Cliente(
            nome="Titular", cpf="52998224725", telefone="47999999999",
            email="titular@example.com", endereco="Rua Teste", organization_id=1,
        )
        db.session.add_all([organization, user, client])
        db.session.commit()
        return app, user.id, client.id


def test_consentimento_exportacao_e_anonimizacao_auditaveis():
    app, user_id, client_id = make_app()
    with app.app_context():
        user = db.session.get(Usuario, user_id)
        client = db.session.get(Cliente, client_id)
        register_consent(client, user, "service_updates", True, source="portal",
                         policy_version="test-v1", evidence_reference="receipt-001")
        archive = export_subject_data(client, user)
        db.session.commit()
        with zipfile.ZipFile(archive) as zipped:
            payload = json.loads(zipped.read("dados.json"))
        assert payload["cliente"]["cpf"] == "52998224725"
        assert payload["consentimentos"][0]["granted"] is True
        assert payload["consentimentos"][0]["policy_version"] == "test-v1"
        assert ConsentRecord.query.count() == 1
        assert has_active_consent(1, client.id, "service_updates") is True
        assert DataSubjectRequest.query.filter_by(request_type="export", status="completed").count() == 0

        anonymize_client(client, user)
        db.session.commit()
        assert client.nome.startswith("Cadastro sem identificação ")
        assert client.cpf is None and client.telefone is None and client.email is None
        assert client.ativo is False
        assert DataSubjectRequest.query.filter_by(request_type="anonymization", status="completed").count() == 0

        events = EventoLog.query.filter_by(modulo="privacidade").order_by(EventoLog.id).all()
        assert [event.tipo for event in events] == ["edicao", "acesso", "exclusao"]
        assert {event.organization_id for event in events} == {1}
        combined = " ".join(f"{event.operacao or ''} {event.descricao or ''}" for event in events)
        assert "Titular" not in combined
        assert "52998224725" not in combined
        assert "titular@example.com" not in combined


def test_concessao_exige_evidencia_e_revogacao_e_append_only():
    app, user_id, client_id = make_app()
    with app.app_context():
        user = db.session.get(Usuario, user_id)
        client = db.session.get(Cliente, client_id)
        for kwargs in ({}, {"policy_version": "test-v1", "evidence_reference": "receipt-001"}):
            try:
                register_consent(client, user, "marketing", True, **kwargs)
            except ValueError as exc:
                assert "Concessão exige" in str(exc)
            else:
                raise AssertionError("Concessão manual ou sem evidência foi aceita")
        grant = register_consent(client, user, "marketing", True, source="portal",
                                 policy_version="test-v1", evidence_reference="receipt-001")
        db.session.commit()
        assert has_active_consent(1, client.id, "marketing") is True
        register_consent(client, user, "marketing", False, source="admin")
        db.session.commit()
        assert has_active_consent(1, client.id, "marketing") is False
        assert ConsentRecord.query.count() == 2
        grant.granted = False
        try:
            db.session.commit()
        except RuntimeError:
            db.session.rollback()
        else:
            raise AssertionError("Registro de consentimento foi alterado")


def test_anonimizacao_e_bloqueada_quando_existe_os():
    app, user_id, client_id = make_app()
    with app.app_context():
        user = db.session.get(Usuario, user_id)
        client = db.session.get(Cliente, client_id)
        db.session.add(OrdemServico(
            organization_id=1, cliente_id=client.id, usuario_id=user.id,
            tipo_aparelho="Notebook", status="entregue",
        ))
        db.session.commit()
        try:
            anonymize_client(client, user)
        except ValueError as exc:
            assert "sujeitos a retencao" in str(exc)
        else:
            raise AssertionError("Cliente com OS foi anonimizado")
        assert client.nome == "Titular"


def test_remocao_cadastral_e_bloqueada_quando_existe_coleta():
    app, user_id, client_id = make_app()
    with app.app_context():
        user = db.session.get(Usuario, user_id)
        client = db.session.get(Cliente, client_id)
        db.session.add(ColetaAgendada(
            organization_id=1, cliente_id=client.id, usuario_id=user.id,
            telefone_contato="47999999999", endereco="Rua Teste",
        ))
        db.session.commit()
        try:
            anonymize_client(client, user)
        except ValueError as exc:
            assert "coleta vinculada" in str(exc)
        else:
            raise AssertionError("Cadastro com coleta vinculada teve identificadores removidos")
        assert client.cpf == "52998224725"
