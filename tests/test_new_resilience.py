from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

from app import create_app
from app.services import asaas_subscriptions, object_storage


def _subscription():
    plan = SimpleNamespace(preco_mensal=99.9, ciclo="MONTHLY", nome="Pro")
    return SimpleNamespace(
        external_customer_id="cus_1", external_id=None, provider=None,
        status=None, checkout_url=None, plan=plan,
    )


def test_asaas_converte_falha_de_rede_em_erro_controlado(monkeypatch):
    monkeypatch.setenv("ASAAS_API_KEY", "test-key")
    monkeypatch.setattr(requests, "request", lambda *args, **kwargs: (_ for _ in ()).throw(requests.Timeout()))
    with pytest.raises(asaas_subscriptions.AsaasSubscriptionError, match="comunicar"):
        asaas_subscriptions._request("GET", "/customers")


@pytest.mark.parametrize("trial_days,billing_type", [(None, "PIX"), (7, "INVALID")])
def test_asaas_rejeita_checkout_invalido_sem_erro_500(monkeypatch, trial_days, billing_type):
    monkeypatch.setattr(asaas_subscriptions, "_request", lambda *args, **kwargs: {"id": "sub_1"})
    organization = SimpleNamespace(id=1, nome="Empresa")
    admin = SimpleNamespace(email="admin@example.com")
    with pytest.raises(asaas_subscriptions.AsaasSubscriptionError):
        asaas_subscriptions.create_subscription(
            _subscription(), organization, admin, "12345678901", billing_type, trial_days,
        )


def test_hydrate_s3_remove_temporario_quando_download_falha(monkeypatch, tmp_path: Path):
    class BrokenClient:
        def download_file(self, _bucket, _key, target):
            Path(target).write_bytes(b"parcial")
            raise RuntimeError("download interrompido")

    app = create_app("development")
    app.config.update(S3_BUCKET="private-bucket")
    monkeypatch.setattr(object_storage, "_client", lambda: BrokenClient())
    target = tmp_path / "photo.jpg"
    with app.app_context(), pytest.raises(RuntimeError):
        object_storage.hydrate("tenant/photo.jpg", target)
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []
