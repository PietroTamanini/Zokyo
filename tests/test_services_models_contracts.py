import hashlib
import hmac
import io
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from PIL import Image

from app import create_app
from app.extensions import db
from app.models import (
    Cliente,
    Configuracao,
    DefeitoPadrao,
    EventoLog,
    InventoryLot,
    OrdemServico,
    OrderSignature,
    Organization,
    OrganizationSubscription,
    OSHistorico,
    PasswordResetToken,
    Peca,
    Plan,
    PortalToken,
    RetentionPolicy,
    StockReservation,
    Transacao,
    UserSession,
    Usuario,
)
from app.models.laudo import LaudoTecnico, LaudoTemplate
from app.models.ordem_servico import os_pecas
from app.services import (
    billing,
    finance,
    inventory,
    order_signatures,
    password_reset,
    portal,
    privacy,
    retention,
    two_factor,
    user_invites,
    user_sessions,
)
from app.services.order_signatures import capture_signature, signature_path


def _make_app(tmp_path=None):
    app = create_app("development")
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SECRET_KEY="service-contract-key",
        SERVER_NAME="example.test",
        WTF_CSRF_ENABLED=False,
    )
    if tmp_path is not None:
        app.instance_path = str(tmp_path)
        app.config["SIGNATURE_UPLOAD_FOLDER"] = str(tmp_path / "signatures")
    with app.app_context():
        db.create_all()
        organization = Organization(id=1, nome="Contratos", slug="contratos")
        other_org = Organization(id=2, nome="Outra", slug="outra")
        user = Usuario(nome="Admin", email="contracts@example.com", nivel="admin", ativo=True, organization_id=1)
        user.set_senha("Senha!123")
        other_user = Usuario(nome="Outro", email="other@example.com", nivel="admin", ativo=True, organization_id=2)
        other_user.set_senha("Senha!123")
        client = Cliente(
            organization_id=1,
            nome="Cliente",
            cpf="52998224725",
            cnpj="04252011000110",
            telefone="47999999999",
            email="cliente@example.com",
            cep="89200000",
            endereco="Rua A",
            numero_casa="12",
            cidade="Joinville",
            uf="SC",
        )
        db.session.add_all([organization, other_org, user, other_user, client])
        db.session.flush()
        order = OrdemServico(
            organization_id=1,
            cliente_id=client.id,
            usuario_id=user.id,
            tipo_aparelho="Notebook",
            marca="Dell",
            modelo="XPS",
            status="aguardando_aprovacao",
            valor_servico=Decimal("100.00"),
            valor_pecas=Decimal("50.00"),
            desconto=Decimal("10.00"),
            data_saida=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        part = Peca(
            organization_id=1,
            nome="Tela",
            codigo="LCD",
            quantidade=10,
            estoque_minimo=1,
            custo=Decimal("20.00"),
        )
        db.session.add_all([order, part])
        db.session.commit()
        return {
            "app": app,
            "user_id": user.id,
            "other_user_id": other_user.id,
            "client_id": client.id,
            "order_id": order.id,
            "part_id": part.id,
        }


def _sign(payload, secret):
    return "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def _png_bytes(width=300, height=120):
    output = io.BytesIO()
    Image.new("RGBA", (width, height), (30, 30, 30, 255)).save(output, format="PNG")
    output.seek(0)
    return output


def test_billing_cobre_eventos_invalidos_plano_cancelamento_e_limites(monkeypatch):
    ctx = _make_app()
    app = ctx["app"]
    secret = "billing-contract"
    monkeypatch.setenv("BILLING_SANDBOX_SECRET", secret)

    with app.app_context():
        plan_a = Plan(code="basic", nome="Basic", ativo=True, limites={"max_os": "1", "bad": "abc"})
        plan_b = Plan(code="pro", nome="Pro", ativo=True, limites={"max_os": None})
        db.session.add_all([plan_a, plan_b])
        db.session.flush()
        db.session.add(OrganizationSubscription(organization_id=1, plan_id=plan_a.id, provider="sandbox", status="trialing"))
        db.session.commit()

        assert billing.verify_sandbox_signature(b"{}", "bad") is False
        with pytest.raises(ValueError, match="Payload JSON"):
            billing.process_sandbox_event(b"{", _sign(b"{", secret))
        invalid = json.dumps({"event_id": "", "type": "unknown", "organization_id": 1}).encode()
        with pytest.raises(ValueError, match="Evento sandbox"):
            billing.process_sandbox_event(invalid, _sign(invalid, secret))
        bad_org = json.dumps({"event_id": "evt-org", "type": "subscription.activated", "organization_id": "1"}).encode()
        with pytest.raises(ValueError, match="organization_id"):
            billing.process_sandbox_event(bad_org, _sign(bad_org, secret))
        missing = json.dumps({"event_id": "evt-missing", "type": "subscription.activated", "organization_id": 999}).encode()
        with pytest.raises(ValueError, match="organizacao"):
            billing.process_sandbox_event(missing, _sign(missing, secret))

        changed = json.dumps({"event_id": "evt-plan", "type": "subscription.plan_changed", "organization_id": 1, "plan_code": "pro"}).encode()
        event, processed = billing.process_sandbox_event(changed, _sign(changed, secret))
        assert processed is True
        assert event.event_type == "subscription.plan_changed"
        assert billing.subscription_for(1).plan.code == "pro"

        bad_plan = json.dumps({"event_id": "evt-bad-plan", "type": "subscription.plan_changed", "organization_id": 1, "plan_code": "missing"}).encode()
        with pytest.raises(ValueError, match="Plano"):
            billing.process_sandbox_event(bad_plan, _sign(bad_plan, secret))

        cancelled = json.dumps({"event_id": "evt-cancel", "type": "subscription.cancelled", "organization_id": 1}).encode()
        billing.process_sandbox_event(cancelled, _sign(cancelled, secret))
        assert billing.subscription_for(1).status == "cancelled"
        assert billing.subscription_for(1).cancelado_em is not None
        with pytest.raises(PermissionError):
            billing.assert_write_allowed(1)

        assert billing.assert_limit(999, "max_os", 100) is None
        subscription = billing.subscription_for(1)
        subscription.status = "active"
        subscription.plan = plan_a
        assert billing.assert_limit(1, "missing", 10) is None
        assert billing.assert_limit(1, "bad", 10) is None
        with pytest.raises(PermissionError, match="max_os"):
            billing.assert_limit(1, "max_os", 1)


def test_payment_gateways_cria_cobranca_asaas_pix_com_cliente_e_qrcode(monkeypatch):
    from app.services.payment_gateways import apply_payment, generate_payment

    ctx = _make_app()
    app = ctx["app"]
    calls = []

    class FakeResponse:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload
            self.text = json.dumps(payload)

        def json(self):
            return self._payload

    def fake_request(method, url, headers=None, timeout=None, **kwargs):
        calls.append({
            "method": method,
            "url": url,
            "headers": headers or {},
            "timeout": timeout,
            "payload": json.loads(kwargs["data"]) if kwargs.get("data") else None,
            "params": kwargs.get("params"),
        })
        assert headers["access_token"] == "asaas-test-token"
        assert headers["user-agent"] == "Zokyo Test/1.0"
        if method == "GET" and url.endswith("/customers"):
            return FakeResponse(200, {"data": []})
        if method == "POST" and url.endswith("/customers"):
            assert calls[-1]["payload"]["externalReference"] == f"zokyo_cliente_{ctx['client_id']}"
            return FakeResponse(200, {"id": "cus_123"})
        if method == "POST" and url.endswith("/payments"):
            payload = calls[-1]["payload"]
            assert payload["customer"] == "cus_123"
            assert payload["billingType"] == "PIX"
            assert payload["value"] == 123.45
            assert payload["externalReference"].startswith("zokyo_transacao_")
            return FakeResponse(200, {
                "id": "pay_123",
                "status": "PENDING",
                "invoiceUrl": "https://sandbox.asaas.com/i/pay_123",
            })
        if method == "GET" and url.endswith("/payments/pay_123/pixQrCode"):
            return FakeResponse(200, {"payload": "000201ASAASPIX"})
        return FakeResponse(404, {"errors": [{"description": "não encontrado"}]})

    monkeypatch.setattr("app.services.payment_gateways.requests.request", fake_request)
    with app.app_context():
        app.config.update(
            ASAAS_API_KEY="asaas-test-token",
            ASAAS_SANDBOX=True,
            ASAAS_TIMEOUT=7,
            ASAAS_USER_AGENT="Zokyo Test/1.0",
        )
        Configuracao.get().nome_empresa = "Contratos"
        order = db.session.get(OrdemServico, ctx["order_id"])
        transacao = Transacao(
            organization_id=1,
            os_id=order.id,
            tipo="receita",
            descricao="Cobrança Asaas",
            valor=Decimal("123.45"),
            status="pendente",
        )
        db.session.add(transacao)
        db.session.commit()

        result = generate_payment(transacao, gateway="asaas", method="pix", days=5)
        apply_payment(transacao, result)
        db.session.commit()

        assert result.gateway == "asaas"
        assert result.provider_id == "pay_123"
        assert result.payment_url == "https://sandbox.asaas.com/i/pay_123"
        assert result.payload == "000201ASAASPIX"
        assert transacao.payment_gateway == "asaas"
        assert transacao.payment_payload == "000201ASAASPIX"
        assert len(calls) == 4


def test_inventory_lotes_reservas_consumo_e_cancelamento():
    ctx = _make_app()
    app = ctx["app"]
    with app.app_context():
        part = db.session.get(Peca, ctx["part_id"])
        order = db.session.get(OrdemServico, ctx["order_id"])

        with pytest.raises(ValueError, match="justificativa"):
            inventory.record_movement(part, ctx["user_id"], "ajuste", 10, 9, "abc")
        with pytest.raises(ValueError, match="maior que zero"):
            inventory.receive_lot(part, ctx["user_id"], "L1", 0, 1, "entrada inicial")
        with pytest.raises(ValueError, match="negativo"):
            inventory.receive_lot(part, ctx["user_id"], "L1", 1, -1, "entrada inicial")

        lot = inventory.receive_lot(part, ctx["user_id"], "L1", 5, Decimal("30.00"), "entrada inicial", location="A1")
        db.session.commit()
        assert lot.id is not None
        assert part.quantidade == 15
        assert float(part.custo) == 23.33
        assert InventoryLot.query.count() == 1
        with pytest.raises(ValueError, match="ja cadastrado"):
            inventory.receive_lot(part, ctx["user_id"], "L1", 1, 1, "entrada repetida")

        with pytest.raises(ValueError, match="maior que zero"):
            inventory.reserve_stock(part, order, ctx["user_id"], 0)
        reservation = inventory.reserve_stock(part, order, ctx["user_id"], 3)
        db.session.flush()
        same = inventory.reserve_stock(part, order, ctx["user_id"], 4)
        assert same.id == reservation.id
        assert same.quantity == 4
        inventory.consume_reservation(part.id, order.id, 2)
        assert same.quantity == 2
        inventory.consume_reservation(part.id, order.id, 2)
        assert same.status == "consumed"
        assert same.closed_at is not None
        part.quantidade = 0
        db.session.flush()
        with pytest.raises(ValueError, match="insuficiente"):
            inventory.reserve_stock(part, order, ctx["user_id"], 1)

        another = StockReservation(
            organization_id=1,
            part_id=part.id,
            order_id=order.id,
            user_id=ctx["user_id"],
            quantity=1,
        )
        db.session.add(another)
        db.session.flush()
        inventory.cancel_reservation(another)
        assert another.status == "cancelled"
        assert inventory.consume_reservation(999, 999, 1) is None


def test_password_reset_token_expirado_usuario_inativo_e_envio_smtp(monkeypatch):
    ctx = _make_app()
    app = ctx["app"]
    with app.app_context():
        user = db.session.get(Usuario, ctx["user_id"])
        token, raw = password_reset.criar_token(user, "127.0.0.1")
        db.session.flush()
        token.expira_em = datetime.now(timezone.utc) - timedelta(minutes=1)
        assert password_reset.localizar_token(raw) is None

        token.expira_em = datetime.now(timezone.utc) + timedelta(minutes=30)
        user.ativo = False
        assert password_reset.localizar_token(raw) is None
        user.ativo = True
        assert password_reset.localizar_token("") is None
        assert password_reset.localizar_token("x" * 201) is None

    sent = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            sent.append(("connect", host, port, timeout))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def starttls(self):
            sent.append(("starttls",))

        def login(self, username, password):
            sent.append(("login", username, password))

        def send_message(self, message):
            sent.append(("send", message["To"], message["From"]))

    app.config.update(TESTING=False, SMTP_HOST="", MAIL_FROM="")
    with app.app_context():
        user = db.session.get(Usuario, ctx["user_id"])
        password_reset.enviar_link(user, "raw")
        app.config.update(
            SMTP_HOST="smtp.example.test",
            SMTP_PORT=2525,
            SMTP_STARTTLS=True,
            SMTP_USERNAME="mailer",
            SMTP_PASSWORD="password",
            MAIL_FROM="noreply@example.test",
        )
        monkeypatch.setattr(password_reset.smtplib, "SMTP", FakeSMTP)
        password_reset.enviar_link(user, "raw")
    assert ("connect", "smtp.example.test", 2525, 15) in sent
    assert ("starttls",) in sent
    assert ("login", "mailer", "password") in sent
    assert ("send", "contracts@example.com", "noreply@example.test") in sent


def test_portal_privacy_finance_retention_e_modelos_de_borda():
    ctx = _make_app()
    app = ctx["app"]
    with app.app_context():
        user = db.session.get(Usuario, ctx["user_id"])
        other_user = db.session.get(Usuario, ctx["other_user_id"])
        client = db.session.get(Cliente, ctx["client_id"])
        order = db.session.get(OrdemServico, ctx["order_id"])

        assert Cliente._format_cpf("123") == "123"
        assert Cliente._format_cnpj("123") == "123"
        assert Cliente(cpf="", cnpj="04252011000110", nome="PJ").documento == "04.252.011/0001-10"
        assert Cliente(nome="Sem doc").documento == ""
        assert client.to_dict()["criado_em"]
        assert DefeitoPadrao(tipo_aparelho="TV", sintoma="Sem imagem", causa="Fonte", solucao="Trocar").to_dict()["sintoma"] == "Sem imagem"
        log = EventoLog(tipo="sistema", modulo="x", operacao="op", criado_em=datetime.now(timezone.utc))
        assert log.to_dict()["criado_em"]
        historico = OSHistorico(
            os_id=order.id,
            usuario_id=user.id,
            status_anterior="recepcao",
            status_novo="pronto",
            criado_em=datetime.now(timezone.utc),
        )
        assert historico.to_dict()["status_novo"] == "pronto"

        order.pecas.append(db.session.get(Peca, ctx["part_id"]))
        db.session.flush()
        db.session.execute(
            os_pecas.update().values(quantidade=2, valor_unitario=Decimal("25.00")).where(os_pecas.c.os_id == order.id)
        )
        db.session.flush()
        order_dict = order.to_dict()
        assert order.valor_total == 140.0
        assert order.em_garantia is True
        assert order_dict["pecas"][0]["subtotal"] == 50.0
        order.data_saida = None
        assert order.em_garantia is False

        template = LaudoTemplate(
            organization_id=1,
            nome="Padrao",
            tipo_laudo="diagnostico",
            versao=1,
            titulo="Titulo",
            fotos_obrigatorias=["frontal"],
            criado_por_id=user.id,
        )
        laudo = LaudoTecnico(
            organization_id=1,
            os_id=order.id,
            cliente_id=client.id,
            criado_por_id=user.id,
            status="custom",
            tipo="custom",
        )
        assert template.snapshot()["fotos_obrigatorias"] == ["frontal"]
        assert laudo.is_draft is False
        assert laudo.is_finalized is False
        assert laudo.status_label() == "custom"
        assert laudo.tipo_label() == "custom"

        with pytest.raises(ValueError, match="Finalidade"):
            portal.criar_link_portal(order, user, "bad")
        order.organization_id = 2
        with pytest.raises(ValueError, match="Ordem"):
            portal.criar_link_portal(order, user, "tracking")
        order.organization_id = 1
        raw = portal.criar_link_portal(order, user, "tracking", dias=200)
        db.session.commit()
        token = portal.buscar_token_portal(raw)
        assert token is not None
        with pytest.raises(ValueError, match="nao permite"):
            portal.decidir_orcamento(token, "approved")
        assert 80 <= (token.expira_em - datetime.now(timezone.utc).replace(tzinfo=None)).days <= 90
        assert portal.buscar_token_portal("") is None
        assert portal.buscar_token_portal("x" * 201) is None
        token.expira_em = datetime.now(timezone.utc) - timedelta(days=1)
        assert portal.buscar_token_portal(raw) is None

        budget_raw = portal.criar_link_portal(order, user, "budget")
        db.session.commit()
        budget_token = portal.buscar_token_portal(budget_raw)
        with pytest.raises(ValueError, match="Decisao"):
            portal.decidir_orcamento(budget_token, "maybe")
        portal.decidir_orcamento(budget_token, "rejected")
        assert order.orcamento_status == "rejected"

        with pytest.raises(ValueError, match="Cliente"):
            privacy.register_consent(client, other_user, "marketing", True)
        with pytest.raises(ValueError, match="Finalidade"):
            privacy.register_consent(client, user, "bad", True)
        client.organization_id = 2
        with pytest.raises(ValueError, match="Cliente"):
            privacy.export_subject_data(client, user)
        with pytest.raises(ValueError, match="Cliente"):
            privacy.anonymize_client(client, user)
        client.organization_id = 1

        assert finance.add_months(datetime(2026, 1, 31), 1).day == 28
        with pytest.raises(ValueError, match="Parcelas"):
            finance.split_money(10, 0)
        with pytest.raises(ValueError, match="Comissao"):
            finance.create_installments(organization_id=1, valor=100, comissao_percentual=101)
        with pytest.raises(ValueError, match="Recorrencia"):
            finance.create_installments(organization_id=1, valor=100, recurrence="semanal")
        parcelas = finance.create_installments(
            organization_id=1,
            valor=Decimal("100.00"),
            installments=2,
            data_vencimento=datetime(2026, 1, 31),
            tipo="receita",
            descricao="Contrato",
            categoria="Servico",
        )
        assert [item.valor for item in parcelas] == [Decimal("50"), Decimal("50")]
        assert parcelas[1].parent_id == parcelas[0].id

        old = datetime.now(timezone.utc) - timedelta(days=120)
        reset = PasswordResetToken(
            usuario_id=user.id,
            token_hash="old",
            expira_em=datetime.now(timezone.utc) - timedelta(days=100),
            criado_em=old,
        )
        expired_portal = PortalToken(
            organization_id=1,
            os_id=order.id,
            token_hash="expired",
            purpose="tracking",
            criado_por_id=user.id,
            expira_em=datetime.now(timezone.utc) - timedelta(days=100),
            criado_em=old,
        )
        db.session.add_all([reset, expired_portal])
        db.session.commit()
        reset_policy = RetentionPolicy(
            organization_id=1,
            category=retention.RESET_TOKEN_CATEGORY,
            retention_days=90,
            active=True,
            approved_at=datetime.now(timezone.utc),
        )
        portal_policy = RetentionPolicy(
            organization_id=1,
            category="portal_tokens",
            retention_days=90,
            active=True,
            approved_at=datetime.now(timezone.utc),
        )
        unknown_policy = RetentionPolicy(
            organization_id=1,
            category="unknown",
            retention_days=90,
            active=True,
            approved_at=datetime.now(timezone.utc),
        )
        db.session.add_all([reset_policy, portal_policy, unknown_policy])
        db.session.commit()
        assert retention.count_candidates(reset_policy) == 1
        assert retention.apply_policy(reset_policy) == 1
        assert retention.count_candidates(portal_policy) >= 1
        assert retention.apply_policy(portal_policy) >= 1
        assert retention.count_candidates(unknown_policy) == 0
        assert retention.apply_policy(unknown_policy) == 0
        assert retention.apply_active_policies() == 0

        first_invite, _ = user_invites.create_invite(1, "dup@example.test", "admin", user.id)
        db.session.flush()
        second_invite, _ = user_invites.create_invite(1, "dup@example.test", "admin", user.id)
        db.session.flush()
        assert first_invite.revoked_at is not None
        assert second_invite.revoked_at is None

        raw_session = "raw-session"
        session_record = UserSession(
            organization_id=1,
            user_id=user.id,
            token_hash=user_sessions._hash(raw_session),
            security_version=user.security_version,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            last_seen_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        )
        db.session.add(session_record)
        db.session.commit()
        with app.test_request_context("/"):
            from flask import session

            session["session_token"] = raw_session
            assert user_sessions.validate_session_record(user) is True


def test_assinatura_cobre_validacoes_arquivo_e_caminho(tmp_path, monkeypatch):
    ctx = _make_app(tmp_path)
    app = ctx["app"]
    with app.app_context():
        order = db.session.get(OrdemServico, ctx["order_id"])
        changing_roots = iter([tmp_path / "assinaturas-a", tmp_path / "assinaturas-b"])
        monkeypatch.setattr(order_signatures, "signature_root", lambda: next(changing_roots))
        with pytest.raises(ValueError, match="Destino"):
            capture_signature(order, ctx["user_id"], "Cliente", _png_bytes(), "127.0.0.1")
        monkeypatch.setattr(order_signatures, "signature_root", lambda: tmp_path / "signatures")

        with pytest.raises(ValueError, match="Nome"):
            capture_signature(order, ctx["user_id"], "A", _png_bytes(), "127.0.0.1")
        with pytest.raises(ValueError, match="maximo"):
            capture_signature(order, ctx["user_id"], "Cliente", io.BytesIO(b""), "127.0.0.1")
        with pytest.raises(ValueError, match="invalida"):
            capture_signature(order, ctx["user_id"], "Cliente", io.BytesIO(b"nao-imagem"), "127.0.0.1")
        with pytest.raises(ValueError, match="Dimensoes"):
            capture_signature(order, ctx["user_id"], "Cliente", _png_bytes(100, 50), "127.0.0.1")

        first = capture_signature(order, ctx["user_id"], "Cliente", _png_bytes(), "127.0.0.1")
        db.session.commit()
        first_path = signature_path(first)
        assert first_path.is_file()
        second = capture_signature(order, ctx["user_id"], "Cliente 2", _png_bytes(), "")
        db.session.commit()
        assert second.ip_address is None
        assert db.session.get(OrderSignature, first.id).revoked_at is not None
        assert signature_path(second).is_file()
        second.storage_key = "../fora.png"
        with pytest.raises(FileNotFoundError):
            signature_path(second)


def test_two_factor_decrypt_rejeita_tokens_invalidos():
    assert two_factor.decrypt_secret(None) is None
    app = create_app("development")
    app.config.update(TESTING=True, SECRET_KEY="two-factor-edge")
    with app.app_context():
        assert two_factor.decrypt_secret("valor-invalido") is None
