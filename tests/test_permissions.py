from types import SimpleNamespace

from app.utils.permissions import has_permission, permissions_for


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
