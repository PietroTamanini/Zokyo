"""models/cliente.py — Modelo de Cliente."""
from datetime import datetime, timezone
from app.extensions import db


class Cliente(db.Model):
    __tablename__ = "clientes"

    id        = db.Column(db.Integer, primary_key=True)
    nome      = db.Column(db.String(200), nullable=False)
    cpf       = db.Column(db.String(11), index=True)
    telefone  = db.Column(db.String(15))
    email     = db.Column(db.String(254), index=True)
    cep       = db.Column(db.String(8))        # somente dígitos
    endereco  = db.Column(db.String(300))
    cidade    = db.Column(db.String(100))
    uf        = db.Column(db.String(2))
    ativo     = db.Column(db.Boolean, default=True, nullable=False)
    criado_em = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    ordens = db.relationship("OrdemServico", backref="cliente", lazy=True)

    def to_dict(self):
        return {
            "id":        self.id,
            "nome":      self.nome,
            "cpf":       self.cpf,
            "telefone":  self.telefone,
            "email":     self.email,
            "cep":       self.cep,
            "endereco":  self.endereco,
            "cidade":    self.cidade,
            "uf":        self.uf,
            "ativo":     self.ativo,
            "criado_em": self.criado_em.isoformat() if self.criado_em else None,
        }
