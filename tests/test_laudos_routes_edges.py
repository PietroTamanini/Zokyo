import io
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from werkzeug.exceptions import Forbidden, NotFound

from app import create_app
from app.extensions import db
from app.models import Cliente, LaudoFoto, LaudoTecnico, OrdemServico, Organization, Usuario
from app.models.laudo import LaudoTemplate


def _png_bytes(size=(120, 120)):
    output = io.BytesIO()
    Image.new("RGB", size, "white").save(output, "PNG")
    output.seek(0)
    return output


def _make_app(tmp_path):
    app = create_app("development")
    reports = tmp_path / "reports"
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SECRET_KEY="laudos-route-key",
        WTF_CSRF_ENABLED=False,
        REPORTS_UPLOAD_FOLDER=str(reports),
        REPORTS_PUBLIC_VERIFICATION=True,
    )
    with app.app_context():
        db.create_all()
        organization = Organization(id=1, nome="Laudos", slug="laudos")
        admin = Usuario(nome="Admin", email="admin@laudos.test", nivel="admin", ativo=True, organization_id=1)
        admin.set_senha("Senha!123")
        client = Cliente(nome="=Cliente CSV", cpf="52998224725", telefone="47999999999", organization_id=1)
        db.session.add_all([organization, admin, client])
        db.session.flush()
        order = OrdemServico(
            organization_id=1,
            cliente_id=client.id,
            usuario_id=admin.id,
            tipo_aparelho="Notebook",
            marca="Dell",
            modelo="XPS",
            numero_serie="@SERIE",
            defeito_alegado="Nao liga",
            defeito_encontrado="Fonte",
            solucao="Trocar fonte",
            observacoes="Obs",
            tecnico_nome="Tecnico",
        )
        template = LaudoTemplate(
            organization_id=1,
            nome="Padrao",
            tipo_laudo="diagnostico",
            versao=1,
            titulo="Laudo",
            fotos_obrigatorias=["frontal"],
            criado_por_id=admin.id,
        )
        db.session.add_all([order, template])
        db.session.flush()
        draft = LaudoTecnico(
            organization_id=1,
            os_id=order.id,
            cliente_id=client.id,
            tipo="diagnostico",
            status="draft",
            criado_por_id=admin.id,
            tecnico_responsavel_nome="Tecnico",
            defeito_relatado="Nao liga",
            inspecao_visual="Visual ok",
            testes_realizados="Teste",
            diagnostico_tecnico="Fonte",
            conclusao_tecnica="Reparo",
            estado_final="Pronto",
            template_id=template.id,
            template_snapshot=template.snapshot(),
        )
        finalized = LaudoTecnico(
            organization_id=1,
            os_id=order.id,
            cliente_id=client.id,
            tipo="diagnostico",
            status="finalized",
            numero="=LAU-CSV",
            criado_por_id=admin.id,
            tecnico_responsavel_nome="Tecnico",
            verification_token="verify-token",
            verificacao_publica=True,
            emitido_em=datetime.now(timezone.utc),
        )
        db.session.add_all([draft, finalized])
        db.session.commit()
        ids = {
            "admin": admin.id,
            "order": order.id,
            "draft": draft.id,
            "finalized": finalized.id,
            "template": template.id,
        }
    browser = app.test_client()
    with browser.session_transaction() as session:
        session["usuario_id"] = ids["admin"]
        session["nivel"] = "admin"
        session["perfil"] = "admin"
        session["usuario_nome"] = "Admin"
        session["_last_active"] = 9999999999
        session["_csrf_token"] = "laudos-csrf"
    return app, browser, ids, reports


def _form(browser, path, data=None, **kwargs):
    with browser.session_transaction() as session:
        session["_csrf_token"] = "laudos-csrf"
    return browser.post(path, data={**(data or {}), "_csrf_token": "laudos-csrf"}, headers={"X-CSRFToken": "laudos-csrf"}, **kwargs)


def test_rotas_laudos_cobrem_listagem_templates_crud_fotos_pdf_e_cancelamento(monkeypatch, tmp_path):
    app, browser, ids, reports = _make_app(tmp_path)

    assert browser.get("/laudos/?q=52998224725&status=draft&tipo=diagnostico&tecnico=Tecnico").status_code == 200
    csv_response = browser.get("/laudos/exportar.csv?q=SERIE")
    assert csv_response.status_code == 200
    assert b"'=LAU-CSV" in csv_response.data
    assert browser.get(f"/laudos/novo?os_id={ids['order']}").status_code == 200
    assert _form(browser, "/laudos/novo", {"os_id": "999", "tipo": "bad"}).status_code == 302
    created = _form(browser, "/laudos/novo", {
        "os_id": str(ids["order"]),
        "tipo": "diagnostico",
        "template_id": str(ids["template"]),
        "inspecao_visual": "Visual",
    })
    assert created.status_code == 302

    assert browser.get(f"/laudos/{ids['draft']}").status_code == 200
    assert browser.get(f"/laudos/{ids['draft']}/editar").status_code == 200
    assert browser.get(f"/laudos/{ids['finalized']}/editar").status_code == 302
    assert _form(browser, f"/laudos/{ids['draft']}/editar", {"analisado_em": "bad"}).status_code == 302
    assert _form(browser, f"/laudos/{ids['draft']}/editar", {"estado_final": "Reparado"}).status_code == 302

    assert browser.get("/laudos/templates").status_code == 200
    assert _form(browser, "/laudos/templates", {"nome": "x", "tipo_laudo": "bad", "titulo": ""}).status_code == 302
    assert _form(browser, "/laudos/templates", {
        "nome": "Padrao",
        "tipo_laudo": "diagnostico",
        "titulo": "Laudo v2",
        "fotos_obrigatorias": "frontal",
    }).status_code == 302
    assert _form(browser, f"/laudos/templates/{ids['template']}/toggle").status_code == 302

    assert _form(browser, f"/laudos/{ids['draft']}/fotos", {"tipo": "bad"}).status_code == 302
    upload = _form(
        browser,
        f"/laudos/{ids['draft']}/fotos",
        {"tipo": "frontal", "legenda": "Frontal", "ordem": "1", "foto": (_png_bytes(), "foto.png")},
        content_type="multipart/form-data",
    )
    assert upload.status_code == 302
    with app.app_context():
        foto = LaudoFoto.query.filter_by(laudo_id=ids["draft"]).first()
        foto_id = foto.id
        storage = reports / foto.storage_key
        thumb = reports / foto.thumbnail_key
        assert storage.is_file()
        second_storage = Path(foto.storage_key).with_name("segunda.png").as_posix()
        (reports / second_storage).write_bytes(storage.read_bytes())
        second = LaudoFoto(
            organization_id=1,
            laudo_id=ids["draft"],
            tipo="traseira",
            storage_key=second_storage,
            mime_type="image/png",
            tamanho_bytes=1,
            sha256="b" * 64,
            usuario_id=ids["admin"],
        )
        db.session.add(second)
        db.session.commit()
        second_id = second.id

    assert browser.get(f"/laudos/fotos/{foto_id}").status_code == 200
    assert browser.get(f"/laudos/fotos/{foto_id}?thumbnail=1").status_code == 200
    thumb.unlink()
    assert browser.get(f"/laudos/fotos/{foto_id}?thumbnail=1").status_code == 404
    storage.unlink()
    assert browser.get(f"/laudos/fotos/{foto_id}").status_code == 404
    assert _form(browser, f"/laudos/{ids['draft']}/fotos/reordenar", {"foto_ids": "bad"}).status_code == 302
    assert _form(browser, f"/laudos/{ids['draft']}/fotos/reordenar", {"foto_ids": [str(foto_id), str(second_id)]}).status_code == 302
    assert _form(browser, f"/laudos/fotos/{second_id}/remover").status_code == 302
    with app.app_context():
        finalized_photo = LaudoFoto(
            organization_id=1,
            laudo_id=ids["finalized"],
            tipo="frontal",
            storage_key="finalized/foto.png",
            mime_type="image/png",
            tamanho_bytes=1,
            sha256="c" * 64,
            usuario_id=ids["admin"],
        )
        db.session.add(finalized_photo)
        db.session.commit()
        finalized_photo_id = finalized_photo.id
    assert _form(browser, f"/laudos/fotos/{finalized_photo_id}/remover").status_code == 302

    assert _form(browser, f"/laudos/{ids['draft']}/finalizar").status_code == 302
    import app.routes.laudos as laudos_routes

    def value_error_finalizar(laudo, usuario):
        raise ValueError("dados incompletos")

    monkeypatch.setattr(laudos_routes, "finalizar_laudo", value_error_finalizar)
    assert _form(browser, f"/laudos/{ids['draft']}/finalizar").status_code == 302

    def runtime_finalizar(laudo, usuario):
        raise RuntimeError("pdf falhou")

    monkeypatch.setattr(laudos_routes, "finalizar_laudo", runtime_finalizar)
    assert _form(browser, f"/laudos/{ids['draft']}/finalizar").status_code == 302

    def ok_finalizar(laudo, usuario):
        laudo.status = "finalized"
        return laudo

    monkeypatch.setattr(laudos_routes, "finalizar_laudo", ok_finalizar)
    assert _form(browser, f"/laudos/{ids['draft']}/finalizar").status_code == 302

    assert browser.get(f"/laudos/{ids['finalized']}/pdf").status_code == 302
    with app.app_context():
        laudo = db.session.get(LaudoTecnico, ids["finalized"])
        laudo.pdf_path = "arquivo-inexistente.pdf"
        db.session.commit()
    assert browser.get(f"/laudos/{ids['finalized']}/pdf").status_code == 404
    with app.app_context():
        laudo = db.session.get(LaudoTecnico, ids["draft"])
        rel = Path("1") / laudo.public_uuid / "laudo.pdf"
        target = reports / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"%PDF-1.4\n")
        laudo.pdf_path = rel.as_posix()
        laudo.numero = "LAU-EDGE"
        db.session.commit()
    assert browser.get(f"/laudos/{ids['draft']}/pdf").status_code == 200

    assert _form(browser, f"/laudos/{ids['draft']}/duplicar").status_code == 302
    assert _form(browser, f"/laudos/{ids['draft']}/revisao").status_code == 302
    assert _form(browser, f"/laudos/{ids['draft']}/cancelar", {"motivo": "curto"}).status_code == 302
    with app.app_context():
        operador = Usuario(nome="Operador", email="op@laudos.test", nivel="operacional", ativo=True, organization_id=1)
        operador.set_senha("Senha!123")
        db.session.add(operador)
        db.session.commit()
        operador_id = operador.id
    with browser.session_transaction() as session:
        session["usuario_id"] = operador_id
        session["nivel"] = "operacional"
        session["perfil"] = "operacional"
        session["_last_active"] = 9999999999
        session["_csrf_token"] = "laudos-csrf"
    assert _form(browser, f"/laudos/{ids['draft']}/cancelar", {"motivo": "Cancelamento formal de teste"}).status_code == 403
    with browser.session_transaction() as session:
        session["usuario_id"] = ids["admin"]
        session["nivel"] = "admin"
        session["perfil"] = "admin"
        session["_last_active"] = 9999999999
        session["_csrf_token"] = "laudos-csrf"
    assert _form(browser, f"/laudos/{ids['draft']}/cancelar", {"motivo": "Cancelamento formal de teste"}).status_code == 302
    assert browser.get(f"/laudos/{ids['draft']}/comprovante-cancelamento.pdf").status_code == 200

    with app.app_context():
        laudo = db.session.get(LaudoTecnico, ids["finalized"])
        laudo.motivo_cancelamento = None
        laudo.cancelado_em = None
        db.session.commit()
    assert browser.get(f"/laudos/{ids['finalized']}/comprovante-cancelamento.pdf").status_code == 302
    assert browser.get("/laudos/verificar/verify-token").status_code == 200
    app.config["REPORTS_PUBLIC_VERIFICATION"] = False
    assert browser.get("/laudos/verificar/verify-token").status_code == 404


def test_rotas_laudos_bloqueiam_sem_permissao(tmp_path):
    app, _browser, ids, _reports = _make_app(tmp_path)
    guest = app.test_client()
    assert guest.get("/laudos/").status_code == 403
    with guest.session_transaction() as session:
        session["usuario_id"] = ids["admin"]
        session["nivel"] = "visitante"
        session["perfil"] = "visitante"
        session["_last_active"] = 9999999999
    assert guest.get("/laudos/").status_code == 200


def test_laudos_cli_e_guardas_internos(monkeypatch, tmp_path):
    app, _browser, ids, reports = _make_app(tmp_path)
    import app.routes.laudos as laudos_routes

    orphan = str(reports / "orfao.pdf")
    monkeypatch.setattr(laudos_routes, "arquivos_orfaos", lambda: [orphan])
    monkeypatch.setattr(laudos_routes, "limpar_arquivos_orfaos", lambda: 1)
    runner = app.test_cli_runner()
    audit = runner.invoke(args=["laudos", "storage-audit"])
    assert audit.exit_code == 0
    assert orphan in audit.output
    deleted = runner.invoke(args=["laudos", "storage-audit", "--delete"])
    assert deleted.exit_code == 0
    assert "1 arquivo(s) removido(s)." in deleted.output

    with app.app_context():
        admin = db.session.get(Usuario, ids["admin"])
        draft = db.session.get(LaudoTecnico, ids["draft"])
        foreign = SimpleNamespace(organization_id=2)

        with app.test_request_context("/laudos"):
            from flask import session

            session["usuario_id"] = admin.id
            admin.nivel = "consulta"
            db.session.commit()
            with pytest.raises(Forbidden):
                laudos_routes._require_manage()

        with app.test_request_context("/laudos"):
            from flask import session

            session["usuario_id"] = admin.id
            admin.nivel = "admin"
            db.session.commit()
            with pytest.raises(Forbidden):
                laudos_routes._require_manage_laudo(foreign)
            with pytest.raises(NotFound):
                laudos_routes._require_laudo_permission("laudos.download_pdf", foreign)
            assert laudos_routes._require_laudo_permission("laudos.download_pdf", draft).id == admin.id
