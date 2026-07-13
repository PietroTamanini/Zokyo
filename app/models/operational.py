from datetime import datetime, timezone

from app.extensions import db


class OperationalHeartbeat(db.Model):
    __tablename__ = "operational_heartbeats"

    id = db.Column(db.Integer, primary_key=True)
    job_name = db.Column(db.String(100), nullable=False, unique=True)
    last_started_at = db.Column(db.DateTime)
    last_success_at = db.Column(db.DateTime)
    last_failure_at = db.Column(db.DateTime)
    last_duration_ms = db.Column(db.Integer)
    consecutive_failures = db.Column(db.Integer, nullable=False, default=0)
    last_error = db.Column(db.String(500))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class OperationalAlert(db.Model):
    __tablename__ = "operational_alerts"

    id = db.Column(db.Integer, primary_key=True)
    severity = db.Column(db.String(20), nullable=False, index=True)
    source = db.Column(db.String(100), nullable=False, index=True)
    message = db.Column(db.String(500), nullable=False)
    fingerprint = db.Column(db.String(64), nullable=False, index=True)
    occurrences = db.Column(db.Integer, nullable=False, default=1)
    first_seen_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    last_seen_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    resolved_at = db.Column(db.DateTime)
