"""
Registro de eventos/auditoria do sistema.
"""
from datetime import datetime, timezone

from sqlalchemy import null

from app.extensions import db

TIPOS_EVENTO = ("criacao","edicao","exclusao","login","logout","status","pagamento","sistema")
_MISSING = object()

class EventoLog(db.Model):
    __tablename__ = "eventos_log"
    __table_args__ = (
        db.Index("ix_eventos_org_criado", "organization_id", "criado_em"),
        db.Index("ix_eventos_org_tipo_criado", "organization_id", "tipo", "criado_em"),
        db.Index("ix_eventos_org_modulo_criado", "organization_id", "modulo", "criado_em"),
    )

    id          = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=True, default=1, index=True)
    usuario_id  = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    usuario_nome= db.Column(db.String(120))           # desnormalizado para histórico
    tipo        = db.Column(db.String(30), nullable=False)
    modulo      = db.Column(db.String(50))             # clientes, os, estoque, etc
    operacao    = db.Column(db.String(200))
    descricao   = db.Column(db.Text)
    criado_em   = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    usuario = db.relationship("Usuario", backref=db.backref("eventos", lazy=True))

    def to_dict(self):
        return {
            "id": self.id, "usuario_id": self.usuario_id,
            "usuario_nome": self.usuario_nome,
            "tipo": self.tipo, "modulo": self.modulo,
            "operacao": self.operacao, "descricao": self.descricao,
            "criado_em": self.criado_em.isoformat(),
        }

def registrar(tipo, modulo, operacao, descricao="", usuario_id=None, usuario_nome=None, organization_id=_MISSING):
    from flask import g, has_request_context
    from flask import session as flask_session
    in_request = has_request_context()
    request_user_id = flask_session.get("usuario_id") if in_request else None
    request_user_name = flask_session.get("usuario_nome", "Sistema") if in_request else "Sistema"
    request_organization_id = getattr(g, "organization_id", None) if in_request else None
    uid = usuario_id or request_user_id
    uname = usuario_nome or request_user_name
    tenant_id = organization_id if organization_id is not _MISSING else (request_organization_id or 1)
    if organization_id is None:
        tenant_id = null()
    ev = EventoLog(usuario_id=uid, usuario_nome=uname, organization_id=tenant_id,
                   tipo=tipo, modulo=modulo, operacao=operacao, descricao=descricao)
    db.session.add(ev)
    # Não faz commit aqui — o caller faz junto com a operação principal
