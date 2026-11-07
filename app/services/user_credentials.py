"""Envio de credenciais iniciais sem registrar senhas em logs."""

from flask import url_for

from app.utils.email_delivery import send_email


def send_initial_credentials(user, organization_name: str, password: str) -> dict:
    """Envia a senha inicial uma única vez; a senha nunca entra na auditoria."""
    login_url = url_for("auth.login_page", _external=True)
    body = (
        f"Olá, {user.nome}!\n\n"
        f"Sua conta da assistência {organization_name} foi criada no Zokyo.\n\n"
        f"Use este e-mail para entrar: {user.email}\n"
        f"Senha temporária: {password}\n\n"
        f"Acesse: {login_url}\n\n"
        "Por segurança, não compartilhe esta mensagem e altere a senha depois do primeiro acesso."
    )
    return send_email(user.email, "Acesso inicial ao Zokyo", body)
