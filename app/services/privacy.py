"""Exportação e anonimização conservadora de dados do titular."""
import hashlib
import io
import json
import re
import secrets
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import current_app
from app.extensions import db
from app.utils.validators import validar_email
from app.models import (
    Cliente,
    ColetaAgendada,
    ConsentRecord,
    DataSubjectRequest,
    LaudoFoto,
    LaudoTecnico,
    OSFoto,
    OrdemServico,
    Transacao,
    Usuario,
    registrar,
)

REQUEST_TYPE_LABELS = {
    "confirmation": "Confirmação de tratamento",
    "access": "Acesso aos dados",
    "correction": "Correção de dados",
    "deletion": "Eliminação de dados",
    "anonymization": "Anonimização de dados",
    "blocking": "Bloqueio de dados",
    "portability": "Portabilidade",
    "information": "Informações sobre o tratamento",
    "sharing": "Informações sobre compartilhamento",
    "non_consent": "Consequências de não consentir",
    "consent_revocation": "Revogação de consentimento",
    "automated_review": "Revisão de decisão automatizada",
}


def _now():
    return datetime.now(timezone.utc)


def _check_client_operator_scope(cliente: Cliente, user: Usuario, target_organization_id=None):
    if target_organization_id is None:
        allowed = bool(user.organization_id and cliente.organization_id == user.organization_id)
    else:
        allowed = bool(
            user.is_platform_admin and user.organization_id is None
            and cliente.organization_id == target_organization_id
        )
    if not allowed:
        raise ValueError("Cliente não encontrado.")


def create_subject_request(*, request_type, requester_name, requester_email,
                           organization_id=None, description=None, channel="public"):
    """Cria uma solicitação de titular sem exigir conta no sistema."""
    if request_type not in REQUEST_TYPE_LABELS:
        raise ValueError("Tipo de solicitação inválido.")
    name = (requester_name or "").strip()[:160]
    email = (requester_email or "").strip().lower()[:254]
    if len(name) < 2 or not validar_email(email):
        raise ValueError("Informe nome e e-mail válidos.")
    record = DataSubjectRequest(
        organization_id=organization_id,
        request_type=request_type,
        status="open",
        solicitado_por_id=None,
        requester_name=name,
        requester_email=email,
        channel=channel[:30],
        identity_verified=False,
        due_at=_now() + timedelta(days=15),
        observacoes=(description or "").strip()[:4000] or None,
    )
    db.session.add(record)
    registrar(
        "criacao", "privacidade", "Solicitação de titular recebida",
        descricao=f"Canal={channel[:30]}; tipo={request_type}",
        organization_id=organization_id,
    )
    return record


def register_consent(cliente: Cliente, user: Usuario, purpose: str, granted: bool, source: str = "admin",
                     *, policy_version=None, evidence_reference=None):
    if cliente.organization_id != user.organization_id:
        raise ValueError("Cliente não encontrado.")
    if purpose not in {"service_updates", "marketing", "data_processing"}:
        raise ValueError("Finalidade de consentimento inválida.")
    version = str(policy_version or "").strip()
    reference = str(evidence_reference or "").strip()
    if len(source) > 60 or len(version) > 40 or len(reference) > 200:
        raise ValueError("Metadados de consentimento excedem o limite permitido.")
    if granted and (source not in {"portal", "public_form"}
                    or not re.fullmatch(r"[A-Za-z0-9._-]{1,40}", version)
                    or not 3 <= len(reference) <= 200):
        raise ValueError("Concessão exige coleta direta, versão do aviso e referência da evidência.")
    record = ConsentRecord(
        organization_id=cliente.organization_id, cliente_id=cliente.id,
        purpose=purpose, granted=bool(granted), source=source[:60], registrado_por_id=user.id,
        policy_version=version or None, evidence_reference=reference or None,
    )
    db.session.add(record)
    registrar(
        "edicao", "privacidade", f"Consentimento {purpose}: {'concedido' if granted else 'revogado'}",
        usuario_id=user.id, usuario_nome=user.nome, organization_id=cliente.organization_id,
    )
    return record


def has_active_consent(organization_id: int, cliente_id: int, purpose: str) -> bool:
    latest = (ConsentRecord.query.filter_by(
        organization_id=organization_id, cliente_id=cliente_id, purpose=purpose,
    ).order_by(ConsentRecord.id.desc()).first())
    return bool(latest and latest.granted and latest.policy_version and latest.evidence_reference)


_SUBJECT_ORDER_FIELDS = (
    "id", "numero", "codigo_os", "cliente_id", "tipo_aparelho", "marca",
    "modelo", "numero_serie", "defeito_alegado", "defeito_encontrado",
    "solucao", "observacoes", "valor_servico", "valor_pecas", "desconto",
    "valor_total", "status", "tipo_atendimento", "garantia_dias",
    "data_entrada", "data_saida", "data_prev", "em_garantia",
)

_SUBJECT_TRANSACTION_FIELDS = (
    "id", "os_id", "tipo", "categoria", "descricao", "valor", "forma_pagamento",
    "status", "data_vencimento", "data_pagamento", "criado_em", "parcela_numero",
    "parcela_total", "payment_method", "payment_status",
)

_SUBJECT_REPORT_FIELDS = (
    "id", "numero", "tipo", "status", "versao", "criado_em", "emitido_em",
    "defeito_relatado", "inspecao_visual", "testes_realizados", "instrumentos_metodos",
    "medicoes", "diagnostico_tecnico", "causa_provavel", "servicos_realizados",
    "pecas_utilizadas", "conclusao_tecnica", "estado_final", "recomendacoes",
    "riscos_limitacoes", "garantia", "observacoes", "motivo_cancelamento",
    "equipamento_snapshot", "cliente_snapshot", "assinatura_cliente_nome",
    "assinatura_cliente_em", "assinatura_cliente_metodo",
)


def _selected_fields(data, names):
    return {name: data.get(name) for name in names}


def _export_value(value):
    return value.isoformat() if isinstance(value, datetime) else value


def export_subject_data(cliente: Cliente, user: Usuario, *, target_organization_id=None,
                        access_reason=None, access_reference=None) -> io.BytesIO:
    _check_client_operator_scope(cliente, user, target_organization_id)
    if access_reason is not None and access_reason not in {
        "subject_request", "support_request", "incident_investigation",
    }:
        raise ValueError("Motivo de acesso inválido.")
    if access_reference and not re.fullmatch(
        r"(?:(?:solicitacao_id|incidente_id)=[1-9][0-9]*|protocolo=[A-Z0-9][A-Z0-9-]{3,39})",
        access_reference,
    ):
        raise ValueError("Referência de acesso inválida.")
    organization_id = cliente.organization_id
    orders = OrdemServico.query.filter_by(
        organization_id=organization_id, cliente_id=cliente.id,
    ).order_by(OrdemServico.id).all()
    order_ids = [order.id for order in orders]
    reports = LaudoTecnico.query.filter_by(
        organization_id=organization_id, cliente_id=cliente.id,
    ).order_by(LaudoTecnico.id).all()
    collections = ColetaAgendada.query.filter_by(
        organization_id=organization_id, cliente_id=cliente.id,
    ).order_by(ColetaAgendada.id).all()
    subject_requests = DataSubjectRequest.query.filter_by(
        organization_id=organization_id, cliente_id=cliente.id,
    ).order_by(DataSubjectRequest.id).all()
    transactions = Transacao.query.filter(
        Transacao.organization_id == organization_id,
        Transacao.os_id.in_(order_ids),
    ).order_by(Transacao.id).all() if order_ids else []
    consents = ConsentRecord.query.filter_by(
        organization_id=organization_id, cliente_id=cliente.id,
    ).order_by(ConsentRecord.registrado_em).all()
    report_ids = [report.id for report in reports]
    laudo_photos = LaudoFoto.query.filter(
        LaudoFoto.organization_id == organization_id,
        LaudoFoto.laudo_id.in_(report_ids),
    ).all() if report_ids else []
    os_photos = OSFoto.query.filter(
        OSFoto.organization_id == organization_id,
        OSFoto.os_id.in_(order_ids),
    ).all() if order_ids else []
    client_data = cliente.to_dict()
    client_data["email"] = cliente.email or ""
    payload = {
        "exported_at": _now().isoformat(),
        "cliente": client_data,
        "ordens_servico": [
            _selected_fields(order.to_dict(), _SUBJECT_ORDER_FIELDS) for order in orders
        ],
        "laudos": [
            {field: _export_value(getattr(report, field)) for field in _SUBJECT_REPORT_FIELDS}
            for report in reports
        ],
        "coletas": [{
            "id": item.id, "os_id": item.os_id, "status": item.status,
            "data_agendada": _export_value(item.data_agendada), "telefone_contato": item.telefone_contato,
            "cep": item.cep, "endereco": item.endereco, "numero_casa": item.numero_casa,
            "cidade": item.cidade, "uf": item.uf, "observacoes": item.observacoes,
            "criado_em": _export_value(item.criado_em),
        } for item in collections],
        "solicitacoes": [{
            "id": item.id, "tipo": item.request_type, "status": item.status,
            "solicitado_em": _export_value(item.solicitado_em),
            "concluido_em": _export_value(item.concluido_em),
            "resposta": item.response_notes, "canal_resposta": item.response_channel,
            "entregue_em": _export_value(item.delivered_at),
        } for item in subject_requests],
        "transacoes": [
            _selected_fields(transaction.to_dict(), _SUBJECT_TRANSACTION_FIELDS)
            for transaction in transactions
        ],
        "consentimentos": [{
            "purpose": consent.purpose, "granted": consent.granted,
            "source": consent.source, "policy_version": consent.policy_version,
            "evidence_reference": consent.evidence_reference,
            "registrado_em": consent.registrado_em.isoformat(),
        } for consent in consents],
        "arquivos": {
            "laudos": [{
                "id": photo.id, "laudo_id": photo.laudo_id,
                "nome_original": photo.nome_original, "mime_type": photo.mime_type,
                "tamanho_bytes": photo.tamanho_bytes, "sha256": photo.sha256,
            } for photo in laudo_photos],
            "ordens_servico": [{
                "id": photo.id, "os_id": photo.os_id,
                "nome_original": photo.original_filename, "mime_type": photo.mime_type,
                "tamanho_bytes": photo.tamanho_bytes,
            } for photo in os_photos],
        },
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("dados.json", json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        files_added = 0
        # Inclui os binários somente após confirmar que cada caminho permanece
        # dentro do diretório de uploads correspondente. O storage externo é
        # hidratado pelo mesmo adaptador usado nas rotas autenticadas.
        from app.services.laudos import safe_file_path
        from app.services.object_storage import hydrate

        for photo in laudo_photos:
            try:
                target = safe_file_path(photo.storage_key)
                if target.exists():
                    archive.write(target, f"arquivos/laudos/{photo.id}-{Path(photo.nome_original or target.name).name}")
                    files_added += 1
            except (OSError, ValueError):
                continue
        upload_root = Path(current_app.instance_path) / "uploads"
        resolved_root = upload_root.resolve()
        for photo in os_photos:
            try:
                target = (upload_root / photo.filename).resolve()
                if not target.is_relative_to(resolved_root):
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                hydrate(photo.filename, target)
                if target.exists():
                    archive.write(target, f"arquivos/ordens-servico/{photo.id}-{Path(photo.original_filename or target.name).name}")
                    files_added += 1
            except (OSError, ValueError):
                continue
        archive.writestr(
            "LEIA-ME.txt",
            f"Exportação estruturada de dados do titular. Arquivos incluídos: {files_added}. "
            "Arquivos ausentes no storage foram mantidos no manifesto para permitir conferência. "
            "Revise textos livres, imagens e dados de terceiros antes de entregar o arquivo. "
            "Este download administrativo não registra entrega nem conclui pedido do titular.\n",
        )
    view = output.getbuffer()
    try:
        archive_hash = hashlib.sha256(view).hexdigest()
    finally:
        view.release()
    registrar(
        "acesso", "privacidade", f"Exportação administrativa dos dados do cliente #{cliente.id}",
        descricao=(f"motivo={access_reason};{access_reference};zip_sha256={archive_hash}"
                   if access_reference else
                   f"motivo={access_reason or 'não registrado'};zip_sha256={archive_hash}"),
        usuario_id=user.id, usuario_nome=user.nome, organization_id=cliente.organization_id,
    )
    output.export_sha256 = archive_hash
    output.seek(0)
    return output


def anonymize_client(cliente: Cliente, user: Usuario, *, target_organization_id=None,
                     access_reason=None, access_reference=None):
    """Remove identificadores do cadastro; não elimina histórico nem garante anonimização."""
    _check_client_operator_scope(cliente, user, target_organization_id)
    if access_reason is not None and access_reason not in {
        "subject_request", "duplicate_record", "data_minimization",
    }:
        raise ValueError("Motivo de remoção inválido.")
    if access_reference and not re.fullmatch(
        r"(?:solicitacao_id=[1-9][0-9]*|protocolo=[A-Z0-9][A-Z0-9-]{3,39})",
        access_reference,
    ):
        raise ValueError("Referência de remoção inválida.")
    if OrdemServico.query.filter_by(cliente_id=cliente.id).count() or LaudoTecnico.query.filter_by(cliente_id=cliente.id).count():
        raise ValueError("Anonimizacao bloqueada: existem OS ou laudos sujeitos a retencao.")
    if ColetaAgendada.query.filter_by(cliente_id=cliente.id).count():
        raise ValueError("Remoção cadastral bloqueada: existe coleta vinculada ao cliente.")
    marker = secrets.token_hex(6)
    cliente.nome = f"Cadastro sem identificação {marker}"
    for field in ("cpf", "cnpj", "telefone", "email", "cep", "endereco", "numero_casa", "cidade", "uf"):
        setattr(cliente, field, None)
    cliente.ativo = False
    registrar(
        "exclusao", "privacidade", f"Dados cadastrais do cliente #{cliente.id} removidos",
        descricao=(f"motivo={access_reason};{access_reference}" if access_reference
                   else f"motivo={access_reason or 'não registrado'}"),
        usuario_id=user.id, usuario_nome=user.nome, organization_id=cliente.organization_id,
    )
