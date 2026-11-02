"""Leitura das configurações globais da plataforma."""

from flask import current_app, has_app_context
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.models import PlatformSetting


def get_platform_setting(key: str, default=None):
    try:
        value = PlatformSetting.get_value(key, None)
    except (OperationalError, ProgrammingError):
        value = None
    return value if value else default


def get_base_domain() -> str:
    fallback = "tamanini.dev.br"
    if has_app_context():
        fallback = current_app.config.get("TENANT_BASE_DOMAIN", fallback) or fallback
    return str(get_platform_setting("tenant_base_domain", fallback)).strip().lower().strip(".")
