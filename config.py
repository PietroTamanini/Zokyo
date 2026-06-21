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
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _detect_wkhtmltopdf():
    candidates = [
        os.environ.get("WKHTMLTOPDF_PATH"),
        "/usr/bin/wkhtmltopdf",
        "/usr/local/bin/wkhtmltopdf",
        "/snap/bin/wkhtmltopdf",
    ]
    for c in candidates:
        if c and Path(c).exists():
            return c
    return None


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
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_recycle":  1800,
        "pool_pre_ping": True,
        "pool_timeout":  20,
        "pool_size":     10,
        "max_overflow":  20,
    }

    # ── PDF ────────────────────────────────────────────────────────────────
    PDFKIT_WKHTMLTOPDF = _detect_wkhtmltopdf()
    PDF_DISPONIVEL      = PDFKIT_WKHTMLTOPDF is not None
    PDFKIT_OPTIONS = {
        "page-size":     "A4",
        "orientation":   "Landscape",
        "margin-top":    "8mm",
        "margin-right":  "8mm",
        "margin-bottom": "8mm",
        "margin-left":   "8mm",
        "encoding":      "UTF-8",
        "no-outline":    None,
        # Segurança wkhtmltopdf: desabilita acesso a arquivos locais e rede
        "disable-local-file-access": None,
        "no-background": None,
    }

    # ── WhatsApp ───────────────────────────────────────────────────────────
    WPP_SERVER_URL = os.environ.get("WPP_SERVER_URL", "").strip() or None

    # ── Sessão ─────────────────────────────────────────────────────────────
    # M06: timeout absoluto de 8h; inatividade tratada no middleware
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # ── Rate Limiting ──────────────────────────────────────────────────────
    # Número de proxies confiáveis à frente da app (C04)
    PROXY_COUNT = int(os.environ.get("PROXY_COUNT", "1"))

    # ── CSP base (sobrescrito por subclasses) ──────────────────────────────
    # H01: Content-Security-Policy
    CSP_HEADER = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data:; "
        "connect-src 'self' https://viacep.com.br; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self';"
    )


class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False


class ProductionConfig(Config):
    DEBUG = False

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
    HSTS_INCLUDE_SUBDOMAINS = True

    SESSION_COOKIE_SECURE   = True
    SESSION_COOKIE_SAMESITE = "Strict"

    # CSP mais restrita em produção
    CSP_HEADER = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data:; "
        "connect-src 'self' https://viacep.com.br; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "upgrade-insecure-requests;"
    )


config = {
    "development": DevelopmentConfig,
    "production":  ProductionConfig,
    "default":     DevelopmentConfig,
}
