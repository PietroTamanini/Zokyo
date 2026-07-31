from app import create_app
from app.extensions import db
from app.models import Cliente, Configuracao, Organization
from app.utils.field_crypto import PREFIX, decrypt_value, encrypt_value


def make_app():
    app = create_app("development")
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    with app.app_context():
        db.drop_all()
        db.create_all()
    return app


def test_campos_sensiveis_sao_criptografados_no_banco_e_lidos_em_texto():
    app = make_app()
    with app.app_context():
        db.session.add(Organization(id=1, nome="Crypto", slug="crypto"))
        cliente = Cliente(organization_id=1, nome="Cliente", endereco="Rua Secreta", numero_casa="123")
        cfg = Configuracao(organization_id=1, nome_empresa="Crypto", pix_chave="pix@example.com")
        db.session.add_all([cliente, cfg])
        db.session.commit()
        cliente_id = cliente.id
        cfg_id = cfg.id

        raw_cliente = db.session.execute(
            db.text("select endereco, numero_casa from clientes where id=:id"),
            {"id": cliente_id},
        ).mappings().one()
        raw_cfg = db.session.execute(
            db.text("select pix_chave from configuracoes where id=:id"),
            {"id": cfg_id},
        ).mappings().one()

        assert raw_cliente["endereco"].startswith(PREFIX)
        assert raw_cliente["numero_casa"].startswith(PREFIX)
        assert raw_cfg["pix_chave"].startswith(PREFIX)
        assert "Rua Secreta" not in raw_cliente["endereco"]
        assert "pix@example.com" not in raw_cfg["pix_chave"]

        db.session.expire_all()
        assert db.session.get(Cliente, cliente_id).endereco == "Rua Secreta"
        assert db.session.get(Configuracao, cfg_id).pix_chave == "pix@example.com"


def test_descriptografia_aceita_valor_criptografado_mais_de_uma_vez():
    app = make_app()
    with app.app_context():
        double_wrapped = encrypt_value(encrypt_value("Rua Duplamente Protegida"))
        assert double_wrapped.startswith(PREFIX)
        assert decrypt_value(double_wrapped) == "Rua Duplamente Protegida"
