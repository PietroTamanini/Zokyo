from datetime import datetime, timezone

from app.extensions import db

TIPOS_TRANSACAO      = ("receita","despesa")
STATUS_TRANSACAO     = ("pendente","pago","cancelado")
CATEGORIAS_TRANSACAO = ("servico","peca","aluguel","salario","fornecedor","imposto","outros")
class Transacao(db.Model):
    __tablename__ = "transacoes"
    __table_args__ = (
        db.Index("ix_transacoes_status_tipo_criado", "status", "tipo", "criado_em"),
        db.Index("ix_transacoes_descricao", "descricao"),
        db.Index("ix_transacoes_org_status_tipo_criado", "organization_id", "status", "tipo", "criado_em"),
        db.Index("ix_transacoes_org_status_venc", "organization_id", "status", "data_vencimento"),
        db.Index("ix_transacoes_org_os_status_tipo_venc", "organization_id", "os_id", "status", "tipo", "data_vencimento"),
        db.Index("ix_transacoes_org_tipo_criado", "organization_id", "tipo", "criado_em"),
        db.Index("ix_transacoes_org_tipo_status_venc", "organization_id", "tipo", "status", "data_vencimento"),
        db.Index("ix_transacoes_org_pago_data", "organization_id", "status", "data_pagamento"),
    )
    id              = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, default=1, index=True)
    os_id           = db.Column(db.Integer, db.ForeignKey("ordens_servico.id"))
    tipo            = db.Column(db.String(10), nullable=False)
    categoria       = db.Column(db.String(50))
    descricao       = db.Column(db.String(300))
    valor           = db.Column(db.Numeric(10,2), nullable=False)
    forma_pagamento = db.Column(db.String(50))
    status          = db.Column(db.String(20), default="pendente")
    data_vencimento = db.Column(db.DateTime)
    data_pagamento  = db.Column(db.DateTime)
    criado_em       = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    parent_id       = db.Column(db.Integer, db.ForeignKey("transacoes.id"), index=True)
    parcela_numero  = db.Column(db.Integer, default=1, nullable=False)
    parcela_total   = db.Column(db.Integer, default=1, nullable=False)
    recorrencia     = db.Column(db.String(20))
    conciliado_em   = db.Column(db.DateTime)
    conciliado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    conciliacao_ref = db.Column(db.String(120))
    comissao_usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    comissao_percentual = db.Column(db.Numeric(5,2), default=0)
    comissao_valor = db.Column(db.Numeric(10,2), default=0)
    payment_gateway = db.Column(db.String(40))
    payment_method = db.Column(db.String(40))
    payment_provider_id = db.Column(db.String(160))
    payment_status = db.Column(db.String(40))
    payment_url = db.Column(db.String(600))
    payment_link = db.Column(db.String(600))
    payment_barcode = db.Column(db.String(300))
    payment_payload = db.Column(db.Text)
    payment_expires_at = db.Column(db.DateTime)
    os = db.relationship("OrdemServico", foreign_keys=[os_id])
    parent = db.relationship("Transacao", remote_side=[id], backref=db.backref("parcelas", lazy=True))
    def to_dict(self):
        return {"id":self.id,"os_id":self.os_id,"tipo":self.tipo,
                "categoria":self.categoria,"descricao":self.descricao,
                "valor":float(self.valor or 0),"forma_pagamento":self.forma_pagamento,
                "status":self.status,
                "data_vencimento":self.data_vencimento.isoformat() if self.data_vencimento else None,
                "data_pagamento":self.data_pagamento.isoformat() if self.data_pagamento else None,
                "criado_em":self.criado_em.isoformat(),
                "parent_id": self.parent_id,
                "parcela_numero": self.parcela_numero,
                "parcela_total": self.parcela_total,
                "recorrencia": self.recorrencia,
                "conciliado_em": self.conciliado_em.isoformat() if self.conciliado_em else None,
                "conciliacao_ref": self.conciliacao_ref,
                "comissao_usuario_id": self.comissao_usuario_id,
                "comissao_percentual": float(self.comissao_percentual or 0),
                "comissao_valor": float(self.comissao_valor or 0),
                "payment_gateway": self.payment_gateway,
                "payment_method": self.payment_method,
                "payment_provider_id": self.payment_provider_id,
                "payment_status": self.payment_status,
                "payment_url": self.payment_url,
                "payment_link": self.payment_link,
                "payment_barcode": self.payment_barcode,
                "payment_payload": self.payment_payload,
                "payment_expires_at": self.payment_expires_at.isoformat() if self.payment_expires_at else None}
