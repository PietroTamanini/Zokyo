from datetime import datetime, timezone

from app.extensions import db


class OrderSignature(db.Model):
    __tablename__ = "order_signatures"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    order_id = db.Column(db.Integer, db.ForeignKey("ordens_servico.id"), nullable=False, index=True)
    captured_by_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    signer_name = db.Column(db.String(120), nullable=False)
    storage_key = db.Column(db.String(500), nullable=False, unique=True)
    mime_type = db.Column(db.String(40), nullable=False, default="image/png")
    size_bytes = db.Column(db.Integer, nullable=False)
    sha256 = db.Column(db.String(64), nullable=False)
    ip_address = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    revoked_at = db.Column(db.DateTime)

    order = db.relationship("OrdemServico", backref=db.backref("signatures", lazy=True))
    captured_by = db.relationship("Usuario")
