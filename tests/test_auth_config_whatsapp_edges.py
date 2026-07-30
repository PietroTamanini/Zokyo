import time
import types
from datetime import datetime, timedelta, timezone

import pyotp
from werkzeug.datastructures import MultiDict

from app import create_app
from app.extensions import db
from app.models import Configuracao, Notification, Organization, PasswordResetToken, UserSession, Usuario
from app.services.two_factor import decrypt_secret, encrypt_secret, generate_recovery_codes
from app.utils import whatsapp


def _app_with_users():
    app = create_app("development")
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SECRET_KEY="auth-config-edge-key",
        WTF_CSRF_ENABLED=False,
        SERVER_NAME="example.test",
    )
    with app.app_context():
        db.create_all()
        db.session.add(Organization(id=1, nome="Auth", slug="auth"))
        admin = Usuario(nome="Admin", email="admin@auth.test", nivel="admin", ativo=True, organization_id=1)
        admin.set_senha("Senha!123")
        user = Usuario(nome="Operador", email="op@auth.test", nivel="operacional", ativo=True, organization_id=1)
        user.set_senha("Senha!123")
        cfg = Configuracao(nome_empresa="Auth Config")
        db.session.add_all([admin, user, cfg])
        db.session.commit()
        return app, admin.id, user.id


def _empty_app():
    app = create_app("development")
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SECRET_KEY="first-access-edge-key",
        WTF_CSRF_ENABLED=False,
        SERVER_NAME="example.test",
    )
    with app.app_context():
        db.create_all()
    return app


def _csrf(client):
    with client.session_transaction() as session:
        session["_csrf_token"] = "edge-csrf"
    return "edge-csrf"


def _login(client, email="admin@auth.test", senha="Senha!123"):
    return client.post("/login", data={"email": email, "senha": senha, "_csrf_token": _csrf(client)})


def _admin_session(client, admin_id):
    with client.session_transaction() as session:
        session["usuario_id"] = admin_id
        session["nivel"] = "admin"
        session["perfil"] = "admin"
        session["usuario_nome"] = "Admin"
        session["_last_active"] = 9999999999
        session["_csrf_token"] = "edge-csrf"


def _form(client, path, data=None):
    with client.session_transaction() as session:
        session["_csrf_token"] = "edge-csrf"
    payload = MultiDict(data or {})
    payload.add("_csrf_token", "edge-csrf")
    return client.post(path, data=payload, headers={"X-CSRFToken": "edge-csrf"})


def _json(client, path, payload=None):
    with client.session_transaction() as session:
        session["_csrf_token"] = "edge-csrf"
    return client.post(path, json=payload or {}, headers={"X-CSRFToken": "edge-csrf"})


def test_auth_fluxos_de_erro_2fa_sessoes_reset_e_primeiro_acesso(monkeypatch):
    app, admin_id, _user_id = _app_with_users()
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    client = app.test_client()

    assert client.get("/login").status_code == 200
    _admin_session(client, admin_id)
    assert client.get("/login").status_code == 302
    assert client.post("/logout", data={"_csrf_token": _csrf(client)}).status_code == 302
    assert client.post("/logout", data={"_csrf_token": _csrf(client)}).status_code == 302

    import app.routes.auth as auth_routes

    monkeypatch.setattr("app.utils.rate_limit.check_lock", lambda ip: (True, 10))
    assert client.post("/login", data={"email": "admin@auth.test", "senha": "Senha!123", "_csrf_token": _csrf(client)}).status_code == 429
    monkeypatch.setattr("app.utils.rate_limit.check_lock", lambda ip: (False, 0))
    monkeypatch.setattr("app.utils.rate_limit.register_fail", lambda ip: 30)
    assert client.post("/login", data={"email": "bad", "senha": "x", "_csrf_token": _csrf(client)}).status_code == 200
    assert client.post("/login", data={"email": "admin@auth.test", "senha": "errada", "_csrf_token": _csrf(client)}).status_code == 200

    assert client.get("/2fa").status_code == 302
    with client.session_transaction() as session:
        session["2fa_user_id"] = admin_id
        session["2fa_expires"] = time.time() - 1
    assert client.get("/2fa").status_code == 302
    with client.session_transaction() as session:
        session["2fa_user_id"] = admin_id
        session["2fa_expires"] = time.time() + 300
    assert client.get("/2fa").status_code == 302
    secret = pyotp.random_base32()
    with app.app_context():
        admin = db.session.get(Usuario, admin_id)
        admin.totp_secret_encrypted = encrypt_secret(secret)
        admin.totp_enabled = True
        codes, hashes = generate_recovery_codes(1)
        admin.recovery_codes_hash = hashes
        db.session.commit()
    with client.session_transaction() as session:
        session["2fa_user_id"] = admin_id
        session["2fa_expires"] = time.time() + 300
        session["_csrf_token"] = "edge-csrf"
    assert _form(client, "/2fa", {"codigo": "000000"}).status_code == 200
    with client.session_transaction() as session:
        session["2fa_user_id"] = admin_id
        session["2fa_expires"] = time.time() + 300
        session["_csrf_token"] = "edge-csrf"
    assert _form(client, "/2fa", {"codigo": codes[0]}).status_code == 302

    assert client.get("/seguranca/2fa").status_code == 200
    assert _form(client, "/seguranca/2fa", {"codigo": "000000"}).status_code == 302
    assert _form(client, "/seguranca/2fa/desativar", {"senha": "errada", "codigo": "000000"}).status_code == 302
    with app.app_context():
        admin = db.session.get(Usuario, admin_id)
        secret = decrypt_secret(admin.totp_secret_encrypted)
    assert _form(client, "/seguranca/2fa/desativar", {"senha": "Senha!123", "codigo": pyotp.TOTP(secret).now()}).status_code == 302

    _login(client)
    with app.app_context():
        record_id = UserSession.query.filter_by(user_id=admin_id, revoked_at=None).order_by(UserSession.id.desc()).first().id
    assert _form(client, f"/seguranca/sessoes/{record_id}/revogar").status_code == 302
    _login(client)
    assert _form(client, "/seguranca/sessoes/revogar-outras").status_code == 302

    assert client.get("/recuperar-senha").status_code == 200
    monkeypatch.setattr(auth_routes, "enviar_link", lambda *_: (_ for _ in ()).throw(RuntimeError("smtp")))
    assert _form(client, "/recuperar-senha", {"email": "admin@auth.test"}).status_code == 302
    with app.app_context():
        token = PasswordResetToken.query.order_by(PasswordResetToken.id.desc()).first()
        raw = "raw-reset"
        token.token_hash = auth_routes.localizar_token.__globals__["_hash"](raw)
        token.expira_em = datetime.now(timezone.utc) + timedelta(minutes=30)
        token.usado_em = None
        db.session.commit()
    assert client.get(f"/redefinir-senha/{raw}").status_code == 200
    assert _form(client, f"/redefinir-senha/{raw}", {"senha": "Nova!1234", "confirmar_senha": "Outra!1234"}).status_code == 200
    assert _form(client, f"/redefinir-senha/{raw}", {"senha": "fraca", "confirmar_senha": "fraca"}).status_code == 200

    first = _empty_app().test_client()
    assert first.get("/primeiro-acesso").status_code == 200
    assert first.get("/register").status_code == 302
    for payload in (
        {},
        {"nome": "Admin", "email": "admin@first.test", "senha": "Senha!123", "confirmar_senha": "Outra!123"},
        {"nome": "Admin", "email": "admin@first.test", "senha": "fraca", "confirmar_senha": "fraca"},
        {"nome": "Admin", "email": "bad", "senha": "Senha!123", "confirmar_senha": "Senha!123"},
        {"nome": "A", "email": "admin@first.test", "senha": "Senha!123", "confirmar_senha": "Senha!123"},
    ):
        assert first.post("/primeiro-acesso", data={**payload, "_csrf_token": _csrf(first)}).status_code == 200
    assert first.post("/primeiro-acesso", data={
        "nome": "Admin First",
        "email": "admin@first.test",
        "senha": "Senha!123",
        "confirmar_senha": "Senha!123",
        "empresa_nome": "Primeira Empresa",
        "_csrf_token": _csrf(first),
    }).status_code == 302
    assert first.get("/primeiro-acesso").status_code == 302
    assert first.post("/primeiro-acesso", data={
        "nome": "Admin First Novo",
        "email": "admin2@first.test",
        "senha": "Senha!123",
        "confirmar_senha": "Senha!123",
        "_csrf_token": _csrf(first),
    }).status_code == 302

    no_lock_app = _empty_app()
    no_lock_app._primeiro_acesso_lock = None
    no_lock = no_lock_app.test_client()
    assert no_lock.post("/primeiro-acesso", data={
        "nome": "Admin Sem Lock",
        "email": "admin@nolock.test",
        "senha": "Senha!123",
        "confirmar_senha": "Senha!123",
        "_csrf_token": _csrf(no_lock),
    }).status_code == 302


def test_configuracoes_rotas_e_whatsapp_utils(monkeypatch):
    app, admin_id, _user_id = _app_with_users()
    client = app.test_client()
    _admin_session(client, admin_id)
    original_safe_wpp_url = whatsapp._is_safe_wpp_url
    original_enviar_whatsapp = whatsapp.enviar_whatsapp
    original_status_wpp = whatsapp.status_wpp

    with app.app_context():
        notification = Notification(
            organization_id=1,
            channel="whatsapp",
            recipient="47999999999",
            event_type="test",
            idempotency_key="edge",
            payload={},
            status="failed",
        )
        db.session.add(notification)
        db.session.commit()
        notification_id = notification.id

    assert client.get("/configuracoes/notificacoes?status=failed&page=-1").status_code == 200
    monkeypatch.setattr("app.services.notifications.retry_notification", lambda notification_id, organization_id: (_ for _ in ()).throw(LookupError()))
    assert _form(client, f"/configuracoes/notificacoes/{notification_id}/retry").status_code == 404
    monkeypatch.setattr("app.services.notifications.retry_notification", lambda notification_id, organization_id: (_ for _ in ()).throw(ValueError("estado invalido")))
    assert _form(client, f"/configuracoes/notificacoes/{notification_id}/retry").status_code == 302
    monkeypatch.setattr("app.services.notifications.retry_notification", lambda notification_id, organization_id: None)
    assert _form(client, f"/configuracoes/notificacoes/{notification_id}/retry").status_code == 302

    for payload in (
        {"nome_empresa": ""},
        {"nome_empresa": "Empresa", "cnpj": "111"},
        {"nome_empresa": "Empresa", "email": "bad"},
        {"nome_empresa": "Empresa", "telefone": "123"},
        {"nome_empresa": "Empresa", "primary_color": "blue"},
    ):
        assert _form(client, "/configuracoes/salvar", payload).status_code == 302
    assert _form(client, "/configuracoes/salvar", {
        "nome_empresa": "Empresa Edge",
        "cnpj": "04.252.011/0001-10",
        "email": "empresa@example.test",
        "telefone": "47999999999",
        "primary_color": "#111111",
        "accent_color": "#222222",
        "dias_vencimento": "x",
    }).status_code == 302
    assert _form(client, "/configuracoes/os-opcoes", MultiDict([
        ("status_key[]", "recepcao"),
        ("status_label[]", "Recepção"),
        ("status_key[]", "aguardando_peca"),
        ("status_label[]", "Aguardando peça"),
        ("status_key[]", "entregue"),
        ("status_label[]", "Entregue"),
        ("priority_key[]", "normal"),
        ("priority_label[]", "Normal"),
        ("priority_key[]", "alta"),
        ("priority_label[]", "Alta"),
        ("attendance_key[]", "balcao"),
        ("attendance_label[]", "Balcão"),
        ("attendance_key[]", "coleta"),
        ("attendance_label[]", "Coleta"),
        ("entry_checklist_key[]", "liga"),
        ("entry_checklist_label[]", "Liga"),
        ("entry_checklist_key[]", "tela"),
        ("entry_checklist_label[]", "Tela"),
    ])).status_code == 302
    with app.app_context():
        cfg = Configuracao.get()
        assert cfg.get_os_status_map()["aguardando_peca"] == "Aguardando peça"
        assert cfg.get_os_priority_map()["alta"] == "Alta"
        assert cfg.get_attendance_type_map()["coleta"] == "Coleta"
        assert cfg.get_entry_checklist_options()[1]["label"] == "Tela"
    assert _form(client, "/configuracoes/dashboard", {
        "meta_receita_mensal": "x",
        "alerta_caixa_minimo": "x",
        "alerta_estoque_minimo": "x",
        "alerta_vencimento_dias": "x",
    }).status_code == 302
    assert _form(client, "/configuracoes/dashboard", {
        "meta_receita_mensal": "100",
        "alerta_caixa_minimo": "50",
        "alerta_estoque_minimo": "2",
        "alerta_vencimento_dias": "3",
    }).status_code == 302

    monkeypatch.setattr("app.utils.whatsapp._is_safe_wpp_url", lambda url: False)
    assert _form(client, "/configuracoes/whatsapp", {"wpp_server_url": "https://blocked.example.test"}).status_code == 302
    monkeypatch.setattr("app.utils.whatsapp._is_safe_wpp_url", lambda url: True)
    assert _form(client, "/configuracoes/whatsapp", {"wpp_server_url": "https://wpp.example.test"}).status_code == 302
    assert _form(client, "/configuracoes/whatsapp", {"wpp_server_url": ""}).status_code == 302
    monkeypatch.setattr("app.utils.whatsapp.status_wpp", lambda: {"status": "ok"})
    assert client.get("/api/whatsapp/status").get_json() == {"status": "ok"}
    assert _json(client, "/api/whatsapp/teste", {}).status_code == 400
    monkeypatch.setattr("app.utils.whatsapp.enviar_whatsapp", lambda numero, mensagem: {"numero": numero, "ok": True})
    assert _json(client, "/api/whatsapp/teste", {"numero": "47999999999"}).get_json()["ok"] is True
    assert _json(client, "/api/message-templates", {"event_type": "", "channel": "sms", "body": ""}).status_code == 400

    monkeypatch.setattr(whatsapp, "_is_safe_wpp_url", original_safe_wpp_url)
    monkeypatch.setattr(whatsapp, "enviar_whatsapp", original_enviar_whatsapp)
    monkeypatch.setattr(whatsapp, "status_wpp", original_status_wpp)
    monkeypatch.setenv("WPP_ALLOWED_HOSTS", "wpp.example.test")
    monkeypatch.setattr(whatsapp.socket, "getaddrinfo", lambda host, port: [(None, None, None, None, ("8.8.8.8", port or 443))])
    assert whatsapp._allowed_hosts() >= {"localhost", "127.0.0.1", "wpp.example.test"}
    assert whatsapp._is_safe_wpp_url("ftp://wpp.example.test") is False
    assert whatsapp._is_safe_wpp_url("https://user:pass@wpp.example.test") is False
    assert whatsapp._is_safe_wpp_url("https://wpp.example.test/send?x=1") is False
    assert whatsapp._is_safe_wpp_url("https://wpp.example.test") is True
    monkeypatch.setattr(whatsapp.socket, "getaddrinfo", lambda host, port: [(None, None, None, None, ("127.0.0.1", port or 443))])
    assert whatsapp._is_safe_wpp_url("https://wpp.example.test") is False

    monkeypatch.delenv("WHATSAPP_CLOUD_API_TOKEN", raising=False)
    assert whatsapp._cloud_config() is None
    monkeypatch.setenv("WHATSAPP_CLOUD_API_TOKEN", "token")
    monkeypatch.setenv("WHATSAPP_CLOUD_PHONE_NUMBER_ID", "abc")
    monkeypatch.setenv("WHATSAPP_CLOUD_API_VERSION", "v20.0")
    assert whatsapp._cloud_config() is None
    monkeypatch.setenv("WHATSAPP_CLOUD_PHONE_NUMBER_ID", "12345")
    assert whatsapp._cloud_config() == ("token", "12345", "v20.0")

    class FakeResponse:
        def __init__(self, status_code=200, payload=None):
            self.status_code = status_code
            self._payload = payload or {"messages": [{"id": "msg-1"}], "status": "online"}

        def json(self):
            return self._payload

    monkeypatch.setattr(whatsapp.requests, "post", lambda *args, **kwargs: FakeResponse())
    assert whatsapp.enviar_whatsapp("47999999999", "Oi")["modo"] == "whatsapp_cloud"
    monkeypatch.setattr(whatsapp.requests, "post", lambda *args, **kwargs: FakeResponse(500, {"erro": "fail"}))
    assert whatsapp.enviar_whatsapp("47999999999", "Oi")["sucesso"] is False
    monkeypatch.setattr(whatsapp.requests, "post", lambda *args, **kwargs: (_ for _ in ()).throw(whatsapp.RequestException("offline")))
    assert whatsapp.enviar_whatsapp("47999999999", "Oi")["modo"] == "fallback"

    monkeypatch.delenv("WHATSAPP_CLOUD_API_TOKEN", raising=False)
    monkeypatch.setenv("WPP_SECRET", "secret")
    monkeypatch.setenv("WPP_SERVER_URL", "http://localhost:3000")
    monkeypatch.setattr(whatsapp.socket, "getaddrinfo", lambda host, port: [(None, None, None, None, ("127.0.0.1", port or 3000))])
    monkeypatch.setattr(whatsapp.requests, "post", lambda *args, **kwargs: FakeResponse(200, {"ok": True}))
    with app.app_context():
        Configuracao.get().wpp_server_url = None
        db.session.commit()
        assert whatsapp.enviar_whatsapp("47999999999", "Oi")["modo"] == "gateway"
        monkeypatch.setattr(whatsapp.requests, "post", lambda *args, **kwargs: FakeResponse(400, {"erro": "bad"}))
        assert whatsapp.enviar_whatsapp("47999999999", "Oi")["erro"] == "bad"
        monkeypatch.setattr(whatsapp.requests, "get", lambda *args, **kwargs: FakeResponse(200, {"status": "online"}))
        assert whatsapp.status_wpp()["status"] == "online"
        monkeypatch.setattr(whatsapp.requests, "get", lambda *args, **kwargs: (_ for _ in ()).throw(whatsapp.RequestException("offline")))
        assert whatsapp.status_wpp()["status"] == "offline"
        monkeypatch.setattr(whatsapp.requests, "get", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
        assert whatsapp.status_wpp()["status"] == "erro"

    monkeypatch.delenv("WPP_SECRET", raising=False)
    assert whatsapp.enviar_whatsapp("47999999999", "Oi")["modo"] == "simulacao"
    assert whatsapp.status_wpp()["modo"] == "simulacao"

    monkeypatch.setattr(whatsapp.urllib.parse, "urlparse", lambda _url: (_ for _ in ()).throw(ValueError("url ruim")))
    assert whatsapp._is_safe_wpp_url("https://wpp.example.test") is False
    monkeypatch.undo()

    monkeypatch.setenv("WPP_ALLOWED_HOSTS", "wpp.example.test")
    monkeypatch.setattr(whatsapp.socket, "getaddrinfo", lambda *_args: (_ for _ in ()).throw(whatsapp.socket.gaierror()))
    assert whatsapp._is_safe_wpp_url("https://wpp.example.test") is False

    with app.app_context():
        Configuracao.get().wpp_server_url = "http://localhost:3000/"
        db.session.commit()
        assert whatsapp._wpp_url() == "http://localhost:3000"

    monkeypatch.setenv("WPP_SECRET", "secret")
    monkeypatch.setattr(whatsapp, "_wpp_url", lambda: "https://wpp.example.test")
    monkeypatch.setattr(whatsapp, "_is_safe_wpp_url", lambda _url: False)
    assert "bloqueada" in whatsapp.enviar_whatsapp("47999999999", "Oi")["erro"]
    assert whatsapp.status_wpp()["status"] == "erro"

    monkeypatch.setattr(whatsapp, "_is_safe_wpp_url", lambda _url: True)
    monkeypatch.setattr(whatsapp.requests, "post", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    assert whatsapp.enviar_whatsapp("47999999999", "Oi")["erro"] == "boom"

    monkeypatch.setenv("WHATSAPP_CLOUD_API_TOKEN", "token")
    monkeypatch.setenv("WHATSAPP_CLOUD_PHONE_NUMBER_ID", "12345")
    monkeypatch.setenv("WHATSAPP_CLOUD_API_VERSION", "v20.0")
    assert whatsapp.status_wpp() == {"status": "configurado", "modo": "whatsapp_cloud"}

    monkeypatch.setattr(Configuracao, "get", lambda: (_ for _ in ()).throw(RuntimeError("sem cfg")))
    fake_os = types.SimpleNamespace(
        id=7,
        valor_total=12.5,
        marca="Marca",
        modelo="Modelo",
        solucao="Pronto",
        cliente=types.SimpleNamespace(nome="Cliente"),
    )
    assert "Zokyo Platform" in whatsapp.mensagem_os_pronta(fake_os)
