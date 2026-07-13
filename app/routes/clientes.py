"""routes/clientes.py - CRUD de clientes (API JSON)."""
from flask import Blueprint, jsonify, request, session

from app.extensions import db
from app.models import Cliente, Usuario, registrar
from app.services.billing import assert_limit, assert_write_allowed
from app.utils.auth import api_login_required as login_required
from app.utils.auth import nivel_required
from app.utils.request_data import get_request_data
from app.utils.sanitizers import (
    sanitize_cep,
    sanitize_cpf_cnpj,
    sanitize_phone,
    sanitize_search_query,
    sanitize_text,
)
from app.utils.validators import (
    validar_cep,
    validar_cpf_cnpj,
    validar_telefone,
    validar_uf,
)

clientes_bp = Blueprint("clientes", __name__)


def _check_client_limit():
    user = db.session.get(Usuario, session.get("usuario_id"))
    organization_id = user.organization_id if user else -1
    assert_write_allowed(organization_id)
    assert_limit(organization_id, "max_clients", Cliente.query.filter_by(organization_id=organization_id).count())


def _escape_like(q: str) -> str:
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _documento_from_data(data: dict) -> tuple[str | None, str | None, str | None]:
    raw = data.get("cpf_cnpj", data.get("documento", data.get("cpf") or data.get("cnpj") or ""))
    doc = sanitize_cpf_cnpj(raw)
    valido, cpf, cnpj, mensagem = validar_cpf_cnpj(doc)
    if not valido:
        return None, None, mensagem
    return cpf, cnpj, None


def _duplicidade_documento(cpf: str | None, cnpj: str | None, cliente_id: int | None = None):
    if cpf:
        q = Cliente.query.filter_by(cpf=cpf)
        if cliente_id:
            q = q.filter(Cliente.id != cliente_id)
        if q.first():
            return "cpf_cnpj", "CPF ja cadastrado para outro cliente."
    if cnpj:
        q = Cliente.query.filter_by(cnpj=cnpj)
        if cliente_id:
            q = q.filter(Cliente.id != cliente_id)
        if q.first():
            return "cpf_cnpj", "CNPJ ja cadastrado para outro cliente."
    return None, None


def _duplicidade_cliente(d: dict, cliente_id: int | None = None):
    field, msg = _duplicidade_documento(d.get("cpf"), d.get("cnpj"), cliente_id=cliente_id)
    if msg:
        return field, msg

    if not d.get("cpf") and not d.get("cnpj") and d.get("nome") and d.get("telefone"):
        q = Cliente.query.filter_by(nome=d["nome"], telefone=d["telefone"])
        if cliente_id:
            q = q.filter(Cliente.id != cliente_id)
        if q.first():
            return "telefone", "Ja existe cliente sem documento com este nome e telefone."

    return None, None


def _validar_e_sanitizar(data: dict, parcial: bool = False) -> tuple[dict, dict[str, str]]:
    erros = {}
    d = {}

    if "nome" in data or not parcial:
        nome = sanitize_text(data.get("nome", ""), max_length=150)
        if not nome or len(nome) < 2:
            erros["nome"] = "Nome deve ter pelo menos 2 caracteres."
        d["nome"] = nome

    if any(k in data for k in ("cpf_cnpj", "documento", "cpf", "cnpj")) or not parcial:
        cpf, cnpj, msg = _documento_from_data(data)
        if msg:
            erros["cpf_cnpj"] = msg
        d["cpf"] = cpf
        d["cnpj"] = cnpj

    if "telefone" in data or not parcial:
        tel_raw = sanitize_phone(data.get("telefone", ""))
        if tel_raw and not validar_telefone(tel_raw):
            erros["telefone"] = "Telefone invalido. Use DDD + numero."
        d["telefone"] = tel_raw or None

    if "cep" in data or not parcial:
        cep_raw = sanitize_cep(data.get("cep", ""))
        if cep_raw and not validar_cep(cep_raw):
            erros["cep"] = "CEP invalido."
        d["cep"] = cep_raw or None

    if "endereco" in data or not parcial:
        d["endereco"] = sanitize_text(data.get("endereco", ""), max_length=300) or None

    if "numero_casa" in data or not parcial:
        d["numero_casa"] = sanitize_text(data.get("numero_casa", ""), max_length=20) or None

    if "cidade" in data or not parcial:
        d["cidade"] = sanitize_text(data.get("cidade", ""), max_length=100) or None

    if "uf" in data or not parcial:
        uf = sanitize_text(data.get("uf", ""), max_length=2).upper()
        if uf and not validar_uf(uf):
            erros["uf"] = "UF invalida."
        d["uf"] = uf or None

    if "ativo" in data:
        val = data["ativo"]
        d["ativo"] = val if isinstance(val, bool) else str(val).lower() not in ("0", "false", "no", "")

    return d, erros


def _erro_json(erros: dict[str, str], status=400):
    field, msg = next(iter(erros.items()))
    return jsonify({"success": False, "field": field, "message": msg, "erro": msg, "errors": erros}), status


@clientes_bp.route("/api/clientes", methods=["GET"])
@login_required
def listar():
    q = sanitize_search_query(request.args.get("q", ""), max_length=100)
    query = Cliente.query
    if q:
        qe = _escape_like(q)
        digitos = sanitize_cpf_cnpj(q)
        filtros = [
            Cliente.nome.ilike(f"%{qe}%"),
            Cliente.telefone.ilike(f"%{qe}%"),
        ]
        if digitos:
            filtros.extend([
                Cliente.cpf.ilike(f"%{digitos}%"),
                Cliente.cnpj.ilike(f"%{digitos}%"),
                Cliente.telefone.ilike(f"%{digitos}%"),
            ])
        query = query.filter(db.or_(*filtros))
    return jsonify([c.to_dict() for c in query.order_by(Cliente.nome).all()])


@clientes_bp.route("/api/clientes/<int:id>", methods=["GET"])
@login_required
def obter(id):
    return jsonify(db.get_or_404(Cliente, id).to_dict())


@clientes_bp.route("/api/clientes", methods=["POST"])
@nivel_required("admin", "operacional", "cadastro")
def criar():
    try:
        _check_client_limit()
    except PermissionError as exc:
        return jsonify({"success": False, "erro": str(exc)}), 403
    data, _ = get_request_data()
    d, erros = _validar_e_sanitizar(data)
    if erros:
        return _erro_json(erros)

    field, msg = _duplicidade_cliente(d)
    if msg:
        return _erro_json({field: msg})

    c = Cliente(**d)
    db.session.add(c)
    registrar("criacao", "clientes", f"Cliente criado: {d['nome']}")
    db.session.commit()
    return jsonify({"success": True, "cliente": c.to_dict(), **c.to_dict()}), 201


@clientes_bp.route("/api/clientes/quick-create", methods=["POST"])
@nivel_required("admin", "operacional", "cadastro")
def quick_create():
    try:
        _check_client_limit()
    except PermissionError as exc:
        return jsonify({"success": False, "erro": str(exc)}), 403
    data, _ = get_request_data()
    d, erros = _validar_e_sanitizar(data)
    if erros:
        return _erro_json(erros)

    field, msg = _duplicidade_cliente(d)
    if msg:
        return _erro_json({field: msg})

    c = Cliente(**d)
    db.session.add(c)
    registrar("criacao", "clientes", f"Cliente rapido criado: {d['nome']}")
    db.session.commit()
    return jsonify({"success": True, "cliente": c.to_dict()}), 201


@clientes_bp.route("/api/clientes/<int:id>", methods=["PUT"])
@nivel_required("admin", "operacional", "cadastro")
def atualizar(id):
    c = db.get_or_404(Cliente, id)
    data, _ = get_request_data()

    if not data:
        return _erro_json({"geral": "Nenhum dado enviado."})

    d, erros = _validar_e_sanitizar(data, parcial=True)
    if erros:
        return _erro_json(erros)

    candidato = {
        "nome": d.get("nome", c.nome),
        "telefone": d.get("telefone", c.telefone),
        "cpf": d.get("cpf", c.cpf),
        "cnpj": d.get("cnpj", c.cnpj),
    }
    field, msg = _duplicidade_cliente(candidato, cliente_id=c.id)
    if msg:
        return _erro_json({field: msg})

    for campo, valor in d.items():
        setattr(c, campo, valor)

    registrar("edicao", "clientes", f"Cliente atualizado: {c.nome}")
    db.session.commit()
    return jsonify({"success": True, "cliente": c.to_dict(), **c.to_dict()})


@clientes_bp.route("/api/clientes/<int:id>", methods=["DELETE"])
@nivel_required("admin")
def deletar(id):
    c = db.get_or_404(Cliente, id)
    c.ativo = False
    registrar("arquivamento", "clientes", f"Cliente arquivado: {c.nome}; historico preservado.")
    db.session.commit()
    return jsonify({"success": True, "mensagem": "Cliente arquivado; historico preservado"})
