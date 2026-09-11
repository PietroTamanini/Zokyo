from datetime import datetime, timezone

from sqlalchemy import event
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.utils.blind_index import blind_index

PERFIS = ("admin","operacional","cadastro","consulta","financeiro")
PERFIS_LABELS = {
    "admin":       "Administrador",
    "operacional": "Operacional",
    "cadastro":    "Cadastro",
    "consulta":    "Consulta",
    "financeiro":  "Financeiro",
}
# Backwards compat
NIVEIS = PERFIS

class Usuario(db.Model):
    __tablename__ = "usuarios"
    __table_args__ = (
        db.Index("ix_usuarios_org_active_nome", "organization_id", "ativo", "nome"),
        db.Index("ix_usuarios_org_nivel_active", "organization_id", "nivel", "ativo"),
    )

    id         = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, default=1, index=True)
    nome       = db.Column(db.String(120), nullable=False)
    email      = db.Column(db.String(120), nullable=False, unique=True)
    email_bidx = db.Column(db.String(64), index=True)
    senha_hash = db.Column(db.String(256), nullable=False)
    nivel      = db.Column(db.String(20), nullable=False, default="operacional")
    ativo      = db.Column(db.Boolean, default=True)
    criado_em  = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    totp_secret_encrypted = db.Column(db.Text)
    totp_enabled = db.Column(db.Boolean, default=False, nullable=False)
    recovery_codes_hash = db.Column(db.JSON)
    permissoes_extra = db.Column(db.JSON)
    permissoes_negadas = db.Column(db.JSON)
    is_platform_admin = db.Column(db.Boolean, default=False, nullable=False)
    onboarding_completed = db.Column(db.Boolean, default=True, nullable=False)
    security_version = db.Column(db.Integer, default=1, nullable=False)
    organization = db.relationship("Organization", backref=db.backref("usuarios", lazy=True))

    def set_senha(self, senha):
        self.senha_hash = generate_password_hash(senha)
    def check_senha(self, senha):
        return check_password_hash(self.senha_hash, senha)
    def to_dict(self):
        return {"id":self.id,"nome":self.nome,"email":self.email,
                "nivel":self.nivel,"ativo":self.ativo,
                "criado_em":self.criado_em.isoformat(),
                "totp_enabled": self.totp_enabled,
                "is_platform_admin": self.is_platform_admin,
                "permissoes_extra": self.permissoes_extra or [],
                "permissoes_negadas": self.permissoes_negadas or []}

    def refresh_blind_indexes(self):
        self.email_bidx = blind_index(self.email, "email")


@event.listens_for(Usuario, "before_insert")
@event.listens_for(Usuario, "before_update")
def _usuario_blind_indexes(_mapper, _connection, target):
    target.refresh_blind_indexes()
