"""Matriz central e overrides persistidos de autorizacao."""
from functools import wraps

from flask import abort, jsonify, redirect, request, session, url_for

from app.extensions import db

ROLE_PERMISSIONS = {
    "admin": {"*"},
    "operacional": {
        "clientes.view", "clientes.manage", "os.view", "os.manage",
        "estoque.view", "estoque.manage", "fornecedores.view",
        "laudos.view", "laudos.create", "laudos.edit_draft",
        "laudos.finalize", "laudos.download_pdf", "laudos.revise",
    },
    "cadastro": {"clientes.view", "clientes.manage", "os.view", "estoque.view", "fornecedores.view", "laudos.view", "laudos.download_pdf"},
    "consulta": {"clientes.view", "os.view", "estoque.view", "fornecedores.view", "laudos.view", "laudos.download_pdf"},
    "financeiro": {"financeiro.view", "financeiro.manage", "clientes.view", "os.view", "relatorios.view", "relatorios.export"},
}

KNOWN_PERMISSIONS = frozenset().union(*(items - {"*"} for items in ROLE_PERMISSIONS.values())) | {
    "usuarios.manage", "configuracoes.manage", "logs.view", "importacao.manage",
    "laudos.cancel", "laudos.admin_templates", "fornecedores.manage", "estoque.delete",
    "relatorios.view", "relatorios.export",
}


def permissions_for(user) -> set[str]:
    if not user or not user.ativo:
        return set()
    base = set(ROLE_PERMISSIONS.get(user.nivel, set()))
    if "*" in base:
        return set(KNOWN_PERMISSIONS) | {"*"}
    extras = {item for item in (user.permissoes_extra or []) if item in KNOWN_PERMISSIONS}
    denied = {item for item in (user.permissoes_negadas or []) if item in KNOWN_PERMISSIONS}
    return (base | extras) - denied


def has_permission(user, permission: str) -> bool:
    permissions = permissions_for(user)
    return "*" in permissions or permission in permissions


def _current_user():
    from app.models import Usuario
    return db.session.get(Usuario, session.get("usuario_id")) if session.get("usuario_id") else None


def permission_required(permission: str, api: bool = True):
    def decorator(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            user = _current_user()
            if not user:
                if api:
                    return jsonify({"erro": "Autenticacao necessaria"}), 401
                return redirect(url_for("auth.login_page"))
            if not has_permission(user, permission):
                if api or request.path.startswith("/api/"):
                    return jsonify({"erro": "Acesso negado", "permissao": permission}), 403
                abort(403)
            return func(*args, **kwargs)
        return wrapped
    return decorator
