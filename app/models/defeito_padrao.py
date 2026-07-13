from datetime import datetime, timezone

from app.extensions import db


class DefeitoPadrao(db.Model):
    __tablename__ = "defeitos_padrao"
    id            = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, default=1, index=True)
    tipo_aparelho = db.Column(db.String(100))
    sintoma       = db.Column(db.String(300), nullable=False)
    causa         = db.Column(db.Text)
    solucao       = db.Column(db.Text)
    criado_em     = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {"id":self.id,"tipo_aparelho":self.tipo_aparelho,
                "sintoma":self.sintoma,"causa":self.causa,"solucao":self.solucao}
