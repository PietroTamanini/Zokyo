"""Registros operacionais de privacidade e atendimento ao titular."""
import json
from datetime import datetime, timezone
from sqlalchemy import event

from app.extensions import db
from app.utils.field_crypto import EncryptedText


def _now():
    return datetime.now(timezone.utc)


class ConsentRecord(db.Model):
    __tablename__ = "consent_records"
    __table_args__ = (
        db.Index("ix_consent_records_org_cliente_registrado", "organization_id", "cliente_id", "registrado_em"),
    )

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey("clientes.id"), nullable=False, index=True)
    purpose = db.Column(db.String(60), nullable=False)
    granted = db.Column(db.Boolean, nullable=False)
    source = db.Column(db.String(60), nullable=False, default="admin")
    policy_version = db.Column(db.String(40))
    evidence_reference = db.Column(db.String(200))
    registrado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    registrado_em = db.Column(db.DateTime, nullable=False, default=_now)


@event.listens_for(ConsentRecord, "before_update")
@event.listens_for(ConsentRecord, "before_delete")
def _reject_consent_mutation(_mapper, _connection, _target):
    raise RuntimeError("Consentimentos são append-only; registre uma nova decisão.")


class DataSubjectRequest(db.Model):
    __tablename__ = "data_subject_requests"
    __table_args__ = (
        db.Index("ix_data_subject_requests_org_cliente_solicitado", "organization_id", "cliente_id", "solicitado_em"),
        db.Index("ix_data_subject_requests_org_status_solicitado", "organization_id", "status", "solicitado_em"),
    )

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=True, index=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey("clientes.id"), nullable=True, index=True)
    request_type = db.Column(db.String(40), nullable=False)
    status = db.Column(db.String(30), nullable=False, default="open")
    solicitado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    solicitado_em = db.Column(db.DateTime, nullable=False, default=_now)
    concluido_em = db.Column(db.DateTime)
    observacoes = db.Column(EncryptedText)
    requester_name = db.Column(EncryptedText)
    requester_email = db.Column(EncryptedText)
    channel = db.Column(db.String(30), nullable=False, default="admin")
    identity_verified = db.Column(db.Boolean, nullable=False, default=False)
    identity_method = db.Column(db.String(30))
    identity_reference = db.Column(EncryptedText)
    identity_verified_at = db.Column(db.DateTime)
    due_at = db.Column(db.DateTime)
    response_notes = db.Column(EncryptedText)
    response_channel = db.Column(db.String(30))
    delivery_reference = db.Column(EncryptedText)
    delivered_at = db.Column(db.DateTime)
    prepared_export_sha256 = db.Column(db.String(64))
    prepared_export_at = db.Column(db.DateTime)


class DataSubjectRequestRevision(db.Model):
    """Histórico append-only do atendimento dos direitos do titular."""
    __tablename__ = "data_subject_request_revisions"

    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey("data_subject_requests.id"), nullable=False, index=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    action = db.Column(db.String(20), nullable=False)
    recorded_at = db.Column(db.DateTime, nullable=False, default=_now)
    snapshot = db.Column(EncryptedText, nullable=False)

    @property
    def details(self):
        return json.loads(self.snapshot)


_REQUEST_SNAPSHOT_FIELDS = (
    "organization_id", "cliente_id", "request_type", "status", "identity_verified", "identity_method",
    "identity_reference", "identity_verified_at", "due_at", "response_notes",
    "response_channel", "delivery_reference", "delivered_at", "concluido_em",
    "prepared_export_sha256", "prepared_export_at",
)


def _record_request_revision(connection, target, action):
    snapshot = {
        field: value.isoformat() if isinstance(value := getattr(target, field), datetime) else value
        for field in _REQUEST_SNAPSHOT_FIELDS
    }
    connection.execute(DataSubjectRequestRevision.__table__.insert().values(
        request_id=target.id,
        actor_id=(getattr(target, "_revision_actor_id", None)
                  if action == "updated" else target.solicitado_por_id),
        action=action,
        recorded_at=_now(),
        snapshot=json.dumps(snapshot, ensure_ascii=False),
    ))


@event.listens_for(DataSubjectRequest, "after_insert")
def _request_created(_mapper, connection, target):
    _record_request_revision(connection, target, "created")


@event.listens_for(DataSubjectRequest, "after_update")
def _request_updated(_mapper, connection, target):
    _record_request_revision(connection, target, "updated")


@event.listens_for(DataSubjectRequestRevision, "before_update")
@event.listens_for(DataSubjectRequestRevision, "before_delete")
def _reject_request_revision_mutation(_mapper, _connection, _target):
    raise RuntimeError("O histórico de solicitações é append-only.")


class PrivacyIncident(db.Model):
    """Registro interno de incidentes, preservado para investigação e prestação de contas."""
    __tablename__ = "privacy_incidents"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=True, index=True)
    reported_by_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    title = db.Column(EncryptedText, nullable=False)
    status = db.Column(db.String(30), nullable=False, default="open")
    severity = db.Column(db.String(20), nullable=False, default="medium")
    detected_at = db.Column(db.DateTime, nullable=False, default=_now)
    known_at = db.Column(db.DateTime)
    reported_at = db.Column(db.DateTime, nullable=False, default=_now)
    anpd_notified_at = db.Column(db.DateTime)
    subjects_notified_at = db.Column(db.DateTime)
    notification_reference = db.Column(EncryptedText)
    closed_at = db.Column(db.DateTime)
    description = db.Column(EncryptedText, nullable=False)
    affected_data = db.Column(EncryptedText)
    affected_subjects = db.Column(db.Integer)
    notification_decision = db.Column(EncryptedText)
    corrective_actions = db.Column(EncryptedText)
    created_at = db.Column(db.DateTime, nullable=False, default=_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=_now, onupdate=_now)


class PrivacyIncidentRevision(db.Model):
    """Versão preservada de cada registro/alteração de incidente."""
    __tablename__ = "privacy_incident_revisions"

    id = db.Column(db.Integer, primary_key=True)
    incident_id = db.Column(db.Integer, db.ForeignKey("privacy_incidents.id"), nullable=False, index=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    action = db.Column(db.String(20), nullable=False)
    recorded_at = db.Column(db.DateTime, nullable=False, default=_now)
    snapshot = db.Column(EncryptedText, nullable=False)

    @property
    def details(self):
        return json.loads(self.snapshot)


@event.listens_for(PrivacyIncidentRevision, "before_update")
@event.listens_for(PrivacyIncidentRevision, "before_delete")
def _reject_incident_revision_mutation(_mapper, _connection, _target):
    raise RuntimeError("O histórico de incidentes é append-only.")
