"""routes/fornecedores.py — CRUD de fornecedores (API JSON)."""
from flask import Blueprint, jsonify, request

from app.extensions import db
from app.models import Fornecedor, registrar
from app.utils.auth import api_login_required as login_required
from app.utils.auth import nivel_required
from app.utils.request_data import get_request_data
from app.utils.sanitizers import sanitize_cep, sanitize_cnpj, sanitize_email, sanitize_phone, sanitize_text
from app.utils.validators import validar_cep, validar_cnpj, validar_email, validar_telefone

fornecedores_bp = Blueprint("fornecedores", __name__)


def _request_limit(default=100, maximum=500):
    value = request.args.get("limit", default, type=int)
    return max(1, min(value or default, maximum))


def _validar_e_sanitizar(data: dict) -> tuple[dict, list[str]]:
    erros = []
    d = {}

    if "nome" in data:
        nome = sanitize_text(data["nome"], max_length=200)
        if not nome or len(nome) < 2:
            erros.append("Nome deve ter pelo menos 2 caracteres.")
        d["nome"] = nome

    if "cnpj" in data:
        cnpj_raw = sanitize_cnpj(data["cnpj"])
        if cnpj_raw and not validar_cnpj(cnpj_raw):
            erros.append("CNPJ inválido.")
        d["cnpj"] = cnpj_raw or None

    if "telefone" in data:
        tel_raw = sanitize_phone(data["telefone"])
        if tel_raw and not validar_telefone(tel_raw):
            erros.append("Telefone inválido.")
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

    if "ativo" in data:
        val = data["ativo"]
        d["ativo"] = val if isinstance(val, bool) else str(val).lower() not in ("0", "false")

    return d, erros


@fornecedores_bp.route("/api/fornecedores", methods=["GET"])
@login_required
def listar():
    limit = _request_limit()
    return jsonify([f.to_dict() for f in
                    Fornecedor.query.order_by(Fornecedor.nome).limit(limit).all()])


@fornecedores_bp.route("/api/fornecedores/<int:id>", methods=["GET"])
@login_required
def obter(id):
    return jsonify(db.get_or_404(Fornecedor, id).to_dict())


@fornecedores_bp.route("/api/fornecedores", methods=["POST"])
@nivel_required("admin")
def criar():
    data, _ = get_request_data()
    if not data.get("nome"):
        return jsonify({"success": False, "erro": "Nome é obrigatório"}), 400

    d, erros = _validar_e_sanitizar(data)
    if erros:
        return jsonify({"success": False, "erro": erros[0], "errors": erros}), 400

    f = Fornecedor(**d)
    db.session.add(f)
    registrar("criacao", "fornecedores", f"Fornecedor criado: {d['nome']}")
    db.session.commit()
    return jsonify(f.to_dict()), 201


@fornecedores_bp.route("/api/fornecedores/<int:id>", methods=["PUT"])
@nivel_required("admin")
def atualizar(id):
    f       = db.get_or_404(Fornecedor, id)
    data, _ = get_request_data()

    d, erros = _validar_e_sanitizar(data)
    if erros:
        return jsonify({"success": False, "erro": erros[0], "errors": erros}), 400

    for campo, valor in d.items():
        setattr(f, campo, valor)

    registrar("edicao", "fornecedores", f"Fornecedor atualizado: {f.nome}")
    db.session.commit()
    return jsonify(f.to_dict())


@fornecedores_bp.route("/api/fornecedores/<int:id>", methods=["DELETE"])
@nivel_required("admin")
def deletar(id):
    f = db.get_or_404(Fornecedor, id)
    f.ativo = False
    registrar("arquivamento", "fornecedores", f"Fornecedor arquivado: {f.nome}")
    db.session.commit()
    return jsonify({"success": True, "mensagem": "Fornecedor arquivado; histórico preservado"})
