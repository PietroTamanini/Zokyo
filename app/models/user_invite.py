from datetime import datetime, timezone

from app.extensions import db


class UserInvite(db.Model):
    __tablename__ = "user_invites"
    __table_args__ = (
        db.Index("ix_user_invites_org_email_open", "organization_id", "email", "used_at", "revoked_at", "expires_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    email = db.Column(db.String(254), nullable=False, index=True)
    role = db.Column(db.String(20), nullable=False)
    token_hash = db.Column(db.String(64), nullable=False, unique=True)
    invited_by_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime)
    revoked_at = db.Column(db.DateTime)

    invited_by = db.relationship("Usuario")
