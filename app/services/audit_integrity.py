"""Verificação da cadeia de integridade da auditoria."""
import os
from pathlib import Path

from app.extensions import db
from app.models import EventoLog, registrar
from app.models.evento_log import AuditChainHead
from scripts.audit_anchor import latest_anchor, publish_anchor


def verify_event_chain():
    events = EventoLog.query.execution_options(include_all_tenants=True).order_by(EventoLog.id.asc()).all()
    legacy = 0
    checked = 0
    errors = []
    previous = "GENESIS"
    for event in events:
        if not event.integrity_hash:
            legacy += 1
            continue
        checked += 1
        expected = event.calculate_integrity_hash()
        if event.previous_hash != previous:
            errors.append({"id": event.id, "reason": "previous_hash", "expected": previous})
        if event.integrity_hash != expected:
            errors.append({"id": event.id, "reason": "integrity_hash"})
        previous = event.integrity_hash
    head = AuditChainHead.query.filter_by(id=1).first()
    if head is None:
        errors.append({"id": None, "reason": "chain_head_missing"})
    elif head.last_hash != previous:
        errors.append({"id": None, "reason": "chain_head_mismatch", "expected": previous})
    return {
        "total": len(events), "checked": checked, "legacy": legacy, "errors": errors,
        "head_hash": head.last_hash if head else None,
        "last_event_id": events[-1].id if events else None,
    }


def verify_saved_anchor(directory):
    saved = latest_anchor(Path(directory))
    if saved is None:
        return None
    path, anchor = saved
    if anchor["last_event_id"] is not None:
        event = EventoLog.query.execution_options(include_all_tenants=True).filter_by(
            id=anchor["last_event_id"]
        ).first()
        if event is None or event.integrity_hash != anchor["head_hash"]:
            raise RuntimeError("Cadeia de auditoria diverge da última âncora preservada.")
    return path


def assert_event_chain(*, record_success=False, anchor_dir=None):
    """Usado pelo job monitorado; não expõe payloads nos alertas."""
    result = verify_event_chain()
    if result["errors"] or result["legacy"]:
        raise RuntimeError(
            f"Auditoria inconsistente: {len(result['errors'])} erro(s), "
            f"{result['legacy']} evento(s) sem hash."
        )
    anchor_dir = anchor_dir or (os.environ.get("AUDIT_ANCHOR_DIR") if record_success else None)
    if anchor_dir:
        verify_saved_anchor(anchor_dir)
    if record_success:
        registrar(
            "sistema", "audit_integrity", "Cadeia de auditoria verificada",
            f"eventos={result['checked']};ultimo_id={result['last_event_id'] or 0};"
            f"hash_ponta={result['head_hash']}",
            organization_id=None,
        )
        db.session.commit()
        if anchor_dir:
            publish_anchor(Path(anchor_dir), result)
    return result


def backfill_legacy_events():
    """Após o selo transacional, eventos legados exigem investigação manual."""
    head = AuditChainHead.query.filter_by(id=1).first()
    events = EventoLog.query.execution_options(include_all_tenants=True).order_by(EventoLog.id.asc()).all()
    if head is None:
        raise RuntimeError("Aplique a migration 0043, que valida e completa hashes históricos.")
    if any(not event.integrity_hash for event in events):
        raise RuntimeError("Evento sem hash após selagem da cadeia; investigue antes de alterar a auditoria.")
    return 0
