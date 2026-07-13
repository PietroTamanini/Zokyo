import io

from PIL import Image

from app import create_app
from app.extensions import db
from app.models import Cliente, OrdemServico, OrderSignature, Organization, Usuario


def _png():
    output = io.BytesIO()
    Image.new("RGB", (600, 180), "white").save(output, "PNG")
    output.seek(0)
    return output


def test_assinatura_e_reprocessada_hasheada_privada_e_substituivel(tmp_path):
    app = create_app("development")
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:", SIGNATURE_UPLOAD_FOLDER=str(tmp_path))
    with app.app_context():
        db.create_all()
        organization = Organization(id=1, nome="Teste", slug="teste")
        user = Usuario(organization_id=1, nome="Admin", email="admin@teste.com", nivel="admin", ativo=True)
        user.set_senha("Senha!123")
        client = Cliente(organization_id=1, nome="Cliente")
        db.session.add_all([organization, user, client])
        db.session.flush()
        order = OrdemServico(organization_id=1, cliente_id=client.id, usuario_id=user.id)
        db.session.add(order)
        db.session.commit()
        order_id = order.id
        user_id = user.id
    browser = app.test_client()
    with browser.session_transaction() as current:
        current.update({
            "usuario_id": user_id, "nivel": "admin", "perfil": "admin", "usuario_nome": "Admin",
            "_last_active": 9999999999, "_csrf_token": "signature-csrf",
        })
    response = browser.post(
        f"/api/os/{order_id}/assinatura",
        data={"signatario": "Cliente", "assinatura": (_png(), "signature.png")},
        headers={"X-CSRFToken": "signature-csrf"}, content_type="multipart/form-data",
    )
    assert response.status_code == 201
    digest = response.get_json()["sha256"]
    assert len(digest) == 64
    assert browser.get(f"/api/os/{order_id}/assinatura").data.startswith(b"\x89PNG")
    with app.app_context():
        signature = OrderSignature.query.one()
        assert signature.storage_key not in str(tmp_path)
        assert (tmp_path / signature.storage_key).is_file()
