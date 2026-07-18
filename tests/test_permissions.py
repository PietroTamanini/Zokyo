from types import SimpleNamespace

from flask import Blueprint, Flask

from app.utils.permissions import has_permission, permission_required, permissions_for


def user(role, extra=None, denied=None, active=True):
    return SimpleNamespace(
        nivel=role,
        permissoes_extra=extra,
        permissoes_negadas=denied,
        ativo=active,
    )


def test_matriz_overrides_e_usuario_inativo():
    operacional = user("operacional")
    assert has_permission(operacional, "laudos.finalize")
    assert not has_permission(operacional, "laudos.cancel")

    custom = user("consulta", extra=["laudos.create"], denied=["laudos.download_pdf"])
    assert has_permission(custom, "laudos.create")
    assert not has_permission(custom, "laudos.download_pdf")
    assert permissions_for(user("admin", denied=["usuarios.manage"])) >= {"usuarios.manage"}
    assert permissions_for(user("consulta", active=False)) == set()


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
