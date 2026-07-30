"""Checks executaveis de prontidao para producao."""
from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

MYSQL_SCHEMES = {"mysql", "mysql+pymysql", "mysql+mysqldb", "mariadb", "mariadb+pymysql"}
TRUTHY = {"1", "true", "yes", "on"}
PLACEHOLDER_PREFIXES = ("SUBSTITUA", "GERE", "CONFIGURE")


@dataclass(frozen=True)
class ReadinessIssue:
    severity: str
    code: str
    message: str


def _get(env: dict[str, str], name: str) -> str:
    return (env.get(name) or "").strip()


def _is_placeholder(value: str) -> bool:
    normalized = value.strip().upper()
    return not normalized or normalized.startswith(PLACEHOLDER_PREFIXES) or "SUBSTITUA" in normalized


def _base64_decodes_to_32_bytes(value: str, *, urlsafe: bool = False) -> bool:
    if not value or _is_placeholder(value):
        return False
    try:
        decoder = base64.urlsafe_b64decode if urlsafe else base64.b64decode
        return len(decoder(value.encode("ascii"))) == 32
    except Exception:
        return False


def _is_truthy(value: str) -> bool:
    return value.strip().lower() in TRUTHY


def check_production_readiness(
    env: dict[str, str],
    *,
    strict_integrations: bool = False,
) -> list[ReadinessIssue]:
    issues: list[ReadinessIssue] = []

    def add(severity: str, code: str, message: str) -> None:
        issues.append(ReadinessIssue(severity, code, message))

    def integration(code: str, message: str) -> None:
        add("error" if strict_integrations else "warning", code, message)

    if _get(env, "FLASK_ENV") != "production":
        add("error", "FLASK_ENV", "Defina FLASK_ENV=production.")

    secret = _get(env, "SECRET_KEY")
    if _is_placeholder(secret) or len(secret) < 32:
        add("error", "SECRET_KEY", "Defina SECRET_KEY real com pelo menos 32 caracteres.")

    database_url = _get(env, "DATABASE_URL")
    parsed_db = urlparse(database_url)
    if _is_placeholder(database_url):
        add("error", "DATABASE_URL", "Defina DATABASE_URL real.")
    elif parsed_db.scheme not in MYSQL_SCHEMES:
        add("error", "DATABASE_URL", "Use MySQL/MariaDB em produção, não SQLite ou outro backend.")
    elif not parsed_db.username or not parsed_db.password or not parsed_db.hostname or not parsed_db.path.lstrip("/"):
        add("error", "DATABASE_URL", "DATABASE_URL deve conter usuario, senha, host e banco.")

    if not _base64_decodes_to_32_bytes(_get(env, "ENCRYPTION_SALT")):
        add("error", "ENCRYPTION_SALT", "Defina ENCRYPTION_SALT Base64 com exatamente 32 bytes.")

    if not _is_truthy(_get(env, "REQUIRE_ADMIN_2FA") or "true"):
        add("error", "REQUIRE_ADMIN_2FA", "Mantenha REQUIRE_ADMIN_2FA=true em producao.")

    public_url = _get(env, "PUBLIC_BASE_URL") or _get(env, "HEALTHCHECK_URL")
    if not public_url:
        integration("PUBLIC_BASE_URL", "Defina PUBLIC_BASE_URL ou HEALTHCHECK_URL com a URL HTTPS publica.")
    else:
        parsed_public = urlparse(public_url)
        if parsed_public.scheme != "https" or not parsed_public.hostname or "." not in parsed_public.hostname:
            integration("PUBLIC_BASE_URL", "A URL publica deve usar HTTPS e dominio real.")

    metrics_token = _get(env, "METRICS_TOKEN")
    if _is_placeholder(metrics_token) or len(metrics_token) < 32:
        integration("METRICS_TOKEN", "Defina METRICS_TOKEN aleatorio com pelo menos 32 caracteres.")

    backup_key = _get(env, "BACKUP_ENCRYPTION_KEY")
    if not _base64_decodes_to_32_bytes(backup_key, urlsafe=True):
        integration("BACKUP_ENCRYPTION_KEY", "Defina BACKUP_ENCRYPTION_KEY URL-safe Base64 com exatamente 32 bytes.")

    upload_folder = _get(env, "REPORTS_UPLOAD_FOLDER")
    if not upload_folder:
        integration("REPORTS_UPLOAD_FOLDER", "Defina REPORTS_UPLOAD_FOLDER em volume privado persistente.")
    else:
        normalized = Path(upload_folder).as_posix().lower()
        if "/static" in normalized or normalized.endswith("/static"):
            add("error", "REPORTS_UPLOAD_FOLDER", "Uploads sensíveis não podem ficar dentro de static.")

    alert_email = _get(env, "ALERT_EMAIL")
    alert_webhook = _get(env, "ALERT_WEBHOOK_URL")
    if not alert_email and not alert_webhook:
        integration("ALERT_CHANNEL", "Configure ALERT_EMAIL ou ALERT_WEBHOOK_URL para falhas operacionais.")
    if alert_webhook:
        parsed_webhook = urlparse(alert_webhook)
        allowed_hosts = {
            item.strip().lower()
            for item in _get(env, "ALERT_WEBHOOK_ALLOWED_HOSTS").split(",")
            if item.strip()
        }
        if parsed_webhook.scheme != "https" or not parsed_webhook.hostname:
            add("error", "ALERT_WEBHOOK_URL", "Webhook de alerta deve usar HTTPS.")
        elif parsed_webhook.hostname.lower() not in allowed_hosts:
            add("error", "ALERT_WEBHOOK_ALLOWED_HOSTS", "Inclua o host do webhook em ALERT_WEBHOOK_ALLOWED_HOSTS.")

    smtp_host = _get(env, "SMTP_HOST")
    mail_from = _get(env, "MAIL_FROM")
    if not smtp_host or not mail_from:
        integration("SMTP", "Configure SMTP_HOST e MAIL_FROM para recuperação de senha por e-mail.")

    meta_values = (
        _get(env, "WHATSAPP_CLOUD_API_TOKEN"),
        _get(env, "WHATSAPP_CLOUD_PHONE_NUMBER_ID"),
        _get(env, "WHATSAPP_CLOUD_API_VERSION"),
    )
    gateway_values = (_get(env, "WPP_SERVER_URL"), _get(env, "WPP_SECRET"), _get(env, "WPP_ALLOWED_HOSTS"))
    if any(meta_values) and not all(meta_values):
        add("error", "WHATSAPP_CLOUD", "Preencha token, phone number id e versao da Meta Cloud API juntos.")
    if any(gateway_values) and not all(gateway_values):
        add("error", "WPP_GATEWAY", "Preencha URL, segredo e allowlist do gateway WhatsApp juntos.")
    if not any(meta_values) and not any(gateway_values):
        integration("WHATSAPP", "WhatsApp automático não configurado; o sistema ficará no fallback manual.")

    return issues
