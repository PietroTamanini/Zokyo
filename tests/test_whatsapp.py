import os

from requests.exceptions import ConnectionError

from app.utils import whatsapp


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


def test_envio_nunca_chama_rede_sem_cloud_api(monkeypatch):
    monkeypatch.delenv("WHATSAPP_CLOUD_API_TOKEN", raising=False)
    monkeypatch.delenv("WHATSAPP_CLOUD_PHONE_NUMBER_ID", raising=False)
    monkeypatch.delenv("WHATSAPP_CLOUD_API_VERSION", raising=False)
    monkeypatch.setattr(
        whatsapp.requests,
        "post",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("rede chamada")),
    )

    result = whatsapp.enviar_whatsapp("47999999999", "Teste")

    assert result["modo"] == "simulacao"
    assert result["sucesso"] is False
    assert result["link"] == "https://wa.me/5547999999999?text=Teste"
    assert "Meta WhatsApp Cloud API" in result["aviso"]
    assert whatsapp.status_wpp() == {"status": "desconectado", "modo": "simulacao"}


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
    assert whatsapp.status_wpp() == {"status": "configurado", "modo": "whatsapp_cloud"}


def test_cloud_api_rejeita_configuracao_ambigua(monkeypatch):
    monkeypatch.setenv("WHATSAPP_CLOUD_API_TOKEN", "meta-token")
    monkeypatch.setenv("WHATSAPP_CLOUD_PHONE_NUMBER_ID", "../messages")
    monkeypatch.setenv("WHATSAPP_CLOUD_API_VERSION", "latest")
    assert whatsapp._cloud_config() is None


def test_cloud_api_indisponivel_retorna_fallback(monkeypatch):
    monkeypatch.setenv("WHATSAPP_CLOUD_API_TOKEN", "meta-token")
    monkeypatch.setenv("WHATSAPP_CLOUD_PHONE_NUMBER_ID", "123456")
    monkeypatch.setenv("WHATSAPP_CLOUD_API_VERSION", "v23.0")
    monkeypatch.setattr(
        whatsapp.requests,
        "post",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ConnectionError("offline")),
    )

    result = whatsapp.enviar_whatsapp("47999999999", "Teste")

    assert result["modo"] == "fallback"
    assert result["sucesso"] is False
    assert result["link"].startswith("https://wa.me/")


def teardown_module():
    os.environ.pop("WHATSAPP_CLOUD_API_TOKEN", None)
    os.environ.pop("WHATSAPP_CLOUD_PHONE_NUMBER_ID", None)
    os.environ.pop("WHATSAPP_CLOUD_API_VERSION", None)
