from types import SimpleNamespace

from flask import Blueprint, Flask

from app import create_app
from app.extensions import db
from app.models import Cliente, OrdemServico, Organization, Usuario
from app.utils.permissions import (
    KNOWN_PERMISSIONS,
    has_permission,
    is_public_endpoint,
    permission_for_endpoint,
    permission_required,
    permissions_for,
)


def user(role, extra=None, denied=None, active=True):
    return SimpleNamespace(
        nivel=role,
        permissoes_extra=extra,
        permissoes_negadas=denied,
        ativo=active,
        organization_id=1,
    )


def make_policy_app():
    app = create_app("development")
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:", ALLOW_LEGACY_SESSIONS=True)
    with app.app_context():
        db.drop_all()
        db.create_all()
        org1 = Organization(id=1, nome="Org 1", slug="org-1")
        org2 = Organization(id=2, nome="Org 2", slug="org-2")
        admin = Usuario(nome="Admin", email="admin@rbac.test", nivel="admin", ativo=True, organization_id=1)
        consulta = Usuario(nome="Consulta", email="consulta@rbac.test", nivel="consulta", ativo=True, organization_id=1)
        intruso = Usuario(nome="Intruso", email="intruso@rbac.test", nivel="admin", ativo=True, organization_id=2)
        for item in (admin, consulta, intruso):
            item.set_senha("Senha!123")
        cliente1 = Cliente(nome="Cliente Um", telefone="4700000000", organization_id=1)
        cliente2 = Cliente(nome="Cliente Dois", telefone="4800000000", organization_id=2)
        db.session.add_all([org1, org2, admin, consulta, intruso, cliente1, cliente2])
        db.session.flush()
        ordem2 = OrdemServico(
            organization_id=2,
            cliente_id=cliente2.id,
            usuario_id=intruso.id,
            tipo_aparelho="Notebook",
            marca="Dell",
            modelo="XPS",
        )
        db.session.add(ordem2)
        db.session.commit()
        return app, {"admin": admin.id, "consulta": consulta.id, "ordem_org2": ordem2.id}


def login(client, user_id, role):
    with client.session_transaction() as session:
        session["usuario_id"] = user_id
        session["nivel"] = role
        session["perfil"] = role
        session["_last_active"] = 9999999999


def test_matriz_overrides_e_usuario_inativo():
    operacional = user("operacional")
    assert has_permission(operacional, "laudos.finalize")
    assert not has_permission(operacional, "laudos.cancel")

    custom = user("consulta", extra=["laudos.create"], denied=["laudos.download_pdf"])
    assert has_permission(custom, "laudos.create")
    assert not has_permission(custom, "laudos.download_pdf")
    assert permissions_for(user("admin", denied=["usuarios.manage"])) >= {"usuarios.manage"}
    assert permissions_for(user("consulta", active=False)) == set()


def test_resolucao_de_politica_cobre_endpoints_principais():
    assert permission_for_endpoint("pages.os_lista", "GET", "/os") == "os.view"
    assert permission_for_endpoint("pages.os_criar", "POST", "/os/adicionar") == "os.manage"
    assert permission_for_endpoint("clientes.listar", "GET", "/api/clientes") == "clientes.view"
    assert permission_for_endpoint("clientes.criar", "POST", "/api/clientes") == "clientes.manage"
    assert permission_for_endpoint("relatorios.ordens_csv", "GET", "/relatorios/ordens.csv") == "relatorios.view"
    assert permission_for_endpoint("laudos.baixar_pdf", "GET", "/laudos/1/pdf") == "laudos.download_pdf"
    assert permission_for_endpoint("auth.login_page", "GET", "/login") is None


def test_toda_rota_nao_publica_tem_permissao_conhecida():
    app = create_app("development")
    for rule in app.url_map.iter_rules():
        if is_public_endpoint(rule.endpoint):
            continue
        for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
            permission = permission_for_endpoint(rule.endpoint, method, rule.rule)
            assert permission in KNOWN_PERMISSIONS, f"{rule.endpoint} {method} {rule.rule} => {permission}"


def test_rbac_global_bloqueia_escrita_sem_permissao():
    app, ids = make_policy_app()
    client = app.test_client()
    login(client, ids["consulta"], "consulta")
    with client.session_transaction() as session:
        session["_csrf_token"] = "rbac"

    assert client.get("/clientes").status_code == 200
    response = client.post("/os/adicionar", data={"_csrf_token": "rbac"})
    assert response.status_code == 403


def test_abac_global_bloqueia_recurso_de_outra_organizacao():
    app, ids = make_policy_app()
    client = app.test_client()
    login(client, ids["admin"], "admin")

    response = client.get(f"/os/{ids['ordem_org2']}")
    assert response.status_code == 404


def test_permission_required_cobre_sem_usuario_e_sem_permissao(monkeypatch):
    app = Flask(__name__)
    app.secret_key = "test"
    auth_bp = Blueprint("auth", __name__)

    @auth_bp.route("/login")
    def login_page():
        return "login"

    @app.route("/api/protegida")
    @permission_required("usuarios.manage")
    def api_protegida():
        return {"ok": True}

    @app.route("/pagina")
    @permission_required("usuarios.manage", api=False)
    def pagina():
        return "ok"

    app.register_blueprint(auth_bp)
    client = app.test_client()
    assert client.get("/api/protegida").status_code == 401
    assert client.get("/pagina").status_code == 302

    limited = user("consulta")
    monkeypatch.setattr("app.utils.permissions._current_user", lambda: limited)
    assert client.get("/api/protegida").status_code == 403
    assert client.get("/pagina").status_code == 403

    allowed = user("consulta", extra=["usuarios.manage"])
    monkeypatch.setattr("app.utils.permissions._current_user", lambda: allowed)
    assert client.get("/api/protegida").status_code == 200
    assert client.get("/pagina").status_code == 200
