from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db

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
    id         = db.Column(db.Integer, primary_key=True)
    nome       = db.Column(db.String(120), nullable=False)
    email      = db.Column(db.String(120), nullable=False, unique=True)
    senha_hash = db.Column(db.String(256), nullable=False)
    nivel      = db.Column(db.String(20), nullable=False, default="operacional")
    ativo      = db.Column(db.Boolean, default=True)
    criado_em  = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def set_senha(self, senha):
        self.senha_hash = generate_password_hash(senha)
    def check_senha(self, senha):
        return check_password_hash(self.senha_hash, senha)
    def to_dict(self):
        return {"id":self.id,"nome":self.nome,"email":self.email,
                "nivel":self.nivel,"ativo":self.ativo,
                "criado_em":self.criado_em.isoformat()}
