from datetime import datetime, timezone

from app.extensions import db


class Peca(db.Model):
    __tablename__ = "pecas"
    __table_args__ = (
        db.Index("ix_pecas_nome", "nome"),
        db.Index("ix_pecas_codigo", "codigo"),
    )
    id             = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, default=1, index=True)
    nome           = db.Column(db.String(200), nullable=False)
    codigo         = db.Column(db.String(100))
    categoria      = db.Column(db.String(100))
    localizacao    = db.Column(db.String(100))
    quantidade     = db.Column(db.Integer, default=0, nullable=False)
    estoque_minimo = db.Column(db.Integer, default=5, nullable=False)
    custo          = db.Column(db.Numeric(10,2), default=0)
    margem         = db.Column(db.Numeric(5,2), default=0)
    fornecedor_id  = db.Column(db.Integer, db.ForeignKey("fornecedores.id"))
    ativo          = db.Column(db.Boolean, default=True, nullable=False, index=True)
    deletado_em    = db.Column(db.DateTime, nullable=True, index=True)
    criado_em      = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    @property
    def preco_venda(self):
        return round(float(self.custo or 0)*(1+float(self.margem or 0)/100),2)
    @property
    def quantidade_reservada(self):
        return sum(
            item.quantity for item in self.reservations
            if item.status == "active"
        )
    @property
    def quantidade_disponivel(self):
        return max(0, self.quantidade - self.quantidade_reservada)
    def to_dict(self):
        return {"id":self.id,"nome":self.nome,"codigo":self.codigo,
                "categoria":self.categoria,"localizacao":self.localizacao,
                "quantidade":self.quantidade,"estoque_minimo":self.estoque_minimo,
                "quantidade_reservada":self.quantidade_reservada,
                "quantidade_disponivel":self.quantidade_disponivel,
                "custo":float(self.custo or 0),"margem":float(self.margem or 0),
                "ativo":bool(self.ativo),
                "preco_venda":self.preco_venda,"fornecedor_id":self.fornecedor_id}
