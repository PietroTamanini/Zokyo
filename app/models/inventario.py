"""Inventário físico: sessões, itens e ajustes.

Modelos:
  - InventarioSessao: sessão de inventário (aberto/fechado)
  - InventarioItem: peça + quantidade física + divergência
  - InventarioAjuste: ajuste aprovado que atualiza estoque

Relacionamento: uma sessão pertence a um tenant, contém vários itens.
Ao fechar, gera-se um ajuste por item com divergência != 0 e atualiza-se a
quantidade da peça (Peca.quantidade).
"""
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from app.extensions import db

if TYPE_CHECKING:
    from app.models.peca import Peca

# ── Tabela de associação peça ↔ sessão ──────────────────────────────
pecas_inventario = Table(
    "pecas_inventario",
    db.Model.metadata,
    Column("peca_id", Integer, ForeignKey("pecas.id"), primary_key=True),
    Column("sessao_id", Integer, ForeignKey("inventario_sessoes.id"), primary_key=True),
    Column("quantidade_sistema", Integer, nullable=False, server_default="0"),
    Column("quantidade_fisica", Integer, nullable=False, server_default="0"),
    Column("divergencia", Integer, nullable=False, server_default="0"),
    Column("justificativa", Text, nullable=True),
    Column("aprovado", Boolean, nullable=False, server_default="0"),
    Column("aprovado_em", DateTime, nullable=True),
    Column("aprovado_por_id", Integer, ForeignKey("usuarios.id"), nullable=True),
    Column("aprovado_por_nome", String(120), nullable=True),
    Column("created_at", DateTime, nullable=False, server_default=func.now()),
)


class InventarioSessao(db.Model):
    __tablename__ = "inventario_sessoes"
    __table_args__ = (
        Index("ix_inventario_sessao_org_status", "organization_id", "status"),
        Index("ix_inventario_sessao_org_aberta", "organization_id", "status", "data_abertura"),
    )

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    status = db.Column(
        db.String(20), nullable=False, default="aberto"
    )  # "aberto" | "fechado"
    data_abertura = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    data_fechamento = db.Column(db.DateTime, nullable=True)
    responsavel_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id"), nullable=True
    )
    responsavel_nome = db.Column(db.String(120), nullable=True)
    observacoes = db.Column(db.Text, nullable=True)

    itens = relationship(
        "InventarioItem",
        back_populates="sessao",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    def __repr__(self):
        return f"<InventarioSessao id={self.id} org={self.organization_id} status={self.status}>"


class InventarioItem(db.Model):
    __tablename__ = "inventario_itens"
    __table_args__ = (
        Index("ix_inventario_peca_sessao", "peca_id", "sessao_id"),
        UniqueConstraint("peca_id", "sessao_id", name="uq_inventario_peca_sessao"),
    )

    id = db.Column(db.Integer, primary_key=True)
    sessao_id = db.Column(
        db.Integer, db.ForeignKey("inventario_sessoes.id"), nullable=False, index=True
    )
    peca_id = db.Column(
        db.Integer, db.ForeignKey("pecas.id"), nullable=False, index=True
    )
    quantidade_sistema = db.Column(
        db.Integer, nullable=False, server_default="0"
    )  # quantidade no banco antes do inventário
    quantidade_fisica = db.Column(
        db.Integer, nullable=False, server_default="0"
    )  # quantidade contada fisicamente
    divergencia = db.Column(
        db.Integer, nullable=False, server_default="0"
    )  # fisica - sistema
    justificativa = db.Column(db.Text, nullable=True)
    aprovado = db.Column(db.Boolean, nullable=False, server_default="0")
    aprovado_em = db.Column(db.DateTime, nullable=True)
    aprovado_por_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id"), nullable=True
    )
    aprovado_por_nome = db.Column(db.String(120), nullable=True)

    sessao = relationship("InventarioSessao", back_populates="itens")
    peca = relationship("Peca", back_populates="_inventario_items")

    @property
    def is_divergente(self):
        return self.divergencia != 0


class InventarioAjuste(db.Model):
    """Registro de ajuste que já foi aplicado ao estoque."""

    __tablename__ = "inventario_ajustes"
    __table_args__ = (
        Index("ix_inventario_ajuste_org_data", "organizacao_id", "aplicado_em"),
    )

    id = db.Column(db.Integer, primary_key=True)
    organizacao_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    sessao_id = db.Column(
        db.Integer, db.ForeignKey("inventario_sessoes.id"), nullable=False, index=True
    )
    peca_id = db.Column(
        db.Integer, db.ForeignKey("pecas.id"), nullable=False, index=True
    )
    quantidade_anterior = db.Column(db.Integer, nullable=False)
    quantidade_nova = db.Column(db.Integer, nullable=False)
    divergencia = db.Column(db.Integer, nullable=False)
    justificativa = db.Column(db.Text, nullable=False)
    aplicado_em = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    aplicado_por_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id"), nullable=False
    )
    aplicado_por_nome = db.Column(db.String(120), nullable=False)

    peca = relationship("Peca", foreign_keys=[peca_id])


# ── Helper para calcular disponível após inventário ──────────────────

def _quantidade_disponivel_apos(part: "Peca", delta: int) -> int:
    """Retorna nova quantidade disponível após aplicar delta (pode ser negativo)."""
    return max(0, part.quantidade + delta)