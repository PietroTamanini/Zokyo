"""
extensions.py
-------------
Instâncias compartilhadas de extensões Flask.
Importar daqui evita imports circulares entre app/__init__.py e models.
"""

from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
migrate = Migrate()
