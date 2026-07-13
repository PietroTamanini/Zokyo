"""
Registro de eventos/auditoria do sistema.
"""
from datetime import datetime, timezone

from app.extensions import db

TIPOS_EVENTO = ("criacao","edicao","exclusao","login","logout","status","pagamento","sistema")

class EventoLog(db.Model):
    __tablename__ = "eventos_log"
    id          = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, default=1, index=True)
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

def registrar(tipo, modulo, operacao, descricao="", usuario_id=None, usuario_nome=None, organization_id=None):
    from flask import has_request_context
    from flask import session as flask_session
    request_user_id = flask_session.get("usuario_id") if has_request_context() else None
    request_user_name = flask_session.get("usuario_nome", "Sistema") if has_request_context() else "Sistema"
    uid = usuario_id or request_user_id
    uname = usuario_nome or request_user_name
    ev = EventoLog(usuario_id=uid, usuario_nome=uname, organization_id=organization_id or 1,
                   tipo=tipo, modulo=modulo, operacao=operacao, descricao=descricao)
    db.session.add(ev)
    # Não faz commit aqui — o caller faz junto com a operação principal
