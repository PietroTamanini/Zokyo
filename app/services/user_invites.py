"""Convites de usuario de uso unico e expiracao curta."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models import UserInvite


def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def create_invite(organization_id, email, role, invited_by_id, ttl_hours=48):
    now = datetime.now(timezone.utc)
    for old in UserInvite.query.filter_by(email=email, used_at=None, revoked_at=None).all():
        old.revoked_at = now
    raw_token = secrets.token_urlsafe(32)
    invite = UserInvite(
        organization_id=organization_id,
        email=email,
        role=role,
        token_hash=_hash(raw_token),
        invited_by_id=invited_by_id,
        expires_at=now + timedelta(hours=max(1, min(ttl_hours, 168))),
    )
    db.session.add(invite)
    return invite, raw_token


def find_valid_invite(raw_token):
    invite = UserInvite.query.execution_options(include_all_tenants=True).filter_by(token_hash=_hash(raw_token)).first()
    if not invite or invite.used_at or invite.revoked_at:
        return None
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    expires = invite.expires_at.replace(tzinfo=None)
    return invite if expires > now else None
