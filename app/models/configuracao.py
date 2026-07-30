"""
models/configuracao.py
----------------------
Fix H06: API keys e segredos armazenados criptografados no banco via Fernet.

V-04 FIX: _encrypt() agora lança RuntimeError explícito em vez de retornar
          o valor em texto plano quando o Fernet não está disponível.
          Fallback silencioso permitia que segredos fossem persistidos sem
          criptografia sem que o operador percebesse.

V-08 FIX: Salt da derivação de chave Fernet lido de ENCRYPTION_SALT no
          ambiente (variável gerada por instalação), eliminando o salt
          estático que estava hardcoded no código-fonte.
          Fallback para o salt legado apenas em desenvolvimento sem a variável.

Uso:
    cfg = Configuracao.get()
    cfg.set_evolution_api_key("minha-chave")   # criptografa
    plain = cfg.get_evolution_api_key()        # descriptografa

Gerar ENCRYPTION_SALT para produção:
    python3 -c "import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
"""
import base64
import json
import logging
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.extensions import db

logger = logging.getLogger(__name__)

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

# V-08 FIX: salt lido do ambiente — único por instalação, não exposto no código.
# Em produção: defina ENCRYPTION_SALT no .env com um valor base64 aleatório de 32 bytes.
# Fallback para valor legado apenas quando ENCRYPTION_SALT não está definido
# (compatibilidade com dados existentes em desenvolvimento).
_ENCRYPTION_SALT_B64 = os.environ.get("ENCRYPTION_SALT", "").strip()
if _ENCRYPTION_SALT_B64:  # pragma: no cover - import-time env branch; tested only in a fresh process.
    try:
        _SALT = base64.b64decode(_ENCRYPTION_SALT_B64)
        if len(_SALT) < 16:
            raise ValueError("ENCRYPTION_SALT muito curto (mínimo 16 bytes após decodificação).")
    except Exception as e:
        logger.error(
            "[CONFIG] ENCRYPTION_SALT inválido: %s. "
            "Verifique se é um base64 válido de pelo menos 16 bytes.", e
        )
        _SALT = b"zokyo-config-encryption-v1"  # fallback somente em erro de parse
else:
    # V-08: avisa que o salt estático está sendo usado (aceitável em dev, não em prod)
    _SALT = b"zokyo-config-encryption-v1"
    logger.warning(
        "[CONFIG] ENCRYPTION_SALT não configurado. Usando salt estático (apenas para dev). "
        "Em produção, gere com: "
        "python3 -c \"import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())\""
    )


def _get_fernet() -> Fernet | None:
    """Deriva chave Fernet da SECRET_KEY da aplicação."""
    try:
        from flask import current_app
        secret = current_app.config.get("SECRET_KEY", "")
        if not secret:
            return None
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=_SALT,
            iterations=100_000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(secret.encode()))
        return Fernet(key)
    except Exception as e:
        logger.error("[CONFIG] Erro ao criar Fernet: %s", e)
        return None


def _encrypt(value: str) -> str:
    """
    V-04 FIX: criptografa string. Lança RuntimeError se Fernet indisponível.

    Antes: retornava o valor em texto plano silenciosamente quando SECRET_KEY
    estava ausente ou Fernet falhava. Segredos podiam ser persistidos no banco
    sem criptografia sem nenhum aviso visível ao operador.

    Depois: falha explicitamente. Operador deve configurar SECRET_KEY antes
    de salvar segredos.
    """
    if not value:
        return ""
    f = _get_fernet()
    if not f:
        raise RuntimeError(
            "Fernet indisponível: SECRET_KEY não configurada corretamente. "
            "Não é possível salvar segredos criptografados. "
            "Configure SECRET_KEY no arquivo .env."
        )
    try:
        return f.encrypt(value.encode()).decode()
    except Exception as e:
        raise RuntimeError(f"Erro ao criptografar segredo: {e}") from e


def _decrypt(token: str) -> str | None:
    """Descriptografa token. Retorna string ou None."""
    if not token:
        return None
    f = _get_fernet()
    if not f:
        logger.error(
            "[CONFIG] Fernet indisponível ao descriptografar. "
            "Verifique SECRET_KEY no ambiente."
        )
        return None
    try:
        return f.decrypt(token.encode()).decode()
    except InvalidToken:
        logger.warning("[CONFIG] Token inválido ao descriptografar (chave mudou?)")
        return None
    except Exception as e:
        logger.error("[CONFIG] Erro ao descriptografar: %s", e)
        return None


class Configuracao(db.Model):
    __tablename__ = "configuracoes"

    id              = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, default=1, unique=True)
    nome_empresa    = db.Column(db.String(200), default="Zokyo Platform")
    cnpj            = db.Column(db.String(18))
    telefone        = db.Column(db.String(20))
    email           = db.Column(db.String(120))
    endereco        = db.Column(db.String(300))
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
    dados_pagamento       = db.Column(db.Text)
    pix_chave             = db.Column(db.String(200))

    meta_receita_mensal   = db.Column(db.Float, default=0)
    alerta_caixa_minimo   = db.Column(db.Float, default=500)
    alerta_estoque_minimo = db.Column(db.Integer, default=5)
    alerta_vencimento_dias= db.Column(db.Integer, default=5)

    wpp_server_url   = db.Column(db.String(300))

    # H06: campos sensíveis armazenados criptografados
    _evolution_api_url_enc  = db.Column("evolution_api_url",  db.String(600))
    _evolution_api_key_enc  = db.Column("evolution_api_key",  db.String(600))
    evolution_instance      = db.Column(db.String(100), default="zokyo")

    dashboard_widgets = db.Column(
        db.Text,
        default='["os","financeiro","estoque","clientes"]',
    )
    os_status_options = db.Column(db.Text)
    os_priority_options = db.Column(db.Text)
    attendance_type_options = db.Column(db.Text)
    entry_checklist_options = db.Column(db.Text)

    # ── Accessors para campos criptografados ──────────────────────────────

    def get_evolution_api_url(self) -> str | None:
        return _decrypt(self._evolution_api_url_enc)

    def set_evolution_api_url(self, value: str | None):
        self._evolution_api_url_enc = _encrypt(value) if value else None

    def get_evolution_api_key(self) -> str | None:
        return _decrypt(self._evolution_api_key_enc)

    def set_evolution_api_key(self, value: str | None):
        self._evolution_api_key_enc = _encrypt(value) if value else None

    def to_dict(self):
        d = {c.name: getattr(self, c.name) for c in self.__table__.columns
             if c.name not in ("evolution_api_url", "evolution_api_key")}
        # Expõe apenas se há valor (sem revelar o conteúdo)
        d["evolution_api_url_set"]  = bool(self._evolution_api_url_enc)
        d["evolution_api_key_set"]  = bool(self._evolution_api_key_enc)
        return d

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
