"""models/cliente.py - Modelo de Cliente."""
from datetime import datetime, timezone

from sqlalchemy import event

from app.extensions import db
from app.utils.blind_index import blind_index
from app.utils.field_crypto import EncryptedText


class Cliente(db.Model):
    __tablename__ = "clientes"
    __table_args__ = (
        db.Index("ix_clientes_nome", "nome"),
        db.Index("ix_clientes_telefone", "telefone"),
    )

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, default=1, index=True)
    nome = db.Column(db.String(150), nullable=False)
    cpf = db.Column(db.String(11), index=True, nullable=True)
    cnpj = db.Column(db.String(14), index=True, nullable=True)
    telefone = db.Column(db.String(20), nullable=True)
    email = db.Column(db.String(254), index=True)
    cpf_bidx = db.Column(db.String(64), index=True)
    cnpj_bidx = db.Column(db.String(64), index=True)
    telefone_bidx = db.Column(db.String(64), index=True)
    email_bidx = db.Column(db.String(64), index=True)
    cep = db.Column(db.String(8), nullable=True)
    endereco = db.Column(EncryptedText, nullable=True)
    numero_casa = db.Column(EncryptedText, nullable=True)
    cidade = db.Column(db.String(100), nullable=True)
    uf = db.Column(db.String(2), nullable=True)
    ativo = db.Column(db.Boolean, default=True, nullable=False)
    criado_em = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    ordens = db.relationship("OrdemServico", backref="cliente", lazy=True)

    @staticmethod
    def _format_cpf(valor):
        d = "".join(ch for ch in str(valor or "") if ch.isdigit())
        if len(d) != 11:
            return d
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"

    @staticmethod
    def _format_cnpj(valor):
        d = "".join(ch for ch in str(valor or "") if ch.isdigit())
        if len(d) != 14:
            return d
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"

    @property
    def documento(self):
        if self.cpf:
            return self._format_cpf(self.cpf)
        if self.cnpj:
            return self._format_cnpj(self.cnpj)
        return ""

    def to_dict(self):
        return {
            "id": self.id,
            "nome": self.nome,
            "cpf": self.cpf or "",
            "cnpj": self.cnpj or "",
            "documento": self.documento,
            "telefone": self.telefone or "",
            "cep": self.cep or "",
            "endereco": self.endereco or "",
            "numero_casa": self.numero_casa or "",
            "cidade": self.cidade or "",
            "uf": self.uf or "",
            "ativo": self.ativo,
            "criado_em": self.criado_em.isoformat() if self.criado_em else None,
        }

    def refresh_blind_indexes(self):
        self.cpf_bidx = blind_index(self.cpf, "cpf")
        self.cnpj_bidx = blind_index(self.cnpj, "cnpj")
        self.telefone_bidx = blind_index(self.telefone, "telefone")
        self.email_bidx = blind_index(self.email, "email")


@event.listens_for(Cliente, "before_insert")
@event.listens_for(Cliente, "before_update")
def _cliente_blind_indexes(_mapper, _connection, target):
    target.refresh_blind_indexes()
