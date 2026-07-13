"""Registro e revogacao de sessoes autenticadas."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from flask import current_app, request, session

from app.extensions import db
from app.models import UserSession


def _now():
    return datetime.now(timezone.utc)


def _hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_session_record(user) -> UserSession:
    raw_token = secrets.token_urlsafe(32)
    lifetime = current_app.config.get("PERMANENT_SESSION_LIFETIME", timedelta(hours=8))
    record = UserSession(
        organization_id=user.organization_id,
        user_id=user.id,
        token_hash=_hash(raw_token),
        security_version=user.security_version,
        ip_address=(request.remote_addr or "unknown")[:45],
        user_agent=(request.user_agent.string or "Desconhecido")[:300],
        expires_at=_now() + lifetime,
    )
    db.session.add(record)
    session["session_token"] = raw_token
    return record


def current_session_record(user_id: int) -> UserSession | None:
    raw_token = session.get("session_token")
    if not raw_token:
        return None
    return UserSession.query.filter_by(user_id=user_id, token_hash=_hash(raw_token)).first()


def validate_session_record(user) -> bool:
    record = current_session_record(user.id)
    if not record or not record.is_active:
        return False
    now = _now()
    last_seen = record.last_seen_at.replace(tzinfo=timezone.utc)
    if now - last_seen >= timedelta(minutes=5):
        record.last_seen_at = now
        db.session.commit()
    return True


def revoke_record(record: UserSession, reason: str) -> None:
    if record.revoked_at is None:
        record.revoked_at = _now()
        record.revoked_reason = reason[:100]


def revoke_all(user_id: int, reason: str, except_id: int | None = None) -> int:
    query = UserSession.query.filter_by(user_id=user_id, revoked_at=None)
    records = query.all()
    changed = 0
    for record in records:
        if record.id == except_id:
            continue
        revoke_record(record, reason)
        changed += 1
    return changed
