"""Tokens de recuperacao de senha armazenados somente como hash."""
from datetime import datetime, timezone

from app.extensions import db


def _now():
    return datetime.now(timezone.utc)


class PasswordResetToken(db.Model):
    __tablename__ = "password_reset_tokens"
    __table_args__ = (
        db.Index("ix_password_reset_user_created", "usuario_id", "criado_em"),
        db.Index("ix_password_reset_expires", "expira_em"),
    )

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    token_hash = db.Column(db.String(64), unique=True, nullable=False)
    criado_em = db.Column(db.DateTime, default=_now, nullable=False)
    expira_em = db.Column(db.DateTime, nullable=False)
    usado_em = db.Column(db.DateTime)
    solicitado_ip_hash = db.Column(db.String(64))

    usuario = db.relationship("Usuario")
