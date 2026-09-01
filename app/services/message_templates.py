"""Templates versionados com substituicao restrita de variaveis."""
import re

from app.models import MessageTemplate

VARIABLE_RE = re.compile(r"\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}", re.I)
ALLOWED_VARIABLES = {"cliente", "os_id", "status", "equipamento", "total", "empresa"}

DEFAULT_TEMPLATES = (
    ("os_status_recepcao", "whatsapp", "", "Olá, {{cliente}}! A OS #{{os_id}} foi aberta para {{equipamento}} na {{empresa}}."),
    ("os_status_aguardando_aprovacao", "whatsapp", "", "Olá, {{cliente}}! O orçamento da OS #{{os_id}} está disponível. Total: {{total}}."),
    ("os_status_em_reparo", "whatsapp", "", "Olá, {{cliente}}! O orçamento da OS #{{os_id}} foi aprovado e o reparo está em andamento."),
    ("os_status_pronto", "whatsapp", "", "Olá, {{cliente}}! A OS #{{os_id}} está pronta para retirada na {{empresa}}."),
    ("os_status_entregue", "whatsapp", "", "Olá, {{cliente}}! A OS #{{os_id}} foi entregue. Guarde esta mensagem para referência da garantia."),
    ("payment_due", "email", "Cobrança da OS #{{os_id}}", "Olá, {{cliente}}. Há um pagamento de {{total}} referente à OS #{{os_id}}."),
    ("warranty_return", "whatsapp", "", "Olá, {{cliente}}! Registramos o retorno em garantia da OS #{{os_id}} na {{empresa}}."),
)


def seed_default_templates(organization_id: int) -> int:
    """Instala templates editáveis sem substituir versões criadas pelo cliente."""
    from app.extensions import db

    created = 0
    for event_type, channel, subject, body in DEFAULT_TEMPLATES:
        exists = MessageTemplate.query.execution_options(include_all_tenants=True).filter_by(
            organization_id=organization_id, event_type=event_type, channel=channel,
        ).first()
        if not exists:
            db.session.add(MessageTemplate(
                organization_id=organization_id, event_type=event_type, channel=channel,
                version=1, subject=subject or None, body=body, active=True,
            ))
            created += 1
    return created


def render_text(text: str, context: dict) -> str:
    def replace(match):
        name = match.group(1)
        return str(context.get(name, "")) if name in ALLOWED_VARIABLES else ""
    return VARIABLE_RE.sub(replace, text or "")


def active_template(event_type, channel):
    return MessageTemplate.query.filter_by(event_type=event_type, channel=channel, active=True).order_by(
        MessageTemplate.version.desc(),
    ).first()


def render_template(event_type, channel, context, default_subject="", default_body=""):
    template = active_template(event_type, channel)
    if not template:
        return default_subject, default_body
    return render_text(template.subject or "", context), render_text(template.body, context)
