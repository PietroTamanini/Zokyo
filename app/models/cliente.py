"""models/cliente.py - Modelo de Cliente."""
from datetime import datetime, timezone

from app.extensions import db


class Cliente(db.Model):
    __tablename__ = "clientes"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(150), nullable=False)
    cpf = db.Column(db.String(11), index=True, nullable=True)
    cnpj = db.Column(db.String(14), index=True, nullable=True)
    telefone = db.Column(db.String(20), nullable=True)
    email = db.Column(db.String(254), index=True)
    cep = db.Column(db.String(8), nullable=True)
    endereco = db.Column(db.String(300), nullable=True)
    numero_casa = db.Column(db.String(20), nullable=True)
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
