import os

from requests.exceptions import ConnectionError

from app.utils import whatsapp


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


def test_url_wpp_bloqueia_esquemas_e_ips_privados(monkeypatch):
    assert not whatsapp._is_safe_wpp_url("file:///etc/passwd")
    assert not whatsapp._is_safe_wpp_url("http://169.254.169.254/latest/meta-data")
    monkeypatch.setattr(whatsapp.socket, "getaddrinfo", lambda *_args: [(None, None, None, None, ("10.0.0.5", 0))])
    assert not whatsapp._is_safe_wpp_url("http://interno:3333")


def test_allowlist_exige_https_para_gateway_remoto(monkeypatch):
    monkeypatch.setenv("WPP_ALLOWED_HOSTS", "gateway.example")
    monkeypatch.setattr(whatsapp.socket, "getaddrinfo", lambda *_args: [(None, None, None, None, ("8.8.8.8", 0))])
    assert not whatsapp._is_safe_wpp_url("http://gateway.example")
    assert whatsapp._is_safe_wpp_url("https://gateway.example")
    assert not whatsapp._is_safe_wpp_url("https://gateway.example?redirect=http://interno")


def test_envio_wpp_usa_token_sem_redirect_e_normaliza_numero(monkeypatch):
    monkeypatch.setattr(whatsapp, "_wpp_url", lambda: "http://localhost:3333")
    monkeypatch.setenv("WPP_SECRET", "segredo")
    captured = {}

    def fake_post(url, **kwargs):
        captured.update(url=url, **kwargs)
        return FakeResponse(200, {"ok": True})

    monkeypatch.setattr(whatsapp.requests, "post", fake_post)
    result = whatsapp.enviar_whatsapp("(47) 99999-9999", "Teste")

    assert result["sucesso"] is True
    assert captured["json"]["number"] == "5547999999999"
    assert captured["headers"]["X-Wpp-Token"] == "segredo"
    assert captured["allow_redirects"] is False


def test_envio_nunca_chama_rede_sem_configuracao(monkeypatch):
    monkeypatch.setattr(whatsapp, "_wpp_url", lambda: None)
    monkeypatch.setattr(whatsapp.requests, "post", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("rede chamada")))
    result = whatsapp.enviar_whatsapp("47999999999", "Teste")
    assert result["modo"] == "simulacao"
    assert result["sucesso"] is False
    assert result["link"].startswith("https://wa.me/")


def test_envio_offline_retorna_fallback(monkeypatch):
    monkeypatch.setattr(whatsapp, "_wpp_url", lambda: "http://localhost:3333")
    monkeypatch.setenv("WPP_SECRET", "segredo")
    monkeypatch.setattr(whatsapp.requests, "post", lambda *_args, **_kwargs: (_ for _ in ()).throw(ConnectionError("offline")))
    result = whatsapp.enviar_whatsapp("47999999999", "Teste")
    assert result["modo"] == "fallback"
    assert result["sucesso"] is False


def test_status_wpp_com_mock(monkeypatch):
    monkeypatch.setattr(whatsapp, "_wpp_url", lambda: "http://localhost:3333")
    monkeypatch.setenv("WPP_SECRET", "segredo")
    monkeypatch.setattr(whatsapp.requests, "get", lambda *_args, **_kwargs: FakeResponse(200, {"status": "conectado"}))
    assert whatsapp.status_wpp() == {"status": "conectado", "modo": "gateway"}


def test_gateway_sem_token_nunca_chama_rede(monkeypatch):
    monkeypatch.setattr(whatsapp, "_wpp_url", lambda: "http://localhost:3333")
    monkeypatch.delenv("WPP_SECRET", raising=False)
    monkeypatch.setattr(whatsapp.requests, "post", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("rede chamada")))
    assert whatsapp.enviar_whatsapp("47999999999", "Teste")["modo"] == "simulacao"


def test_cloud_api_oficial_tem_prioridade_e_host_fixo(monkeypatch):
    monkeypatch.setenv("WHATSAPP_CLOUD_API_TOKEN", "meta-token")
    monkeypatch.setenv("WHATSAPP_CLOUD_PHONE_NUMBER_ID", "123456")
    monkeypatch.setenv("WHATSAPP_CLOUD_API_VERSION", "v23.0")
    captured = {}

    def fake_post(url, **kwargs):
        captured.update(url=url, **kwargs)
        return FakeResponse(200, {"messages": [{"id": "wamid.123"}]})

    monkeypatch.setattr(whatsapp.requests, "post", fake_post)
    result = whatsapp.enviar_whatsapp("(47) 99999-9999", "Teste oficial")

    assert result == {
        "modo": "whatsapp_cloud", "sucesso": True,
        "link": "https://wa.me/5547999999999?text=Teste%20oficial", "message_id": "wamid.123",
    }
    assert captured["url"] == "https://graph.facebook.com/v23.0/123456/messages"
    assert captured["headers"]["Authorization"] == "Bearer meta-token"
    assert captured["json"]["to"] == "5547999999999"
    assert captured["allow_redirects"] is False


def test_cloud_api_rejeita_configuracao_ambigua(monkeypatch):
    monkeypatch.setenv("WHATSAPP_CLOUD_API_TOKEN", "meta-token")
    monkeypatch.setenv("WHATSAPP_CLOUD_PHONE_NUMBER_ID", "../messages")
    monkeypatch.setenv("WHATSAPP_CLOUD_API_VERSION", "latest")
    assert whatsapp._cloud_config() is None


def teardown_module():
    os.environ.pop("WPP_ALLOWED_HOSTS", None)
