"""routes/usuarios.py — CRUD de usuários.

Segurança:
  - Sanitização de todos os inputs
  - Validação de e-mail (RFC robusta)
  - Política de senha forte (validar_senha_forte)
  - Mass Assignment: whitelist explícita
  - Impede remoção do próprio usuário
"""
from flask import (Blueprint, request, jsonify, session,
                   render_template)
from app.extensions import db
from app.models import Usuario, registrar
from app.models.usuario import PERFIS
from app.utils.auth import (
    api_login_required, nivel_required, page_nivel_required, validar_senha_forte
)
from app.utils.validators import validar_email
from app.utils.sanitizers import sanitize_text, sanitize_email
from app.utils.request_data import get_request_data

usuarios_bp = Blueprint("usuarios", __name__)


@usuarios_bp.route("/usuarios")
@page_nivel_required("admin")
def usuarios_page():
    lista = Usuario.query.order_by(Usuario.nome).all()
    return render_template("pages/usuarios.html", active="usuarios",
                           usuarios=lista, perfis=PERFIS)


@usuarios_bp.route("/api/usuarios", methods=["GET"])
@nivel_required("admin")
def listar():
    return jsonify([u.to_dict() for u in Usuario.query.all()])


@usuarios_bp.route("/api/usuarios/<int:id>", methods=["GET"])
@nivel_required("admin")
def obter(id):
    return jsonify(db.get_or_404(Usuario, id).to_dict())


@usuarios_bp.route("/api/usuarios", methods=["POST"])
@nivel_required("admin")
def criar():
    data, _ = get_request_data()

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

    u = Usuario(nome=nome, email=email, nivel=nivel)
    u.set_senha(data["senha"])
    db.session.add(u)
    registrar("criacao", "usuarios", f"Usuário criado: {nome}")
    db.session.commit()
    return jsonify(u.to_dict()), 201


@usuarios_bp.route("/api/usuarios/<int:id>", methods=["PUT"])
@nivel_required("admin")
def atualizar(id):
    u       = db.get_or_404(Usuario, id)
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

    registrar("edicao", "usuarios", f"Usuário editado: {u.nome}")
    db.session.commit()
    return jsonify(u.to_dict())


@usuarios_bp.route("/api/usuarios/<int:id>", methods=["DELETE"])
@nivel_required("admin")
def deletar(id):
    u = db.get_or_404(Usuario, id)
    if u.id == session["usuario_id"]:
        return jsonify({"success": False,
                        "erro": "Não é possível remover seu próprio usuário"}), 400
    registrar("exclusao", "usuarios", f"Usuário removido: {u.nome}")
    db.session.delete(u)
    db.session.commit()
    return jsonify({"success": True, "mensagem": "Usuário removido"})


@usuarios_bp.route("/api/usuarios/alterar-senha", methods=["POST"])
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
    db.session.commit()
    return jsonify({"success": True, "mensagem": "Senha alterada com sucesso"})
