import base64

from scripts.generate_production_env import generate_lines, main


def _env_map(lines):
    return dict(line.split("=", 1) for line in lines if line and not line.startswith("#"))


def test_generate_production_env_cria_segredos_fortes(capsys):
    lines = generate_lines(
        "https://zokyo.example.com",
        "mysql+pymysql://user:pass@db:3306/zokyo?charset=utf8mb4",
        "redis://redis:6379/0",
    )
    env = _env_map(lines)

    assert env["FLASK_ENV"] == "production"
    assert env["PUBLIC_BASE_URL"] == "https://zokyo.example.com"
    assert env["DATABASE_URL"] == "mysql+pymysql://user:pass@db:3306/zokyo?charset=utf8mb4"
    assert env["REDIS_URL"] == "redis://redis:6379/0"
    assert len(env["SECRET_KEY"]) == 64
    assert len(env["METRICS_TOKEN"]) == 64
    assert len(env["ASAAS_WEBHOOK_TOKEN"]) == 64
    assert len(base64.b64decode(env["ENCRYPTION_SALT"].encode("ascii"))) == 32
    assert len(base64.urlsafe_b64decode(env["BLIND_INDEX_KEY"].encode("ascii"))) == 32
    assert len(base64.urlsafe_b64decode(env["BACKUP_ENCRYPTION_KEY"].encode("ascii"))) == 32

    assert main(["--public-base-url", "https://prod.example.com"]) == 0
    assert "PUBLIC_BASE_URL=https://prod.example.com" in capsys.readouterr().out
