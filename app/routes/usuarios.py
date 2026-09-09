"""routes/usuarios.py — CRUD de usuários.

Segurança:
  - Sanitização de todos os inputs
  - Validação de e-mail (RFC robusta)
  - Política de senha forte (validar_senha_forte)
  - Mass Assignment: whitelist explícita
  - Impede remoção do próprio usuário
"""
from datetime import datetime, timezone

from flask import Blueprint, flash, g, jsonify, redirect, render_template, request, session, url_for

from app.extensions import db
from app.models import Organization, Usuario, registrar
from app.models.usuario import PERFIS
from app.services.billing import assert_limit, assert_write_allowed
from app.services.user_invites import create_invite, find_valid_invite
from app.utils.auth import api_login_required, nivel_required, page_nivel_required, validar_senha_forte
from app.utils.permissions import KNOWN_PERMISSIONS
from app.utils.request_data import get_request_data
from app.utils.sanitizers import sanitize_email, sanitize_text
from app.utils.validators import validar_email

usuarios_bp = Blueprint("usuarios", __name__)


def _organization_id():
    if getattr(g, "organization_id", None):
        return g.organization_id
    usuario = getattr(g, "current_user", None)
    if usuario:
        return usuario.organization_id
    usuario = db.session.get(Usuario, session.get("usuario_id"))
    return usuario.organization_id if usuario else -1


def _permission_list(value):
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError("Permissões devem ser enviadas como lista.")
    values = sorted(set(value))
    invalid = [item for item in values if item not in KNOWN_PERMISSIONS]
    if invalid:
        raise ValueError("Permissões inválidas: " + ", ".join(invalid))
    return values


@usuarios_bp.route("/usuarios")
@page_nivel_required("admin")
def usuarios_page():
    lista = Usuario.query.filter_by(organization_id=_organization_id()).order_by(Usuario.nome).all()
    return render_template("pages/usuarios.html", active="usuarios",
                           usuarios=lista, perfis=PERFIS,
                           permissoes=sorted(KNOWN_PERMISSIONS))


@usuarios_bp.route("/api/permissoes", methods=["GET"])
@usuarios_bp.route("/api/v1/permissoes", methods=["GET"])
@nivel_required("admin")
def listar_permissoes():
    return jsonify(sorted(KNOWN_PERMISSIONS))


@usuarios_bp.route("/api/usuarios", methods=["GET"])
@usuarios_bp.route("/api/v1/usuarios", methods=["GET"])
@nivel_required("admin")
def listar():
    return jsonify([u.to_dict() for u in Usuario.query.filter_by(organization_id=_organization_id()).all()])


@usuarios_bp.route("/api/usuarios/<int:id>", methods=["GET"])
@usuarios_bp.route("/api/v1/usuarios/<int:id>", methods=["GET"])
@nivel_required("admin")
def obter(id):
    return jsonify(Usuario.query.filter_by(id=id, organization_id=_organization_id()).first_or_404().to_dict())


@usuarios_bp.route("/api/usuarios", methods=["POST"])
@usuarios_bp.route("/api/v1/usuarios", methods=["POST"])
@nivel_required("admin")
def criar():
    data, _ = get_request_data()
    organization_id = _organization_id()
    try:
        assert_write_allowed(organization_id)
        assert_limit(organization_id, "max_users", Usuario.query.filter_by(organization_id=organization_id).count())
    except PermissionError as exc:
        return jsonify({"success": False, "erro": str(exc)}), 403

    # Campos obrigatórios
    for c in ("nome", "email", "senha", "nivel"):
        if not data.get(c):
            return jsonify({"success": False, "erro": f"{c} é obrigatório"}), 400

    # Sanitização
    nome  = sanitize_text(data["nome"], max_length=120)
    email = sanitize_email(data["email"])
    nivel = sanitize_text(data.get("nivel", ""), max_length=20)

    if len(nome) < 2:
        return jsonify({"success": False, "erro": "Nome deve ter pelo menos 2 caracteres"}), 400

    if not validar_email(email):
        return jsonify({"success": False, "erro": "E-mail inválido"}), 400

    if nivel not in PERFIS:
        return jsonify({"success": False,
                        "erro": f"Perfil inválido. Válidos: {', '.join(PERFIS)}"}), 400

    # Unicidade do e-mail
    if Usuario.query.filter_by(email=email).first():
        return jsonify({"success": False, "erro": "E-mail já cadastrado"}), 409

    # Política de senha forte
    erros_senha = validar_senha_forte(data["senha"])
    if erros_senha:
        return jsonify({"success": False, "erro": erros_senha[0], "errors": erros_senha}), 400

    u = Usuario(nome=nome, email=email, nivel=nivel, organization_id=organization_id)
    try:
        u.permissoes_extra = _permission_list(data.get("permissoes_extra"))
        u.permissoes_negadas = _permission_list(data.get("permissoes_negadas"))
    except ValueError as exc:
        return jsonify({"success": False, "erro": str(exc)}), 400
    u.set_senha(data["senha"])
    db.session.add(u)
    registrar("criacao", "usuarios", f"Usuário criado: {nome}")
    db.session.commit()
    return jsonify(u.to_dict()), 201


@usuarios_bp.route("/api/usuarios/convites", methods=["POST"])
@nivel_required("admin")
def criar_convite():
    data, _ = get_request_data()
    email = sanitize_email(data.get("email", ""))
    role = sanitize_text(data.get("nivel", ""), max_length=20)
    if not validar_email(email) or role not in PERFIS:
        return jsonify({"erro": "E-mail ou perfil inválido"}), 400
    if Usuario.query.execution_options(include_all_tenants=True).filter_by(email=email).first():
        return jsonify({"erro": "E-mail já cadastrado"}), 409
    organization_id = _organization_id()
    try:
        assert_write_allowed(organization_id)
        assert_limit(organization_id, "max_users", Usuario.query.filter_by(organization_id=organization_id).count())
    except PermissionError as exc:
        return jsonify({"erro": str(exc)}), 403
    invite, raw_token = create_invite(organization_id, email, role, session["usuario_id"])
    db.session.commit()
    link = url_for("usuarios.aceitar_convite", token=raw_token, _external=True)
    from app.utils.email_delivery import send_email
    delivery = send_email(
        email, "Convite para acessar o Zokyo",
        f"Você foi convidado para acessar o sistema. O link expira em 48 horas e pode ser usado uma vez.\n\n{link}",
    )
    registrar("convite", "usuarios", f"Convite criado para {email}")
    db.session.commit()
    return jsonify({"id": invite.id, "link": link, "delivery": delivery}), 201


@usuarios_bp.route("/convite/<token>", methods=["GET", "POST"])
def aceitar_convite(token):
    invite = find_valid_invite(token)
    if not invite:
        return render_template("pages/invite_accept.html", invalid=True), 410
    organization = db.session.execute(
        db.select(Organization).where(Organization.id == invite.organization_id).execution_options(include_all_tenants=True)
    ).scalar_one()
    if request.method == "POST":
        nome = sanitize_text(request.form.get("nome", ""), max_length=120)
        password = request.form.get("senha", "")
        errors = validar_senha_forte(password)
        if len(nome) < 2 or errors:
            for error in errors or ["Nome deve ter pelo menos 2 caracteres."]:
                flash(error, "error")
            return render_template("pages/invite_accept.html", invite=invite, organization=organization)
        if Usuario.query.execution_options(include_all_tenants=True).filter_by(email=invite.email).first():
            return render_template("pages/invite_accept.html", invalid=True), 409
        user = Usuario(
            organization_id=invite.organization_id, nome=nome, email=invite.email,
            nivel=invite.role, ativo=True, onboarding_completed=False,
        )
        user.set_senha(password)
        db.session.add(user)
        invite.used_at = datetime.now(timezone.utc)
        db.session.commit()
        flash("Conta criada. Entre com sua senha.", "success")
        return redirect(url_for("auth.login_page"))
    return render_template("pages/invite_accept.html", invite=invite, organization=organization)


@usuarios_bp.route("/api/usuarios/<int:id>", methods=["PUT"])
@usuarios_bp.route("/api/v1/usuarios/<int:id>", methods=["PUT"])
@nivel_required("admin")
def atualizar(id):
    u = Usuario.query.filter_by(id=id, organization_id=_organization_id()).first_or_404()
    data, _ = get_request_data()

    if "nome" in data:
        nome = sanitize_text(data["nome"], max_length=120)
        if len(nome) < 2:
            return jsonify({"success": False, "erro": "Nome deve ter pelo menos 2 caracteres"}), 400
        u.nome = nome

    if "email" in data:
        email = sanitize_email(data["email"])
        if not validar_email(email):
            return jsonify({"success": False, "erro": "E-mail inválido"}), 400
        # Verifica duplicidade (exceto o próprio usuário)
        existente = Usuario.query.filter_by(email=email).first()
        if existente and existente.id != u.id:
            return jsonify({"success": False, "erro": "E-mail já em uso"}), 409
        u.email = email

    if "nivel" in data:
        nivel = sanitize_text(data["nivel"], max_length=20)
        if nivel not in PERFIS:
            return jsonify({"success": False,
                            "erro": f"Perfil inválido. Válidos: {', '.join(PERFIS)}"}), 400
        u.nivel = nivel

    if "ativo" in data:
        val = data["ativo"]
        u.ativo = val if isinstance(val, bool) else str(val).lower() not in ("0", "false")

    if data.get("senha"):
        erros_senha = validar_senha_forte(data["senha"])
        if erros_senha:
            return jsonify({"success": False,
                            "erro": erros_senha[0], "errors": erros_senha}), 400
        u.set_senha(data["senha"])
        u.security_version += 1

    try:
        if "permissoes_extra" in data:
            u.permissoes_extra = _permission_list(data["permissoes_extra"])
        if "permissoes_negadas" in data:
            u.permissoes_negadas = _permission_list(data["permissoes_negadas"])
    except ValueError as exc:
        return jsonify({"success": False, "erro": str(exc)}), 400

    registrar("edicao", "usuarios", f"Usuário editado: {u.nome}")
    db.session.commit()
    return jsonify(u.to_dict())


@usuarios_bp.route("/api/usuarios/<int:id>/revogar-sessoes", methods=["POST"])
@nivel_required("admin")
def revogar_sessoes(id):
    u = Usuario.query.filter_by(id=id, organization_id=_organization_id()).first_or_404()
    from app.services.user_sessions import revoke_all
    revoke_all(u.id, "revogacao administrativa")
    u.security_version += 1
    registrar("seguranca", "usuarios", f"Sessões revogadas: {u.nome}")
    db.session.commit()
    if u.id == session["usuario_id"]:
        session.clear()
    return jsonify({"success": True, "mensagem": "Todas as sessoes foram encerradas"})


@usuarios_bp.route("/api/usuarios/<int:id>", methods=["DELETE"])
@usuarios_bp.route("/api/v1/usuarios/<int:id>", methods=["DELETE"])
@nivel_required("admin")
def deletar(id):
    u = Usuario.query.filter_by(id=id, organization_id=_organization_id()).first_or_404()
    if u.id == session["usuario_id"]:
        return jsonify({"success": False,
                        "erro": "Não é possível remover seu próprio usuário"}), 400
    registrar("exclusao", "usuarios", f"Usuário removido: {u.nome}")
    db.session.delete(u)
    db.session.commit()
    return jsonify({"success": True, "mensagem": "Usuário removido"})


@usuarios_bp.route("/api/usuarios/alterar-senha", methods=["POST"])
@usuarios_bp.route("/api/v1/usuarios/alterar-senha", methods=["POST"])
@api_login_required
def alterar_senha():
    data, _ = get_request_data()
    u = db.session.get(Usuario, session["usuario_id"])

    if not u.check_senha(data.get("senha_atual", "")):
        return jsonify({"success": False, "erro": "Senha atual incorreta"}), 401

    nova_senha = data.get("nova_senha", "")
    erros_senha = validar_senha_forte(nova_senha)
    if erros_senha:
        return jsonify({"success": False,
                        "erro": erros_senha[0], "errors": erros_senha}), 400

    # Garante que a nova senha é diferente da atual
    if u.check_senha(nova_senha):
        return jsonify({"success": False,
                        "erro": "A nova senha deve ser diferente da senha atual"}), 400

    u.set_senha(nova_senha)
    u.security_version += 1
    db.session.commit()
    session.clear()
    return jsonify({"success": True, "mensagem": "Senha alterada; entre novamente"})


@usuarios_bp.route("/api/v1/conta", methods=["GET"])
@api_login_required
def conta_v1():
    usuario = db.session.get(Usuario, session["usuario_id"])
    if not usuario:
        return jsonify({"erro": "Usuário não encontrado"}), 404
    return jsonify(usuario.to_dict())
