"""Adapter de assinaturas recorrentes do Asaas."""
from __future__ import annotations

import hmac
import os
from datetime import date, timedelta

import requests


class AsaasSubscriptionError(RuntimeError):
    pass


def _settings():
    token = os.environ.get("ASAAS_API_KEY", "").strip()
    sandbox = os.environ.get("ASAAS_SANDBOX", "true").lower() in {"1", "true", "yes", "on"}
    base = os.environ.get("ASAAS_BASE_URL", "").strip() or (
        "https://api-sandbox.asaas.com/v3" if sandbox else "https://api.asaas.com/v3"
    )
    if not token:
        raise AsaasSubscriptionError("ASAAS_API_KEY não configurada.")
    return base.rstrip("/"), token


def _request(method: str, path: str, *, json=None, params=None):
    base, token = _settings()
    try:
        timeout = float(os.environ.get("ASAAS_TIMEOUT", "15"))
        if timeout <= 0:
            raise ValueError
    except ValueError:
        timeout = 15.0
    try:
        response = requests.request(
            method, f"{base}/{path.lstrip('/')}", json=json, params=params,
            headers={
                "access_token": token,
                "Content-Type": "application/json",
                "User-Agent": os.environ.get("ASAAS_USER_AGENT", "Zokyo/1.0 (Flask)"),
            },
            timeout=timeout, allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise AsaasSubscriptionError("Nao foi possivel comunicar com o Asaas. Tente novamente.") from exc
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if response.status_code >= 400:
        errors = payload.get("errors") or []
        detail = "; ".join(str(item.get("description", "")) for item in errors) or f"HTTP {response.status_code}"
        raise AsaasSubscriptionError(f"Asaas recusou a operação: {detail[:400]}")
    return payload


def ensure_customer(subscription, organization, admin, document: str) -> str:
    if subscription.external_customer_id:
        return subscription.external_customer_id
    external_reference = f"zokyo-org-{organization.id}"
    found = _request("GET", "/customers", params={"externalReference": external_reference, "limit": 1})
    rows = found.get("data") or []
    if rows:
        customer_id = rows[0]["id"]
    else:
        created = _request("POST", "/customers", json={
            "name": organization.nome,
            "cpfCnpj": "".join(character for character in document if character.isdigit()),
            "email": admin.email,
            "externalReference": external_reference,
            "notificationDisabled": False,
        })
        customer_id = created.get("id")
    if not customer_id:
        raise AsaasSubscriptionError("Asaas não retornou o identificador do cliente.")
    subscription.external_customer_id = customer_id
    return customer_id


def create_subscription(subscription, organization, admin, document: str, billing_type="UNDEFINED", trial_days=7):
    customer_id = ensure_customer(subscription, organization, admin, document)
    plan = subscription.plan
    if float(plan.preco_mensal or 0) <= 0:
        raise AsaasSubscriptionError("O plano não possui preço recorrente configurado.")
    if billing_type not in {"UNDEFINED", "BOLETO", "CREDIT_CARD", "PIX"}:
        raise AsaasSubscriptionError("Forma de pagamento invalida.")
    try:
        trial_days = max(0, min(int(trial_days), 90))
    except (TypeError, ValueError):
        raise AsaasSubscriptionError("Periodo de teste invalido.") from None
    result = _request("POST", "/subscriptions", json={
        "customer": customer_id,
        "billingType": billing_type,
        "value": float(plan.preco_mensal),
        "nextDueDate": (date.today() + timedelta(days=trial_days)).isoformat(),
        "cycle": plan.ciclo or "MONTHLY",
        "description": f"Zokyo - plano {plan.nome}",
        "externalReference": f"zokyo-org-{organization.id}",
    })
    subscription.external_id = result.get("id")
    subscription.provider = "asaas"
    subscription.status = "trialing" if trial_days else "pending"
    subscription.checkout_url = None
    return result


def cancel_subscription(subscription):
    if subscription.provider == "asaas" and subscription.external_id:
        _request("DELETE", f"/subscriptions/{subscription.external_id}")
    subscription.status = "cancelled"
    subscription.cancelar_no_fim = False


def verify_webhook_token(received: str) -> bool:
    expected = os.environ.get("ASAAS_WEBHOOK_TOKEN", "").strip()
    return bool(expected and received and hmac.compare_digest(received, expected))
