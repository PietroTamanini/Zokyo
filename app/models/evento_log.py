"""Registro de eventos/auditoria do sistema com encadeamento de integridade."""
import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import null, select, update
from sqlalchemy import event

from app.extensions import db

TIPOS_EVENTO = ("criacao","edicao","exclusao","login","logout","acesso","status","pagamento","sistema")
_MISSING = object()


class AuditChainHead(db.Model):
    """Ponta persistida da cadeia; a linha única serializa novas gravações."""

    __tablename__ = "audit_chain_head"

    id = db.Column(db.Integer, primary_key=True)
    last_hash = db.Column(db.String(64), nullable=False)


@event.listens_for(AuditChainHead.__table__, "after_create")
def _seed_audit_chain_head(_table, connection, **_kwargs):
    """Mantém db.create_all de testes equivalente ao estado pós-migration."""
    connection.execute(AuditChainHead.__table__.insert().values(id=1, last_hash="GENESIS"))


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
    previous_hash = db.Column(db.String(64), nullable=True)
    integrity_hash = db.Column(db.String(64), nullable=True, unique=True)

    usuario = db.relationship("Usuario", backref=db.backref("eventos", lazy=True))

    def to_dict(self):
        return {
            "id": self.id, "usuario_id": self.usuario_id,
            "usuario_nome": self.usuario_nome,
            "tipo": self.tipo, "modulo": self.modulo,
            "operacao": self.operacao, "descricao": self.descricao,
            "criado_em": self.criado_em.isoformat(),
            "integrity_hash": self.integrity_hash,
        }

    def calculate_integrity_hash(self):
        created_at = self.criado_em
        if created_at and created_at.tzinfo:
            created_at = created_at.astimezone(timezone.utc).replace(tzinfo=None)
        if created_at:
            created_at = created_at.replace(microsecond=0)
        organization_id = self.organization_id if isinstance(self.organization_id, int) else None
        payload = {
            "previous_hash": self.previous_hash or "GENESIS",
            "organization_id": organization_id,
            "usuario_id": self.usuario_id,
            "usuario_nome": self.usuario_nome,
            "tipo": self.tipo,
            "modulo": self.modulo,
            "operacao": self.operacao,
            "descricao": self.descricao,
            "criado_em": created_at.isoformat() if created_at else None,
        }
        return hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()


@event.listens_for(EventoLog, "before_insert")
def _chain_evento_log(_mapper, connection, target):
    """Preenche o elo anterior e o hash antes de qualquer gravação."""
    # O modelo tem default 1; materialize-o antes do hash para que o valor
    # calculado seja o mesmo que o banco persiste quando o campo é omitido.
    if target.organization_id is None:
        target.organization_id = 1
    if target.criado_em is None:
        target.criado_em = datetime.now(timezone.utc)
    head = connection.execute(
        select(AuditChainHead.__table__.c.last_hash)
        .where(AuditChainHead.__table__.c.id == 1)
        .with_for_update()
    ).scalar_one_or_none()
    if head is None:
        raise RuntimeError("Ponta da cadeia de auditoria ausente. Execute a migration antes de gravar eventos.")
    target.previous_hash = head
    target.integrity_hash = target.calculate_integrity_hash()
    connection.execute(
        update(AuditChainHead.__table__)
        .where(AuditChainHead.__table__.c.id == 1)
        .values(last_hash=target.integrity_hash)
    )


@event.listens_for(EventoLog, "before_update")
@event.listens_for(EventoLog, "before_delete")
def _reject_audit_mutation(_mapper, _connection, _target):
    raise RuntimeError("Eventos de auditoria são append-only; alterações e exclusões são proibidas.")


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
