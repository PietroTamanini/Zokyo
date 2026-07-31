"""Regras de links publicos de acompanhamento e aprovacao."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models import OrdemServico, OSHistorico, PortalToken, Usuario, registrar

PORTAL_PURPOSES = {"tracking", "budget"}


def _now():
    return datetime.now(timezone.utc)


def _hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def criar_link_portal(os_obj: OrdemServico, usuario: Usuario, purpose: str, dias: int = 30) -> str:
    if purpose not in PORTAL_PURPOSES:
        raise ValueError("Finalidade de link invalida.")
    if os_obj.organization_id != usuario.organization_id:
        raise ValueError("Ordem de serviço não encontrada.")
    dias = min(max(int(dias), 1), 90)
    now = _now()
    PortalToken.query.filter_by(os_id=os_obj.id, purpose=purpose, revogado_em=None).update({"revogado_em": now})
    raw_token = secrets.token_urlsafe(32)
    db.session.add(PortalToken(
        organization_id=os_obj.organization_id,
        os_id=os_obj.id,
        token_hash=_hash(raw_token),
        purpose=purpose,
        criado_por_id=usuario.id,
        expira_em=now + timedelta(days=dias),
    ))
    registrar(
        "criacao", "portal", f"Link {purpose} criado para OS #{os_obj.id:04d}",
        usuario_id=usuario.id, usuario_nome=usuario.nome, organization_id=os_obj.organization_id,
    )
    return raw_token


def buscar_token_portal(raw_token: str) -> PortalToken | None:
    if not raw_token or len(raw_token) > 200:
        return None
    statement = (
        db.select(PortalToken)
        .where(PortalToken.token_hash == _hash(raw_token))
        .execution_options(include_all_tenants=True)
    )
    token = db.session.execute(statement).scalar_one_or_none()
    return token if token and token.valido else None


def decidir_orcamento(token: PortalToken, decisao: str):
    if token.purpose != "budget":
        raise ValueError("Este link não permite decidir o orçamento.")
    if token.usado_em:
        raise ValueError("Este orçamento já recebeu uma decisão.")
    if decisao not in {"approved", "rejected"}:
        raise ValueError("Decisao invalida.")
    os_obj = token.os
    previous_status = os_obj.status
    os_obj.orcamento_status = decisao
    os_obj.orcamento_decidido_em = _now()
    token.usado_em = _now()
    if decisao == "approved" and os_obj.status == "aguardando_aprovacao":
        os_obj.status = "em_reparo"
        db.session.add(OSHistorico(
            organization_id=os_obj.organization_id,
            os_id=os_obj.id,
            usuario_id=None,
            status_anterior=previous_status,
            status_novo=os_obj.status,
        ))
    registrar(
        "status", "portal", f"Orçamento da OS #{os_obj.id:04d}: {decisao}",
        organization_id=os_obj.organization_id,
    )
