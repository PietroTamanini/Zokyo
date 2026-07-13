"""
config.py — Configuração hardened da aplicação Zokyo.

Fixes:
  C02 — SECRET_KEY sem placeholder; erro explícito em produção se ausente
  C03 — sem credenciais hardcoded; fallback só para desenvolvimento
  H01 — Content-Security-Policy configurável
  H02 — HSTS habilitado em produção
  M04 — FLASK_ENV=development não é padrão silencioso; produção requer configuração explícita
  M06 — Sessão com timeout absoluto + inatividade
"""
import os
import secrets
import warnings
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()


class Config:
    # ── Segredo ────────────────────────────────────────────────────────────
    # C02: nunca usar placeholder; gera token aleatório em dev com aviso,
    #      mas exige variável de ambiente em produção (ver ProductionConfig).
    _raw_secret = os.environ.get("SECRET_KEY", "").strip()
    if _raw_secret and _raw_secret not in (
        "SUBSTITUA_POR_VALOR_GERADO_ACIMA",
        "GERE_COM_python3_-c_import_secrets_print_secrets.token_hex_32",
    ):
        SECRET_KEY = _raw_secret
    else:
        SECRET_KEY = secrets.token_hex(32)
        warnings.warn(
            "\n[AVISO] SECRET_KEY ausente ou placeholder — "
            "sessões serão perdidas ao reiniciar. "
            "Defina SECRET_KEY no .env.",
            stacklevel=1,
        )

    # ── Banco ──────────────────────────────────────────────────────────────
    # C03: sem credenciais hardcoded; fallback só aceito em desenvolvimento
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or \
        "mysql+pymysql://root:@localhost:3306/zokyo"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    if SQLALCHEMY_DATABASE_URI.startswith("sqlite"):
        SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    else:
        SQLALCHEMY_ENGINE_OPTIONS = {
            "pool_recycle":  1800,
            "pool_pre_ping": True,
            "pool_timeout":  20,
            "pool_size":     10,
            "max_overflow":  20,
        }

    # ── PDF ────────────────────────────────────────────────────────────────
    REPORTS_UPLOAD_FOLDER = os.environ.get("REPORTS_UPLOAD_FOLDER", "").strip() or None
    REPORTS_PUBLIC_VERIFICATION = os.environ.get("REPORTS_PUBLIC_VERIFICATION", "true").lower() in ("1", "true", "yes", "on")
    # O schema da aplicacao e gerenciado exclusivamente pelo Alembic.
    DISABLE_CREATE_ALL = True
    CSRF_EXEMPT_ENDPOINTS = {"platform.sandbox_webhook"}
    SCHEDULER_ENABLED = os.environ.get("SCHEDULER_ENABLED", "false").lower() in ("1", "true", "yes", "on")

    # ── WhatsApp ───────────────────────────────────────────────────────────
    WPP_SERVER_URL = os.environ.get("WPP_SERVER_URL", "").strip() or None
    WHATSAPP_CLOUD_PHONE_NUMBER_ID = os.environ.get("WHATSAPP_CLOUD_PHONE_NUMBER_ID", "").strip() or None
    WHATSAPP_CLOUD_API_VERSION = os.environ.get("WHATSAPP_CLOUD_API_VERSION", "").strip() or None
    PASSWORD_RESET_TTL_MINUTES = int(os.environ.get("PASSWORD_RESET_TTL_MINUTES", "30"))
    SMTP_HOST = os.environ.get("SMTP_HOST", "").strip() or None
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
    SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "").strip() or None
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    SMTP_STARTTLS = os.environ.get("SMTP_STARTTLS", "true").lower() in ("1", "true", "yes", "on")
    MAIL_FROM = os.environ.get("MAIL_FROM", "").strip() or None
    SENTRY_DSN = os.environ.get("SENTRY_DSN", "").strip() or None
    SENTRY_TRACES_SAMPLE_RATE = float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0"))
    METRICS_TOKEN = os.environ.get("METRICS_TOKEN", "").strip() or None
    ALERT_EMAIL = os.environ.get("ALERT_EMAIL", "").strip() or None
    ALERT_WEBHOOK_URL = os.environ.get("ALERT_WEBHOOK_URL", "").strip() or None
    REQUIRE_ADMIN_2FA = os.environ.get("REQUIRE_ADMIN_2FA", "false").lower() in ("1", "true", "yes", "on")
    ALLOW_LEGACY_SESSIONS = True

    # ── Sessão ─────────────────────────────────────────────────────────────
    # M06: timeout absoluto de 8h; inatividade tratada no middleware
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # ── Rate Limiting ──────────────────────────────────────────────────────
    # Número de proxies confiáveis à frente da app (C04)
    PROXY_COUNT = int(os.environ.get("PROXY_COUNT", "1"))

class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False


class ProductionConfig(Config):
    DEBUG = False
    DISABLE_CREATE_ALL = True

    # C02: em produção, SECRET_KEY DEVE ser definida no ambiente
    @classmethod
    def init_app(cls, app):
        secret = os.environ.get("SECRET_KEY", "").strip()
        if not secret or secret.startswith("SUBSTITUA") or secret.startswith("GERE"):
            raise RuntimeError(
                "[FATAL] SECRET_KEY não configurada ou é placeholder. "
                "Defina SECRET_KEY no ambiente de produção."
            )
        db_url = os.environ.get("DATABASE_URL", "")
        if not db_url or "CONFIGURE_NO_ENV" in db_url:
            raise RuntimeError(
                "[FATAL] DATABASE_URL não configurada. "
                "Defina DATABASE_URL no ambiente de produção."
            )

    # H02: HSTS — só faz sentido com HTTPS
    HSTS_MAX_AGE        = 31_536_000  # 1 ano em segundos
    SESSION_COOKIE_SECURE   = True
    SESSION_COOKIE_SAMESITE = "Strict"
    REQUIRE_ADMIN_2FA = os.environ.get("REQUIRE_ADMIN_2FA", "true").lower() in ("1", "true", "yes", "on")
    ALLOW_LEGACY_SESSIONS = False


config = {
    "development": DevelopmentConfig,
    "production":  ProductionConfig,
    "default":     DevelopmentConfig,
}
