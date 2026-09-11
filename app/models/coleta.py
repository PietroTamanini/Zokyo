from datetime import datetime, timezone

from app.extensions import db
from app.utils.field_crypto import EncryptedText

STATUS_COLETA = ("agendada", "em_coleta", "concluida", "cancelada")

STATUS_COLETA_LABELS = {
    "agendada": "Agendada",
    "em_coleta": "Em coleta",
    "concluida": "Concluida",
    "cancelada": "Cancelada",
}


class ColetaAgendada(db.Model):
    __tablename__ = "coletas_agendadas"
    __table_args__ = (
        db.Index("ix_coletas_org_status_agendada_criado", "organization_id", "status", "data_agendada", "criado_em"),
        db.Index("ix_coletas_org_cliente_criado", "organization_id", "cliente_id", "criado_em"),
    )

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, default=1, index=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey("clientes.id"), nullable=False, index=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True)
    os_id = db.Column(db.Integer, db.ForeignKey("ordens_servico.id"), nullable=True, index=True)

    status = db.Column(db.String(20), nullable=False, default="agendada", index=True)
    data_agendada = db.Column(db.DateTime, nullable=True, index=True)

    telefone_contato = db.Column(EncryptedText, nullable=True)
    cep = db.Column(db.String(8), nullable=True)
    endereco = db.Column(EncryptedText, nullable=True)
    numero_casa = db.Column(EncryptedText, nullable=True)
    cidade = db.Column(db.String(100), nullable=True)
    uf = db.Column(db.String(2), nullable=True)
    observacoes = db.Column(EncryptedText, nullable=True)

    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    atualizado_em = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    cliente = db.relationship("Cliente", backref=db.backref("coletas", lazy=True))
    usuario = db.relationship("Usuario", backref=db.backref("coletas_criadas", lazy=True))
    os = db.relationship("OrdemServico", backref=db.backref("coleta_origem", uselist=False))

    @property
    def endereco_completo(self):
        partes = []
        if self.endereco:
            partes.append(self.endereco)
        if self.numero_casa:
            partes.append(self.numero_casa)
        local = ""
        if self.cidade:
            local = self.cidade
        if self.uf:
            local = f"{local}/{self.uf}" if local else self.uf
        if local:
            partes.append(local)
        return ", ".join(partes)
