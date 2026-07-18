"""Ambiente deterministico carregado pelo pytest antes dos modulos de teste."""
import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SECRET_KEY"] = "pytest-secret-key"  # pragma: allowlist secret
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["DISABLE_CREATE_ALL"] = "true"
