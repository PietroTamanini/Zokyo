"""Caixa: sessoes de abertura, movimentacoes e fechamento diario."""
from datetime import datetime, timezone

from sqlalchemy import Index

from app.extensions import db

STATUS_CAIXA = ("aberto", "fechado")
TIPO_CAIXA_MOVIMENTO = ("entrada", "saida", "sangria", "suprimento")


class CaixaMovimento(db.Model):
    __tablename__ = "caixa_movimentos"
    __table_args__ = (
        Index("ix_caixa_movimentos_org_sessao", "organization_id", "sessao_id", "criado_em"),
        Index("sessao_id", "sessao_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer,
        db.ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        default=1,
    )
    sessao_id = db.Column(
        db.Integer,
        db.ForeignKey("caixas_sessoes.id", ondelete="CASCADE"),
        nullable=False,
        index=False,
    )
    tipo = db.Column(db.String(10), nullable=False)
    valor = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    forma_pagamento = db.Column(db.String(50))
    descricao = db.Column(db.String(300))
    responsavel_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL")
    )
    responsavel_nome = db.Column(db.String(120))
    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    sessao = db.relationship("CaixaSessao", back_populates="movimentos")


class CaixaSessao(db.Model):
    __tablename__ = "caixas_sessoes"
    __table_args__ = (
        Index("ix_caixas_org_status_abertura", "organization_id", "status", "data_abertura"),
    )

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer,
        db.ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        default=1,
    )
    status = db.Column(db.String(10), nullable=False, default="aberto")
    data_abertura = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    saldo_inicial = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    valor_fechado_esperado = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    valor_conferido = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    diferenca = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    observacoes = db.Column(db.Text)
    responsavel_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL")
    )
    responsavel_nome = db.Column(db.String(120))
    fechada_em = db.Column(db.DateTime)

    movimentos = db.relationship("CaixaMovimento", back_populates="sessao", lazy=True)
