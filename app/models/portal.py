"""Tokens publicos de acompanhamento e aprovacao de orcamento."""
from datetime import datetime, timezone

from app.extensions import db


def _now():
    return datetime.now(timezone.utc)


class PortalToken(db.Model):
    __tablename__ = "portal_tokens"
    __table_args__ = (
        db.Index("ix_portal_token_os_purpose", "os_id", "purpose", "revogado_em"),
    )

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    os_id = db.Column(db.Integer, db.ForeignKey("ordens_servico.id"), nullable=False, index=True)
    token_hash = db.Column(db.String(64), nullable=False, unique=True)
    purpose = db.Column(db.String(30), nullable=False, default="tracking")
    criado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    criado_em = db.Column(db.DateTime, nullable=False, default=_now)
    expira_em = db.Column(db.DateTime, nullable=False)
    usado_em = db.Column(db.DateTime)
    revogado_em = db.Column(db.DateTime)

    os = db.relationship("OrdemServico", foreign_keys=[os_id])
    criado_por = db.relationship("Usuario", foreign_keys=[criado_por_id])

    @property
    def valido(self):
        now = _now().replace(tzinfo=None)
        expires = self.expira_em.replace(tzinfo=None) if self.expira_em else now
        return self.revogado_em is None and expires > now
