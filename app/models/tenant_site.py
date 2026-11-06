"""models/tenant_site.py - Configuracao de site publico por tenant (organizacao)."""
from datetime import datetime, timezone

from app.extensions import db


def _now():
    return datetime.now(timezone.utc)


class TenantSite(db.Model):
    """Configuracao do site publico institucional de uma empresa."""

    __tablename__ = "tenant_sites"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer,
        db.ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    site_enabled = db.Column(db.Boolean, nullable=False, default=True)
    # Publicacao de arquivos estaticos enviados pela empresa.
    site_mode = db.Column(db.String(20), nullable=False, default="builder")
    site_bundle_version = db.Column(db.String(64), nullable=True)
    site_bundle_entrypoint = db.Column(db.String(255), nullable=False, default="index.html")
    site_bundle_uploaded_at = db.Column(db.DateTime, nullable=True)
    site_bundle_file_count = db.Column(db.Integer, nullable=True)
    site_bundle_size_bytes = db.Column(db.BigInteger, nullable=True)
    # Identidade visual / hero
    site_title = db.Column(db.String(200), nullable=True)
    site_subtitle = db.Column(db.String(300), nullable=True)
    site_description = db.Column(db.Text, nullable=True)
    primary_color = db.Column(db.String(7), nullable=True)
    accent_color = db.Column(db.String(7), nullable=True)
    logo_url = db.Column(db.String(600), nullable=True)
    favicon_url = db.Column(db.String(600), nullable=True)
    cover_image = db.Column(db.String(600), nullable=True)
    secondary_color = db.Column(db.String(7), nullable=True)
    # Conteudo institucional / comercial
    site_name = db.Column(db.String(200), nullable=True)
    tagline = db.Column(db.String(300), nullable=True)
    story = db.Column(db.Text, nullable=True)
    description = db.Column(db.Text, nullable=True)
    services_json = db.Column(db.Text, nullable=True)
    socials_json = db.Column(db.Text, nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    whatsapp = db.Column(db.String(20), nullable=True)
    address = db.Column(db.Text, nullable=True)
    hours = db.Column(db.Text, nullable=True)
    diferencias_json = db.Column(db.Text, nullable=True)
    # SEO
    seo_title = db.Column(db.String(200), nullable=True)
    seo_description = db.Column(db.String(500), nullable=True)
    seo_image = db.Column(db.String(600), nullable=True)
    # Dominio customizado do site publico
    custom_domain = db.Column(
        db.String(255), nullable=True, unique=True, index=True
    )
    custom_domain_validated = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=_now)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=_now, onupdate=_now
    )

    organization = db.relationship(
        "Organization",
        backref=db.backref("tenant_site", uselist=False, cascade="all, delete-orphan"),
        foreign_keys=[organization_id],
    )

    def __repr__(self):
        return f"<TenantSite organization_id={self.organization_id} enabled={self.site_enabled}>"
