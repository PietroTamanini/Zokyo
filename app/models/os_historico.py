"""
models/os_historico.py
----------------------
Fix #22: histórico real de transições de status por OS.
Popule via _registrar_historico_status() em routes/pages.py e routes/os.py.
"""

from datetime import datetime, timezone

from app.extensions import db


class OSHistorico(db.Model):
    __tablename__ = "os_historico"
    __table_args__ = (
        db.Index("ix_os_historico_os_criado", "os_id", "criado_em"),
        db.Index("ix_os_historico_org_criado", "organization_id", "criado_em"),
    )

    id              = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, default=1, index=True)
    os_id           = db.Column(db.Integer, db.ForeignKey("ordens_servico.id"), nullable=False)
    usuario_id      = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    status_anterior = db.Column(db.String(30))
    status_novo     = db.Column(db.String(30), nullable=False)
    criado_em       = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id":              self.id,
            "os_id":           self.os_id,
            "usuario_id":      self.usuario_id,
            "status_anterior": self.status_anterior,
            "status_novo":     self.status_novo,
            "criado_em":       self.criado_em.isoformat(),
        }
