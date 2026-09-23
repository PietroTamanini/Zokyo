"""Generate safe production environment values for Zokyo.

The command prints values to stdout only. Store the output in a password
manager, secret manager, or protected environment file outside Git.
"""
from __future__ import annotations

import argparse
import base64
import secrets
from collections.abc import Iterable


def _hex_secret(bytes_len: int = 32) -> str:
    return secrets.token_hex(bytes_len)


def _b64_secret(*, urlsafe: bool = False, bytes_len: int = 32) -> str:
    raw = secrets.token_bytes(bytes_len)
    encoder = base64.urlsafe_b64encode if urlsafe else base64.b64encode
    return encoder(raw).decode("ascii")


def generate_lines(public_base_url: str, database_url: str, redis_url: str) -> list[str]:
    """Return a production env skeleton with freshly generated secret values."""
    return [
        "# Zokyo production secrets generated locally.",
        "# Review URLs, SMTP, alerting, WhatsApp, DNS, storage and billing before go-live.",
        "FLASK_ENV=production",
        f"SECRET_KEY={_hex_secret()}",
        f"DATABASE_URL={database_url}",
        "DB_POOL_SIZE=10",
        "DB_MAX_OVERFLOW=20",
        "DB_POOL_TIMEOUT=20",
        "DB_POOL_RECYCLE=900",
        "DB_ISOLATION_LEVEL=READ COMMITTED",
        f"ENCRYPTION_SALT={_b64_secret()}",
        f"BLIND_INDEX_KEY={_b64_secret(urlsafe=True)}",
        f"PUBLIC_BASE_URL={public_base_url}",
        "PROXY_COUNT=1",
        "REPORTS_UPLOAD_FOLDER=/var/lib/zokyo/uploads/reports",
        "REPORTS_PUBLIC_VERIFICATION=true",
        "SCHEDULER_ENABLED=false",
        f"METRICS_TOKEN={_hex_secret()}",
        f"BACKUP_ENCRYPTION_KEY={_b64_secret(urlsafe=True)}",
        "REQUIRE_ADMIN_2FA=true",
        f"REDIS_URL={redis_url}",
        "SMTP_HOST=",
        "SMTP_PORT=587",
        "SMTP_USERNAME=",
        "SMTP_PASSWORD=",
        "SMTP_STARTTLS=true",
        "MAIL_FROM=",
        "ALERT_EMAIL=",
        "ALERT_WEBHOOK_URL=",
        "ALERT_WEBHOOK_ALLOWED_HOSTS=",
        "WHATSAPP_CLOUD_API_TOKEN=",
        "WHATSAPP_CLOUD_PHONE_NUMBER_ID=",
        "WHATSAPP_CLOUD_API_VERSION=",
        "ASAAS_API_KEY=",
        "ASAAS_SANDBOX=false",
        f"ASAAS_WEBHOOK_TOKEN={_hex_secret()}",
        f"BILLING_SANDBOX_SECRET={_hex_secret()}",
        "TENANT_BASE_DOMAIN=seudominio.com",
        "TENANT_DNS_MODE=wildcard",
        "TENANT_DNS_TARGET=",
        "CLOUDFLARE_API_TOKEN=",
        "CLOUDFLARE_ZONE_ID=",
        "GUNICORN_WORKERS=4",
        "GUNICORN_ACCESSLOG=-",
        "GUNICORN_ERRORLOG=-",
        "GUNICORN_FORWARDED_IPS=*",
    ]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Print a Zokyo production env skeleton with generated secrets.",
    )
    parser.add_argument(
        "--public-base-url",
        default="https://zokyo.seudominio.com",
        help="Final HTTPS public URL used by links and readiness checks.",
    )
    parser.add_argument(
        "--database-url",
        default="mysql+pymysql://zokyo:SUBSTITUA_SENHA_FORTE@db:3306/zokyo?charset=utf8mb4",
        help="SQLAlchemy MariaDB/MySQL URL. Replace the password before using.",
    )
    parser.add_argument(
        "--redis-url",
        default="redis://redis:6379/0",
        help="Redis URL for sessions and distributed rate limits.",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    print("\n".join(generate_lines(args.public_base_url, args.database_url, args.redis_url)))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
