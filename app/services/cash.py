"""Caixa: abertura, movimentacoes, conferencia e fechamento diario.

Regras de negocio:
  - Cada tenant possui no maximo uma sessao de caixa aberta simultaneamente.
  - Movimentacoes de entrada/saida/sangria/suprimento pertencem a uma sessao.
  - O fechamento calcula o valor esperado (saldo inicial + movimentacoes) e
    compara com o valor conferido, registrando a diferenca.
"""
import math
from datetime import datetime, timezone
from decimal import Decimal

from app.extensions import db
from app.models import CaixaMovimento, CaixaSessao, EventoLog

MAX_VALOR_CAIXA = 9_999_999.99
DELTAS_CAIXA = {"entrada": 1, "suprimento": 1, "saida": -1, "sangria": -1}


def _now():
    return datetime.now(timezone.utc)


def _float(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def get_open_caixa(organization_id: int):
    return (
        CaixaSessao.query
        .filter_by(organization_id=organization_id, status="aberto")
        .order_by(CaixaSessao.data_abertura.desc())
        .first()
    )


def open_caixa(organization_id: int, saldo_inicial: float = 0, responsavel_id=None, responsavel_nome=None):
    """Abre uma nova sessao de caixa (idempotente enquanto houver uma aberta)."""
    saldo_inicial = float(saldo_inicial or 0)
    if not math.isfinite(saldo_inicial) or saldo_inicial < 0 or saldo_inicial > MAX_VALOR_CAIXA:
        raise ValueError("Saldo inicial deve ser finito, nao negativo e dentro do limite da caixa")
    existing = get_open_caixa(organization_id)
    if existing:
        return existing
    session = CaixaSessao(
        organization_id=organization_id,
        status="aberto",
        data_abertura=_now(),
        saldo_inicial=saldo_inicial,
        valor_fechado_esperado=0,
        valor_conferido=0,
        diferenca=0,
        responsavel_id=responsavel_id,
        responsavel_nome=responsavel_nome,
    )
    db.session.add(session)
    db.session.add(EventoLog(
        organization_id=organization_id,
        usuario_id=responsavel_id,
        usuario_nome=responsavel_nome or "Sistema",
        tipo="abertura",
        modulo="financeiro",
        operacao=f"Caixa aberta: saldo_inicial={float(saldo_inicial or 0)}",
        descricao="",
    ))
    db.session.commit()
    db.session.refresh(session)
    return session


def list_caixa_sessoes(organization_id: int, limit: int = 30):
    return (
        CaixaSessao.query
        .filter_by(organization_id=organization_id)
        .order_by(CaixaSessao.data_abertura.desc(), CaixaSessao.id.desc())
        .limit(int(limit or 30))
        .all()
    )


def get_caixa_sessao(organization_id: int, sessao_id: int):
    return CaixaSessao.query.filter_by(id=sessao_id, organization_id=organization_id).first()


def add_caixa_movimento(
    organization_id: int,
    sessao_id: int,
    tipo: str,
    valor: float,
    forma_pagamento: str = None,
    descricao: str = None,
    responsavel_id=None,
    responsavel_nome=None,
):
    if tipo not in ("entrada", "saida", "sangria", "suprimento"):
        raise ValueError("tipo de movimentacao invalido. Use: entrada, saida, sangria, suprimento")
    valor_float = float(valor)
    if not math.isfinite(valor_float) or valor_float <= 0:
        raise ValueError("Valor da movimentacao deve ser positivo")
    if valor_float > MAX_VALOR_CAIXA:
        raise ValueError("Valor excede o maximo permitido para caixa")

    session = CaixaSessao.query.filter_by(id=sessao_id, organization_id=organization_id).first()
    if not session:
        raise ValueError("Sessao de caixa nao encontrada")
    if session.status != "aberto":
        raise ValueError("Sessao de caixa ja fechada")

    movement = CaixaMovimento(
        organization_id=organization_id,
        sessao_id=session.id,
        tipo=tipo,
        valor=float(Decimal(str(valor_float)).quantize(Decimal("0.01"))),
        forma_pagamento=(forma_pagamento or None),
        descricao=(descricao or None),
        responsavel_id=responsavel_id,
        responsavel_nome=responsavel_nome,
    )
    db.session.add(movement)
    db.session.add(EventoLog(
        organization_id=organization_id,
        usuario_id=responsavel_id,
        usuario_nome=responsavel_nome or "Sistema",
        tipo="movimentacao",
        modulo="financeiro",
        operacao=f"Caixa movimentacao {tipo}: valor={valor_float}",
        descricao=descricao or "",
    ))
    db.session.commit()
    return movement


def close_caixa(organization_id: int, sessao_id: int, valor_conferido: float, observacoes: str = None, usuario_id=None, usuario_nome=None):
    session = CaixaSessao.query.filter_by(id=sessao_id, organization_id=organization_id).first()
    if not session:
        raise ValueError("Sessao de caixa nao encontrada")
    if session.status != "aberto":
        raise ValueError("Sessao de caixa ja fechada")

    movements = sorted(session.movimentos, key=lambda item: (item.criado_em or _now(), item.id or 0))
    expected = float(session.saldo_inicial or 0)
    for movement in movements:
        expected += float(movement.valor or 0) * float(DELTAS_CAIXA.get(movement.tipo, 0))

    conferido = float(valor_conferido or 0)
    if not math.isfinite(conferido) or conferido < 0 or conferido > MAX_VALOR_CAIXA:
        raise ValueError("Valor conferido deve ser finito, nao negativo e dentro do limite da caixa")
    diferenca = round(conferido - expected, 2)

    session.status = "fechado"
    session.valor_fechado_esperado = float(expected)
    session.valor_conferido = conferido
    session.diferenca = diferenca
    session.fechada_em = _now()
    session.observacoes = observacoes or None

    db.session.add(session)
    db.session.add(EventoLog(
        organization_id=organization_id,
        usuario_id=usuario_id,
        usuario_nome=usuario_nome or "Sistema",
        tipo="fechamento",
        modulo="financeiro",
        operacao=f"Caixa fechada: conferido={conferido} diferenca={diferenca}",
        descricao="",
    ))
    db.session.commit()
    return session


def caixa_resumo(organization_id: int, sessao_id: int = None) -> dict:
    session = None
    if sessao_id is not None:
        session = CaixaSessao.query.filter_by(id=sessao_id, organization_id=organization_id).first()
    if not session:
        session = get_open_caixa(organization_id)
    if not session:
        return {
            "sessao_id": None,
            "status": "sem_abertura",
            "data_abertura": None,
            "saldo_inicial": 0.0,
            "entradas": 0.0,
            "saidas": 0.0,
            "sangrias": 0.0,
            "suprimentos": 0.0,
            "movimentos": [],
            "valor_fechado_esperado": 0.0,
            "valor_conferido": 0.0,
            "diferenca": 0.0,
        }

    movements = sorted(session.movimentos, key=lambda item: (item.criado_em or _now(), item.id or 0))
    totals = {"entrada": 0.0, "saida": 0.0, "sangria": 0.0, "suprimento": 0.0}
    for movement in movements:
        totals[movement.tipo] = round(totals[movement.tipo] + float(movement.valor or 0), 2)

    expected = float(session.saldo_inicial or 0)
    for movement in movements:
        expected += float(movement.valor or 0) * float(DELTAS_CAIXA.get(movement.tipo, 0))

    return {
        "sessao_id": session.id,
        "status": session.status,
        "data_abertura": session.data_abertura.isoformat() if session.data_abertura else None,
        "saldo_inicial": float(session.saldo_inicial or 0),
        "entradas": totals["entrada"],
        "saidas": totals["saida"],
        "sangrias": totals["sangria"],
        "suprimentos": totals["suprimento"],
        "movimentos": [
            {
                "id": movement.id,
                "tipo": movement.tipo,
                "valor": float(movement.valor or 0),
                "forma_pagamento": movement.forma_pagamento,
                "descricao": movement.descricao,
                "criado_em": movement.criado_em.isoformat() if movement.criado_em else None,
            }
            for movement in movements
        ],
        "valor_fechado_esperado": float(expected),
        "valor_conferido": float(session.valor_conferido or 0),
        "diferenca": float(session.diferenca or 0),
    }
