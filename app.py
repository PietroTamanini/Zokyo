"""
app.py — Ponto de entrada da aplicação.

Desenvolvimento:  python app.py
Produção:         gunicorn -c gunicorn.conf.py app:app
"""
import os

from app import create_app

_env = os.environ.get("FLASK_ENV", "development")
app  = create_app(_env)

# Configura logging após criação da app
from app.utils.logging_config import configure_logging
configure_logging(app)

if __name__ == "__main__":
    is_dev = _env == "development"
    app.run(
        host  = "127.0.0.1",   # Nunca bind 0.0.0.0 em produção manual
        port  = int(os.environ.get("PORT", 5000)),
        debug = is_dev,
    )
