"""Inventário físico: sessões, itens e ajustes.

Regras de negocio:
  - Cada tenant tem no máximo uma sessão de inventário aberta simultaneamente.
  - O sistema pré-carrega a quantidade atual (quantidade_sistema) para cada peça.
  - O usuário informa a quantidade_fisica contada.
  - A divergência é calculada automaticamente: fisica - sistema.
  - Apenas itens divergentes (divergencia != 0) precisam de justificativa.
  - A aprovação de ajuste atualiza Peca.quantidade e registra movimento.
  - O fechamento de sessão só pode ocorrer após aprovação de todos os itens
    ou após decisão manual de descarte.
"""
from datetime import datetime, timezone

from app.extensions import db
from app.models import (
    InventarioAjuste,
    InventarioItem,
    InventarioSessao,
    InventoryMovement,
    Peca,
    Usuario,
)
from app.utils.auth import session as auth_session

MAX_QUANTIDADE_PIECA = 999_999


def _now():
    return datetime.now(timezone.utc)


def _float(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError("Quantidade fisica deve ser um inteiro valido") from None
    if parsed < 0 or parsed > MAX_QUANTIDADE_PIECA:
        raise ValueError(f"Quantidade fisica deve estar entre 0 e {MAX_QUANTIDADE_PIECA}")
    return parsed


def _quantidade_disponivel_apos(peca, delta):
    return max(0, int(peca.quantidade or 0) + int(delta or 0))


def _organization_id() -> int:
    return int(getattr(auth_session(), "organization_id", None) or 0) or None


def get_open_inventario(organization_id: int = None):
    """Retorna a sessão de inventário aberta para o tenant, ou None."""
    org_id = organization_id or _organization_id()
    if not org_id:
        return None
    return (
        InventarioSessao.query
        .filter_by(organization_id=org_id, status="aberto")
        .order_by(InventarioSessao.data_abertura.desc())
        .first()
    )


def open_inventario(organization_id: int, responsavel_id=None, responsavel_nome=None, observacoes=None):
    """Abre uma nova sessão de inventário (idempotente enquanto houver aberta)."""
    org_id = int(organization_id) if organization_id is not None else _organization_id()
    existing = get_open_inventario(org_id)
    if existing:
        return existing
    sessao = InventarioSessao(
        organization_id=org_id,
        status="aberto",
        data_abertura=_now(),
        data_fechamento=None,
        responsavel_id=responsavel_id,
        responsavel_nome=responsavel_nome,
        observacoes=observacoes,
    )
    db.session.add(sessao)
    db.session.commit()
    db.session.refresh(sessao)
    # Pré-carregar itens: todas as peças ativas do tenant
    todas = Peca.query.filter_by(organization_id=org_id, ativo=True).all()
    for p in todas:
        item = InventarioItem(
            sessao_id=sessao.id,
            peca_id=p.id,
            quantidade_sistema=p.quantidade,
            quantidade_fisica=p.quantidade,  # inicial igual ao sistema
            divergencia=0,
            justificativa=None,
            aprovado=False,
        )
        db.session.add(item)
    db.session.commit()
    return sessao


def close_inventario(organization_id: int, sessao_id: int, justificativa_fechamento: str = None):
    """Fecha a sessão de inventário.

    Regra: só pode fechar se todos os itens já foram aprovados (ou admin force-close).
    """
    org_id = int(organization_id) if isinstance(organization_id, (str, int)) else _organization_id()
    sessao = InventarioSessao.query.filter_by(id=sessao_id, organization_id=org_id).first()
    if not sessao:
        raise ValueError("Sessão de inventário não encontrada")
    if sessao.status != "aberto":
        raise ValueError("Sessão de inventário já está fechada")

    # Verificar se todos os itens foram aprovados
    itens_nao_aprovados = sessao.itens.filter(~InventarioItem.aprovado).count()
    if itens_nao_aprovados > 0:
        raise ValueError(
            f"Não é possível fechar: {itens_nao_aprovados} item(ns) ainda não foram aprovados."
        )

    sessao.status = "fechado"
    sessao.data_fechamento = _now()
    db.session.add(sessao)
    db.session.commit()
    return sessao


def listar_inventario_sessoes(organization_id: int, limit: int = 30):
    """Lista sessões de inventário por organização."""
    org_id = int(organization_id) if isinstance(organization_id, (str, int)) else _organization_id()
    return (
        InventarioSessao.query
        .filter_by(organization_id=org_id)
        .order_by(InventarioSessao.data_abertura.desc(), InventarioSessao.id.desc())
        .limit(int(limit or 30))
        .all()
    )


def get_inventario_sessao(organization_id: int, sessao_id: int):
    """Retorna uma sessão de inventário por ID."""
    org_id = int(organization_id) if isinstance(organization_id, (str, int)) else _organization_id()
    return InventarioSessao.query.filter_by(id=sessao_id, organization_id=org_id).first()


def get_inventario_itens(organization_id: int, sessao_id: int):
    """Retorna todos os itens de uma sessão de inventário."""
    org_id = int(organization_id) if isinstance(organization_id, (str, int)) else _organization_id()
    sessao = InventarioSessao.query.filter_by(id=sessao_id, organization_id=org_id).first()
    if not sessao:
        return []
    return sorted(sessao.itens, key=lambda item: (item.peca_id or 0, item.id or 0))


def informar_quantidade_fisica(
    organization_id: int,
    sessao_id: int,
    peca_id: int,
    quantidade_fisica: int,
    usuario_id: int,
    justificativa: str = None,
):
    """Registra a quantidade física contada para um item da sessão."""
    org_id = int(organization_id) if isinstance(organization_id, (str, int)) else _organization_id()
    sessao = InventarioSessao.query.filter_by(id=sessao_id, organization_id=org_id).first()
    if not sessao:
        raise ValueError("Sessão de inventário não encontrada")
    if sessao.status != "aberto":
        raise ValueError("Sessão de inventário já está fechada")

    item = InventarioItem.query.filter_by(
        sessao_id=sessao_id, peca_id=peca_id
    ).first()
    if not item:
        raise ValueError("Peça não encontrada nesta sessão de inventário")

    quantidade_sistema = item.quantidade_sistema
    quantidade_fisica_int = _float(quantidade_fisica)
    divergencia = quantidade_fisica_int - quantidade_sistema

    item.quantidade_fisica = quantidade_fisica_int
    item.divergencia = divergencia

    # Regras de justificativa
    if divergencia != 0:
        if not justificativa or len(str(justificativa).strip()) < 5:
            raise ValueError(
                "Peça divergente requer justificativa de pelo menos 5 caracteres."
            )
        item.justificativa = str(justificativa)[:300]
    else:
        item.justificativa = None

    db.session.add(item)
    db.session.commit()
    return item


def aprovar_ajuste(
    organization_id: int,
    sessao_id: int,
    peca_id: int,
    usuario_id: int,
    justificativa: str = None,
):
    """Aprova o ajuste de uma peça, atualizando o estoque do sistema."""
    org_id = int(organization_id) if isinstance(organization_id, (str, int)) else _organization_id()
    sessao = InventarioSessao.query.filter_by(id=sessao_id, organization_id=org_id).first()
    if not sessao:
        raise ValueError("Sessão de inventário não encontrada")
    if sessao.status not in {"aberto", "fechado"}:
        raise ValueError("Sessão de inventário não pode receber ajustes neste estado")

    item = InventarioItem.query.filter_by(
        sessao_id=sessao_id, peca_id=peca_id
    ).first()
    if not item:
        raise ValueError("Peça não encontrada nesta sessão de inventário")

    if item.aprovado:
        raise ValueError("Ajuste desta peça já foi aprovado anteriormente.")

    # Calcular nova quantidade
    quantidade_anterior = item.peca.quantidade
    delta = item.divergencia  # positivo = sobra, negativo = falta
    nova_qtd = _quantidade_disponivel_apos(item.peca, delta)

    if nova_qtd > MAX_QUANTIDADE_PIECA:
        raise ValueError(
            f"Quantidade resultante ({nova_qtd}) excede o limite máximo ({MAX_QUANTIDADE_PIECA})."
        )

    # Atualizar quantidade da peça
    item.peca.quantidade = nova_qtd

    # Registrar movimento de estoque
    usuario = db.session.get(Usuario, usuario_id) or Usuario.query.get(usuario_id)
    motivo = f"Inventário fisica: divergencia={item.divergencia}"
    if justificativa and len(str(justificativa).strip()) >= 5:
        motivo += f" — {justificativa}"

    db.session.add(InventoryMovement(
        organization_id=org_id,
        part_id=item.peca.id,
        user_id=usuario_id,
        movement_type="inventario",
        quantity_before=quantidade_anterior,
        quantity_after=nova_qtd,
        quantity_delta=int(nova_qtd - quantidade_anterior),
        reason=motivo[:300],
    ))

    # Registrar ajuste de inventário
    item.aprovado = True
    item.aprovado_em = _now()
    item.aprovado_por_id = usuario_id
    item.aprovado_por_nome = (usuario.nome if usuario else "Sistema")

    # Registrar no historico de ajustes
    ajuste = InventarioAjuste(
        organizacao_id=org_id,
        sessao_id=sessao_id,
        peca_id=item.peca.id,
        quantidade_anterior=quantidade_anterior,
        quantidade_nova=nova_qtd,
        divergencia=item.divergencia,
        justificativa=str(justificativa)[:300] if justificativa else "",
        aplicado_por_id=usuario_id,
        aplicado_por_nome=(usuario.nome if usuario else "Sistema"),
    )
    db.session.add(ajuste)

    db.session.commit()
    return {"status": "aprovado", "nova_quantidade": nova_qtd, "divergencia": item.divergencia}


def rejeitar_ajuste(organization_id: int, sessao_id: int, peca_id: int, usuario_id: int, motivo: str):
    """Rejeita a aprovação de ajuste, desfazendo quaisquer alterações parciais."""
    org_id = int(organization_id) if isinstance(organization_id, (str, int)) else _organization_id()
    sessao = InventarioSessao.query.filter_by(id=sessao_id, organization_id=org_id).first()
    if not sessao:
        raise ValueError("Sessão de inventário não encontrada")

    item = InventarioItem.query.filter_by(sessao_id=sessao_id, peca_id=peca_id).first()
    if not item:
        raise ValueError("Peça não encontrada nesta sessão de inventário")

    item.aprovado = False
    item.aprovado_em = None
    item.aprovado_por_id = None
    item.aprovado_por_nome = None
    db.session.add(item)
    db.session.commit()
    return {"status": "rejeitado"}


def resumo_sessao(organization_id: int, sessao_id: int) -> dict:
    """Retorna um resumo da sessão de inventário."""
    org_id = int(organization_id) if isinstance(organization_id, (str, int)) else _organization_id()
    sessao = InventarioSessao.query.filter_by(id=sessao_id, organization_id=org_id).first()
    if not sessao:
        return {"status": "nao_encontrada"}

    itens = sessao.itens.all()
    total_itens = len(itens)
    itens_divergentes = sum(1 for i in itens if i.divergencia != 0)
    itens_aprovados = sum(1 for i in itens if i.aprovado)
    total_divergencia = sum(abs(i.divergencia) for i in itens)

    # Totais de quantidade
    total_sistema = sum(i.quantidade_sistema for i in itens)
    total_fisico = sum(i.quantidade_fisica for i in itens)

    return {
        "sessao_id": sessao.id,
        "status": sessao.status,
        "data_abertura": sessao.data_abertura.isoformat() if sessao.data_abertura else None,
        "data_fechamento": sessao.data_fechamento.isoformat() if sessao.data_fechamento else None,
        "total_itens": total_itens,
        "itens_divergentes": itens_divergentes,
        "itens_aprovados": itens_aprovados,
        "total_divergencia_absoluta": total_divergencia,
        "total_quantidade_sistema": total_sistema,
        "total_quantidade_fisica": total_fisico,
        "percentual_divergente": round((itens_divergentes / total_itens * 100) if total_itens else 0, 2),
    }


def historico_ajustes(organization_id: int, sessao_id: int = None, limit: int = 50) -> list:
    """Retorna o histórico de ajustes de inventário."""
    org_id = int(organization_id) if isinstance(organization_id, (str, int)) else _organization_id()
    query = InventarioAjuste.query.filter_by(organizacao_id=org_id)
    if sessao_id:
        query = query.filter_by(sessao_id=sessao_id)
    ajustes = query.order_by(InventarioAjuste.aplicado_em.desc()).limit(int(limit or 50)).all()
    return [
        {
            "id": ajuste.id,
            "peca_id": ajuste.peca_id,
            "quantidade_anterior": ajuste.quantidade_anterior,
            "quantidade_nova": ajuste.quantidade_nova,
            "divergencia": ajuste.divergencia,
            "justificativa": ajuste.justificativa,
            "aplicado_em": ajuste.aplicado_em,
            "aplicado_por": ajuste.aplicado_por_nome,
        }
        for ajuste in ajustes
    ]