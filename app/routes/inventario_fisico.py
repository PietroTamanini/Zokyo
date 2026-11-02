"""routes/inventario_fisico.py — Inventário físico: sessões, itens, aprovação e relatório."""
from flask import Blueprint, g, jsonify, request

from app.services import inventario_fisico as inv_svc
from app.utils.auth import nivel_required
from app.utils.request_data import get_request_data

inventario_bp = Blueprint("inventario_fisico", __name__)


def _org_id() -> int:
    return int(getattr(g, "organization_id", None) or 0) or None


@inventario_bp.route("/api/inventario/sessoes", methods=["GET"])
@nivel_required("admin", "operacional")
def listar_sessoes():
    org_id = _org_id()
    limit = request.args.get("limit", default=30, type=int)
    sessoes = inv_svc.listar_inventario_sessoes(org_id, limit=limit)
    return jsonify({
        "sessoes": [
            {
                "id": s.id,
                "status": s.status,
                "data_abertura": s.data_abertura.isoformat() if s.data_abertura else None,
                "data_fechamento": s.data_fechamento.isoformat() if s.data_fechamento else None,
                "responsavel": s.responsavel_nome,
                "observacoes": s.observacoes,
            }
            for s in sessoes
        ]
    }), 200


@inventario_bp.route("/api/inventario/sessoes/abrir", methods=["POST"])
@nivel_required("admin", "operacional")
def abrir():
    org_id = _org_id()
    data, _ = get_request_data()
    responsavel_id = data.get("responsavel_id") or None
    responsavel_nome = data.get("responsavel_nome") or None
    observacoes = data.get("observacoes") or None
    sessao = inv_svc.open_inventario(
        org_id,
        responsavel_id=responsavel_id,
        responsavel_nome=responsavel_nome,
        observacoes=observacoes,
    )
    return jsonify({
        "success": True,
        "sessao": {
            "id": sessao.id,
            "status": sessao.status,
            "data_abertura": sessao.data_abertura.isoformat() if sessao.data_abertura else None,
        },
    }), 201


@inventario_bp.route("/api/inventario/sessoes/<int:sessao_id>", methods=["GET"])
@nivel_required("admin", "operacional")
def sessao_detail(sessao_id):
    org_id = _org_id()
    sessao = inv_svc.get_inventario_sessao(org_id, sessao_id)
    if not sessao:
        return jsonify({"success": False, "erro": "Sessão de inventário não encontrada"}), 404
    return jsonify({
        "sessao": {
            "id": sessao.id,
            "status": sessao.status,
            "data_abertura": sessao.data_abertura.isoformat() if sessao.data_abertura else None,
            "data_fechamento": sessao.data_fechamento.isoformat() if sessao.data_fechamento else None,
            "responsavel": sessao.responsavel_nome,
            "observacoes": sessao.observacoes,
        }
    })


@inventario_bp.route("/api/inventario/sessoes/<int:sessao_id>/fechar", methods=["POST"])
@nivel_required("admin", "operacional")
def fechar(sessao_id):
    org_id = _org_id()
    data, _ = get_request_data()
    justificativa = data.get("justificativa") or None
    try:
        sessao = inv_svc.close_inventario(org_id, sessao_id, justificativa_fechamento=justificativa)
    except ValueError as exc:
        return jsonify({"success": False, "erro": str(exc)}), 400
    return jsonify({
        "success": True,
        "sessao": {
            "id": sessao.id,
            "status": sessao.status,
            "data_fechamento": sessao.data_fechamento.isoformat() if sessao.data_fechamento else None,
        },
    }), 200


@inventario_bp.route("/api/inventario/sessoes/<int:sessao_id>/itens", methods=["GET"])
@nivel_required("admin", "operacional")
def itens_sessao(sessao_id):
    org_id = _org_id()
    itens = inv_svc.get_inventario_itens(org_id, sessao_id)
    return jsonify({
        "itens": [
            {
                "id": item.id,
                "peca_id": item.peca_id,
                "nome": item.peca.nome,
                "codigo": item.peca.codigo,
                "quantidade_sistema": item.quantidade_sistema,
                "quantidade_fisica": item.quantidade_fisica,
                "divergencia": item.divergencia,
                "is_divergente": item.is_divergente,
                "justificativa": item.justificativa,
                "aprovado": item.aprovado,
            }
            for item in itens
        ]
    }), 200


@inventario_bp.route("/api/inventario/itens", methods=["POST"])
@nivel_required("admin", "operacional")
def informar_quantidade():
    """Registra a quantidade física contada para uma peça na sessão."""
    org_id = _org_id()
    data, _ = get_request_data()
    peca_id = data.get("peca_id")
    quantidade_fisica = data.get("quantidade_fisica")
    usuario_id = data.get("usuario_id") or getattr(g, "usuario_id", None) or 1
    justificativa = data.get("justificativa") or None

    try:
        item = inv_svc.informar_quantidade_fisica(
            org_id,
            data.get("sessao_id") or None,
            peca_id,
            quantidade_fisica,
            usuario_id,
            justificativa=justificativa,
        )
    except ValueError as exc:
        return jsonify({"success": False, "erro": str(exc)}), 400

    return jsonify({
        "success": True,
        "item": {
            "id": item.id,
            "peca_id": item.peca_id,
            "nome": item.peca.nome,
            "quantidade_sistema": item.quantidade_sistema,
            "quantidade_fisica": item.quantidade_fisica,
            "divergencia": item.divergencia,
            "is_divergente": item.is_divergente,
            "justificativa": item.justificativa,
        },
    }), 200


@inventario_bp.route("/api/inventario/itens/<int:peca_id>/aprovar", methods=["POST"])
@inventario_bp.route("/api/inventario/itens/peca_id_aprovar", methods=["POST"])
@nivel_required("admin", "operacional")
def aprovar_peca(sessao_id=None, peca_id=None):
    """Approva o ajuste de uma peça, atualizando o estoque."""
    org_id = _org_id()
    data, _ = get_request_data()
    peca_id = data.get("peca_id") or peca_id
    usuario_id = data.get("usuario_id") or getattr(g, "usuario_id", None) or 1
    justificativa = data.get("justificativa") or None

    try:
        resultado = inv_svc.aprovar_ajuste(org_id, data.get("sessao_id") or sessao_id, peca_id, usuario_id, justificativa=justificativa)
    except ValueError as exc:
        return jsonify({"success": False, "erro": str(exc)}), 400

    return jsonify({
        "success": True,
        "resultado": resultado,
    }), 200


@inventario_bp.route("/api/inventario/itens/<int:peca_id>/rejeitar", methods=["POST"])
@nivel_required("admin", "operacional")
def rejeitar_peca(sessao_id=None, peca_id=None):
    """Rejeita a aprovação de ajuste de uma peça."""
    org_id = _org_id()
    data, _ = get_request_data()
    peca_id = data.get("peca_id") or peca_id
    usuario_id = data.get("usuario_id") or getattr(g, "usuario_id", None) or 1
    motivo = data.get("motivo") or "Não informado"

    try:
        resultado = inv_svc.rejeitar_ajuste(org_id, data.get("sessao_id") or sessao_id, peca_id, usuario_id, motivo=motivo)
    except ValueError as exc:
        return jsonify({"success": False, "erro": str(exc)}), 400

    return jsonify({
        "success": True,
        "resultado": resultado,
    }), 200


@inventario_bp.route("/api/inventario/sessoes/<int:sessao_id>/resumo", methods=["GET"])
@nivel_required("admin", "operacional")
def resumo_sessao(sessao_id):
    org_id = _org_id()
    resumo = inv_svc.resumo_sessao(org_id, sessao_id)
    return jsonify(resumo), 200


@inventario_bp.route("/api/inventario/historico/ajustes", methods=["GET"])
@nivel_required("admin", "operacional")
def historico_ajustes():
    org_id = _org_id()
    sessao_id = request.args.get("sessao_id", type=int)
    limit = request.args.get("limit", default=50, type=int)
    ajustes = inv_svc.historico_ajustes(org_id, sessao_id=sessao_id, limit=limit)
    return jsonify({
        "ajustes": [
            {
                "id": a["id"],
                "peca_id": a["peca_id"],
                "quantidade_anterior": a["quantidade_anterior"],
                "quantidade_nova": a["quantidade_nova"],
                "divergencia": a["divergencia"],
                "justificativa": a["justificativa"],
                "aplicado_em": a["aplicado_em"].isoformat() if a["aplicado_em"] else None,
                "aplicado_por": a["aplicado_por"],
            }
            for a in ajustes
        ]
    }), 200