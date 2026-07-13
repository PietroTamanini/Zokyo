from datetime import datetime, timezone

from app.extensions import db


class SavedReport(db.Model):
    __tablename__ = "saved_reports"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    report_type = db.Column(db.String(40), nullable=False, default="management")
    filters = db.Column(db.JSON, nullable=False)
    frequency = db.Column(db.String(20))
    recipient = db.Column(db.String(254))
    active = db.Column(db.Boolean, nullable=False, default=True)
    next_run_at = db.Column(db.DateTime, index=True)
    last_run_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    user = db.relationship("Usuario")
