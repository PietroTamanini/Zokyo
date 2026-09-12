"""Autorizacao e credenciais temporarias do admin global."""

import os
import secrets
import string
from functools import wraps

from flask import abort, g, redirect, session, url_for

from app.extensions import db
from app.models import Usuario


def temporary_password() -> str:
    alphabet = string.ascii_letters + string.digits
    return "Zk!" + "".join(secrets.choice(alphabet) for _ in range(13)) + "9"


def platform_admin_emails() -> set[str]:
    return {item.strip().lower() for item in os.environ.get("PLATFORM_ADMIN_EMAILS", "").split(",") if item.strip()}


def can_manage_platform(user) -> bool:
    return bool(
        user and user.ativo and user.nivel == "admin"
        and (user.is_platform_admin or user.email.lower() in platform_admin_emails())
    )


def global_admin_required(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        user = getattr(g, "current_user", None)
        if user is None and session.get("usuario_id"):
            user = db.session.get(Usuario, session.get("usuario_id"))
        if not user:
            return redirect(url_for("auth.login_page"))
        if not can_manage_platform(user):
            abort(403)
        return function(*args, **kwargs)

    return wrapped
