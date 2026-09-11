"""Organizacoes para isolamento incremental multiempresa."""
import uuid
from datetime import datetime, timezone

from app.extensions import db


class Organization(db.Model):
    __tablename__ = "organizations"

    id = db.Column(db.Integer, primary_key=True)
    public_uuid = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    nome = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(80), unique=True, nullable=False)
    subdomain = db.Column(db.String(80), unique=True)
    custom_domain = db.Column(db.String(255), unique=True)
    dns_status = db.Column(db.String(30), nullable=False, default="pending")
    dns_last_error = db.Column(db.String(500))
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    criado_em = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    @property
    def hostnames(self):
        return [item for item in (self.custom_domain,) if item]
