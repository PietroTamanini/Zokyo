from datetime import datetime, timezone

from app.extensions import db


def _now():
    return datetime.now(timezone.utc)


class UserSession(db.Model):
    __tablename__ = "user_sessions"
    __table_args__ = (
        db.Index("ix_user_sessions_user_active", "user_id", "revoked_at", "expires_at"),
        db.Index("ix_user_sessions_user_last_seen", "user_id", "last_seen_at"),
        db.Index("ix_user_sessions_org_user_active", "organization_id", "user_id", "revoked_at", "expires_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True)
    token_hash = db.Column(db.String(64), nullable=False, unique=True)
    security_version = db.Column(db.Integer, nullable=False)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, nullable=False, default=_now)
    last_seen_at = db.Column(db.DateTime, nullable=False, default=_now)
    expires_at = db.Column(db.DateTime, nullable=False)
    revoked_at = db.Column(db.DateTime)
    revoked_reason = db.Column(db.String(100))

    user = db.relationship(
        "Usuario",
        backref=db.backref("active_sessions", lazy=True, cascade="all, delete-orphan"),
    )

    @property
    def is_active(self):
        now = _now().replace(tzinfo=None)
        expires = self.expires_at.replace(tzinfo=None)
        return self.revoked_at is None and expires > now and self.security_version == self.user.security_version
