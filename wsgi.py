"""Entrada WSGI/CLI sem colisao com o pacote app/."""
import os

from app import create_app
from app.utils.logging_config import configure_logging

flask_env = os.environ.get("FLASK_ENV", "development")
app = create_app(flask_env)
configure_logging(app)
