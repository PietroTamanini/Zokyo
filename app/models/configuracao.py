"""Configuração principal do tenant."""
import json

from app.extensions import db
from app.utils.field_crypto import EncryptedText

DEFAULT_OS_STATUS_OPTIONS = [
    {"key": "recepcao", "label": "Recepção"},
    {"key": "em_analise", "label": "Em Análise"},
    {"key": "aguardando_aprovacao", "label": "Aprovação"},
    {"key": "em_reparo", "label": "Em Reparo"},
    {"key": "pronto", "label": "Pronto"},
    {"key": "entregue", "label": "Entregue"},
    {"key": "cancelado", "label": "Cancelado"},
]

DEFAULT_OS_PRIORITY_OPTIONS = [
    {"key": "alta", "label": "Alta"},
    {"key": "normal", "label": "Normal"},
    {"key": "baixa", "label": "Baixa"},
    {"key": "urgente", "label": "Urgente"},
    {"key": "critico", "label": "Crítico"},
]

DEFAULT_ATTENDANCE_TYPE_OPTIONS = [
    {"key": "balcao", "label": "Balcão"},
    {"key": "coleta", "label": "Coleta"},
]

DEFAULT_ENTRY_CHECKLIST_OPTIONS = [
    {"key": "liga", "label": "Liga"},
    {"key": "touch", "label": "Touch"},
    {"key": "camera", "label": "Câmera"},
    {"key": "botoes", "label": "Botões"},
    {"key": "wifi_rede", "label": "Wi-Fi / Rede"},
    {"key": "outro", "label": "Outro"},
    {"key": "tela", "label": "Tela"},
    {"key": "audio", "label": "Áudio"},
    {"key": "conectores", "label": "Conectores"},
    {"key": "carregamento", "label": "Carregamento"},
    {"key": "bateria", "label": "Bateria"},
]


def _options_from_json(raw_value, defaults):
    if not raw_value:
        return list(defaults)
    try:
        parsed = json.loads(raw_value)
    except (TypeError, ValueError):
        return list(defaults)
    options = []
    seen = set()
    if not isinstance(parsed, list):
        return list(defaults)
    for item in parsed:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip().lower()
        label = str(item.get("label") or "").strip()
        if not key or not label or key in seen:
            continue
        options.append({"key": key[:50], "label": label[:80]})
        seen.add(key)
    return options or list(defaults)


def _options_to_json(options):
    clean = []
    seen = set()
    for item in options or []:
        key = str(item.get("key") or "").strip().lower()
        label = str(item.get("label") or "").strip()
        if not key or not label or key in seen:
            continue
        clean.append({"key": key[:50], "label": label[:80]})
        seen.add(key)
    return json.dumps(clean, ensure_ascii=False)


def _options_map(options):
    return {item["key"]: item["label"] for item in options}

class Configuracao(db.Model):
    __tablename__ = "configuracoes"

    id              = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, default=1, unique=True)
    nome_empresa    = db.Column(db.String(200), default="Zokyo Platform")
    cnpj            = db.Column(db.String(18))
    telefone        = db.Column(db.String(20))
    email           = db.Column(db.String(120))
    endereco        = db.Column(EncryptedText)
    cidade          = db.Column(db.String(100), default="Joinville")
    uf              = db.Column(db.String(2), default="SC")
    subtitulo_empresa = db.Column(db.String(160), default="Assistência técnica e manutenção")
    logo_url        = db.Column(db.String(600))
    site_url        = db.Column(db.String(300))
    instagram_url   = db.Column(db.String(300))
    whatsapp_publico= db.Column(db.String(20))
    primary_color   = db.Column(db.String(7), default="#2563eb")
    accent_color    = db.Column(db.String(7), default="#6366f1")

    dias_vencimento       = db.Column(db.Integer, default=30)
    dados_pagamento       = db.Column(EncryptedText)
    pix_chave             = db.Column(EncryptedText)

    meta_receita_mensal   = db.Column(db.Float, default=0)
    alerta_caixa_minimo   = db.Column(db.Float, default=500)
    alerta_estoque_minimo = db.Column(db.Integer, default=5)
    alerta_vencimento_dias= db.Column(db.Integer, default=5)

    dashboard_widgets = db.Column(
        db.Text,
        default='["os","financeiro","estoque","clientes"]',
    )
    os_status_options = db.Column(db.Text)
    os_priority_options = db.Column(db.Text)
    attendance_type_options = db.Column(db.Text)
    entry_checklist_options = db.Column(db.Text)

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}

    def get_os_status_options(self):
        return _options_from_json(self.os_status_options, DEFAULT_OS_STATUS_OPTIONS)

    def set_os_status_options(self, options):
        self.os_status_options = _options_to_json(options)

    def get_os_status_map(self):
        return _options_map(self.get_os_status_options())

    def get_os_priority_options(self):
        return _options_from_json(self.os_priority_options, DEFAULT_OS_PRIORITY_OPTIONS)

    def set_os_priority_options(self, options):
        self.os_priority_options = _options_to_json(options)

    def get_os_priority_map(self):
        return _options_map(self.get_os_priority_options())

    def get_attendance_type_options(self):
        return _options_from_json(self.attendance_type_options, DEFAULT_ATTENDANCE_TYPE_OPTIONS)

    def set_attendance_type_options(self, options):
        self.attendance_type_options = _options_to_json(options)

    def get_attendance_type_map(self):
        return _options_map(self.get_attendance_type_options())

    def get_entry_checklist_options(self):
        return _options_from_json(self.entry_checklist_options, DEFAULT_ENTRY_CHECKLIST_OPTIONS)

    def set_entry_checklist_options(self, options):
        self.entry_checklist_options = _options_to_json(options)

    @classmethod
    def get(cls):
        cfg = cls.query.first()
        if not cfg:
            cfg = cls()
            from app.extensions import db as _db
            _db.session.add(cfg)
            _db.session.flush()
        return cfg
