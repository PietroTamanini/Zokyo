"""models/fornecedor.py — Modelo de Fornecedor."""
from datetime import datetime, timezone

from app.extensions import db


class Fornecedor(db.Model):
    __tablename__ = "fornecedores"

    id        = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, default=1, index=True)
    nome      = db.Column(db.String(200), nullable=False)
    cnpj      = db.Column(db.String(14), index=True)
    telefone  = db.Column(db.String(15))
    email     = db.Column(db.String(254), index=True)
    cep       = db.Column(db.String(8))        # somente dígitos
    endereco  = db.Column(db.String(300))
    cidade    = db.Column(db.String(100))
    ativo     = db.Column(db.Boolean, default=True, nullable=False)
    criado_em = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    pecas = db.relationship("Peca", backref="fornecedor", lazy=True)

    def to_dict(self):
        return {
            "id":        self.id,
            "nome":      self.nome,
            "cnpj":      self.cnpj,
            "telefone":  self.telefone,
            "email":     self.email,
            "cep":       self.cep,
            "endereco":  self.endereco,
            "cidade":    self.cidade,
            "ativo":     self.ativo,
        }
