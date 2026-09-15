import json
import zipfile

from app import create_app
from app.extensions import db
from app.models import Cliente, ConsentRecord, DataSubjectRequest, EventoLog, OrdemServico, Organization, Usuario
from app.services.privacy import anonymize_client, export_subject_data, register_consent


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
        register_consent(client, user, "service_updates", True)
        archive = export_subject_data(client, user)
        db.session.commit()
        with zipfile.ZipFile(archive) as zipped:
            payload = json.loads(zipped.read("dados.json"))
        assert payload["cliente"]["cpf"] == "52998224725"
        assert payload["consentimentos"][0]["granted"] is True
        assert ConsentRecord.query.count() == 1
        assert DataSubjectRequest.query.filter_by(request_type="export", status="completed").count() == 1

        anonymize_client(client, user)
        db.session.commit()
        assert client.nome.startswith("Titular anonimizado ")
        assert client.cpf is None and client.telefone is None and client.email is None
        assert client.ativo is False

        events = EventoLog.query.filter_by(modulo="privacidade").order_by(EventoLog.id).all()
        assert [event.tipo for event in events] == ["edicao", "sistema", "exclusao"]
        assert {event.organization_id for event in events} == {1}
        combined = " ".join(f"{event.operacao or ''} {event.descricao or ''}" for event in events)
        assert "Titular" not in combined
        assert "52998224725" not in combined
        assert "titular@example.com" not in combined


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
