"""Exportação e anonimização conservadora de dados do titular."""
import io
import json
import secrets
import zipfile
from datetime import datetime, timezone

from app.extensions import db
from app.models import (
    Cliente,
    ConsentRecord,
    DataSubjectRequest,
    LaudoTecnico,
    OrdemServico,
    Transacao,
    Usuario,
    registrar,
)


def _now():
    return datetime.now(timezone.utc)


def register_consent(cliente: Cliente, user: Usuario, purpose: str, granted: bool, source: str = "admin"):
    if cliente.organization_id != user.organization_id:
        raise ValueError("Cliente não encontrado.")
    if purpose not in {"service_updates", "marketing", "data_processing"}:
        raise ValueError("Finalidade de consentimento invalida.")
    record = ConsentRecord(
        organization_id=cliente.organization_id, cliente_id=cliente.id,
        purpose=purpose, granted=bool(granted), source=source[:60], registrado_por_id=user.id,
    )
    db.session.add(record)
    registrar(
        "edicao", "privacidade", f"Consentimento {purpose}: {'concedido' if granted else 'revogado'}",
        usuario_id=user.id, usuario_nome=user.nome, organization_id=cliente.organization_id,
    )
    return record


def export_subject_data(cliente: Cliente, user: Usuario) -> io.BytesIO:
    if cliente.organization_id != user.organization_id:
        raise ValueError("Cliente não encontrado.")
    orders = OrdemServico.query.filter_by(cliente_id=cliente.id).order_by(OrdemServico.id).all()
    order_ids = [order.id for order in orders]
    reports = LaudoTecnico.query.filter_by(cliente_id=cliente.id).order_by(LaudoTecnico.id).all()
    transactions = Transacao.query.filter(Transacao.os_id.in_(order_ids)).all() if order_ids else []
    consents = ConsentRecord.query.filter_by(cliente_id=cliente.id).order_by(ConsentRecord.registrado_em).all()
    payload = {
        "exported_at": _now().isoformat(),
        "cliente": cliente.to_dict(),
        "ordens_servico": [order.to_dict() for order in orders],
        "laudos": [{
            "numero": report.numero, "tipo": report.tipo, "status": report.status,
            "versao": report.versao, "criado_em": report.criado_em.isoformat(),
            "defeito_relatado": report.defeito_relatado, "diagnostico_tecnico": report.diagnostico_tecnico,
            "conclusao_tecnica": report.conclusao_tecnica,
        } for report in reports],
        "transacoes": [transaction.to_dict() for transaction in transactions],
        "consentimentos": [{
            "purpose": consent.purpose, "granted": consent.granted,
            "source": consent.source, "registrado_em": consent.registrado_em.isoformat(),
        } for consent in consents],
    }
    request_record = DataSubjectRequest(
        organization_id=cliente.organization_id, cliente_id=cliente.id, request_type="export",
        status="completed", solicitado_por_id=user.id, concluido_em=_now(),
    )
    db.session.add(request_record)
    registrar(
        "sistema", "privacidade", f"Exportacao do titular cliente #{cliente.id}",
        usuario_id=user.id, usuario_nome=user.nome, organization_id=cliente.organization_id,
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("dados.json", json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        archive.writestr(
            "LEIA-ME.txt",
            "Exportação estruturada de dados do titular. PDFs e fotografias privadas não estão incluídos neste pacote.\n",
        )
    output.seek(0)
    return output


def anonymize_client(cliente: Cliente, user: Usuario):
    if cliente.organization_id != user.organization_id:
        raise ValueError("Cliente não encontrado.")
    if OrdemServico.query.filter_by(cliente_id=cliente.id).count() or LaudoTecnico.query.filter_by(cliente_id=cliente.id).count():
        raise ValueError("Anonimizacao bloqueada: existem OS ou laudos sujeitos a retencao.")
    marker = secrets.token_hex(6)
    cliente.nome = f"Titular anonimizado {marker}"
    for field in ("cpf", "cnpj", "telefone", "email", "cep", "endereco", "numero_casa", "cidade", "uf"):
        setattr(cliente, field, None)
    cliente.ativo = False
    db.session.add(DataSubjectRequest(
        organization_id=cliente.organization_id, cliente_id=cliente.id, request_type="anonymization",
        status="completed", solicitado_por_id=user.id, concluido_em=_now(),
    ))
    registrar(
        "exclusao", "privacidade", f"Cliente #{cliente.id} anonimizado",
        usuario_id=user.id, usuario_nome=user.nome, organization_id=cliente.organization_id,
    )
