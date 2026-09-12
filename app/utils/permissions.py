"""Central RBAC and ABAC authorization helpers."""
from functools import wraps
from typing import Any

from flask import abort, current_app, g, jsonify, redirect, request, session, url_for
from sqlalchemy import select

from app.extensions import db

READ_METHODS = {"GET", "HEAD", "OPTIONS"}
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

BASE_PERMISSIONS = {
    "sistema.access",
    "dashboard.view",
    "ajuda.view",
    "pesquisa.view",
    "clientes.view",
    "clientes.manage",
    "os.view",
    "os.manage",
    "estoque.view",
    "estoque.manage",
    "estoque.delete",
    "servicos.view",
    "servicos.manage",
    "fornecedores.view",
    "fornecedores.manage",
    "financeiro.view",
    "financeiro.manage",
    "cobrancas.view",
    "cobrancas.manage",
    "vendas.view",
    "vendas.manage",
    "coletas.view",
    "coletas.manage",
    "agenda.view",
    "bancada.view",
    "checklists.view",
    "checklists.manage",
    "compras_pecas.view",
    "compras_pecas.manage",
    "garantias.view",
    "garantias.manage",
    "arquivos.view",
    "arquivos.manage",
    "laudos.view",
    "laudos.create",
    "laudos.edit_draft",
    "laudos.finalize",
    "laudos.download_pdf",
    "laudos.revise",
    "laudos.cancel",
    "laudos.admin_templates",
    "relatorios.view",
    "relatorios.export",
    "relatorios.manage",
    "usuarios.manage",
    "configuracoes.manage",
    "logs.view",
    "auditoria.manage",
    "importacao.manage",
    "privacidade.manage",
    "mensagens.manage",
    "backup.manage",
    "produtividade.view",
    "portal_cliente.manage",
    "platform.manage",
}

ROLE_PERMISSIONS = {
    "admin": {"*"},
    "operacional": {
        "sistema.access", "dashboard.view", "ajuda.view", "pesquisa.view",
        "clientes.view", "clientes.manage",
        "os.view", "os.manage",
        "estoque.view", "estoque.manage",
        "servicos.view", "servicos.manage",
        "fornecedores.view",
        "coletas.view", "coletas.manage",
        "agenda.view", "bancada.view",
        "checklists.view", "checklists.manage",
        "compras_pecas.view", "compras_pecas.manage",
        "garantias.view", "garantias.manage",
        "arquivos.view", "arquivos.manage",
        "laudos.view", "laudos.create", "laudos.edit_draft",
        "laudos.finalize", "laudos.download_pdf", "laudos.revise",
        "produtividade.view",
        "portal_cliente.manage",
    },
    "cadastro": {
        "sistema.access", "dashboard.view", "ajuda.view", "pesquisa.view",
        "clientes.view", "clientes.manage",
        "os.view", "estoque.view", "servicos.view", "fornecedores.view",
        "coletas.view", "agenda.view", "checklists.view",
        "garantias.view", "arquivos.view",
        "laudos.view", "laudos.download_pdf",
    },
    "consulta": {
        "sistema.access", "dashboard.view", "ajuda.view", "pesquisa.view",
        "clientes.view", "os.view", "estoque.view", "servicos.view",
        "fornecedores.view", "coletas.view", "agenda.view", "checklists.view",
        "garantias.view", "arquivos.view",
        "laudos.view", "laudos.download_pdf",
    },
    "financeiro": {
        "sistema.access", "dashboard.view", "ajuda.view", "pesquisa.view",
        "clientes.view", "os.view", "estoque.view", "servicos.view",
        "fornecedores.view",
        "financeiro.view", "financeiro.manage",
        "cobrancas.view", "cobrancas.manage",
        "vendas.view", "vendas.manage",
        "relatorios.view", "relatorios.export", "relatorios.manage",
        "portal_cliente.manage",
    },
}

KNOWN_PERMISSIONS = frozenset(BASE_PERMISSIONS)

PUBLIC_ENDPOINTS = {
    "auth.login_page",
    "auth.login_post",
    "auth.primeiro_acesso_page",
    "auth.primeiro_acesso_post",
    "auth.recuperar_senha",
    "auth.redefinir_senha",
    "auth.api_v1_login",
    "auth.two_factor_challenge",
    "usuarios.aceitar_convite",
    "health.api_v1_index",
    "health.healthz",
    "health.readyz",
    "health.metrics",
    "pages.service_worker",
    "pages.pwa_start",
    "portal.publico",
    "portal.publico_pdf",
    "laudos.verificar",
    "client_api.auth",
    "client_api.consulta_os_publica",
    "client_api.index",
    "client_api.os_collection",
    "client_api.os_detail",
    "client_api.compras",
    "client_api.cobrancas",
    "platform.sandbox_webhook",
    "platform.asaas_webhook",
    "static",
}

PUBLIC_ENDPOINT_PREFIXES = ("static",)

PREFIX_POLICIES: tuple[tuple[str, str, str], ...] = (
    ("clientes.", "clientes.view", "clientes.manage"),
    ("fornecedores.", "fornecedores.view", "fornecedores.manage"),
    ("pecas.", "estoque.view", "estoque.manage"),
    ("defeitos.", "servicos.view", "servicos.manage"),
    ("transacoes.", "financeiro.view", "financeiro.manage"),
    ("usuarios.", "usuarios.manage", "usuarios.manage"),
    ("configuracoes.", "configuracoes.manage", "configuracoes.manage"),
    ("logs.", "logs.view", "logs.view"),
    ("importacao.", "importacao.manage", "importacao.manage"),
    ("privacy.", "privacidade.manage", "privacidade.manage"),
    ("relatorios.", "relatorios.view", "relatorios.manage"),
    ("platform.", "platform.manage", "platform.manage"),
    ("portal.", "portal_cliente.manage", "portal_cliente.manage"),
    ("os.", "os.view", "os.manage"),
)

PAGE_POLICIES: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (("pages.cliente", "pages.clientes"), "clientes.view", "clientes.manage"),
    (("pages.fornecedor", "pages.fornecedores"), "fornecedores.view", "fornecedores.manage"),
    (("pages.estoque", "pages.produtos", "pages.peca_"), "estoque.view", "estoque.manage"),
    (("pages.servicos",), "servicos.view", "servicos.manage"),
    (("pages.financeiro", "pages.transacao_"), "financeiro.view", "financeiro.manage"),
    (("pages.cobrancas", "pages.api_cobranca_"), "cobrancas.view", "cobrancas.manage"),
    (("pages.vendas",), "vendas.view", "vendas.manage"),
    (("pages.coleta",), "coletas.view", "coletas.manage"),
    (("pages.agenda",), "agenda.view", "agenda.view"),
    (("pages.bancada",), "bancada.view", "bancada.view"),
    (("pages.checklist",), "checklists.view", "checklists.manage"),
    (("pages.compras_pecas",), "compras_pecas.view", "compras_pecas.manage"),
    (("pages.garantias",), "garantias.view", "garantias.manage"),
    (("pages.arquivos",), "arquivos.view", "arquivos.manage"),
    (("pages.os_",), "os.view", "os.manage"),
    (("pages.produtividade",), "produtividade.view", "produtividade.view"),
    (("pages.zokyo_pesquisar",), "pesquisa.view", "pesquisa.view"),
    (("pages.zokyo_backup",), "backup.manage", "backup.manage"),
    (("pages.zokyo_auditoria",), "logs.view", "auditoria.manage"),
    (("pages.zokyo_configurar", "pages.zokyo_emitente", "pages.zokyo_atualizacao"), "configuracoes.manage", "configuracoes.manage"),
    (("pages.zokyo_emails", "pages.zokyo_excluir_email"), "mensagens.manage", "mensagens.manage"),
    (("pages.zokyo_permissoes",), "usuarios.manage", "usuarios.manage"),
    (("pages.zokyo_mine",), "portal_cliente.manage", "portal_cliente.manage"),
)

EXACT_POLICIES: dict[str, tuple[str, str]] = {
    "pages.dashboard": ("dashboard.view", "dashboard.view"),
    "pages.zokyo_home": ("dashboard.view", "dashboard.view"),
    "pages.ajuda": ("ajuda.view", "ajuda.view"),
    "pages.ajuda_concluir": ("ajuda.view", "ajuda.view"),
    "pages.zokyo_alterar_senha": ("sistema.access", "sistema.access"),
    "pages.zokyo_minha_conta": ("sistema.access", "sistema.access"),
    "pages.zokyo_upload_user_image": ("sistema.access", "sistema.access"),
    "pages.zokyo_logout": ("sistema.access", "sistema.access"),
    "auth.logout": ("sistema.access", "sistema.access"),
    "auth.api_v1_regen_token": ("sistema.access", "sistema.access"),
    "auth.sessions_page": ("sistema.access", "sistema.access"),
    "auth.session_revoke": ("sistema.access", "sistema.access"),
    "auth.sessions_revoke_others": ("sistema.access", "sistema.access"),
    "auth.two_factor_setup": ("sistema.access", "sistema.access"),
    "auth.two_factor_disable": ("sistema.access", "sistema.access"),
    "configuracoes.emitente_v1": ("sistema.access", "sistema.access"),
    "configuracoes.whatsapp_status": ("configuracoes.manage", "configuracoes.manage"),
    "configuracoes.whatsapp_teste": ("configuracoes.manage", "configuracoes.manage"),
    "health.operations_status": ("logs.view", "logs.view"),
}

LAUDOS_EXACT_POLICIES = {
    "laudos.baixar_pdf": "laudos.download_pdf",
    "laudos.comprovante_cancelamento": "laudos.download_pdf",
    "laudos.cancelar": "laudos.cancel",
    "laudos.criar": "laudos.create",
    "laudos.duplicar": "laudos.create",
    "laudos.finalizar": "laudos.finalize",
    "laudos.revisao": "laudos.revise",
    "laudos.salvar": "laudos.edit_draft",
    "laudos.upload_foto": "laudos.edit_draft",
    "laudos.excluir_foto": "laudos.edit_draft",
    "laudos.reordenar_fotos_rota": "laudos.edit_draft",
    "laudos.templates": "laudos.admin_templates",
    "laudos.template_toggle": "laudos.admin_templates",
    "laudos.exportar_csv": "laudos.view",
}

GLOBAL_PLATFORM_ENDPOINTS = {
    "auth.logout",
    "platform.index",
    "platform.create_organization",
    "platform.update_organization",
    "platform.create_tenant_admin",
    "platform.reset_tenant_admin_password",
    "platform.sync_dns",
    "platform.create_plan",
    "platform.assign_subscription",
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

    if session.get("usuario_id"):
        return db.session.get(Usuario, session.get("usuario_id"))

    if request.headers.get("Authorization", "").lower().startswith("bearer "):
        from app.utils.auth import authenticate_bearer_session

        return authenticate_bearer_session()
    return None


def is_public_endpoint(endpoint: str | None) -> bool:
    endpoint = endpoint or ""
    if not endpoint:
        return True
    return endpoint in PUBLIC_ENDPOINTS or any(endpoint.startswith(prefix) for prefix in PUBLIC_ENDPOINT_PREFIXES)


def _choose_policy(read_permission: str, write_permission: str, method: str | None) -> str:
    return write_permission if (method or request.method) in WRITE_METHODS else read_permission


def permission_for_endpoint(endpoint: str | None, method: str | None = None, path: str | None = None) -> str | None:
    endpoint = endpoint or ""
    if is_public_endpoint(endpoint):
        return None

    if endpoint in LAUDOS_EXACT_POLICIES:
        return LAUDOS_EXACT_POLICIES[endpoint]
    if endpoint.startswith("laudos."):
        return "laudos.view"

    if endpoint in EXACT_POLICIES:
        read_permission, write_permission = EXACT_POLICIES[endpoint]
        return _choose_policy(read_permission, write_permission, method)

    for prefix, read_permission, write_permission in PREFIX_POLICIES:
        if endpoint.startswith(prefix):
            return _choose_policy(read_permission, write_permission, method)

    if endpoint.startswith("pages."):
        for prefixes, read_permission, write_permission in PAGE_POLICIES:
            if any(endpoint.startswith(prefix) for prefix in prefixes):
                return _choose_policy(read_permission, write_permission, method)
        return "sistema.access"

    if (path or request.path or "").startswith("/api/"):
        return "sistema.access"
    return "sistema.access"


def user_can_access_org(user: Any, organization_id: Any) -> bool:
    if not user or organization_id is None:
        return False
    try:
        return int(user.organization_id) == int(organization_id)
    except (TypeError, ValueError):
        return False


def same_organization(user: Any, resource: Any) -> bool:
    organization_id = getattr(resource, "organization_id", None)
    if organization_id is None:
        return True
    return user_can_access_org(user, organization_id)


def _model_name_for_resource(endpoint: str, arg_name: str) -> str | None:
    explicit = {
        "client_id": "Cliente",
        "cliente_id": "Cliente",
        "os_id": "OrdemServico",
        "ordem_id": "OrdemServico",
        "peca_id": "Peca",
        "produto_id": "Peca",
        "fornecedor_id": "Fornecedor",
        "transacao_id": "Transacao",
        "usuario_id": "Usuario",
        "notification_id": "Notification",
        "report_id": "SavedReport",
    }
    if arg_name in explicit:
        return explicit[arg_name]
    if arg_name != "id":
        return None
    rules = (
        (("pages.os_", "os."), "OrdemServico"),
        (("pages.cliente", "clientes."), "Cliente"),
        (("pages.fornecedor", "fornecedores."), "Fornecedor"),
        (("pages.estoque", "pages.produtos", "pages.peca_", "pecas."), "Peca"),
        (("pages.financeiro", "pages.transacao_", "pages.cobrancas", "pages.vendas", "transacoes."), "Transacao"),
        (("laudos.",), "LaudoTecnico"),
        (("privacy.",), "Cliente"),
    )
    for prefixes, model_name in rules:
        if any(endpoint.startswith(prefix) for prefix in prefixes):
            return model_name
    return None


def _get_model(model_name: str):
    import app.models as models

    return getattr(models, model_name, None)


def _resource_visible_to_user(user, endpoint: str, arg_name: str, value: Any) -> bool:
    model_name = _model_name_for_resource(endpoint, arg_name)
    if not model_name:
        return True
    model = _get_model(model_name)
    if model is None or not hasattr(model, "id"):
        return True
    obj = db.session.execute(
        select(model).execution_options(include_all_tenants=True).where(model.id == value)
    ).scalar_one_or_none()
    if obj is None:
        return True
    return same_organization(user, obj)


def abac_allows_request(user) -> bool:
    endpoint = request.endpoint or ""
    if getattr(user, "is_platform_admin", False) and not getattr(user, "organization_id", None):
        return endpoint in GLOBAL_PLATFORM_ENDPOINTS
    if not user or not getattr(user, "organization_id", None):
        return False
    g.organization_id = user.organization_id
    view_args = request.view_args or {}

    if "organization_id" in view_args and not user_can_access_org(user, view_args["organization_id"]):
        return False

    for arg_name, value in view_args.items():
        if not _resource_visible_to_user(user, endpoint, arg_name, value):
            return False
    return True


def _wants_json_response() -> bool:
    if (request.path or "").startswith("/api/"):
        return True
    best = request.accept_mimetypes.best_match(["application/json", "text/html"])
    return best == "application/json" and request.accept_mimetypes[best] > request.accept_mimetypes["text/html"]


def _deny(status_code: int, message: str, permission: str | None = None):
    if _wants_json_response():
        payload = {"success": False, "erro": message}
        if permission:
            payload["permissao"] = permission
        return jsonify(payload), status_code
    if status_code == 401:
        return redirect(url_for("auth.login_page"))
    abort(status_code)


def _is_platform_admin_without_tenant(user) -> bool:
    return bool(getattr(user, "is_platform_admin", False) and not getattr(user, "organization_id", None))


def _is_platform_endpoint(endpoint: str | None) -> bool:
    return (endpoint or "").startswith("platform.")


def enforce_request_authorization():
    if request.method == "OPTIONS":
        return None
    endpoint = request.endpoint or ""
    if is_public_endpoint(endpoint):
        return None

    user = _current_user()
    if not user:
        if endpoint.startswith("laudos."):
            return _deny(403, "Acesso negado")
        return _deny(401, "Autenticacao necessaria")

    permission = permission_for_endpoint(endpoint, request.method, request.path)
    if permission and not has_permission(user, permission):
        current_app.logger.info(
            "RBAC negou acesso: usuario=%s endpoint=%s permissao=%s",
            getattr(user, "id", None),
            endpoint,
            permission,
        )
        return _deny(403, "Acesso negado", permission)

    if not abac_allows_request(user):
        if _is_platform_admin_without_tenant(user) and not _is_platform_endpoint(endpoint) and not _wants_json_response():
            return redirect(url_for("platform.index"))
        current_app.logger.warning(
            "ABAC negou acesso cross-tenant: usuario=%s endpoint=%s view_args=%s",
            getattr(user, "id", None),
            endpoint,
            request.view_args or {},
        )
        return _deny(404, "Recurso nao encontrado")

    return None


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
            if not abac_allows_request(user):
                if api or request.path.startswith("/api/"):
                    return jsonify({"erro": "Recurso nao encontrado"}), 404
                abort(404)
            return func(*args, **kwargs)
        return wrapped
    return decorator
