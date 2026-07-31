"""Criacao, envio e consumo seguro de recuperacao de senha."""
import hashlib
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from flask import current_app, url_for

from app.extensions import db
from app.models import PasswordResetToken, Usuario, registrar


def _now():
    return datetime.now(timezone.utc)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def criar_token(usuario: Usuario, ip: str) -> tuple[PasswordResetToken, str]:
    now = _now()
    PasswordResetToken.query.filter_by(usuario_id=usuario.id, usado_em=None).update({"usado_em": now})
    raw_token = secrets.token_urlsafe(32)
    token = PasswordResetToken(
        usuario_id=usuario.id,
        token_hash=_hash(raw_token),
        expira_em=now + timedelta(minutes=current_app.config["PASSWORD_RESET_TTL_MINUTES"]),
        solicitado_ip_hash=_hash(ip or "unknown"),
    )
    db.session.add(token)
    registrar("senha", "usuarios", "Recuperação de senha solicitada.", usuario_id=usuario.id, usuario_nome=usuario.nome)
    return token, raw_token


def localizar_token(raw_token: str) -> PasswordResetToken | None:
    if not raw_token or len(raw_token) > 200:
        return None
    token = PasswordResetToken.query.filter_by(token_hash=_hash(raw_token), usado_em=None).first()
    if not token:
        return None
    expires = token.expira_em
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return token if expires > _now() and token.usuario.ativo else None


def consumir_token(token: PasswordResetToken, nova_senha: str):
    now = _now()
    token.usuario.set_senha(nova_senha)
    token.usuario.security_version += 1
    from app.services.user_sessions import revoke_all
    revoke_all(token.usuario_id, "redefinicao de senha")
    PasswordResetToken.query.filter_by(usuario_id=token.usuario_id, usado_em=None).update({"usado_em": now})
    registrar("senha", "usuarios", "Senha redefinida por token de recuperacao.", usuario_id=token.usuario_id, usuario_nome=token.usuario.nome)


def enviar_link(usuario: Usuario, raw_token: str):
    link = url_for("auth.redefinir_senha", token=raw_token, _external=True)
    if current_app.testing:
        current_app.extensions.setdefault("password_reset_outbox", []).append({"to": usuario.email, "link": link})
        return
    host = current_app.config.get("SMTP_HOST")
    sender = current_app.config.get("MAIL_FROM")
    if not host or not sender:
        current_app.logger.error("Recuperação solicitada, mas SMTP_HOST/MAIL_FROM não estão configurados.")
        return
    message = EmailMessage()
    message["Subject"] = "Redefinicao de senha - Zokyo"
    message["From"] = sender
    message["To"] = usuario.email
    message.set_content(f"Use o link abaixo para redefinir sua senha. Ele expira em breve e pode ser usado uma vez.\n\n{link}")
    port = current_app.config.get("SMTP_PORT", 587)
    with smtplib.SMTP(host, port, timeout=15) as smtp:
        if current_app.config.get("SMTP_STARTTLS", True):
            smtp.starttls()
        username = current_app.config.get("SMTP_USERNAME")
        if username:
            smtp.login(username, current_app.config.get("SMTP_PASSWORD", ""))
        smtp.send_message(message)
