"""Entrega SMTP sem expor credenciais ou detalhes internos ao usuário."""
import smtplib
from email.message import EmailMessage

from flask import current_app


def send_email(recipient: str, subject: str, body: str) -> dict:
    if current_app.testing:
        current_app.extensions.setdefault("email_outbox", []).append({"to": recipient, "subject": subject, "body": body})
        return {"sucesso": True, "modo": "testing"}
    host = current_app.config.get("SMTP_HOST")
    sender = current_app.config.get("MAIL_FROM")
    if not host or not sender:
        return {"sucesso": False, "modo": "simulacao", "aviso": "SMTP não configurado"}
    message = EmailMessage()
    message["Subject"] = subject[:200]
    message["From"] = sender
    message["To"] = recipient
    message.set_content(body)
    try:
        with smtplib.SMTP(host, current_app.config.get("SMTP_PORT", 587), timeout=15) as smtp:
            if current_app.config.get("SMTP_STARTTLS", True):
                smtp.starttls()
            username = current_app.config.get("SMTP_USERNAME")
            if username:
                smtp.login(username, current_app.config.get("SMTP_PASSWORD", ""))
            smtp.send_message(message)
        return {"sucesso": True, "modo": "smtp"}
    except (OSError, smtplib.SMTPException) as exc:
        current_app.logger.warning("Falha de entrega SMTP: %s", exc)
        return {"sucesso": False, "modo": "fallback", "erro": "Falha temporária de e-mail"}
