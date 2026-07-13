from datetime import datetime, timezone

from app.extensions import db


class MessageTemplate(db.Model):
    __tablename__ = "message_templates"
    __table_args__ = (
        db.UniqueConstraint("organization_id", "event_type", "channel", "version", name="uq_message_template_version"),
    )

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    event_type = db.Column(db.String(80), nullable=False, index=True)
    channel = db.Column(db.String(20), nullable=False)
    version = db.Column(db.Integer, nullable=False)
    subject = db.Column(db.String(200))
    body = db.Column(db.Text, nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
