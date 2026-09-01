import base64

from app.utils.production_readiness import check_production_readiness


def _valid_base64_32_bytes(fill: bytes = b"0") -> str:
    return base64.b64encode(fill * 32).decode("ascii")


def _valid_urlsafe_base64_32_bytes() -> str:
    return base64.urlsafe_b64encode(b"1" * 32).decode("ascii")


def _production_env() -> dict[str, str]:
    return {
        "FLASK_ENV": "production",
        "SECRET_KEY": "s" * 32,  # pragma: allowlist secret
        "DATABASE_URL": "mysql+pymysql://zokyo:" + "senha" + "@db:3306/zokyo",
        "ENCRYPTION_SALT": _valid_base64_32_bytes(),
        "BLIND_INDEX_KEY": _valid_urlsafe_base64_32_bytes(),
        "REQUIRE_ADMIN_2FA": "true",
        "PUBLIC_BASE_URL": "https://zokyo.example.com",
        "METRICS_TOKEN": "m" * 32,
        "BACKUP_ENCRYPTION_KEY": _valid_urlsafe_base64_32_bytes(),
        "REPORTS_UPLOAD_FOLDER": "/var/lib/zokyo/uploads/reports",
        "ALERT_EMAIL": "ops@example.com",
        "SMTP_HOST": "smtp.example.com",
        "MAIL_FROM": "no-reply@example.com",
        "WHATSAPP_CLOUD_API_TOKEN": "meta-token",
        "WHATSAPP_CLOUD_PHONE_NUMBER_ID": "1234567890",
        "WHATSAPP_CLOUD_API_VERSION": "v23.0",
        "REDIS_URL": "redis://redis:6379/0",
    }


def test_production_readiness_reprova_pendencias_criticas():
    issues = check_production_readiness(
        {
            "FLASK_ENV": "development",
            "SECRET_KEY": "curta",  # pragma: allowlist secret
            "DATABASE_URL": "sqlite:///:memory:",
            "ENCRYPTION_SALT": "invalido",
            "BLIND_INDEX_KEY": "invalido",
        },
        strict_integrations=True,
    )

    errors = {issue.code for issue in issues if issue.severity == "error"}
    assert {"FLASK_ENV", "SECRET_KEY", "DATABASE_URL", "ENCRYPTION_SALT", "BLIND_INDEX_KEY"}.issubset(errors)


def test_production_readiness_aprova_env_completo_em_modo_estrito():
    issues = check_production_readiness(_production_env(), strict_integrations=True)

    assert issues == []


def test_production_readiness_cobre_configuracoes_inseguras_especificas():
    env = _production_env()
    env.update(
        {
            "DATABASE_URL": "mysql+pymysql://zokyo@db/zokyo",
            "ENCRYPTION_SALT": "nao-ascii-\u2603",
            "BLIND_INDEX_KEY": "curta",
            "REQUIRE_ADMIN_2FA": "false",
            "PUBLIC_BASE_URL": "http://localhost:8000",
            "REPORTS_UPLOAD_FOLDER": "/srv/app/static/reports",
            "ALERT_WEBHOOK_URL": "http://alerts.example.com/hook",
            "ALERT_WEBHOOK_ALLOWED_HOSTS": "",
            "WHATSAPP_CLOUD_API_TOKEN": "token",
            "WHATSAPP_CLOUD_PHONE_NUMBER_ID": "",
            "WHATSAPP_CLOUD_API_VERSION": "v23.0",
            "WPP_SERVER_URL": "https://whatsapp.example.com",
            "WPP_SECRET": "",
            "WPP_ALLOWED_HOSTS": "whatsapp.example.com",
        }
    )

    codes = {issue.code for issue in check_production_readiness(env, strict_integrations=True)}

    assert {
        "DATABASE_URL",
        "ENCRYPTION_SALT",
        "BLIND_INDEX_KEY",
        "REQUIRE_ADMIN_2FA",
        "PUBLIC_BASE_URL",
        "REPORTS_UPLOAD_FOLDER",
        "ALERT_WEBHOOK_URL",
        "WHATSAPP_CLOUD",
        "WPP_GATEWAY",
    }.issubset(codes)


def test_production_readiness_reprova_webhook_fora_da_allowlist_e_placeholder():
    env = _production_env()
    env.update(
        {
            "DATABASE_URL": "SUBSTITUA",
            "ALERT_EMAIL": "",
            "ALERT_WEBHOOK_URL": "https://alerts.example.com/hook",
            "ALERT_WEBHOOK_ALLOWED_HOSTS": "outro.example.com",
        }
    )

    codes = {issue.code for issue in check_production_readiness(env)}

    assert "DATABASE_URL" in codes
    assert "ALERT_WEBHOOK_ALLOWED_HOSTS" in codes
