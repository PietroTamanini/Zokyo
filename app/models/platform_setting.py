"""Configurações globais editáveis pelo administrador da plataforma."""

from app.extensions import db


class PlatformSetting(db.Model):
    __tablename__ = "platform_settings"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(80), nullable=False, unique=True)
    value = db.Column(db.String(500), nullable=True)

    @classmethod
    def get_value(cls, key: str, default=None):
        item = cls.query.execution_options(include_all_tenants=True).filter_by(key=key).first()
        return item.value if item and item.value else default

    @classmethod
    def set_value(cls, key: str, value: str | None):
        item = cls.query.execution_options(include_all_tenants=True).filter_by(key=key).first()
        if not item:
            item = cls(key=key)
            db.session.add(item)
        item.value = value
        return item
