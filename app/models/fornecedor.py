"""models/fornecedor.py — Modelo de Fornecedor."""
from datetime import datetime, timezone

from sqlalchemy import event

from app.extensions import db
from app.utils.blind_index import blind_index
from app.utils.field_crypto import EncryptedText


class Fornecedor(db.Model):
    __tablename__ = "fornecedores"
    __table_args__ = (
        db.Index("ix_fornecedores_nome", "nome"),
        db.Index("ix_fornecedores_telefone", "telefone"),
        db.Index("ix_fornecedores_org_active_nome", "organization_id", "ativo", "nome"),
    )

    id        = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, default=1, index=True)
    nome      = db.Column(db.String(200), nullable=False)
    cnpj      = db.Column(db.String(14), index=True)
    telefone  = db.Column(db.String(15))
    email     = db.Column(db.String(254), index=True)
    cnpj_bidx = db.Column(db.String(64), index=True)
    telefone_bidx = db.Column(db.String(64), index=True)
    email_bidx = db.Column(db.String(64), index=True)
    cep       = db.Column(db.String(8))        # somente dígitos
    endereco  = db.Column(EncryptedText)
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

    def refresh_blind_indexes(self):
        self.cnpj_bidx = blind_index(self.cnpj, "cnpj")
        self.telefone_bidx = blind_index(self.telefone, "telefone")
        self.email_bidx = blind_index(self.email, "email")


@event.listens_for(Fornecedor, "before_insert")
@event.listens_for(Fornecedor, "before_update")
def _fornecedor_blind_indexes(_mapper, _connection, target):
    target.refresh_blind_indexes()
