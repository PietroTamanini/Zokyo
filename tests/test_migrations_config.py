import base64
import importlib
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

import config as config_module
from app import create_app


def valid_encryption_salt():
    return base64.b64encode(b"0" * 32).decode("ascii")


def test_flask_migrate_registrado():
    app = create_app("development")
    assert "migrate" in app.extensions


def test_producao_desabilita_create_all(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "prod-secret-key-with-32-plus-chars")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("ENCRYPTION_SALT", valid_encryption_salt())
    app = create_app("production")
    assert app.config["DISABLE_CREATE_ALL"] is True


def test_producao_nao_libera_origens_locais_do_portal_por_padrao(monkeypatch):
    monkeypatch.delenv("DJTECH_SITE_ORIGINS", raising=False)
    monkeypatch.setenv("SECRET_KEY", "prod-secret-key-with-32-plus-chars")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("ENCRYPTION_SALT", valid_encryption_salt())
    app = create_app("production")
    origins = app.config["DJTECH_SITE_ORIGINS"]
    assert "localhost" not in origins
    assert "127.0.0.1" not in origins
    assert "https://djtechinfo.com.br" in origins


def test_producao_exige_encryption_salt(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "prod-secret-key-with-32-plus-chars")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.delenv("ENCRYPTION_SALT", raising=False)

    with pytest.raises(RuntimeError, match="ENCRYPTION_SALT"):
        create_app("production")


def test_config_cobre_fallback_dev_mysql_e_erros_de_producao(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("DATABASE_URL", "mysql+pymysql://user:pass@localhost/db")
    reloaded = importlib.reload(config_module)
    assert reloaded.Config.SECRET_KEY
    assert reloaded.Config.SQLALCHEMY_ENGINE_OPTIONS["pool_size"] == 10

    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        reloaded.ProductionConfig.init_app(None)

    monkeypatch.setenv("SECRET_KEY", "prod-secret-key-with-32-plus-chars")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        reloaded.ProductionConfig.init_app(None)

    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("ENCRYPTION_SALT", "nao-e-base64!")
    with pytest.raises(RuntimeError, match="ENCRYPTION_SALT"):
        reloaded.ProductionConfig.init_app(None)

    monkeypatch.setenv("SECRET_KEY", "test-secret-key-with-32-plus-chars")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("ENCRYPTION_SALT", valid_encryption_salt())
    importlib.reload(config_module)


def test_migrations_criam_schema_completo_em_banco_vazio(tmp_path):
    database = tmp_path / "fresh.db"
    repo = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.update({
        "DATABASE_URL": f"sqlite:///{database.as_posix()}",
        "SECRET_KEY": "migration-test-secret-with-32-plus-chars",
        "DISABLE_CREATE_ALL": "true",
        "SCHEDULER_ENABLED": "false",
    })
    result = subprocess.run(
        [sys.executable, "-m", "flask", "--app", "wsgi:app", "db", "upgrade"],
        cwd=repo,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    with sqlite3.connect(database) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        organization_columns = {row[1] for row in connection.execute("PRAGMA table_info(organizations)")}
        user_columns = {row[1] for row in connection.execute("PRAGMA table_info(usuarios)")}
        photo_columns = {row[1] for row in connection.execute("PRAGMA table_info(laudo_fotos)")}
        config_columns = {row[1] for row in connection.execute("PRAGMA table_info(configuracoes)")}
        order_columns = {row[1] for row in connection.execute("PRAGMA table_info(ordens_servico)")}
        order_part_columns = {row[1] for row in connection.execute("PRAGMA table_info(os_pecas)")}
        part_columns = {row[1] for row in connection.execute("PRAGMA table_info(pecas)")}
        service_columns = {row[1] for row in connection.execute("PRAGMA table_info(defeitos_padrao)")}
        order_indexes = {row[1] for row in connection.execute("PRAGMA index_list(ordens_servico)")}
        report_indexes = {row[1] for row in connection.execute("PRAGMA index_list(laudos_tecnicos)")}
        notification_indexes = {row[1] for row in connection.execute("PRAGMA index_list(notifications)")}
        collection_indexes = {row[1] for row in connection.execute("PRAGMA index_list(coletas_agendadas)")}
        counter_foreign_keys = list(connection.execute("PRAGMA foreign_key_list(laudo_counters)"))
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert {"organizations", "usuarios", "clientes", "ordens_servico", "laudos_tecnicos", "laudo_fotos", "laudo_templates", "notifications", "retention_policies"} <= tables
    assert "thumbnail_key" in photo_columns
    assert {"subdomain", "custom_domain", "dns_status", "dns_last_error"} <= organization_columns
    assert "is_platform_admin" in user_columns
    assert {"subtitulo_empresa", "logo_url", "site_url", "instagram_url", "whatsapp_publico"} <= config_columns
    assert {"os_status_options", "os_priority_options", "attendance_type_options", "entry_checklist_options"} <= config_columns
    assert "tipo_atendimento" in order_columns
    assert {"horas_trabalho", "custo_hora"} <= order_columns
    assert {"link_compra", "custo_unitario"} <= order_part_columns
    assert {"ativo", "deletado_em"} <= part_columns
    assert {"ativo", "deletado_em"} <= service_columns
    assert {"ix_os_org_open_tecnico_prev", "ix_os_org_deleted_atualizado"} <= order_indexes
    assert {"ix_laudos_org_status_tipo_criado", "ix_laudos_org_cliente_criado"} <= report_indexes
    assert "ix_notifications_org_status_next" in notification_indexes
    assert "ix_coletas_org_status_agendada_criado" in collection_indexes
    assert any(row[2] == "organizations" and row[3] == "organization_id" for row in counter_foreign_keys)
    assert revision == "20260911_0023"
