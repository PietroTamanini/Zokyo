from datetime import datetime, timezone

from app.extensions import db


class OSFoto(db.Model):
    __tablename__ = "os_fotos"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, default=1, index=True)
    os_id = db.Column(db.Integer, db.ForeignKey("ordens_servico.id"), nullable=False, index=True)
    coleta_id = db.Column(db.Integer, db.ForeignKey("coletas_agendadas.id"), nullable=True, index=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True)

    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=True)
    mime_type = db.Column(db.String(80), nullable=True)
    tamanho_bytes = db.Column(db.Integer, default=0)
    descricao = db.Column(db.String(200), nullable=True)
    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    os = db.relationship("OrdemServico", backref=db.backref("fotos", lazy=True, cascade="all, delete-orphan"))
    coleta = db.relationship("ColetaAgendada", backref=db.backref("fotos", lazy=True))
    usuario = db.relationship("Usuario", backref=db.backref("fotos_os", lazy=True))
