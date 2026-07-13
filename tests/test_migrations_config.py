import os
import sqlite3
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from app import create_app


def test_flask_migrate_registrado():
    app = create_app("development")
    assert "migrate" in app.extensions


def test_producao_desabilita_create_all():
    os.environ["SECRET_KEY"] = "prod-secret-key"
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    app = create_app("production")
    assert app.config["DISABLE_CREATE_ALL"] is True


def test_migrations_criam_schema_completo_em_banco_vazio(tmp_path):
    database = tmp_path / "fresh.db"
    repo = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.update({
        "DATABASE_URL": f"sqlite:///{database.as_posix()}",
        "SECRET_KEY": "migration-test-secret",
        "DISABLE_CREATE_ALL": "true",
        "SCHEDULER_ENABLED": "false",
    })
    subprocess.run(
        [sys.executable, "-m", "flask", "--app", "wsgi:app", "db", "upgrade"],
        cwd=repo,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    with sqlite3.connect(database) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        photo_columns = {row[1] for row in connection.execute("PRAGMA table_info(laudo_fotos)")}
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert {"organizations", "usuarios", "clientes", "ordens_servico", "laudos_tecnicos", "laudo_fotos", "laudo_templates", "notifications", "retention_policies"} <= tables
    assert "thumbnail_key" in photo_columns
    assert revision == "20260712_0026"
