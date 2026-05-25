from datetime import datetime, timezone
from app.extensions import db
class Peca(db.Model):
    __tablename__ = "pecas"
    id             = db.Column(db.Integer, primary_key=True)
    nome           = db.Column(db.String(200), nullable=False)
    codigo         = db.Column(db.String(100))
    categoria      = db.Column(db.String(100))
    localizacao    = db.Column(db.String(100))
    quantidade     = db.Column(db.Integer, default=0, nullable=False)
    estoque_minimo = db.Column(db.Integer, default=5, nullable=False)
    custo          = db.Column(db.Numeric(10,2), default=0)
    margem         = db.Column(db.Numeric(5,2), default=0)
    fornecedor_id  = db.Column(db.Integer, db.ForeignKey("fornecedores.id"))
    criado_em      = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    @property
    def preco_venda(self):
        return round(float(self.custo or 0)*(1+float(self.margem or 0)/100),2)
    def to_dict(self):
        return {"id":self.id,"nome":self.nome,"codigo":self.codigo,
                "categoria":self.categoria,"localizacao":self.localizacao,
                "quantidade":self.quantidade,"estoque_minimo":self.estoque_minimo,
                "custo":float(self.custo or 0),"margem":float(self.margem or 0),
                "preco_venda":self.preco_venda,"fornecedor_id":self.fornecedor_id}
