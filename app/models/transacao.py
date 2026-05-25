from datetime import datetime, timezone
from app.extensions import db
TIPOS_TRANSACAO      = ("receita","despesa")
STATUS_TRANSACAO     = ("pendente","pago","cancelado")
CATEGORIAS_TRANSACAO = ("servico","peca","aluguel","salario","fornecedor","imposto","outros")
class Transacao(db.Model):
    __tablename__ = "transacoes"
    id              = db.Column(db.Integer, primary_key=True)
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
    def to_dict(self):
        return {"id":self.id,"os_id":self.os_id,"tipo":self.tipo,
                "categoria":self.categoria,"descricao":self.descricao,
                "valor":float(self.valor or 0),"forma_pagamento":self.forma_pagamento,
                "status":self.status,
                "data_vencimento":self.data_vencimento.isoformat() if self.data_vencimento else None,
                "data_pagamento":self.data_pagamento.isoformat() if self.data_pagamento else None,
                "criado_em":self.criado_em.isoformat()}
