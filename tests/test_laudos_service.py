import os
import tempfile
from io import BytesIO

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from app import create_app
from app.extensions import db
from app.models import Cliente, LaudoFoto, OrdemServico, Usuario
from app.models.laudo import LAUDO_FOTOS_OBRIGATORIAS
from app.services.laudos import adicionar_foto, atualizar_laudo, criar_rascunho, finalizar_laudo, safe_file_path


def make_app():
    app = create_app("development")
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        REPORTS_UPLOAD_FOLDER=tempfile.mkdtemp(prefix="zokyo-reports-"),
        WTF_CSRF_ENABLED=False,
    )
    return app


def seed_base():
    usuario = Usuario(nome="Tecnico", email="tec@example.com", nivel="operacional", ativo=True)
    usuario.set_senha("Senha!123")
    cliente = Cliente(nome="Cliente Teste", cpf="52998224725", telefone="47999999999")
    db.session.add_all([usuario, cliente])
    db.session.flush()
    os_obj = OrdemServico(
        cliente_id=cliente.id,
        usuario_id=usuario.id,
        tipo_aparelho="Notebook",
        marca="Dell",
        modelo="XPS",
        numero_serie="ABC123",
        defeito_alegado="Nao liga",
        defeito_encontrado="Fonte em curto",
        solucao="Substituir fonte",
        tecnico_nome="Tecnico",
    )
    db.session.add(os_obj)
    db.session.commit()
    return usuario, cliente, os_obj


def test_cria_rascunho_preenchido_por_os():
    app = make_app()
    with app.app_context():
        db.drop_all()
        db.create_all()
        usuario, cliente, os_obj = seed_base()

        laudo = criar_rascunho(os_obj.id, usuario)
        db.session.commit()

        assert laudo.id is not None
        assert laudo.status == "draft"
        assert laudo.cliente_id == cliente.id
        assert laudo.defeito_relatado == "Nao liga"
        assert laudo.diagnostico_tecnico == "Fonte em curto"


def test_edita_rascunho_e_bloqueia_finalizado():
    app = make_app()
    with app.app_context():
        db.drop_all()
        db.create_all()
        usuario, _cliente, os_obj = seed_base()
        laudo = criar_rascunho(os_obj.id, usuario)
        atualizar_laudo(laudo, {
            "inspecao_visual": "Carcaca integra",
            "testes_realizados": "Teste de fonte",
            "diagnostico_tecnico": "Fonte em curto",
            "conclusao_tecnica": "Reparo recomendado",
            "estado_final": "Aguardando aprovacao",
        }, usuario)
        assert laudo.inspecao_visual == "Carcaca integra"

        laudo.status = "finalized"
        try:
            atualizar_laudo(laudo, {"conclusao_tecnica": "Alteracao indevida"}, usuario)
        except ValueError as exc:
            assert "nao podem ser editados" in str(exc)
        else:
            raise AssertionError("Laudo finalizado aceitou edicao")


def test_finaliza_gera_pdf_hash_e_numero():
    app = make_app()
    with app.app_context():
        db.drop_all()
        db.create_all()
        usuario, _cliente, os_obj = seed_base()
        laudo = criar_rascunho(os_obj.id, usuario)
        atualizar_laudo(laudo, {
            "inspecao_visual": "Carcaca integra",
            "testes_realizados": "Teste de fonte",
            "diagnostico_tecnico": "Fonte em curto",
            "conclusao_tecnica": "Reparo recomendado",
            "estado_final": "Aguardando aprovacao",
        }, usuario)
        db.session.flush()
        for ordem, tipo in enumerate(LAUDO_FOTOS_OBRIGATORIAS):
            db.session.add(LaudoFoto(
                laudo_id=laudo.id,
                tipo=tipo,
                ordem=ordem,
                storage_key=f"1/{laudo.public_uuid}/missing-{tipo}.jpg",
                mime_type="image/jpeg",
                tamanho_bytes=1,
                sha256="0" * 64,
                usuario_id=usuario.id,
            ))
        db.session.commit()

        finalizar_laudo(laudo, usuario)
        pdf = safe_file_path(laudo.pdf_path).read_bytes()

        assert laudo.status == "finalized"
        assert laudo.numero.startswith("LAU-")
        assert len(laudo.pdf_sha256) == 64
        assert pdf.startswith(b"%PDF")


def test_verificacao_publica_pode_ser_desativada():
    app = make_app()
    app.config["REPORTS_PUBLIC_VERIFICATION"] = False
    with app.app_context():
        db.drop_all()
        db.create_all()
        usuario, _cliente, os_obj = seed_base()
        laudo = criar_rascunho(os_obj.id, usuario)
        atualizar_laudo(laudo, {
            "inspecao_visual": "Carcaca integra",
            "testes_realizados": "Teste de fonte",
            "diagnostico_tecnico": "Fonte em curto",
            "conclusao_tecnica": "Reparo recomendado",
            "estado_final": "Aguardando aprovacao",
        }, usuario)
        db.session.flush()
        for ordem, tipo in enumerate(LAUDO_FOTOS_OBRIGATORIAS):
            db.session.add(LaudoFoto(
                laudo_id=laudo.id,
                tipo=tipo,
                ordem=ordem,
                storage_key=f"1/{laudo.public_uuid}/missing-{tipo}.jpg",
                mime_type="image/jpeg",
                tamanho_bytes=1,
                sha256="0" * 64,
                usuario_id=usuario.id,
            ))
        db.session.commit()
        finalizar_laudo(laudo, usuario)
        token = laudo.verification_token
        assert laudo.verificacao_publica is False

    response = app.test_client().get(f"/laudos/verificar/{token}")
    assert response.status_code == 404


def _image_file(fmt="PNG"):
    from PIL import Image
    image = Image.new("RGB", (80, 80), color=(30, 90, 120))
    data = BytesIO()
    image.save(data, format=fmt)
    data.seek(0)
    return data


def test_upload_foto_valida_grava_metadados():
    app = make_app()
    with app.app_context():
        db.drop_all()
        db.create_all()
        usuario, _cliente, os_obj = seed_base()
        laudo = criar_rascunho(os_obj.id, usuario)
        db.session.commit()

        from werkzeug.datastructures import FileStorage
        foto = adicionar_foto(
            laudo,
            FileStorage(stream=_image_file(), filename="frontal.png", content_type="image/png"),
            "frontal",
            "Frente do equipamento",
            1,
            usuario,
        )
        db.session.commit()

        assert foto.id is not None
        assert foto.mime_type == "image/png"
        assert foto.largura == 80
        assert foto.altura == 80
        assert len(foto.sha256) == 64
        assert safe_file_path(foto.storage_key).exists()


def test_upload_foto_rejeita_mime_falso():
    app = make_app()
    with app.app_context():
        db.drop_all()
        db.create_all()
        usuario, _cliente, os_obj = seed_base()
        laudo = criar_rascunho(os_obj.id, usuario)
        db.session.commit()

        from werkzeug.datastructures import FileStorage
        try:
            adicionar_foto(
                laudo,
                FileStorage(stream=BytesIO(b"<script>alert(1)</script>"), filename="foto.png", content_type="image/png"),
                "frontal",
                "",
                1,
                usuario,
            )
        except ValueError as exc:
            assert "imagem valida" in str(exc)
        else:
            raise AssertionError("Upload falso foi aceito")
