import io
from datetime import datetime

from app import create_app
from app.extensions import db
from app.models import (
    Cliente,
    EventoLog,
    OrdemServico,
    OrderSignature,
    Organization,
    Peca,
    ServiceChecklistTemplate,
    StockReservation,
    Transacao,
    Usuario,
)


def _make_client(tmp_path):
    app = create_app("development")
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SECRET_KEY="os-route-key",
        WTF_CSRF_ENABLED=False,
        SIGNATURE_UPLOAD_FOLDER=str(tmp_path / "signatures"),
    )
    with app.app_context():
        db.create_all()
        organization = Organization(id=1, nome="OS", slug="os")
        admin = Usuario(nome="Admin", email="admin@os.test", nivel="admin", ativo=True, organization_id=1)
        admin.set_senha("Senha!123")
        client = Cliente(nome="Cliente OS", telefone="47999999999", organization_id=1)
        no_phone = Cliente(nome="Sem Telefone", organization_id=1)
        part = Peca(nome="Tela", codigo="TELA", quantidade=3, custo=50, organization_id=1)
        checklist = ServiceChecklistTemplate(organization_id=1, category="Notebook", version=1, items=["Fonte", "Cabo"], active=True)
        db.session.add_all([organization, admin, client, no_phone, part, checklist])
        db.session.flush()
        order = OrdemServico(
            organization_id=1,
            cliente_id=client.id,
            usuario_id=admin.id,
            tipo_aparelho="Notebook",
            defeito_alegado="Nao liga",
            valor_servico=100,
            status="recepcao",
        )
        no_phone_order = OrdemServico(
            organization_id=1,
            cliente_id=no_phone.id,
            usuario_id=admin.id,
            tipo_aparelho="Tablet",
            defeito_alegado="Sem tela",
        )
        db.session.add_all([order, no_phone_order])
        db.session.commit()
        ids = {
            "admin": admin.id,
            "client": client.id,
            "no_phone_order": no_phone_order.id,
            "order": order.id,
            "part": part.id,
        }
    browser = app.test_client()
    with browser.session_transaction() as session:
        session["usuario_id"] = ids["admin"]
        session["nivel"] = "admin"
        session["perfil"] = "admin"
        session["usuario_nome"] = "Admin"
        session["_last_active"] = 9999999999
        session["_csrf_token"] = "os-csrf"
    return app, browser, ids


def _json(browser, method, path, payload=None):
    with browser.session_transaction() as session:
        session["_csrf_token"] = "os-csrf"
    return browser.open(path, method=method, json=payload or {}, headers={"X-CSRFToken": "os-csrf"})


def test_os_api_cobre_criacao_atualizacao_checklist_pdf_whatsapp_e_assinatura(monkeypatch, tmp_path):
    app, browser, ids = _make_client(tmp_path)
    import app.routes.os as os_routes

    assert os_routes._normalizar_status("") is None
    assert browser.get("/api/os?status=analise&cliente_id=1&per_page=999").get_json()["per_page"] == 200
    assert browser.get(f"/api/os/{ids['order']}").status_code == 200

    for payload, expected in (
        ({}, 400),
        ({"cliente_id": 9999}, 404),
        ({"cliente_id": ids["client"], "warranty_return_of_id": "bad"}, 400),
        ({"cliente_id": ids["client"], "valor_servico": "x"}, 400),
        ({"cliente_id": ids["client"], "valor_servico": -1}, 400),
        ({"cliente_id": ids["client"], "valor_servico": 1, "desconto": 2}, 400),
        ({"cliente_id": ids["client"], "prio": "fora"}, 400),
        ({"cliente_id": ids["client"], "tipo_atendimento": "fora"}, 400),
        ({"cliente_id": ids["client"], "defeito_alegado": "x" * 5001}, 400),
    ):
        assert _json(browser, "POST", "/api/os", payload).status_code == expected
    monkeypatch.setattr(os_routes, "assert_write_allowed", lambda _organization_id: (_ for _ in ()).throw(PermissionError("plano bloqueado")))
    assert _json(browser, "POST", "/api/os", {"cliente_id": ids["client"], "tipo_aparelho": "Notebook"}).status_code == 403
    monkeypatch.setattr(os_routes, "assert_write_allowed", lambda _organization_id: None)

    warranty = _json(browser, "POST", "/api/os", {
        "cliente_id": ids["client"],
        "tipo_aparelho": "Notebook",
        "defeito_alegado": "Retorno garantia",
        "warranty_return_of_id": ids["order"],
        "status": "reparo",
        "data_entrada": "data ruim",
        "data_prev": datetime.now().isoformat(),
    })
    assert warranty.status_code == 201
    warranty_id = warranty.get_json()["id"]
    assert warranty.get_json()["checklist_snapshot"] == ["Fonte", "Cabo"]

    assert _json(browser, "POST", "/api/checklists", {"categoria": "", "itens": []}).status_code == 400
    assert _json(browser, "POST", "/api/checklists", {"categoria": "Notebook", "itens": ["x"]}).status_code == 400
    assert _json(browser, "POST", "/api/checklists", {"categoria": "Notebook", "itens": ["Carcaca"]}).status_code == 201
    assert browser.get("/api/checklists").status_code == 200
    assert _json(browser, "PUT", f"/api/os/{warranty_id}/checklist", {"respostas": []}).status_code == 400
    assert _json(browser, "PUT", f"/api/os/{warranty_id}/checklist", {"respostas": {"Invalido": True}}).status_code == 400
    assert _json(browser, "PUT", f"/api/os/{warranty_id}/checklist", {"respostas": {"Fonte": True, "Cabo": None}}).status_code == 200
    assert _json(browser, "POST", f"/api/os/{warranty_id}/autorizacao", {"aceito": False, "aceito_por": "A"}).status_code == 400
    assert _json(browser, "POST", f"/api/os/{warranty_id}/autorizacao", {"aceito": True, "aceito_por": "Cliente"}).status_code == 200

    for payload in (
        {"prio": "fora"},
        {"tipo_atendimento": "fora"},
        {"valor_servico": "x"},
        {"valor_servico": -1},
        {"valor_servico": 1, "valor_pecas": 0, "desconto": 2},
        {"status": "invalido"},
    ):
        assert _json(browser, "PUT", f"/api/os/{warranty_id}", payload).status_code == 400
    atualizado = _json(browser, "PUT", f"/api/os/{warranty_id}", {
        "tipo_aparelho": "Notebook Pro",
        "marca": "Dell",
        "defeito_alegado": "Falha intermitente",
        "observacoes": "Observacao tecnica",
        "prio": "urgente",
        "tipo_atendimento": "coleta",
    })
    assert atualizado.status_code == 200
    assert atualizado.get_json()["prio"] == "urgente"
    assert atualizado.get_json()["tipo_atendimento"] == "coleta"
    with app.app_context():
        db.session.add(Transacao(
            organization_id=1,
            os_id=warranty_id,
            tipo="receita",
            categoria="servico",
            descricao="Pagamento OS teste",
            valor=100,
            status="pago",
        ))
        db.session.commit()
    entregue = _json(browser, "PUT", f"/api/os/{warranty_id}", {
        "status": "entregue",
        "valor_servico": 100,
        "valor_pecas": 0,
        "desconto": 0,
        "data_saida": "data ruim",
    })
    assert entregue.status_code == 200
    assert entregue.get_json()["status"] == "entregue"

    for payload in (
        {},
        {"peca_id": ids["part"], "quantidade": "x"},
        {"peca_id": ids["part"], "quantidade": 0},
        {"peca_id": ids["part"], "quantidade": 1, "valor_unitario": -1},
        {"peca_id": 9999, "quantidade": 1},
        {"peca_id": ids["part"], "quantidade": 99},
    ):
        assert _json(browser, "POST", f"/api/os/{ids['order']}/pecas", payload).status_code in {400, 404}
    assert _json(browser, "POST", f"/api/os/{ids['order']}/reservas", {}).status_code == 400
    reservation = _json(browser, "POST", f"/api/os/{ids['order']}/reservas", {"peca_id": ids["part"], "quantidade": 2})
    assert reservation.status_code == 201
    reservation_id = reservation.get_json()["id"]
    adicionada = _json(browser, "POST", f"/api/os/{ids['order']}/pecas", {
        "peca_id": ids["part"],
        "quantidade": 2,
        "valor_unitario": 80,
        "link_compra": "https://fornecedor.example/tela",
    })
    assert adicionada.status_code == 200
    assert adicionada.get_json()["pecas"][0]["link_compra"] == "https://fornecedor.example/tela"
    assert _json(browser, "POST", f"/api/os/{ids['order']}/pecas", {
        "peca_id": ids["part"],
        "quantidade": 2,
        "valor_unitario": 80,
        "link_compra": "javascript:alert(1)",
    }).status_code == 400
    assert _json(browser, "POST", f"/api/os/{ids['order']}/pecas", {"peca_id": ids["part"], "quantidade": 1, "valor_unitario": 70}).status_code == 200
    with app.app_context():
        part = db.session.get(Peca, ids["part"])
        part.quantidade = 1
        db.session.commit()
    assert _json(browser, "POST", f"/api/os/{ids['order']}/pecas", {"peca_id": ids["part"], "quantidade": 5, "valor_unitario": 70}).status_code == 400
    with app.app_context():
        part = db.session.get(Peca, ids["part"])
        part.quantidade = 4
        active = StockReservation(
            organization_id=1,
            part_id=ids["part"],
            order_id=ids["order"],
            user_id=ids["admin"],
            quantity=2,
        )
        db.session.add(active)
        db.session.commit()
    assert _json(browser, "POST", f"/api/os/{ids['order']}/pecas", {"peca_id": ids["part"], "quantidade": 3, "valor_unitario": 70}).status_code == 200
    with app.app_context():
        part = db.session.get(Peca, ids["part"])
        part.quantidade = 1
        cancelable = StockReservation(
            organization_id=1,
            part_id=ids["part"],
            order_id=ids["order"],
            user_id=ids["admin"],
            quantity=1,
        )
        db.session.add(cancelable)
        db.session.commit()
        cancelable_id = cancelable.id
    assert _json(browser, "POST", f"/api/os/{ids['order']}/reservas", {"peca_id": ids["part"], "quantidade": 99}).status_code == 400
    assert _json(browser, "DELETE", f"/api/os/{ids['order']}/reservas/{cancelable_id}").status_code == 200
    assert _json(browser, "DELETE", f"/api/os/{ids['order']}/pecas/{ids['part']}").status_code == 200
    assert _json(browser, "DELETE", f"/api/os/{ids['order']}/reservas/{reservation_id}").status_code in {200, 404}

    assert browser.post(f"/api/os/{ids['order']}/assinatura", data={"_csrf_token": "os-csrf"}, headers={"X-CSRFToken": "os-csrf"}).status_code == 400
    monkeypatch.setattr(os_routes, "capture_signature", lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("assinatura invalida")))
    assert browser.post(
        f"/api/os/{ids['order']}/assinatura",
        data={"_csrf_token": "os-csrf", "signatario": "Cliente", "assinatura": (io.BytesIO(b"png"), "assinatura.png")},
        headers={"X-CSRFToken": "os-csrf"},
        content_type="multipart/form-data",
    ).status_code == 400
    with app.app_context():
        missing = OrderSignature(
            organization_id=1,
            order_id=ids["order"],
            captured_by_id=ids["admin"],
            signer_name="Cliente",
            storage_key="missing.png",
            size_bytes=1,
            sha256="a" * 64,
        )
        db.session.add(missing)
        db.session.commit()
    assert browser.get(f"/api/os/{ids['order']}/assinatura").status_code == 404

    monkeypatch.setattr(os_routes, "gerar_pdf_os", lambda order: (_ for _ in ()).throw(RuntimeError("pdf")))
    assert browser.get(f"/api/os/{ids['order']}/pdf").status_code == 500
    monkeypatch.setattr(os_routes, "gerar_pdf_os", lambda order: b"%PDF-1.4\n")
    assert browser.get(f"/api/os/{ids['order']}/pdf").status_code == 200

    assert _json(browser, "POST", f"/api/os/{ids['no_phone_order']}/whatsapp").status_code == 400
    monkeypatch.setattr(os_routes, "enviar_whatsapp", lambda numero, mensagem: {"sucesso": True, "numero": numero})
    monkeypatch.setattr(os_routes, "mensagem_os_pronta", lambda order: "mensagem")
    assert _json(browser, "POST", f"/api/os/{ids['order']}/whatsapp").get_json()["sucesso"] is True

    assert _json(browser, "DELETE", f"/api/os/{warranty_id}").status_code == 200
    assert browser.get(f"/api/os/{warranty_id}").status_code == 404

    with app.app_context():
        events = EventoLog.query.filter_by(modulo="ordens_servico").order_by(EventoLog.id).all()
        operations = [event.operacao for event in events]
        assert any(operation == f"OS #{warranty_id} criada pela API" for operation in operations)
        assert any(operation == f"OS #{warranty_id} atualizada pela API" for operation in operations)
        assert any(operation == f"Peca #{ids['part']} vinculada a OS #{ids['order']}" for operation in operations)
        assert any(operation == f"Peca #{ids['part']} removida da OS #{ids['order']}" for operation in operations)
        assert any(operation == f"Reserva #{reservation_id} criada para OS #{ids['order']}" for operation in operations)
        assert any(operation == f"OS #{warranty_id} removida pela API" for operation in operations)
        assert {event.organization_id for event in events} == {1}
        combined = " ".join(f"{event.operacao or ''} {event.descricao or ''}" for event in events)
        assert "Falha intermitente" not in combined
        assert "Observacao tecnica" not in combined
        assert "Retorno garantia" not in combined
