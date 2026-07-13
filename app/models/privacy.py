"""Registros operacionais de privacidade e atendimento ao titular."""
from datetime import datetime, timezone

from app.extensions import db


def _now():
    return datetime.now(timezone.utc)


class ConsentRecord(db.Model):
    __tablename__ = "consent_records"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey("clientes.id"), nullable=False, index=True)
    purpose = db.Column(db.String(60), nullable=False)
    granted = db.Column(db.Boolean, nullable=False)
    source = db.Column(db.String(60), nullable=False, default="admin")
    registrado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    registrado_em = db.Column(db.DateTime, nullable=False, default=_now)


class DataSubjectRequest(db.Model):
    __tablename__ = "data_subject_requests"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey("clientes.id"), nullable=False, index=True)
    request_type = db.Column(db.String(40), nullable=False)
    status = db.Column(db.String(30), nullable=False, default="open")
    solicitado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    solicitado_em = db.Column(db.DateTime, nullable=False, default=_now)
    concluido_em = db.Column(db.DateTime)
    observacoes = db.Column(db.Text)
