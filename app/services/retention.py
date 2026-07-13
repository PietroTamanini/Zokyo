"""Retencao conservadora; nunca remove OS, laudos, financeiro ou auditoria."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_

from app.extensions import db
from app.models import Notification, PasswordResetToken, PortalToken, RetentionPolicy, Usuario

CATEGORIES = {
    "password_reset_tokens": "Tokens de recuperacao de senha",
    "portal_tokens": "Tokens expirados/revogados do portal",
    "notifications": "Notificacoes em estado terminal",
}


def _now():
    return datetime.now(timezone.utc)


def count_candidates(policy, now=None):
    cutoff = (now or _now()) - timedelta(days=policy.retention_days)
    if policy.category == "password_reset_tokens":
        return (PasswordResetToken.query.join(Usuario)
                .filter(Usuario.organization_id == policy.organization_id,
                        PasswordResetToken.criado_em < cutoff).count())
    if policy.category == "portal_tokens":
        return PortalToken.query.execution_options(include_all_tenants=True).filter(
            PortalToken.organization_id == policy.organization_id,
            PortalToken.criado_em < cutoff,
            or_(PortalToken.revogado_em.is_not(None), PortalToken.expira_em < (now or _now())),
        ).count()
    if policy.category == "notifications":
        return Notification.query.execution_options(include_all_tenants=True).filter(
            Notification.organization_id == policy.organization_id,
            Notification.created_at < cutoff,
            Notification.status.in_(("sent", "manual_required", "failed")),
        ).count()
    return 0


def apply_policy(policy, now=None):
    if not policy.active or not policy.approved_at or policy.category not in CATEGORIES:
        return 0
    cutoff = (now or _now()) - timedelta(days=policy.retention_days)
    if policy.category == "password_reset_tokens":
        ids = [row[0] for row in (db.session.query(PasswordResetToken.id).join(Usuario)
               .filter(Usuario.organization_id == policy.organization_id,
                       PasswordResetToken.criado_em < cutoff).all())]
        deleted = PasswordResetToken.query.filter(PasswordResetToken.id.in_(ids)).delete(synchronize_session=False) if ids else 0
    elif policy.category == "portal_tokens":
        deleted = PortalToken.query.execution_options(include_all_tenants=True).filter(
            PortalToken.organization_id == policy.organization_id, PortalToken.criado_em < cutoff,
            or_(PortalToken.revogado_em.is_not(None), PortalToken.expira_em < (now or _now())),
        ).delete(synchronize_session=False)
    else:
        deleted = Notification.query.execution_options(include_all_tenants=True).filter(
            Notification.organization_id == policy.organization_id, Notification.created_at < cutoff,
            Notification.status.in_(("sent", "manual_required", "failed")),
        ).delete(synchronize_session=False)
    db.session.commit()
    return deleted


def apply_active_policies():
    policies = RetentionPolicy.query.execution_options(include_all_tenants=True).filter_by(active=True).all()
    return sum(apply_policy(policy) for policy in policies)
