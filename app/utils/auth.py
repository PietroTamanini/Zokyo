"""
utils/auth.py — Decorators de autenticação, controle de acesso e validação de senha.

Fix L04: política de senha forte com verificação de senhas comuns.
"""
import hashlib
import re
import time
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import flash, g, jsonify, redirect, request, session, url_for

# Top-50 senhas mais comuns — expandir conforme necessário
_SENHAS_COMUNS = frozenset({
    "12345678", "123456789", "1234567890", "password", "senha123",
    "qwerty123", "abc12345", "iloveyou", "admin123", "welcome1",
    "monkey12", "dragon12", "master12", "letmein1", "superman",
    "batman12", "charlie1", "donald12", "passw0rd", "p@ssword",
    "senha1234", "zokyo123", "123mudar", "mudar123", "teste123",
    "temp1234", "change12", "default1", "system12", "root1234",
})


def validar_senha_forte(senha: str) -> list[str]:
    """
    L04: Valida política de senha forte.
    Retorna lista de erros (vazia = senha aceita).
    """
    erros = []

    if len(senha) < 8:
        erros.append("Mínimo 8 caracteres.")
    if not re.search(r"[A-Z]", senha):
        erros.append("Pelo menos 1 letra maiúscula.")
    if not re.search(r"[a-z]", senha):
        erros.append("Pelo menos 1 letra minúscula.")
    if not re.search(r"\d", senha):
        erros.append("Pelo menos 1 número.")
    if not re.search(r"[!@#$%^&*()\-_=+\[\]{};:'\",.<>?/\\|`~]", senha):
        erros.append("Pelo menos 1 caractere especial.")
    if senha.lower() in _SENHAS_COMUNS:
        erros.append("Senha muito comum. Escolha uma senha mais única.")

    return erros


# ── Decorators ────────────────────────────────────────────────────────────────

def _bearer_token():
    auth = request.headers.get("Authorization", "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def authenticate_bearer_session():
    raw_token = _bearer_token()
    if not raw_token:
        return None
    from app.extensions import db
    from app.models import UserSession

    record = (
        UserSession.query.execution_options(include_all_tenants=True)
        .filter_by(token_hash=_hash_token(raw_token))
        .first()
    )
    if not record or not record.is_active or not record.user or not record.user.ativo:
        return None
    user = record.user
    if not user.organization or not user.organization.ativo:
        return None
    session.permanent = True
    session["usuario_id"] = user.id
    session["nivel"] = user.nivel
    session["perfil"] = user.nivel
    session["usuario_nome"] = user.nome
    session["security_version"] = user.security_version
    session["session_token"] = raw_token
    session["_last_active"] = time.time()
    g.organization_id = user.organization_id
    now = datetime.now(timezone.utc)
    last_seen = record.last_seen_at.replace(tzinfo=timezone.utc)
    if now - last_seen >= timedelta(minutes=5):
        record.last_seen_at = now
        db.session.commit()
    return user


def _ensure_api_auth():
    if "usuario_id" in session:
        return True
    return authenticate_bearer_session() is not None


def api_login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _ensure_api_auth():
            return jsonify({"erro": "Autenticação necessária"}), 401
        return f(*args, **kwargs)
    return decorated


login_required = api_login_required


def nivel_required(*niveis):
    """Para rotas de API — retorna JSON 403."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not _ensure_api_auth():
                return jsonify({"erro": "Autenticação necessária"}), 401
            if session.get("nivel") not in niveis:
                return jsonify({"erro": "Acesso negado"}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator


def page_nivel_required(*niveis):
    """Para rotas HTML — redireciona com flash."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if "usuario_id" not in session:
                return redirect(url_for("auth.login_page"))
            if session.get("nivel") not in niveis:
                flash("Acesso negado: permissão insuficiente.", "error")
                return redirect(url_for("pages.dashboard"))
            return f(*args, **kwargs)
        return decorated
    return decorator
