"""routes/clientes.py — CRUD de clientes (API JSON).

Segurança:
  - Sanitização de todos os inputs
  - Validação de e-mail, CPF, telefone, CEP, UF
  - Mass Assignment com whitelist explícita
  - Bloqueia exclusão se há OS ativas vinculadas
  - LIKE injection: escapa %, _
"""
from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models import Cliente, OrdemServico, registrar
from app.utils.auth import api_login_required as login_required, nivel_required
from app.utils.validators import validar_email, validar_cpf, validar_telefone, validar_cep, validar_uf
from app.utils.sanitizers import (
    sanitize_text, sanitize_email, sanitize_cpf, sanitize_phone, sanitize_cep
)
from app.utils.request_data import get_request_data

clientes_bp = Blueprint("clientes", __name__)


def _escape_like(q: str) -> str:
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _validar_e_sanitizar(data: dict) -> tuple[dict, list[str]]:
    erros = []
    d = {}

    if "nome" in data:
        nome = sanitize_text(data["nome"], max_length=200)
        if not nome or len(nome) < 2:
            erros.append("Nome deve ter pelo menos 2 caracteres.")
        d["nome"] = nome

    if "cpf" in data:
        cpf_raw = sanitize_cpf(data["cpf"])
        if cpf_raw and not validar_cpf(cpf_raw):
            erros.append("CPF inválido.")
        d["cpf"] = cpf_raw or None

    if "telefone" in data:
        tel_raw = sanitize_phone(data["telefone"])
        if tel_raw and not validar_telefone(tel_raw):
            erros.append("Telefone inválido. Use DDD + número (ex: 47 99999-9999).")
        d["telefone"] = tel_raw or None

    if "email" in data:
        email_clean = sanitize_email(data["email"])
        if email_clean and not validar_email(email_clean):
            erros.append("E-mail inválido.")
        d["email"] = email_clean or None

    if "cep" in data:
        cep_raw = sanitize_cep(data["cep"])
        if cep_raw and not validar_cep(cep_raw):
            erros.append("CEP inválido.")
        d["cep"] = cep_raw or None

    if "endereco" in data:
        d["endereco"] = sanitize_text(data["endereco"], max_length=300) or None

    if "cidade" in data:
        d["cidade"] = sanitize_text(data["cidade"], max_length=100) or None

    if "uf" in data:
        uf = sanitize_text(data["uf"], max_length=2).upper()
        if uf and not validar_uf(uf):
            erros.append("UF inválida.")
        d["uf"] = uf or None

    if "ativo" in data:
        val = data["ativo"]
        d["ativo"] = val if isinstance(val, bool) else str(val).lower() not in ("0", "false", "no", "")

    return d, erros


@clientes_bp.route("/api/clientes", methods=["GET"])
@login_required
def listar():
    from app.utils.sanitizers import sanitize_search_query
    q     = sanitize_search_query(request.args.get("q", ""), max_length=100)
    query = Cliente.query
    if q:
        qe = _escape_like(q)
        query = query.filter(Cliente.nome.ilike(f"%{qe}%"))
    return jsonify([c.to_dict() for c in query.order_by(Cliente.nome).all()])


@clientes_bp.route("/api/clientes/<int:id>", methods=["GET"])
@login_required
def obter(id):
    return jsonify(db.get_or_404(Cliente, id).to_dict())


@clientes_bp.route("/api/clientes", methods=["POST"])
@login_required
def criar():
    data, _ = get_request_data()
    if not data.get("nome"):
        return jsonify({"success": False, "erro": "Nome é obrigatório"}), 400

    d, erros = _validar_e_sanitizar(data)
    if erros:
        return jsonify({"success": False, "erro": erros[0], "errors": erros}), 400

    c = Cliente(**d)
    db.session.add(c)
    registrar("criacao", "clientes", f"Cliente criado: {d['nome']}")
    db.session.commit()
    return jsonify(c.to_dict()), 201


@clientes_bp.route("/api/clientes/<int:id>", methods=["PUT"])
@login_required
def atualizar(id):
    c       = db.get_or_404(Cliente, id)
    data, _ = get_request_data()

    if not data:
        return jsonify({"success": False, "erro": "Nenhum dado enviado"}), 400

    d, erros = _validar_e_sanitizar(data)
    if erros:
        return jsonify({"success": False, "erro": erros[0], "errors": erros}), 400

    for campo, valor in d.items():
        setattr(c, campo, valor)

    registrar("edicao", "clientes", f"Cliente atualizado: {c.nome}")
    db.session.commit()
    return jsonify(c.to_dict())


@clientes_bp.route("/api/clientes/<int:id>", methods=["DELETE"])
@nivel_required("admin")
def deletar(id):
    c = db.get_or_404(Cliente, id)
    os_ativas = OrdemServico.query.filter_by(
        cliente_id=c.id
    ).filter(OrdemServico.deletado_em.is_(None)).count()
    if os_ativas > 0:
        return jsonify({
            "success": False,
            "erro": f"Cliente possui {os_ativas} OS ativa(s). "
                    "Encerre ou cancele as OS antes de remover o cliente."
        }), 400
    registrar("exclusao", "clientes", f"Cliente removido: {c.nome}")
    db.session.delete(c)
    db.session.commit()
    return jsonify({"success": True, "mensagem": "Cliente removido"})
