"""Modelos do modulo de laudos tecnicos."""
from datetime import datetime, timezone
import uuid

from app.extensions import db


LAUDO_STATUS = ("draft", "finalized", "cancelled")
LAUDO_STATUS_LABELS = {
    "draft": "Rascunho",
    "finalized": "Finalizado",
    "cancelled": "Cancelado",
}

LAUDO_TIPOS = (
    "diagnostico",
    "entrada",
    "entrega",
    "complementar",
    "revisao",
    "retificador",
)
LAUDO_TIPOS_LABELS = {
    "diagnostico": "Diagnostico",
    "entrada": "Laudo de entrada",
    "entrega": "Laudo de entrega",
    "complementar": "Complementar",
    "revisao": "Revisao",
    "retificador": "Retificador",
}

LAUDO_FOTO_TIPOS = (
    "frontal",
    "traseira",
    "etiqueta",
    "macro_defeito",
    "detalhe_defeito",
    "adicional",
)
LAUDO_FOTO_TIPOS_LABELS = {
    "frontal": "Foto frontal do equipamento",
    "traseira": "Foto traseira",
    "etiqueta": "Foto da etiqueta",
    "macro_defeito": "Foto macro do defeito",
    "detalhe_defeito": "Foto detalhada do defeito",
    "adicional": "Foto adicional",
}
LAUDO_FOTOS_OBRIGATORIAS = (
    "frontal",
    "traseira",
    "etiqueta",
    "macro_defeito",
    "detalhe_defeito",
)

LAUDO_EVENTOS = (
    "criacao",
    "edicao",
    "finalizacao",
    "pdf_gerado",
    "download_pdf",
    "duplicacao",
    "revisao",
    "cancelamento",
    "foto",
    "responsavel",
)


def _now():
    return datetime.now(timezone.utc)


class LaudoCounter(db.Model):
    __tablename__ = "laudo_counters"
    __table_args__ = (
        db.UniqueConstraint("organization_id", "ano", name="uq_laudo_counter_org_ano"),
    )

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, default=1, nullable=False)
    ano = db.Column(db.Integer, nullable=False)
    proximo_numero = db.Column(db.Integer, default=1, nullable=False)
    atualizado_em = db.Column(db.DateTime, default=_now, onupdate=_now, nullable=False)


class LaudoTecnico(db.Model):
    __tablename__ = "laudos_tecnicos"
    __table_args__ = (
        db.UniqueConstraint("organization_id", "numero", name="uq_laudo_org_numero"),
        db.Index("ix_laudos_os_id", "os_id"),
        db.Index("ix_laudos_cliente_id", "cliente_id"),
        db.Index("ix_laudos_status", "status"),
        db.Index("ix_laudos_emitido_em", "emitido_em"),
        db.Index("ix_laudos_public_uuid", "public_uuid"),
        db.Index("ix_laudos_verification_token", "verification_token"),
    )

    id = db.Column(db.Integer, primary_key=True)
    public_uuid = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    organization_id = db.Column(db.Integer, default=1, nullable=False)
    os_id = db.Column(db.Integer, db.ForeignKey("ordens_servico.id"), nullable=False)
    cliente_id = db.Column(db.Integer, db.ForeignKey("clientes.id"), nullable=False)
    equipamento_id = db.Column(db.Integer, nullable=True)
    tipo = db.Column(db.String(30), default="diagnostico", nullable=False)
    numero = db.Column(db.String(30), nullable=True)
    ano = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(20), default="draft", nullable=False)
    emitido_em = db.Column(db.DateTime)
    analisado_em = db.Column(db.DateTime)
    tecnico_responsavel_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    tecnico_responsavel_nome = db.Column(db.String(120))
    criado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    atualizado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    versao = db.Column(db.Integer, default=1, nullable=False)
    laudo_origem_id = db.Column(db.Integer, db.ForeignKey("laudos_tecnicos.id"))

    defeito_relatado = db.Column(db.Text)
    inspecao_visual = db.Column(db.Text)
    testes_realizados = db.Column(db.Text)
    instrumentos_metodos = db.Column(db.Text)
    medicoes = db.Column(db.Text)
    diagnostico_tecnico = db.Column(db.Text)
    causa_provavel = db.Column(db.Text)
    servicos_realizados = db.Column(db.Text)
    pecas_utilizadas = db.Column(db.Text)
    conclusao_tecnica = db.Column(db.Text)
    estado_final = db.Column(db.String(120))
    recomendacoes = db.Column(db.Text)
    riscos_limitacoes = db.Column(db.Text)
    garantia = db.Column(db.String(200))
    observacoes = db.Column(db.Text)
    motivo_cancelamento = db.Column(db.Text)

    empresa_snapshot = db.Column(db.JSON)
    cliente_snapshot = db.Column(db.JSON)
    equipamento_snapshot = db.Column(db.JSON)
    tecnico_snapshot = db.Column(db.JSON)

    assinatura_tecnico_nome = db.Column(db.String(120))
    assinatura_tecnico_em = db.Column(db.DateTime)
    assinatura_tecnico_metodo = db.Column(db.String(50))
    assinatura_cliente_nome = db.Column(db.String(120))
    assinatura_cliente_em = db.Column(db.DateTime)
    assinatura_cliente_metodo = db.Column(db.String(50))

    criado_em = db.Column(db.DateTime, default=_now, nullable=False)
    atualizado_em = db.Column(db.DateTime, default=_now, onupdate=_now, nullable=False)
    finalizado_em = db.Column(db.DateTime)
    cancelado_em = db.Column(db.DateTime)
    pdf_path = db.Column(db.String(600))
    pdf_sha256 = db.Column(db.String(64))
    pdf_gerado_em = db.Column(db.DateTime)
    pdf_template_version = db.Column(db.String(30), default="laudo-v1")
    verification_token = db.Column(db.String(80), unique=True)
    verificacao_publica = db.Column(db.Boolean, default=True, nullable=False)

    os = db.relationship("OrdemServico", backref=db.backref("laudos", lazy=True))
    cliente = db.relationship("Cliente", backref=db.backref("laudos", lazy=True))
    tecnico_responsavel = db.relationship("Usuario", foreign_keys=[tecnico_responsavel_id])
    criado_por = db.relationship("Usuario", foreign_keys=[criado_por_id])
    atualizado_por = db.relationship("Usuario", foreign_keys=[atualizado_por_id])
    origem = db.relationship("LaudoTecnico", remote_side=[id], backref="revisoes")

    @property
    def is_draft(self):
        return self.status == "draft"

    @property
    def is_finalized(self):
        return self.status == "finalized"

    def status_label(self):
        return LAUDO_STATUS_LABELS.get(self.status, self.status)

    def tipo_label(self):
        return LAUDO_TIPOS_LABELS.get(self.tipo, self.tipo)


class LaudoFoto(db.Model):
    __tablename__ = "laudo_fotos"
    __table_args__ = (
        db.Index("ix_laudo_fotos_laudo_tipo", "laudo_id", "tipo"),
    )

    id = db.Column(db.Integer, primary_key=True)
    laudo_id = db.Column(db.Integer, db.ForeignKey("laudos_tecnicos.id"), nullable=False)
    tipo = db.Column(db.String(30), nullable=False)
    legenda = db.Column(db.String(255))
    ordem = db.Column(db.Integer, default=0, nullable=False)
    nome_original = db.Column(db.String(255))
    storage_key = db.Column(db.String(600), nullable=False)
    mime_type = db.Column(db.String(100), nullable=False)
    tamanho_bytes = db.Column(db.Integer, nullable=False)
    largura = db.Column(db.Integer)
    altura = db.Column(db.Integer)
    sha256 = db.Column(db.String(64), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    criado_em = db.Column(db.DateTime, default=_now, nullable=False)

    laudo = db.relationship("LaudoTecnico", backref=db.backref("fotos", lazy=True, cascade="all, delete-orphan"))
    usuario = db.relationship("Usuario")


class LaudoEvento(db.Model):
    __tablename__ = "laudo_eventos"
    __table_args__ = (
        db.Index("ix_laudo_eventos_laudo", "laudo_id", "criado_em"),
    )

    id = db.Column(db.Integer, primary_key=True)
    laudo_id = db.Column(db.Integer, db.ForeignKey("laudos_tecnicos.id"), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    tipo = db.Column(db.String(30), nullable=False)
    descricao = db.Column(db.Text)
    dados = db.Column(db.JSON)
    criado_em = db.Column(db.DateTime, default=_now, nullable=False)

    laudo = db.relationship("LaudoTecnico", backref=db.backref("eventos", lazy=True, cascade="all, delete-orphan"))
    usuario = db.relationship("Usuario")
