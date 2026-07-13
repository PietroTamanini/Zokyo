from datetime import datetime, timezone

from app.extensions import db


class ServiceChecklistTemplate(db.Model):
    __tablename__ = "service_checklist_templates"
    __table_args__ = (
        db.UniqueConstraint("organization_id", "category", "version", name="uq_checklist_org_category_version"),
    )

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    category = db.Column(db.String(100), nullable=False, index=True)
    version = db.Column(db.Integer, nullable=False)
    items = db.Column(db.JSON, nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
