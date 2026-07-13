import os
import tempfile
from io import BytesIO

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from app import create_app
from app.extensions import db
from app.models import Cliente, Configuracao, LaudoFoto, LaudoTemplate, OrdemServico, Organization, Usuario
from app.models.laudo import LAUDO_FOTOS_OBRIGATORIAS
from app.services.laudos import (
    adicionar_foto,
    arquivos_orfaos,
    atualizar_laudo,
    cancelar_laudo,
    criar_rascunho,
    duplicar_laudo,
    finalizar_laudo,
    gerar_comprovante_cancelamento,
    reordenar_fotos,
    safe_file_path,
)


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
    organization = db.session.get(Organization, 1)
    if not organization:
        organization = Organization(id=1, nome="Teste", slug="test")
        db.session.add(organization)
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


def test_tecnico_nao_finaliza_laudo_de_outro_usuario_pela_rota():
    app = make_app()
    with app.app_context():
        db.drop_all()
        db.create_all()
        usuario, _cliente, os_obj = seed_base()
        outro = Usuario(nome="Outro tecnico", email="outro@example.com", nivel="operacional", ativo=True)
        outro.set_senha("Senha!123")
        db.session.add(outro)
        db.session.flush()
        laudo = criar_rascunho(os_obj.id, usuario)
        db.session.commit()
        laudo_id = laudo.id
        outro_id = outro.id

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["usuario_id"] = outro_id
        sess["nivel"] = "operacional"
        sess["_csrf_token"] = "token"
        sess["_last_active"] = 9999999999

    response = client.post(
        f"/laudos/{laudo_id}/finalizar",
        data={"_csrf_token": "token"},
    )

    assert response.status_code == 403


def test_usuario_de_outra_organizacao_nao_acessa_laudo_por_id():
    app = make_app()
    with app.app_context():
        db.create_all()
        usuario, _cliente, os_obj = seed_base()
        laudo = criar_rascunho(os_obj.id, usuario)
        outra_org = Organization(nome="Outra", slug="outra")
        db.session.add(outra_org)
        db.session.flush()
        intruso = Usuario(
            nome="Intruso", email="intruso@example.com", nivel="admin", ativo=True,
            organization_id=outra_org.id,
        )
        intruso.set_senha("Senha!123")
        db.session.add(intruso)
        db.session.commit()
        laudo_id = laudo.id
        intruso_id = intruso.id

    client = app.test_client()
    with client.session_transaction() as session:
        session["usuario_id"] = intruso_id
        session["nivel"] = "admin"
        session["_last_active"] = 9999999999
    assert client.get(f"/laudos/{laudo_id}").status_code == 404


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
        assert foto.thumbnail_key
        assert safe_file_path(foto.thumbnail_key).exists()


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


def test_storage_rejeita_path_traversal_e_detecta_orfao():
    app = make_app()
    with app.app_context():
        db.create_all()
        try:
            safe_file_path("../fora.pdf")
        except ValueError:
            pass
        else:
            raise AssertionError("Path traversal foi aceito")
        orfao = safe_file_path("1/orfao.txt")
        orfao.parent.mkdir(parents=True, exist_ok=True)
        orfao.write_text("sem referencia", encoding="utf-8")
        assert orfao in arquivos_orfaos()


def test_reordena_fotos_com_lista_completa():
    app = make_app()
    with app.app_context():
        db.create_all()
        usuario, _cliente, os_obj = seed_base()
        laudo = criar_rascunho(os_obj.id, usuario)
        primeira = adicionar_foto(laudo, _file_storage("a.png"), "frontal", "A", 0, usuario)
        segunda = adicionar_foto(laudo, _file_storage("b.png"), "traseira", "B", 1, usuario)
        db.session.flush()
        reordenar_fotos(laudo, [segunda.id, primeira.id], usuario)
        assert segunda.ordem == 0
        assert primeira.ordem == 1


def _file_storage(filename):
    from werkzeug.datastructures import FileStorage
    return FileStorage(stream=_image_file(), filename=filename, content_type="image/png")


def test_revisao_formal_cria_rascunho_vinculado_e_preserva_original():
    app = make_app()
    with app.app_context():
        db.create_all()
        usuario, _cliente, os_obj = seed_base()
        original = criar_rascunho(os_obj.id, usuario)
        original.status = "finalized"
        original.numero = "LAU-2026-000001"
        original.conclusao_tecnica = "Conteudo original"
        revisao = duplicar_laudo(original, usuario, revisao=True)
        db.session.flush()

        assert revisao.status == "draft"
        assert revisao.tipo == "revisao"
        assert revisao.laudo_origem_id == original.id
        assert revisao.versao == 2
        assert revisao.numero is None
        assert revisao.conclusao_tecnica == "Conteudo original"
        assert original.numero == "LAU-2026-000001"


def test_cancelamento_gera_comprovante_sem_substituir_pdf_original():
    app = make_app()
    with app.app_context():
        db.create_all()
        usuario, _cliente, os_obj = seed_base()
        laudo = criar_rascunho(os_obj.id, usuario)
        laudo.status = "finalized"
        laudo.numero = "LAU-2026-000001"
        laudo.pdf_path = "1/original.pdf"
        laudo.pdf_sha256 = "a" * 64
        laudo.empresa_snapshot = {"nome_empresa": "Empresa <Teste>"}
        laudo.cliente_snapshot = {"nome": "Cliente & Filhos"}
        cancelar_laudo(laudo, "Documento emitido com dados tecnicos incorretos.", usuario)

        comprovante = gerar_comprovante_cancelamento(laudo).read()

        assert comprovante.startswith(b"%PDF")
        assert laudo.pdf_path == "1/original.pdf"
        assert laudo.pdf_sha256 == "a" * 64
        assert laudo.status == "cancelled"


def test_comprovante_rejeita_laudo_nao_cancelado():
    app = make_app()
    with app.app_context():
        db.create_all()
        usuario, _cliente, os_obj = seed_base()
        laudo = criar_rascunho(os_obj.id, usuario)
        try:
            gerar_comprovante_cancelamento(laudo)
        except ValueError as exc:
            assert "somente para laudos cancelados" in str(exc)
        else:
            raise AssertionError("Comprovante foi gerado para laudo ativo")


def test_override_negativo_bloqueia_download_de_pdf():
    app = make_app()
    with app.app_context():
        db.create_all()
        usuario, _cliente, os_obj = seed_base()
        usuario.permissoes_negadas = ["laudos.download_pdf"]
        laudo = criar_rascunho(os_obj.id, usuario)
        laudo.status = "finalized"
        laudo.numero = "LAU-2026-000001"
        target = safe_file_path("1/teste-download.pdf")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"%PDF-test")
        laudo.pdf_path = "1/teste-download.pdf"
        db.session.commit()
        usuario_id = usuario.id
        laudo_id = laudo.id

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["usuario_id"] = usuario_id
        sess["nivel"] = "operacional"
        sess["_last_active"] = 9999999999
    assert client.get(f"/laudos/{laudo_id}/pdf").status_code == 403


def test_exportacao_csv_respeita_tenant_filtros_e_neutraliza_formula():
    app = make_app()
    with app.app_context():
        db.create_all()
        usuario, _cliente, os_obj = seed_base()
        visivel = criar_rascunho(os_obj.id, usuario)
        visivel.numero = "=FORMULA"

        outra_org = Organization(nome="Outra", slug="outra-export")
        db.session.add(outra_org)
        db.session.flush()
        outro_usuario = Usuario(
            nome="Outro", email="outro-export@example.com", nivel="admin", ativo=True,
            organization_id=outra_org.id,
        )
        outro_usuario.set_senha("Senha!123")
        outro_cliente = Cliente(nome="Cliente Oculto", telefone="47999999998", organization_id=outra_org.id)
        db.session.add_all([outro_usuario, outro_cliente])
        db.session.flush()
        outra_os = OrdemServico(
            cliente_id=outro_cliente.id, usuario_id=outro_usuario.id, tipo_aparelho="Celular",
            marca="Marca Oculta", modelo="Modelo Oculto", defeito_alegado="Teste",
            organization_id=outra_org.id,
        )
        db.session.add(outra_os)
        db.session.flush()
        oculto = criar_rascunho(outra_os.id, outro_usuario)
        oculto.numero = "LAU-OCULTO"
        db.session.commit()
        usuario_id = usuario.id

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["usuario_id"] = usuario_id
        sess["nivel"] = "operacional"
        sess["_last_active"] = 9999999999
    response = client.get("/laudos/exportar.csv?status=draft")
    text = response.data.decode("utf-8-sig")

    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    assert "'=FORMULA" in text
    assert "LAU-OCULTO" not in text
    assert "Cliente Oculto" not in text


def test_upload_rejeita_arquivo_excessivo_antes_de_processar_imagem():
    app = make_app()
    with app.app_context():
        db.create_all()
        usuario, _cliente, os_obj = seed_base()
        laudo = criar_rascunho(os_obj.id, usuario)
        from werkzeug.datastructures import FileStorage

        from app.services.laudos import MAX_FOTO_BYTES
        oversized = FileStorage(
            stream=BytesIO(b"x" * (MAX_FOTO_BYTES + 1)),
            filename="grande.jpg",
            content_type="image/jpeg",
        )
        try:
            adicionar_foto(laudo, oversized, "frontal", "", 0, usuario)
        except ValueError as exc:
            assert "excede 8 MB" in str(exc)
        else:
            raise AssertionError("Arquivo excessivo foi aceito")


def test_upload_respeita_limite_total_de_fotos():
    app = make_app()
    with app.app_context():
        db.create_all()
        usuario, _cliente, os_obj = seed_base()
        laudo = criar_rascunho(os_obj.id, usuario)
        db.session.flush()
        for index in range(20):
            db.session.add(LaudoFoto(
                laudo_id=laudo.id, tipo="adicional", ordem=index,
                storage_key=f"1/{laudo.public_uuid}/{index}.jpg", mime_type="image/jpeg",
                tamanho_bytes=1, sha256=f"{index:064x}", usuario_id=usuario.id,
            ))
        db.session.flush()
        try:
            adicionar_foto(laudo, _file_storage("extra.png"), "adicional", "", 20, usuario)
        except ValueError as exc:
            assert "Limite de fotos" in str(exc)
        else:
            raise AssertionError("Limite total de fotos nao foi aplicado")


def test_falha_de_pdf_reverte_finalizacao_e_nao_deixa_arquivo(monkeypatch):
    app = make_app()
    with app.app_context():
        db.create_all()
        usuario, _cliente, os_obj = seed_base()
        laudo = criar_rascunho(os_obj.id, usuario)
        atualizar_laudo(laudo, {
            "inspecao_visual": "Integro", "testes_realizados": "Teste",
            "diagnostico_tecnico": "Diagnostico", "conclusao_tecnica": "Conclusao",
            "estado_final": "Aguardando",
        }, usuario)
        db.session.flush()
        for ordem, tipo in enumerate(LAUDO_FOTOS_OBRIGATORIAS):
            db.session.add(LaudoFoto(
                laudo_id=laudo.id, tipo=tipo, ordem=ordem,
                storage_key=f"1/{laudo.public_uuid}/missing-{tipo}.jpg", mime_type="image/jpeg",
                tamanho_bytes=1, sha256="0" * 64, usuario_id=usuario.id,
            ))
        db.session.commit()
        laudo_id = laudo.id

        def fail_pdf(_laudo):
            raise RuntimeError("falha simulada")

        monkeypatch.setattr("app.services.laudos.gerar_pdf_laudo", fail_pdf)
        try:
            finalizar_laudo(laudo, usuario)
        except RuntimeError as exc:
            assert "falha simulada" in str(exc)
        else:
            raise AssertionError("Falha simulada nao interrompeu a finalizacao")

        persisted = db.session.get(type(laudo), laudo_id)
        assert persisted.status == "draft"
        assert persisted.numero is None
        assert persisted.pdf_path is None
        assert not [path for path in safe_file_path(f"1/{persisted.public_uuid}").rglob("*.pdf")]


def test_snapshot_e_pdf_nao_mudam_apos_alterar_cadastros():
    app = make_app()
    with app.app_context():
        db.create_all()
        usuario, cliente, os_obj = seed_base()
        cfg = Configuracao.get()
        cfg.nome_empresa = "Empresa Original"
        laudo = criar_rascunho(os_obj.id, usuario)
        atualizar_laudo(laudo, {
            "inspecao_visual": "Integro", "testes_realizados": "Teste",
            "diagnostico_tecnico": "Diagnostico", "conclusao_tecnica": "Conclusao",
            "estado_final": "Finalizado",
        }, usuario)
        db.session.flush()
        for ordem, tipo in enumerate(LAUDO_FOTOS_OBRIGATORIAS):
            db.session.add(LaudoFoto(
                laudo_id=laudo.id, tipo=tipo, ordem=ordem,
                storage_key=f"1/{laudo.public_uuid}/missing-{tipo}.jpg", mime_type="image/jpeg",
                tamanho_bytes=1, sha256="0" * 64, usuario_id=usuario.id,
            ))
        db.session.commit()
        finalizar_laudo(laudo, usuario)
        original_pdf = safe_file_path(laudo.pdf_path).read_bytes()
        original_hash = laudo.pdf_sha256

        cliente.nome = "Cliente Alterado"
        cfg.nome_empresa = "Empresa Alterada"
        os_obj.modelo = "Modelo Alterado"
        db.session.commit()

        assert laudo.cliente_snapshot["nome"] == "Cliente Teste"
        assert laudo.empresa_snapshot["nome_empresa"] == "Empresa Original"
        assert laudo.equipamento_snapshot["modelo"] == "XPS"
        assert safe_file_path(laudo.pdf_path).read_bytes() == original_pdf
        assert laudo.pdf_sha256 == original_hash


def test_template_define_fotos_e_e_congelado_na_finalizacao():
    app = make_app()
    with app.app_context():
        db.create_all()
        usuario, _cliente, os_obj = seed_base()
        template = LaudoTemplate(
            organization_id=usuario.organization_id, nome="Diagnostico simples", tipo_laudo="diagnostico",
            versao=1, titulo="Relatorio de diagnostico", declaracao_final="Declaracao original",
            rodape="Rodape original", fotos_obrigatorias=["frontal"], criado_por_id=usuario.id,
        )
        db.session.add(template)
        db.session.flush()
        laudo = criar_rascunho(os_obj.id, usuario, template_id=template.id)
        atualizar_laudo(laudo, {
            "inspecao_visual": "Integro", "testes_realizados": "Teste",
            "diagnostico_tecnico": "Diagnostico", "conclusao_tecnica": "Conclusao",
            "estado_final": "Finalizado",
        }, usuario)
        db.session.flush()
        db.session.add(LaudoFoto(
            laudo_id=laudo.id, tipo="frontal", ordem=0,
            storage_key=f"1/{laudo.public_uuid}/missing.jpg", mime_type="image/jpeg",
            tamanho_bytes=1, sha256="0" * 64, usuario_id=usuario.id,
        ))
        db.session.commit()

        finalizar_laudo(laudo, usuario)
        template.titulo = "Titulo alterado posteriormente"
        template.fotos_obrigatorias = list(LAUDO_FOTOS_OBRIGATORIAS)
        db.session.commit()

        assert laudo.template_snapshot["titulo"] == "Relatorio de diagnostico"
        assert laudo.template_snapshot["fotos_obrigatorias"] == ["frontal"]
        assert laudo.pdf_template_version == f"template-{template.id}-v1"


def test_rota_admin_cria_nova_versao_do_template():
    app = make_app()
    with app.app_context():
        db.create_all()
        usuario, _cliente, _os_obj = seed_base()
        usuario.nivel = "admin"
        db.session.commit()
        usuario_id = usuario.id

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["usuario_id"] = usuario_id
        sess["nivel"] = "admin"
        sess["_last_active"] = 9999999999
        sess["_csrf_token"] = "token"
    payload = {
        "nome": "Padrao oficina", "tipo_laudo": "diagnostico", "titulo": "Laudo personalizado",
        "declaracao_final": "Declaracao", "rodape": "Rodape", "fotos_obrigatorias": "frontal",
        "_csrf_token": "token",
    }
    assert client.post("/laudos/templates", data=payload).status_code == 302
    assert client.post("/laudos/templates", data=payload).status_code == 302
    with app.app_context():
        versions = [item.versao for item in LaudoTemplate.query.order_by(LaudoTemplate.versao).all()]
        assert versions == [1, 2]
