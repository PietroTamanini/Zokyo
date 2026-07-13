"""Templates versionados com substituicao restrita de variaveis."""
import re

from app.models import MessageTemplate

VARIABLE_RE = re.compile(r"\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}", re.I)
ALLOWED_VARIABLES = {"cliente", "os_id", "status", "equipamento", "total", "empresa"}


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
