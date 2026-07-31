from app import create_app
from app.extensions import db
from app.models import Cliente, OrdemServico, Organization, Usuario
from app.utils.blind_index import blind_index


def make_app():
    app = create_app("development")
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    with app.app_context():
        db.drop_all()
        db.create_all()
    return app


def test_cliente_mantem_indices_cegos_para_documento_telefone_e_email():
    app = make_app()
    with app.app_context():
        db.session.add(Organization(id=1, nome="Blind", slug="blind"))
        cliente = Cliente(
            organization_id=1,
            nome="Cliente Blind",
            cpf="12345678909",
            telefone="47999999999",
            email="Cliente@Example.com",
        )
        db.session.add(cliente)
        db.session.commit()
        cliente_id = cliente.id

        raw = db.session.execute(
            db.text("select cpf_bidx, telefone_bidx, email_bidx from clientes where id=:id"),
            {"id": cliente_id},
        ).mappings().one()
        assert raw["cpf_bidx"] == blind_index("123.456.789-09", "cpf")
        assert raw["telefone_bidx"] == blind_index("(47) 99999-9999", "telefone")
        assert raw["email_bidx"] == blind_index("cliente@example.com", "email")
        assert "12345678909" not in raw["cpf_bidx"]

        assert Cliente.query.filter_by(cpf_bidx=blind_index("12345678909", "cpf")).one().id == cliente_id


def test_consulta_publica_os_usa_indice_cego_de_documento():
    app = make_app()
    with app.app_context():
        org = Organization(id=1, nome="Blind", slug="blind")
        usuario = Usuario(organization_id=1, nome="Tecnico", email="tec@example.com", nivel="admin", ativo=True)
        usuario.set_senha("Senha!123")
        cliente = Cliente(organization_id=1, nome="Cliente Blind", cpf="12345678909")
        db.session.add_all([org, usuario, cliente])
        db.session.flush()
        ordem = OrdemServico(
            organization_id=1,
            cliente_id=cliente.id,
            usuario_id=usuario.id,
            numero=321,
            tipo_aparelho="Notebook",
            marca="Dell",
            modelo="XPS",
        )
        db.session.add(ordem)
        db.session.commit()

    response = app.test_client().post("/api/public/os-consulta", json={"numero": "321", "cpf": "123.456.789-09"})
    assert response.status_code == 200
    assert response.get_json()["status"] is True
