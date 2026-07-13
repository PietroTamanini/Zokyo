"""
app/config/branding.py — Configuração central de identidade visual.

Para trocar o nome do sistema no futuro, edite APENAS este arquivo.
Todos os templates e rotas consomem daqui via context_processor.

Trocar para white-label por tenant: veja MULTI_TENANT_READY abaixo.
"""

# ── Identidade principal ──────────────────────────────────────────────────
APP_NAME          = "Zokyo"
APP_SHORT_NAME    = "Zokyo"
APP_TAGLINE       = "Plataforma de Gestão"
APP_DESCRIPTION   = "Sistema de gestão para assistências técnicas"
APP_COMPANY       = "Zokyo"
APP_VERSION       = "2.0"

# ── Textos de interface ───────────────────────────────────────────────────
APP_LOGIN_TITLE   = f"Bem-vindo ao {APP_NAME}"
APP_LOGIN_SUBTITLE = "Plataforma de Gestão · Assistência Técnica"
APP_COPYRIGHT     = f"© {APP_NAME}"

# ── Cores primárias (CSS fallback — tema real em theme.css) ───────────────
PRIMARY_COLOR     = "#4f6ef7"
PRIMARY_DARK      = "#3a56d4"
ACCENT_COLOR      = "#7c3aed"

# ── Assets ────────────────────────────────────────────────────────────────
# Troque estes caminhos para customizar logo/favicon por tenant
LOGO_PATH         = "img/zokyo-logo.svg"     # relativo a static/
FAVICON_PATH      = "img/zokyo-favicon.svg"  # relativo a static/

# ── Localização padrão ────────────────────────────────────────────────────
DEFAULT_CITY      = "Joinville"
DEFAULT_UF        = "SC"
DEFAULT_COUNTRY   = "Brasil"

# ── Email remetente padrão ────────────────────────────────────────────────
MAIL_SENDER_NAME  = APP_NAME
MAIL_SENDER_ADDR  = "noreply@zokyo.app"

# ── Infra / deploy ────────────────────────────────────────────────────────
APP_DOMAIN        = "zokyo.app"
DB_NAME           = "zokyo"
DB_USER           = "zokyo"
SESSION_COOKIE_NAME = "zokyo_session"

# ── Multi-tenant (preparado, não ativo) ──────────────────────────────────
# Para ativar white-label por tenant, sobrescreva este dict com
# os valores lidos do banco (Configuracao) via get_branding_for_tenant(tenant_id).
MULTI_TENANT_READY = True

TENANT_DEFAULTS = {
    "name":         APP_NAME,
    "tagline":      APP_TAGLINE,
    "logo":         LOGO_PATH,
    "favicon":      FAVICON_PATH,
    "primary_color": PRIMARY_COLOR,
    "accent_color": ACCENT_COLOR,
}


def get_branding(cfg=None) -> dict:
    """
    Retorna o dict de branding a ser injetado nos templates.

    Se `cfg` (instância de Configuracao) for fornecido, sobrescreve
    os campos com os valores configurados pelo tenant.
    """
    brand = {
        "APP_NAME":        APP_NAME,
        "APP_SHORT_NAME":  APP_SHORT_NAME,
        "APP_TAGLINE":     APP_TAGLINE,
        "APP_DESCRIPTION": APP_DESCRIPTION,
        "APP_COMPANY":     APP_COMPANY,
        "APP_VERSION":     APP_VERSION,
        "APP_LOGIN_TITLE": APP_LOGIN_TITLE,
        "APP_COPYRIGHT":   APP_COPYRIGHT,
        "APP_DOMAIN":      APP_DOMAIN,
        "PRIMARY_COLOR":   PRIMARY_COLOR,
        "ACCENT_COLOR":    ACCENT_COLOR,
        "LOGO_PATH":       LOGO_PATH,
        "FAVICON_PATH":    FAVICON_PATH,
    }

    # Sobrescreve com configurações do tenant (se houver)
    if cfg:
        if getattr(cfg, "nome_empresa", None):
            brand["APP_NAME"]       = cfg.nome_empresa
            brand["APP_SHORT_NAME"] = cfg.nome_empresa
            brand["APP_COMPANY"]    = cfg.nome_empresa
        if getattr(cfg, "primary_color", None):
            brand["PRIMARY_COLOR"] = cfg.primary_color
        if getattr(cfg, "accent_color", None):
            brand["ACCENT_COLOR"] = cfg.accent_color

    return brand
