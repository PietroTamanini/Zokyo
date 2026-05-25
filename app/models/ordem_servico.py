"""
models/ordem_servico.py
-----------------------
Ordem de Serviço (OS) — coração do sistema.
"""

from datetime import datetime, timezone
from sqlalchemy import text
from app.extensions import db


os_pecas = db.Table(
    "os_pecas",
    db.Column("os_id",        db.Integer, db.ForeignKey("ordens_servico.id"), primary_key=True),
    db.Column("peca_id",      db.Integer, db.ForeignKey("pecas.id"),          primary_key=True),
    db.Column("quantidade",    db.Integer,       default=1, nullable=False),
    db.Column("valor_unitario",db.Numeric(10,2), default=0),
)

# Fix #04: "cancelado" adicionado à tupla
STATUS_OS = (
    "recepcao", "em_analise", "aguardando_aprovacao",
    "em_reparo", "pronto", "entregue", "cancelado",
)

# Fix #24: dicionário de rótulos centralizado aqui — importe nos outros módulos
STATUS_OS_LABELS = {
    "recepcao":             "Recepção",
    "em_analise":           "Em Análise",
    "aguardando_aprovacao": "Aprovação",
    "em_reparo":            "Em Reparo",
    "pronto":               "Pronto",
    "entregue":             "Entregue",
    "cancelado":            "Cancelado",
}


class OrdemServico(db.Model):
    __tablename__ = "ordens_servico"

    id         = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey("clientes.id"),  nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"),  nullable=False)

    # Aparelho
    tipo_aparelho  = db.Column(db.String(100))
    marca          = db.Column(db.String(100))
    modelo         = db.Column(db.String(100))
    numero_serie   = db.Column(db.String(100))

    # Diagnóstico
    defeito_alegado    = db.Column(db.Text)
    defeito_encontrado = db.Column(db.Text)
    solucao            = db.Column(db.Text)
    observacoes        = db.Column(db.Text)

    # Financeiro
    valor_servico = db.Column(db.Numeric(10,2), default=0)
    valor_pecas   = db.Column(db.Numeric(10,2), default=0)
    desconto      = db.Column(db.Numeric(10,2), default=0)

    # Campos extras
    prio          = db.Column(db.String(20), default="normal")
    tecnico_nome  = db.Column(db.String(120))
    garantia_dias = db.Column(db.Integer, default=90)
    data_prev     = db.Column(db.DateTime)

    # Status e datas
    status        = db.Column(db.String(30), default="recepcao", nullable=False)
    # Fix #40: datetime.utcnow depreciado → lambda com timezone.utc
    data_entrada  = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    data_saida    = db.Column(db.DateTime)
    atualizado_em = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Fix #32: soft delete — registros financeiros nunca são apagados fisicamente
    deletado_em = db.Column(db.DateTime, nullable=True)

    # Relacionamentos
    pecas   = db.relationship("Peca", secondary=os_pecas, backref=db.backref("ordens", lazy=True))
    usuario = db.relationship("Usuario", backref=db.backref("ordens", lazy=True))

    @property
    def valor_total(self):
        vs = float(self.valor_servico or 0)
        vp = float(self.valor_pecas   or 0)
        dc = float(self.desconto      or 0)
        return round(vs + vp - dc, 2)

    # Fix #33: property calculada de garantia
    @property
    def em_garantia(self):
        if not self.data_saida or not self.garantia_dias:
            return False
        from datetime import timedelta
        expira = self.data_saida + timedelta(days=self.garantia_dias)
        return datetime.now(timezone.utc).replace(tzinfo=None) <= expira

    def to_dict(self):
        # Fix #02: lê quantidade e valor_unitario reais da tabela os_pecas
        assoc = db.session.execute(
            text("SELECT peca_id, quantidade, valor_unitario FROM os_pecas WHERE os_id = :id"),
            {"id": self.id}
        ).fetchall()
        assoc_map = {row.peca_id: row for row in assoc}

        return {
            "id":                  self.id,
            "cliente_id":          self.cliente_id,
            "cliente_nome":        self.cliente.nome if self.cliente else None,
            "tecnico_nome":        self.tecnico_nome or "",
            "usuario_id":          self.usuario_id,
            "tipo_aparelho":       self.tipo_aparelho,
            "marca":               self.marca,
            "modelo":              self.modelo,
            "numero_serie":        self.numero_serie,
            "defeito_alegado":     self.defeito_alegado,
            "defeito_encontrado":  self.defeito_encontrado,
            "solucao":             self.solucao,
            "observacoes":         self.observacoes,
            "valor_servico":       float(self.valor_servico or 0),
            "valor_pecas":         float(self.valor_pecas   or 0),
            "desconto":            float(self.desconto      or 0),
            "valor_total":         self.valor_total,
            "status":              self.status,
            "prio":                self.prio or "normal",
            "garantia_dias":       self.garantia_dias or 90,
            "em_garantia":         self.em_garantia,
            "data_entrada":        self.data_entrada.isoformat() if self.data_entrada else None,
            "data_saida":          self.data_saida.isoformat()   if self.data_saida   else None,
            "data_prev":           self.data_prev.isoformat()    if self.data_prev    else None,
            # Fix #02: quantidade e valor_unitario corretos por peça
            "pecas": [
                {
                    "id":            p.id,
                    "nome":          p.nome,
                    "codigo":        p.codigo or "",
                    "quantidade":    assoc_map[p.id].quantidade if p.id in assoc_map else 1,
                    "valor_unitario": float(assoc_map[p.id].valor_unitario or p.custo or 0)
                                      if p.id in assoc_map else float(p.custo or 0),
                    "subtotal":      round(
                        (assoc_map[p.id].quantidade if p.id in assoc_map else 1) *
                        float(assoc_map[p.id].valor_unitario or p.custo or 0)
                        if p.id in assoc_map else float(p.custo or 0), 2
                    ),
                }
                for p in (self.pecas or [])
            ],
        }
