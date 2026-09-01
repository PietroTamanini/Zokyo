"""
routes/pages.py — Templates HTML. Sistema mono-tenant.

Fixes aplicados:
  - Bug #3:  query.get_or_404 depreciado → db.get_or_404
  - Bug #4:  == None → .is_(None) em queries SQLAlchemy
  - Bug #5:  int(data["cliente_id"]) sem try/except → validação segura
  - Bug #6:  status não validado → rejeitado se fora de STATUS_OS
  - Bug #7:  func.date_format (MySQL-only) → func.strftime para SQLite /
             detecção automática do dialeto
  - Bug #8:  nivel_usuario não injetado no template os_detalhe
  - Bug #9:  Transacao.query.get_or_404 depreciado
  - Fix #10: LIKE injection — % e _ escapados nos campos de busca
  - Fix #11: datas com try/except em todos os pontos de edição de OS
"""

import csv
import io
import json
import math
import re as _re
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    session,
    url_for,
)
from sqlalchemy import func, text
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import (
    LAUDO_STATUS_LABELS,
    LAUDO_TIPOS_LABELS,
    STATUS_COLETA_LABELS,
    Cliente,
    ColetaAgendada,
    Configuracao,
    DefeitoPadrao,
    EventoLog,
    Fornecedor,
    InventoryMovement,
    LaudoFoto,
    LaudoTecnico,
    OrdemServico,
    OrderSignature,
    OSFoto,
    OSHistorico,
    Peca,
    ServiceChecklistTemplate,
    Transacao,
    Usuario,
    proximo_numero_os,
    registrar,
)
from app.models.ordem_servico import STATUS_OS, STATUS_OS_LABELS
from app.services.billing import assert_limit, assert_write_allowed
from app.services.finance import create_installments
from app.services.inventory import record_movement
from app.utils.auth import nivel_required, page_nivel_required
from app.utils.blind_index import blind_index
from app.utils.permissions import KNOWN_PERMISSIONS, ROLE_PERMISSIONS
from app.utils.sanitizers import sanitize_cep, sanitize_cpf_cnpj, sanitize_email, sanitize_phone, sanitize_text
from app.utils.security import gerar_uuid_filename, validar_upload
from app.utils.validators import validar_cep, validar_cpf_cnpj, validar_email, validar_telefone, validar_uf


def _safe_json(data):
    """Serializa dados para script HTML sem permitir fechamento da tag."""
    raw = json.dumps(data, ensure_ascii=False)
    return _re.sub(r"</", r"<\/", raw)


def _check_order_limit():
    user = db.session.get(Usuario, session.get("usuario_id"))
    assert_write_allowed(user.organization_id)
    open_count = OrdemServico.query.filter(
        OrdemServico.deletado_em.is_(None),
        OrdemServico.baixada_em.is_(None),
        ~OrdemServico.status.in_(["entregue", "cancelado"]),
    ).count()
    assert_limit(user.organization_id, "max_open_orders", open_count)

pages_bp = Blueprint("pages", __name__)
STATUS_MAP = STATUS_OS_LABELS


def _configured_status_map():
    return Configuracao.get().get_os_status_map()


def _configured_status_keys():
    return set(_configured_status_map())


def _configured_priority_options():
    return Configuracao.get().get_os_priority_options()


def _configured_priority_map():
    return Configuracao.get().get_os_priority_map()


def _configured_priority_keys():
    return {item["key"] for item in _configured_priority_options()}


def _configured_attendance_options():
    return Configuracao.get().get_attendance_type_options()


def _configured_attendance_map():
    return Configuracao.get().get_attendance_type_map()


def _valid_or_default(value, allowed, default):
    return value if value in allowed else default


def _open_orders_query():
    return (
        OrdemServico.query
        .filter(OrdemServico.deletado_em.is_(None))
        .filter(OrdemServico.baixada_em.is_(None))
        .options(joinedload(OrdemServico.cliente))
    )


def _order_waiting_days(order):
    if not order.data_entrada:
        return 0
    start = order.data_entrada.replace(tzinfo=None) if getattr(order.data_entrada, "tzinfo", None) else order.data_entrada
    return max((datetime.now().date() - start.date()).days, 0)


@pages_bp.route("/ajuda")
@page_nivel_required("admin", "operacional", "cadastro", "consulta", "financeiro")
def ajuda():
    user = db.session.get(Usuario, session["usuario_id"])
    cfg = Configuracao.get()
    checklist = [
        ("Primeiro cliente", Cliente.query.count() > 0, url_for("pages.clientes")),
        ("Primeira OS", OrdemServico.query.filter(OrdemServico.deletado_em.is_(None)).count() > 0, url_for("pages.os_nova")),
        ("Primeiro laudo", LaudoTecnico.query.count() > 0, url_for("laudos.novo")),
    ]
    if user.nivel == "admin":
        checklist[0:0] = [
            ("Empresa", bool(cfg and cfg.nome_empresa and cfg.cnpj), url_for("configuracoes.index")),
            ("Segurança 2FA", bool(user.totp_enabled), url_for("auth.two_factor_setup")),
        ]
    roteiros = [
        {
            "titulo": "Atendimento no balcão",
            "passos": [
                "Busque o cliente pelo telefone ou documento.",
                "Abra a OS e preencha defeito, aparelho, marca, modelo e serial.",
                "Imprima a via do cliente e deixe a OS em Recepção.",
            ],
        },
        {
            "titulo": "Acompanhar conserto",
            "passos": [
                "Use Bancada ou Kanban para ver o que está em análise e reparo.",
                "Registre peça, serviço executado e observação técnica na OS.",
                "Mude para Pronto somente quando o equipamento puder ser retirado.",
            ],
        },
        {
            "titulo": "Entrega com pagamento",
            "passos": [
                "Confira o total da OS e registre pagamentos parciais se houver.",
                "Só finalize como Entregue quando o saldo estiver totalmente pago.",
                "Baixe a OS depois da entrega para tirar da tela principal.",
            ],
        },
    ]
    atalhos_ajuda = [
        ("Busca global", url_for("pages.zokyo_pesquisar"), "Encontre cliente, OS, serial, peça, serviço, laudo ou lançamento."),
        ("OS baixadas", url_for("pages.os_baixadas"), "Veja ordens já entregues sem poluir a lista principal."),
        ("Rota de coleta", url_for("pages.coleta_rota"), "Organize pontos de coleta saindo e voltando da assistência."),
        ("Backup", url_for("pages.zokyo_backup"), "Confira os dados e a rotina de restore."),
    ]
    return render_template(
        "pages/ajuda.html", active="ajuda", checklist=checklist,
        roteiros=roteiros, atalhos_ajuda=atalhos_ajuda,
        onboarding=request.args.get("onboarding") == "1" and not user.onboarding_completed,
    )


@pages_bp.route("/ajuda/concluir", methods=["POST"])
@page_nivel_required("admin", "operacional", "cadastro", "consulta", "financeiro")
def ajuda_concluir():
    user = db.session.get(Usuario, session["usuario_id"])
    user.onboarding_completed = True
    registrar("onboarding", "usuarios", "Onboarding concluído.")
    db.session.commit()
    flash("Configuração inicial concluída. A Central de Ajuda continua disponível no menu.", "success")
    return redirect(url_for("pages.dashboard"))


# ── helpers ───────────────────────────────────────────────────
@pages_bp.route("/service-worker.js")
def service_worker():
    response = make_response(send_from_directory(current_app.static_folder, "service-worker.js"))
    response.headers["Content-Type"] = "application/javascript; charset=utf-8"
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"
    return response


@pages_bp.route("/pwa-start")
def pwa_start():
    target = url_for("pages.coleta") if session.get("usuario_id") else url_for("auth.login_page")
    return render_template("pages/pwa_start.html", target_url=target)


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "usuario_id" not in session:
            return redirect(url_for("auth.login_page"))
        if not Usuario.query.first():
            return redirect(url_for("auth.primeiro_acesso_page"))
        g.usuario = db.session.get(Usuario, session["usuario_id"])
        return f(*args, **kwargs)
    return decorated

def _today(): return date.today().isoformat()
def _now():   return datetime.now(timezone.utc)
def _now_db(): return _now().replace(tzinfo=None)

def _safe_date(valor):
    """Parse seguro de data ISO. Retorna None se inválido."""
    if not valor:
        return None
    try:
        return datetime.fromisoformat(str(valor)[:10])
    except (ValueError, TypeError):
        return None

def _safe_datetime_local(valor):
    if not valor:
        return None
    try:
        return datetime.fromisoformat(str(valor).strip())
    except (ValueError, TypeError):
        return None


def _coleta_form_context(form_data=None, form_errors=None):
    coletas = (
        ColetaAgendada.query
        .options(joinedload(ColetaAgendada.cliente), joinedload(ColetaAgendada.os))
        .order_by(
            ColetaAgendada.status.asc(),
            ColetaAgendada.data_agendada.is_(None),
            ColetaAgendada.data_agendada.asc(),
            ColetaAgendada.criado_em.desc(),
        )
        .all()
    )
    return dict(
        active="coleta",
        coletas=coletas,
        status_coleta_labels=STATUS_COLETA_LABELS,
        form_data=form_data or {},
        form_errors=form_errors or {},
        hoje_iso=_today(),
    )


def _endereco_assistencia(cfg):
    partes = []
    if cfg.endereco:
        partes.append(cfg.endereco)
    local = ""
    if cfg.cidade:
        local = cfg.cidade
    if cfg.uf:
        local = f"{local}/{cfg.uf}" if local else cfg.uf
    if local:
        partes.append(local)
    return ", ".join(partes)


def _coletas_para_rota():
    return (
        ColetaAgendada.query
        .options(joinedload(ColetaAgendada.cliente))
        .filter(ColetaAgendada.status.in_(["agendada", "em_coleta"]))
        .order_by(
            ColetaAgendada.data_agendada.is_(None),
            ColetaAgendada.data_agendada.asc(),
            ColetaAgendada.criado_em.asc(),
        )
        .all()
    )


def _coleta_rota_payload(coletas):
    return _safe_json([
        {
            "id": item.id,
            "cliente": item.cliente.nome if item.cliente else "Cliente",
            "telefone": item.telefone_contato or (item.cliente.telefone if item.cliente else "") or "",
            "endereco": item.endereco_completo or "",
            "horario": item.data_agendada.strftime("%d/%m/%Y %H:%M") if item.data_agendada else "",
        }
        for item in coletas
        if item.endereco_completo
    ])


def _render_coleta_error(form_data, form_errors):
    _field, message = next(iter(form_errors.items()))
    flash(message, "error")
    return render_template("pages/coleta.html", **_coleta_form_context(form_data, form_errors)), 400


def _coleta_cliente_payload(data):
    erros = {}
    nome = sanitize_text(data.get("nome", ""), max_length=150)
    if not nome or len(nome) < 2:
        erros["nome"] = "Informe o nome do cliente."

    valido, cpf, cnpj, msg = validar_cpf_cnpj(sanitize_cpf_cnpj(data.get("cpf_cnpj", "")))
    if not valido:
        erros["cpf_cnpj"] = msg

    telefone = sanitize_phone(data.get("telefone", ""))
    if telefone and not validar_telefone(telefone):
        erros["telefone"] = "Telefone inválido."

    cep = sanitize_cep(data.get("cep", ""))
    if cep and not validar_cep(cep):
        erros["cep"] = "CEP inválido."

    uf = sanitize_text(data.get("uf", ""), max_length=2).upper()
    if uf and not validar_uf(uf):
        erros["uf"] = "UF invalida."

    agendada = _safe_datetime_local(data.get("data_agendada"))
    if data.get("data_agendada") and not agendada:
        erros["data_agendada"] = "Data/hora de coleta invalida."

    payload = {
        "nome": nome,
        "cpf": cpf,
        "cnpj": cnpj,
        "telefone": telefone or None,
        "cep": cep or None,
        "endereco": sanitize_text(data.get("endereco", ""), max_length=300) or None,
        "numero_casa": sanitize_text(data.get("numero_casa", ""), max_length=20) or None,
        "cidade": sanitize_text(data.get("cidade", ""), max_length=100) or None,
        "uf": uf or None,
        "data_agendada": agendada,
        "observacoes": sanitize_text(data.get("observacoes", ""), max_length=3000) or None,
    }
    return payload, erros


def _cliente_para_coleta(payload):
    cliente = None
    if payload.get("cpf"):
        cliente = Cliente.query.filter_by(cpf_bidx=blind_index(payload["cpf"], "cpf")).first()
    if not cliente and payload.get("cnpj"):
        cliente = Cliente.query.filter_by(cnpj_bidx=blind_index(payload["cnpj"], "cnpj")).first()
    if not cliente and payload.get("telefone"):
        cliente = Cliente.query.filter_by(nome=payload["nome"], telefone=payload["telefone"]).first()

    if not cliente:
        cliente = Cliente(
            nome=payload["nome"],
            cpf=payload.get("cpf"),
            cnpj=payload.get("cnpj"),
            telefone=payload.get("telefone"),
            cep=payload.get("cep"),
            endereco=payload.get("endereco"),
            numero_casa=payload.get("numero_casa"),
            cidade=payload.get("cidade"),
            uf=payload.get("uf"),
        )
        db.session.add(cliente)
        db.session.flush()
        return cliente

    for campo in ("telefone", "cep", "endereco", "numero_casa", "cidade", "uf"):
        if payload.get(campo) and not getattr(cliente, campo):
            setattr(cliente, campo, payload[campo])
    return cliente


_FOTO_MIMES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
_FOTO_EXTS = {"jpg", "jpeg", "png", "webp", "gif"}


def _validar_fotos(files):
    fotos = [f for f in files if f and f.filename]
    erros = []
    if not fotos:
        return fotos, ["Adicione pelo menos uma foto da coleta."]
    if len(fotos) > 12:
        return fotos, ["Envie no maximo 12 fotos por coleta."]

    for foto in fotos:
        original = foto.filename or ""
        ext = original.rsplit(".", 1)[-1].lower() if "." in original else ""
        foto.stream.seek(0, 2)
        tamanho = foto.stream.tell()
        foto.stream.seek(0)
        erros.extend(validar_upload(original, foto.mimetype, tamanho))
        if ext not in _FOTO_EXTS or foto.mimetype not in _FOTO_MIMES:
            erros.append(f"{original}: apenas fotos JPG, PNG, WEBP ou GIF são aceitas.")
    return fotos, erros


def _salvar_fotos_os(os_obj, coleta, fotos):
    from app.services.billing import assert_storage_limit
    total_incoming = 0
    for foto in fotos:
        foto.stream.seek(0, 2)
        total_incoming += foto.stream.tell()
        foto.stream.seek(0)
    assert_storage_limit(os_obj.organization_id, total_incoming)
    base = Path(current_app.instance_path) / "uploads" / "os_fotos" / f"os_{os_obj.id:04d}"
    base.mkdir(parents=True, exist_ok=True)
    registros = []
    for foto in fotos:
        original = foto.filename or "foto"
        ext = original.rsplit(".", 1)[-1].lower() if "." in original else "jpg"
        filename = gerar_uuid_filename(ext)
        destino = base / filename
        foto.save(destino)
        rel = Path("os_fotos") / f"os_{os_obj.id:04d}" / filename
        from app.services.object_storage import put
        put(rel.as_posix(), destino.read_bytes(), foto.mimetype or "application/octet-stream")
        registros.append(OSFoto(
            os_id=os_obj.id,
            coleta_id=coleta.id if coleta else None,
            usuario_id=session["usuario_id"],
            filename=rel.as_posix(),
            original_filename=sanitize_text(original, max_length=255) or "foto",
            mime_type=foto.mimetype,
            tamanho_bytes=destino.stat().st_size,
        ))
    db.session.add_all(registros)
    return registros


def _clientes_json_payload(clientes):
    return _safe_json([
        {
            "id": c.id,
            "nome": c.nome,
            "cpf": c.cpf or "",
            "cnpj": c.cnpj or "",
            "documento": c.documento,
            "telefone": c.telefone or "",
            "cep": c.cep or "",
            "endereco": c.endereco or "",
            "numero_casa": c.numero_casa or "",
            "cidade": c.cidade or "",
            "uf": c.uf or "",
        }
        for c in clientes
    ])


def _os_form_context(os_obj=None, form_data=None, form_errors=None, active="os", coleta=False):
    clientes = Cliente.query.filter_by(ativo=True).order_by(Cliente.nome).all()
    tecnicos = (Usuario.query.filter_by(ativo=True)
                .filter(Usuario.nivel.in_(["admin", "operacional"])).all())
    pecas = _pecas_ativas_query().order_by(Peca.nome).all()
    status_map = _configured_status_map()
    priority_options = _configured_priority_options()
    attendance_options = _configured_attendance_options()
    return dict(
        active=active,
        os=os_obj,
        clientes=clientes,
        clientes_json=_clientes_json_payload(clientes),
        pecas_estoque=pecas,
        tecnicos=tecnicos,
        status_map=status_map,
        priority_options=priority_options,
        priority_map={item["key"]: item["label"] for item in priority_options},
        attendance_options=attendance_options,
        attendance_map={item["key"]: item["label"] for item in attendance_options},
        hoje_iso=_today(),
        pecas_usadas=os_obj.to_dict().get("pecas", []) if os_obj else [],
        nivel_usuario=session.get("nivel", "operacional"),
        form_data=form_data or {},
        form_errors=form_errors or {},
        coleta=coleta,
    )


def _render_os_form_error(message, field, form_data, os_obj=None):
    flash(message, "error")
    return render_template(
        "pages/os_form.html",
        **_os_form_context(os_obj, dict(form_data), {field: message}),
    ), 400


def _normalizar_tipo_aparelho(data):
    tipo = sanitize_text(data.get("tipo_aparelho", ""), max_length=100)
    if tipo == "Outros":
        tipo = sanitize_text(data.get("tipo_aparelho_outro", ""), max_length=100)
    return tipo


def _escape_like(q: str) -> str:
    """Escapa % e _ para evitar LIKE injection."""
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _like(q: str) -> str:
    return f"%{_escape_like(q)}%"


def _ilike(col, q: str):
    return col.ilike(_like(q), escape="\\")


def _pecas_ativas_query():
    return Peca.query.filter(Peca.ativo.is_(True), Peca.deletado_em.is_(None))


def _servicos_ativos_query():
    return DefeitoPadrao.query.filter(
        DefeitoPadrao.ativo.is_(True),
        DefeitoPadrao.deletado_em.is_(None),
    )


def _date_trunc_month(col):
    if db.session.get_bind().dialect.name == "sqlite":
        return func.strftime("%Y-%m", col)
    return func.date_format(col, "%Y-%m")

def _date_trunc_day(col):
    if db.session.get_bind().dialect.name == "sqlite":
        return func.strftime("%Y-%m-%d", col)
    return func.date_format(col, "%Y-%m-%d")

def _coalesce_sum(col):
    """sum(...) com fallback 0 quando não há linhas."""
    return func.coalesce(func.sum(col), 0)

def _caixa_expression():
    """
    Saldo de caixa: sum(receitas pagas) - sum(despesas pagas).
    Compatible com SQLite e MySQL.
    """
    from sqlalchemy import case
    return _coalesce_sum(
        case(
            (Transacao.tipo == "receita",  Transacao.valor),
            (Transacao.tipo == "despesa", -Transacao.valor),
            else_=0,
        )
    )


# ══════════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════════
@pages_bp.route("/")
@login_required
def dashboard():
    cfg  = Configuracao.get()
    hoje = _now()
    mes  = hoje.strftime("%Y-%m")
    dia  = hoje.strftime("%Y-%m-%d")

    # Bug #4: .is_(None) em vez de ==None
    os_abertas = OrdemServico.query.filter(
        OrdemServico.deletado_em.is_(None),
        OrdemServico.baixada_em.is_(None),
        ~OrdemServico.status.in_(["entregue", "cancelado"])
    ).count()
    os_prontas = OrdemServico.query.filter_by(status="pronto").filter(
        OrdemServico.deletado_em.is_(None), OrdemServico.baixada_em.is_(None)).count()
    os_atrasadas = OrdemServico.query.filter(
        OrdemServico.data_prev < hoje.replace(tzinfo=None),
        OrdemServico.deletado_em.is_(None),
        OrdemServico.baixada_em.is_(None),
        ~OrdemServico.status.in_(["entregue", "cancelado", "pronto"])
    ).count()
    os_aprovacao = OrdemServico.query.filter_by(
        status="aguardando_aprovacao").filter(
        OrdemServico.deletado_em.is_(None), OrdemServico.baixada_em.is_(None)).count()
    coletas_abertas = ColetaAgendada.query.filter(
        ColetaAgendada.status.in_(["agendada", "em_coleta"])
    ).count()
    pecas_compra_pendentes = db.session.execute(text(
        "SELECT COUNT(*) FROM os_pecas op "
        "JOIN ordens_servico os ON os.id = op.os_id "
        "WHERE os.deletado_em IS NULL AND os.baixada_em IS NULL "
        "AND os.status NOT IN ('entregue', 'cancelado') "
        "AND (op.link_compra IS NOT NULL OR op.quantidade > 0)"
    )).scalar() or 0

    def soma(tipo, st, periodo="mes"):
        q = db.session.query(_coalesce_sum(Transacao.valor)).filter(
            Transacao.tipo == tipo, Transacao.status == st)
        if periodo == "mes":
            q = q.filter(_date_trunc_month(Transacao.criado_em) == mes)
        elif periodo == "dia":
            q = q.filter(_date_trunc_day(Transacao.criado_em) == dia)
        return float(q.scalar() or 0)

    receitas_mes = soma("receita", "pago",     "mes")
    despesas_mes = soma("despesa", "pago",     "mes")
    vendas_dia   = soma("receita", "pago",     "dia")
    saldo_mes    = receitas_mes - despesas_mes
    a_receber    = soma("receita", "pendente", "mes")
    a_pagar      = soma("despesa", "pendente", "mes")

    caixa = float(db.session.query(_caixa_expression()).filter(
        Transacao.status == "pago").scalar() or 0)

    total_clientes     = Cliente.query.filter_by(ativo=True).count()
    total_fornecedores = Fornecedor.query.filter_by(ativo=True).count()
    total_usuarios     = Usuario.query.filter_by(ativo=True).count()
    total_pecas        = _pecas_ativas_query().count()
    estoque_critico    = _pecas_ativas_query().filter(
        Peca.quantidade <= Peca.estoque_minimo).count()
    total_transacoes   = Transacao.query.count()

    valor_estoque = float(db.session.query(
        _coalesce_sum(Peca.custo * Peca.quantidade)
    ).filter(Peca.ativo.is_(True), Peca.deletado_em.is_(None)).scalar() or 0)

    alertas = []
    if cfg.alerta_caixa_minimo and caixa < cfg.alerta_caixa_minimo:
        alertas.append({"tipo": "red",   "icone": "💰",
                        "msg": f"Caixa abaixo do mínimo: R$ {caixa:,.2f}"})
    if estoque_critico > 0:
        alertas.append({"tipo": "amber", "icone": "📦",
                        "msg": f"{estoque_critico} peça(s) com estoque crítico"})
    if os_atrasadas > 0:
        alertas.append({"tipo": "red",   "icone": "⏰",
                        "msg": f"{os_atrasadas} OS atrasada(s)"})
    if os_prontas > 0:
        alertas.append({"tipo": "green", "icone": "✅",
                        "msg": f"{os_prontas} equipamento(s) pronto(s) para retirada"})

    prazo = hoje + timedelta(days=cfg.alerta_vencimento_dias or 5)
    vencendo = Transacao.query.filter(
        Transacao.status == "pendente",
        Transacao.data_vencimento <= prazo.replace(tzinfo=None)
    ).count()
    if vencendo > 0:
        alertas.append({"tipo": "amber", "icone": "📅",
                        "msg": f"{vencendo} transação(ões) vencendo em breve"})

    pct_meta = 0
    if cfg.meta_receita_mensal and cfg.meta_receita_mensal > 0:
        pct_meta = min(100, round(
            (receitas_mes / cfg.meta_receita_mensal) * 100, 1))

    pipeline_counts = {}
    for st in STATUS_OS:
        pipeline_counts[st] = OrdemServico.query.filter_by(
            status=st).filter(OrdemServico.deletado_em.is_(None), OrdemServico.baixada_em.is_(None)).count()

    ultimas_os = (OrdemServico.query
                  .filter(OrdemServico.deletado_em.is_(None))
                  .filter(OrdemServico.baixada_em.is_(None))
                  .options(joinedload(OrdemServico.cliente))
                  .order_by(OrdemServico.data_entrada.desc())
                  .limit(8).all())

    return render_template("pages/dashboard.html",
        active="dashboard",
        hoje=hoje.strftime("%A, %d de %B de %Y"),
        os_abertas=os_abertas, os_prontas=os_prontas,
        os_atrasadas=os_atrasadas, os_aprovacao=os_aprovacao,
        coletas_abertas=coletas_abertas,
        pecas_compra_pendentes=pecas_compra_pendentes,
        receitas_mes=receitas_mes, despesas_mes=despesas_mes,
        saldo_mes=saldo_mes, vendas_dia=vendas_dia,
        a_receber=a_receber, a_pagar=a_pagar, caixa=caixa,
        total_clientes=total_clientes, total_fornecedores=total_fornecedores,
        total_usuarios=total_usuarios, total_pecas=total_pecas,
        estoque_critico=estoque_critico, valor_estoque=valor_estoque,
        total_transacoes=total_transacoes,
        alertas=alertas, pct_meta=pct_meta,
        meta_receita_mensal=cfg.meta_receita_mensal,
        pipeline_counts=pipeline_counts,
        ultimas_os=ultimas_os, status_map=STATUS_MAP,
    )


# ════════════════════════════════════════════════════════════════════════
# FUNCIONALIDADES DO SISTEMA
# ════════════════════════════════════════════════════════════════════════
@pages_bp.route("/zokyo")
@pages_bp.route("/home")
@login_required
def zokyo_home():
    return redirect(url_for("pages.dashboard"))


@pages_bp.route("/login/sair", methods=["GET", "POST"])
@login_required
def zokyo_logout():
    if request.method == "GET":
        return render_template("pages/logout_confirm.html")
    uid, uname = session.get("usuario_id"), session.get("usuario_nome", "-")
    if uid:
        registrar("logout", "sistema", f"Logout: {uname}", usuario_id=uid, usuario_nome=uname)
        db.session.commit()
    session.clear()
    return redirect(url_for("auth.login_page"))


@pages_bp.route("/login/verificarLogin", methods=["GET", "POST"])
def zokyo_verificar_login():
    if request.method == "POST":
        return redirect(url_for("auth.login_page"), code=307)
    return redirect(url_for("auth.login_page"))


@pages_bp.route("/zokyo/pesquisar")
@pages_bp.route("/pesquisar")
@login_required
def zokyo_pesquisar():
    termo = request.args.get("termo") or request.args.get("q") or ""
    q = sanitize_text(termo, max_length=120).strip()
    digitos = "".join(ch for ch in q if ch.isdigit())
    rows = []
    if q:
        cliente_filters = [
            _ilike(Cliente.nome, q),
            _ilike(Cliente.telefone, q),
            _ilike(Cliente.email, q),
        ]
        if digitos:
            cliente_filters.extend([
                Cliente.cpf.ilike(f"%{digitos}%"),
                Cliente.cnpj.ilike(f"%{digitos}%"),
                Cliente.telefone.ilike(f"%{digitos}%"),
            ])
        clientes = Cliente.query.filter(db.or_(*cliente_filters)).order_by(Cliente.nome).limit(10).all()
        rows.extend({
            "tipo": "Cliente",
            "codigo": f"C{item.id:04d}",
            "nome": item.nome,
            "detalhe": item.documento or item.telefone or item.email or "-",
            "acao": "Abrir",
            "acao_url": url_for("pages.clientes", q=item.nome),
        } for item in clientes)

        produtos = _pecas_ativas_query().filter(db.or_(
            _ilike(Peca.nome, q),
            _ilike(Peca.codigo, q),
            _ilike(Peca.categoria, q),
            _ilike(Peca.localizacao, q),
        )).order_by(Peca.nome).limit(10).all()
        rows.extend({
            "tipo": "Produto",
            "codigo": item.codigo or f"P{item.id:04d}",
            "nome": item.nome,
            "detalhe": item.categoria or item.localizacao or "-",
            "acao": "Abrir",
            "acao_url": url_for("pages.estoque", q=item.nome),
        } for item in produtos)

        os_filters = [
            _ilike(Cliente.nome, q),
            _ilike(Cliente.telefone, q),
            _ilike(OrdemServico.tipo_aparelho, q),
            _ilike(OrdemServico.marca, q),
            _ilike(OrdemServico.modelo, q),
            _ilike(OrdemServico.numero_serie, q),
            _ilike(OrdemServico.defeito_alegado, q),
            _ilike(OrdemServico.defeito_encontrado, q),
            _ilike(OrdemServico.solucao, q),
            _ilike(OrdemServico.observacoes, q),
        ]
        if digitos:
            os_filters.extend([
                OrdemServico.numero == int(digitos),
                Cliente.cpf.ilike(f"%{digitos}%"),
                Cliente.cnpj.ilike(f"%{digitos}%"),
                Cliente.telefone.ilike(f"%{digitos}%"),
            ])
        ordens = (
            OrdemServico.query
            .join(Cliente)
            .filter(OrdemServico.deletado_em.is_(None))
            .filter(db.or_(*os_filters))
            .order_by(OrdemServico.data_entrada.desc())
            .limit(10)
            .all()
        )
        rows.extend({
            "tipo": "OS",
            "codigo": f"OS{item.id:04d}",
            "nome": item.cliente.nome if item.cliente else "-",
            "detalhe": " ".join(part for part in [item.tipo_aparelho, item.marca, item.modelo] if part) or "-",
            "acao": "Abrir",
            "acao_url": url_for("pages.os_detalhe", id=item.id),
        } for item in ordens)

        fornecedores = Fornecedor.query.filter(db.or_(
            _ilike(Fornecedor.nome, q),
            _ilike(Fornecedor.email, q),
            _ilike(Fornecedor.telefone, q),
            _ilike(Fornecedor.cidade, q),
            Fornecedor.cnpj.ilike(f"%{digitos}%") if digitos else False,
        )).order_by(Fornecedor.nome).limit(8).all()
        rows.extend({
            "tipo": "Fornecedor",
            "codigo": f"F{item.id:04d}",
            "nome": item.nome,
            "detalhe": item.telefone or item.email or item.cidade or "-",
            "acao": "Abrir",
            "acao_url": url_for("pages.fornecedores", q=item.nome),
        } for item in fornecedores)

        servicos = _servicos_ativos_query().filter(db.or_(
            _ilike(DefeitoPadrao.tipo_aparelho, q),
            _ilike(DefeitoPadrao.sintoma, q),
            _ilike(DefeitoPadrao.causa, q),
            _ilike(DefeitoPadrao.solucao, q),
        )).order_by(DefeitoPadrao.tipo_aparelho, DefeitoPadrao.sintoma).limit(8).all()
        rows.extend({
            "tipo": "Serviço",
            "codigo": f"S{item.id:04d}",
            "nome": item.sintoma,
            "detalhe": item.tipo_aparelho or item.causa or "-",
            "acao": "Abrir",
            "acao_url": url_for("pages.servicos", q=item.sintoma),
        } for item in servicos)

        laudos = (
            LaudoTecnico.query
            .join(Cliente, LaudoTecnico.cliente_id == Cliente.id)
            .join(OrdemServico, LaudoTecnico.os_id == OrdemServico.id)
            .filter(db.or_(
                _ilike(LaudoTecnico.numero, q),
                _ilike(LaudoTecnico.tecnico_responsavel_nome, q),
                _ilike(LaudoTecnico.diagnostico_tecnico, q),
                _ilike(Cliente.nome, q),
                _ilike(OrdemServico.marca, q),
                _ilike(OrdemServico.modelo, q),
                _ilike(OrdemServico.numero_serie, q),
                Cliente.cpf.ilike(f"%{digitos}%") if digitos else False,
                Cliente.cnpj.ilike(f"%{digitos}%") if digitos else False,
            ))
            .order_by(LaudoTecnico.criado_em.desc())
            .limit(8)
            .all()
        )
        rows.extend({
            "tipo": "Laudo",
            "codigo": item.numero or f"L{item.id:04d}",
            "nome": item.cliente.nome if item.cliente else "Cliente",
            "detalhe": LAUDO_STATUS_LABELS.get(item.status, item.status),
            "acao": "Abrir",
            "acao_url": url_for("laudos.detalhe", id=item.id),
        } for item in laudos)

        transacoes = Transacao.query.filter(db.or_(
            _ilike(Transacao.descricao, q),
            _ilike(Transacao.categoria, q),
            _ilike(Transacao.forma_pagamento, q),
            _ilike(Transacao.conciliacao_ref, q),
        )).order_by(
            Transacao.criado_em.desc()
        ).limit(8).all()
        rows.extend({
            "tipo": "Financeiro",
            "codigo": f"L{item.id:04d}",
            "nome": item.descricao,
            "detalhe": f"{item.tipo} / {item.status}",
            "acao": "Abrir",
            "acao_url": url_for("pages.financeiro", q=item.descricao),
        } for item in transacoes)

    return render_template(
        "pages/zokyo_modulo.html",
        active="pesquisa",
        title="Pesquisa",
        breadcrumb="Pesquisa",
        subtitle="Busca global do sistema.",
        empty="Informe um termo para pesquisar." if not q else "Nenhum resultado encontrado.",
        search=q,
        search_name="termo",
        search_placeholder="Buscar cliente, OS, serial, peça, serviço, laudo ou lançamento",
        add_label=None,
        add_url=None,
        columns=[
            {"key": "tipo", "label": "Módulo", "badge": True},
            {"key": "codigo", "label": "Código"},
            {"key": "nome", "label": "Nome"},
            {"key": "detalhe", "label": "Detalhe"},
            {"key": "acao", "label": "Opções", "url_key": "acao_url"},
        ],
        rows=rows,
        pagination=None,
    )


@pages_bp.route("/zokyo/minhaConta")
@pages_bp.route("/minhaConta")
@login_required
def zokyo_minha_conta():
    return redirect(url_for("auth.sessions_page"))


@pages_bp.route("/zokyo/alterarSenha", methods=["GET", "POST"])
@pages_bp.route("/alterarSenha", methods=["GET", "POST"])
@login_required
def zokyo_alterar_senha():
    return redirect(url_for("auth.sessions_page"))


@pages_bp.route("/zokyo/uploadUserImage", methods=["POST"])
@pages_bp.route("/uploadUserImage", methods=["POST"])
@login_required
def zokyo_upload_user_image():
    flash("Foto de perfil é gerenciada pelo cadastro de usuários do Zokyo.", "warning")
    return redirect(url_for("usuarios.usuarios_page"))


@pages_bp.route("/mine")
@pages_bp.route("/mine/painel")
@login_required
def zokyo_area_cliente():
    return redirect(url_for("pages.dashboard"))


@pages_bp.route("/mine/conta")
@pages_bp.route("/mine/editarDados")
@login_required
def zokyo_mine_conta():
    return redirect(url_for("auth.sessions_page"))


@pages_bp.route("/mine/os")
@pages_bp.route("/mine/minha_ordem_de_servico")
@login_required
def zokyo_mine_os():
    return redirect(url_for("pages.os_lista"))


@pages_bp.route("/mine/visualizarOs/<int:id>")
@pages_bp.route("/mine/detalhesOs/<int:id>")
@login_required
def zokyo_mine_visualizar_os(id):
    return redirect(request.form.get("next") or url_for("pages.os_detalhe", id=id))


@pages_bp.route("/os/<int:id>/retorno-garantia", methods=["POST"])
@page_nivel_required("admin", "operacional")
def os_retorno_garantia(id):
    origem = OrdemServico.query.filter_by(id=id).filter(
        OrdemServico.deletado_em.is_(None)).first_or_404()
    if not origem.em_garantia:
        flash("Esta OS não está dentro do prazo de garantia.", "error")
        return redirect(url_for("pages.os_detalhe", id=id))
    usuario = db.session.get(Usuario, session["usuario_id"])
    os_obj = OrdemServico(
        numero=proximo_numero_os(g.organization_id),
        organization_id=g.organization_id,
        cliente_id=origem.cliente_id,
        usuario_id=session["usuario_id"],
        tipo_aparelho=origem.tipo_aparelho,
        marca=origem.marca,
        modelo=origem.modelo,
        numero_serie=origem.numero_serie,
        defeito_alegado=sanitize_text(request.form.get("defeito_alegado", ""), max_length=5000)
        or f"Retorno de garantia da OS #{origem.codigo_os}",
        observacoes=f"Retorno vinculado a OS #{origem.codigo_os}.",
        valor_servico=0,
        valor_pecas=0,
        desconto=0,
        status="recepcao",
        prio="alta",
        tipo_atendimento=origem.tipo_atendimento or "balcao",
        tecnico_nome=origem.tecnico_nome or usuario.nome,
        garantia_dias=origem.garantia_dias or 90,
        warranty_return_of_id=origem.id,
    )
    db.session.add(os_obj)
    db.session.flush()
    db.session.add(OSHistorico(
        os_id=os_obj.id,
        usuario_id=session["usuario_id"],
        status_anterior=None,
        status_novo=os_obj.status,
    ))
    registrar("criacao", "garantia", f"Retorno de garantia OS #{os_obj.codigo_os} criado a partir da OS #{origem.codigo_os}")
    db.session.commit()
    flash("Retorno de garantia criado e vinculado a OS original.", "success")
    return redirect(url_for("pages.os_detalhe", id=os_obj.id))


@pages_bp.route("/mine/imprimirOs/<int:id>")
@login_required
def zokyo_mine_imprimir_os(id):
    return redirect(url_for("pages.os_pdf", id=id))


@pages_bp.route("/mine/compras")
@pages_bp.route("/mine/visualizarCompra/<int:id>")
@login_required
def zokyo_mine_compras(id=None):
    if id:
        return redirect(url_for("pages.vendas_item_alias", id=id))
    return redirect(url_for("pages.vendas"))


@pages_bp.route("/mine/imprimirCompra/<int:id>")
@login_required
def zokyo_mine_imprimir_compra(id):
    return redirect(url_for("pages.vendas_imprimir_alias", id=id))


@pages_bp.route("/mine/adicionarOs")
@login_required
def zokyo_mine_adicionar_os():
    return redirect(url_for("pages.os_nova"))


@pages_bp.route("/mine/cobrancas")
@pages_bp.route("/mine/atualizarcobranca/<int:id>")
@login_required
def zokyo_mine_cobrancas(id=None):
    if id:
        return redirect(url_for("pages.cobrancas_visualizar_alias", id=id))
    return redirect(url_for("pages.cobrancas"))


@pages_bp.route("/mine/cadastrar")
def zokyo_mine_cadastrar():
    return redirect(url_for("auth.register_page"))


@pages_bp.route("/mine/resetarSenha")
def zokyo_mine_resetar_senha():
    return redirect(url_for("auth.recuperar_senha"))


@pages_bp.route("/zokyo/configurar")
@pages_bp.route("/zokyo/emitente")
@pages_bp.route("/configurar")
@pages_bp.route("/emitente")
@page_nivel_required("admin")
def zokyo_configurar():
    return render_template(
        "pages/zokyo_configuracao.html",
        active="configuracoes",
        cfg=Configuracao.get(),
        title="Configurar Sistema" if request.path.endswith("/configurar") else "Emitente",
    )


@pages_bp.route("/zokyo/cadastrarEmitente", methods=["GET", "POST"])
@pages_bp.route("/zokyo/editarEmitente", methods=["GET", "POST"])
@pages_bp.route("/zokyo/editarLogo", methods=["GET", "POST"])
@pages_bp.route("/cadastrarEmitente", methods=["GET", "POST"])
@pages_bp.route("/editarEmitente", methods=["GET", "POST"])
@pages_bp.route("/editarLogo", methods=["GET", "POST"])
@page_nivel_required("admin")
def zokyo_emitente_alias():
    if request.method == "POST":
        return redirect(url_for("configuracoes.salvar"), code=307)
    return render_template(
        "pages/zokyo_configuracao.html",
        active="configuracoes",
        cfg=Configuracao.get(),
        title="Emitente",
    )


@pages_bp.route("/zokyo/atualizarBanco", methods=["GET", "POST"])
@pages_bp.route("/zokyo/atualizarZokyo", methods=["GET", "POST"])
@pages_bp.route("/atualizarBanco", methods=["GET", "POST"])
@login_required
def zokyo_atualizacao_alias():
    flash("Atualizacoes do banco e do sistema são controladas pelas migrações do Zokyo.", "warning")
    return redirect(url_for("configuracoes.index"))


@pages_bp.route("/zokyo/emails")
@pages_bp.route("/emails")
@login_required
def zokyo_emails():
    return redirect(url_for("configuracoes.notificacoes"))


@pages_bp.route("/zokyo/excluirEmail")
@pages_bp.route("/zokyo/excluirEmail/<int:id>")
@pages_bp.route("/excluirEmail")
@pages_bp.route("/excluirEmail/<int:id>")
@login_required
def zokyo_excluir_email(id=None):
    return redirect(url_for("configuracoes.notificacoes"))


@pages_bp.route("/zokyo/backup")
@pages_bp.route("/backup")
@page_nivel_required("admin")
def zokyo_backup():
    tabelas = {
        "clientes": text("SELECT COUNT(*) FROM clientes"),
        "fornecedores": text("SELECT COUNT(*) FROM fornecedores"),
        "pecas": text("SELECT COUNT(*) FROM pecas"),
        "ordens_servico": text("SELECT COUNT(*) FROM ordens_servico"),
        "transacoes": text("SELECT COUNT(*) FROM transacoes"),
        "usuários": text("SELECT COUNT(*) FROM usuarios"),
        "eventos_log": text("SELECT COUNT(*) FROM eventos_log"),
        "configuracoes": text("SELECT COUNT(*) FROM configuracoes"),
    }
    contagens = {}
    for tabela, consulta in tabelas.items():
        try:
            contagens[tabela] = db.session.execute(consulta).scalar() or 0
        except Exception:
            contagens[tabela] = "-"
    db_url = current_app.config.get("SQLALCHEMY_DATABASE_URI", "")
    upload_folder = current_app.config.get("REPORTS_UPLOAD_FOLDER")
    upload_ok = True
    upload_detail = "Usando pasta padrão da instância."
    if upload_folder:
        upload_path = Path(upload_folder)
        upload_ok = upload_path.exists() and upload_path.is_dir()
        upload_detail = str(upload_path)
    checks_backup = [
        {
            "label": "Banco de produção",
            "ok": db_url.startswith(("mysql://", "mysql+pymysql://", "mariadb://", "mariadb+pymysql://")),
            "detail": "MySQL/MariaDB configurado" if "mysql" in db_url or "mariadb" in db_url else "Use MySQL/MariaDB em produção",
        },
        {
            "label": "Uploads/laudos",
            "ok": upload_ok,
            "detail": upload_detail,
        },
        {
            "label": "Chave da sessão",
            "ok": bool(current_app.config.get("SECRET_KEY")) and len(str(current_app.config.get("SECRET_KEY"))) >= 32,
            "detail": "SECRET_KEY forte configurada" if current_app.config.get("SECRET_KEY") else "Defina SECRET_KEY fixa e forte",
        },
        {
            "label": "Migrations",
            "ok": True,
            "detail": "Use flask db current antes e depois do restore",
        },
    ]
    comandos = [
        {
            "titulo": "Backup do banco",
            "cmd": "python scripts/backup_database.py --env-file .env --output backups",
        },
        {
            "titulo": "Restore testado",
            "cmd": "python scripts/restore_database.py --env-file .env --backup backups/ARQUIVO.sql.gz",
        },
        {
            "titulo": "Conferir schema",
            "cmd": "flask --app wsgi:app db current && flask --app wsgi:app db check",
        },
    ]
    return render_template(
        "pages/zokyo_backup.html",
        active="configuracoes",
        contagens=contagens,
        checks_backup=checks_backup,
        comandos=comandos,
    )


@pages_bp.route("/permissoes")
@page_nivel_required("admin")
def zokyo_permissoes():
    usuarios = Usuario.query.order_by(Usuario.nome).all()
    permissoes = sorted(KNOWN_PERMISSIONS)
    return render_template(
        "pages/zokyo_permissoes.html",
        active="permissoes",
        usuarios=usuarios,
        permissoes=permissoes,
        role_permissions=ROLE_PERMISSIONS,
    )


@pages_bp.route("/permissoes/editar/<int:id>", methods=["POST"])
@page_nivel_required("admin")
def zokyo_permissoes_editar(id):
    usuario = db.get_or_404(Usuario, id)
    extras = sorted(set(request.form.getlist("permissoes_extra")) & set(KNOWN_PERMISSIONS))
    negadas = sorted(set(request.form.getlist("permissoes_negadas")) & set(KNOWN_PERMISSIONS))
    usuario.permissoes_extra = extras
    usuario.permissoes_negadas = negadas
    registrar("edicao", "permissoes", f"Permissões atualizadas: {usuario.nome}")
    db.session.commit()
    flash("Permissões atualizadas.", "success")
    return redirect(url_for("pages.zokyo_permissoes"))


@pages_bp.route("/auditoria")
@page_nivel_required("admin")
def zokyo_auditoria():
    data_ini = request.args.get("data_ini", "")
    data_fim = request.args.get("data_fim", "")
    usuario_id = request.args.get("usuario_id", "")
    tipo = request.args.get("tipo", "")
    modulo = request.args.get("modulo", "")
    page = request.args.get("page", 1, type=int)

    query = EventoLog.query
    if data_ini:
        parsed = _safe_date(data_ini)
        if parsed:
            query = query.filter(EventoLog.criado_em >= parsed)
    if data_fim:
        parsed = _safe_date(data_fim)
        if parsed:
            query = query.filter(EventoLog.criado_em <= parsed.replace(hour=23, minute=59, second=59))
    if usuario_id:
        try:
            query = query.filter(EventoLog.usuario_id == int(usuario_id))
        except (TypeError, ValueError):
            pass
    if tipo:
        query = query.filter(EventoLog.tipo == sanitize_text(tipo, max_length=30))
    if modulo:
        query = query.filter(EventoLog.modulo == sanitize_text(modulo, max_length=50))

    pag = query.order_by(EventoLog.criado_em.desc()).paginate(page=page, per_page=50, error_out=False)
    usuarios = Usuario.query.order_by(Usuario.nome).all()
    modulos = [row[0] for row in db.session.query(EventoLog.modulo).distinct().all() if row[0]]
    tipos = [row[0] for row in db.session.query(EventoLog.tipo).distinct().all() if row[0]]
    return render_template(
        "pages/zokyo_auditoria.html",
        active="auditoria",
        eventos=pag.items,
        paginacao=pag,
        usuarios=usuarios,
        modulos=modulos,
        tipos=tipos,
        filtros={
            "data_ini": data_ini,
            "data_fim": data_fim,
            "usuario_id": usuario_id,
            "tipo": tipo,
            "modulo": modulo,
        },
    )


@pages_bp.route("/auditoria/clean", methods=["POST"])
@page_nivel_required("admin")
def zokyo_auditoria_clean():
    flash("Limpeza de auditoria não foi executada; histórico preservado por segurança.", "warning")
    return redirect(url_for("pages.zokyo_auditoria"))


@pages_bp.route("/relatorios/clientes")
@pages_bp.route("/relatorios/produtos")
@pages_bp.route("/relatorios/servicos")
@pages_bp.route("/relatorios/os")
@pages_bp.route("/relatorios/vendas")
@pages_bp.route("/relatorios/financeiro")
@pages_bp.route("/relatorios/sku")
@pages_bp.route("/relatorios/receitasBrutasMei")
@pages_bp.route("/relatorios/clientesRapid")
@pages_bp.route("/relatorios/produtosRapid")
@pages_bp.route("/relatorios/servicosRapid")
@pages_bp.route("/relatorios/osRapid")
@pages_bp.route("/relatorios/vendasRapid")
@pages_bp.route("/relatorios/financeiroRapid")
@pages_bp.route("/relatorios/skuRapid")
@pages_bp.route("/relatorios/receitasBrutasRapid")
@login_required
def zokyo_relatorios_alias():
    tipo = request.path.rsplit("/", 1)[-1].replace("Rapid", "")
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";")

    def cell(value):
        text = str(value or "")
        return "'" + text if text.startswith(("=", "+", "-", "@", "\t", "\r")) else text

    if tipo == "clientes":
        writer.writerow(["ID", "Nome", "Telefone", "Email", "Cidade", "UF", "Ativo"])
        for item in Cliente.query.order_by(Cliente.nome).all():
            writer.writerow([item.id, cell(item.nome), cell(item.telefone), cell(item.email), cell(item.cidade), cell(item.uf), "Sim" if item.ativo else "Não"])
    elif tipo in {"produtos", "sku"}:
        writer.writerow(["ID", "Código", "Produto", "Categoria", "Localização", "Quantidade", "Custo", "Preço venda"])
        for item in _pecas_ativas_query().order_by(Peca.nome).all():
            writer.writerow([item.id, cell(item.codigo), cell(item.nome), cell(item.categoria), cell(item.localizacao), item.quantidade, f"{float(item.custo or 0):.2f}", f"{item.preco_venda:.2f}"])
    elif tipo == "servicos":
        writer.writerow(["ID", "Tipo aparelho", "Sintoma", "Causa", "Solucao"])
        for item in _servicos_ativos_query().order_by(DefeitoPadrao.tipo_aparelho, DefeitoPadrao.sintoma).all():
            writer.writerow([item.id, cell(item.tipo_aparelho), cell(item.sintoma), cell(item.causa), cell(item.solucao)])
    elif tipo == "os":
        writer.writerow(["OS", "Cliente", "Equipamento", "Status", "Técnico", "Entrada", "Total"])
        ordens = OrdemServico.query.filter(OrdemServico.deletado_em.is_(None)).options(joinedload(OrdemServico.cliente)).order_by(OrdemServico.data_entrada.desc()).all()
        for item in ordens:
            equipamento = " ".join(part for part in [item.tipo_aparelho, item.marca, item.modelo] if part)
            writer.writerow([item.id, cell(item.cliente.nome if item.cliente else ""), cell(equipamento), cell(STATUS_MAP.get(item.status, item.status)), cell(item.tecnico_nome), item.data_entrada.strftime("%d/%m/%Y") if item.data_entrada else "", f"{item.valor_total:.2f}"])
    elif tipo in {"vendas", "financeiro", "receitasBrutasMei"}:
        writer.writerow(["ID", "Tipo", "Categoria", "Descrição", "Status", "Vencimento", "Pagamento", "Valor"])
        query = Transacao.query
        if tipo in {"vendas", "receitasBrutasMei"}:
            query = query.filter(Transacao.tipo == "receita")
        for item in query.order_by(Transacao.criado_em.desc()).all():
            writer.writerow([item.id, cell(item.tipo), cell(item.categoria), cell(item.descricao), cell(item.status), item.data_vencimento.strftime("%d/%m/%Y") if item.data_vencimento else "", item.data_pagamento.strftime("%d/%m/%Y") if item.data_pagamento else "", f"{float(item.valor or 0):.2f}"])
    else:
        return redirect(url_for("relatorios.index"))

    response = make_response("\ufeff" + output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = f'attachment; filename="relatorio-{tipo}.csv"'
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


# ══════════════════════════════════════════════════════════════
# OS
# ══════════════════════════════════════════════════════════════
@pages_bp.route("/os")
@pages_bp.route("/os/")
@login_required
def os_lista():
    q             = request.args.get("q", "").strip()
    status_filtro = request.args.get("status", "")
    prio_filtro   = request.args.get("prio", "")
    atendimento_filtro = request.args.get("atendimento", "")
    page          = request.args.get("page", 1, type=int)
    status_map = _configured_status_map()
    priority_options = _configured_priority_options()
    priority_map = _configured_priority_map()
    attendance_options = _configured_attendance_options()
    attendance_map = _configured_attendance_map()

    query = (OrdemServico.query
             .filter(OrdemServico.deletado_em.is_(None))
             .filter(OrdemServico.baixada_em.is_(None))
             .options(joinedload(OrdemServico.cliente)))
    if status_filtro in status_map:
        query = query.filter_by(status=status_filtro)
    if prio_filtro in priority_map:
        query = query.filter_by(prio=prio_filtro)
    if atendimento_filtro in attendance_map:
        query = query.filter_by(tipo_atendimento=atendimento_filtro)
    if q:
        qe = _escape_like(q)
        digitos = sanitize_cpf_cnpj(q)
        filtros = [
            Cliente.nome.ilike(f"%{qe}%"),
            OrdemServico.marca.ilike(f"%{qe}%"),
            OrdemServico.modelo.ilike(f"%{qe}%"),
        ]
        if digitos:
            filtros.extend([
                Cliente.cpf.ilike(f"%{digitos}%"),
                Cliente.cnpj.ilike(f"%{digitos}%"),
                Cliente.telefone.ilike(f"%{digitos}%"),
            ])
        query = query.join(Cliente).filter(db.or_(
            *filtros
        ))
    pag = query.order_by(
        OrdemServico.data_entrada.desc()).paginate(
        page=page, per_page=25, error_out=False)

    pipeline_os = {st: OrdemServico.query.filter_by(
        status=st).filter(OrdemServico.deletado_em.is_(None), OrdemServico.baixada_em.is_(None)).count()
        for st in status_map}

    return render_template("pages/os_lista.html",
        active="os", os_list=pag.items, paginacao=pag,
        q=q, status_filtro=status_filtro, prio_filtro=prio_filtro,
        atendimento_filtro=atendimento_filtro,
        status_map=status_map, priority_options=priority_options,
        priority_map=priority_map, attendance_options=attendance_options,
        attendance_map=attendance_map, hoje_dt=_now_db(), pipeline_os=pipeline_os,
        baixadas=False)


@pages_bp.route("/os/baixadas")
@login_required
def os_baixadas():
    q = request.args.get("q", "").strip()
    status_filtro = request.args.get("status", "")
    prio_filtro = request.args.get("prio", "")
    atendimento_filtro = request.args.get("atendimento", "")
    page = request.args.get("page", 1, type=int)
    status_map = _configured_status_map()
    priority_options = _configured_priority_options()
    priority_map = _configured_priority_map()
    attendance_options = _configured_attendance_options()
    attendance_map = _configured_attendance_map()

    query = (OrdemServico.query
             .filter(OrdemServico.deletado_em.is_(None))
             .filter(OrdemServico.baixada_em.isnot(None))
             .options(joinedload(OrdemServico.cliente)))
    if status_filtro in status_map:
        query = query.filter_by(status=status_filtro)
    if prio_filtro in priority_map:
        query = query.filter_by(prio=prio_filtro)
    if atendimento_filtro in attendance_map:
        query = query.filter_by(tipo_atendimento=atendimento_filtro)
    if q:
        qe = _escape_like(q)
        digitos = sanitize_cpf_cnpj(q)
        filtros = [
            Cliente.nome.ilike(f"%{qe}%"),
            OrdemServico.marca.ilike(f"%{qe}%"),
            OrdemServico.modelo.ilike(f"%{qe}%"),
        ]
        if digitos:
            filtros.extend([
                Cliente.cpf.ilike(f"%{digitos}%"),
                Cliente.cnpj.ilike(f"%{digitos}%"),
                Cliente.telefone.ilike(f"%{digitos}%"),
            ])
        query = query.join(Cliente).filter(db.or_(*filtros))
    pag = query.order_by(OrdemServico.baixada_em.desc(), OrdemServico.data_entrada.desc()).paginate(
        page=page, per_page=25, error_out=False)
    pipeline_os = {st: OrdemServico.query.filter_by(
        status=st).filter(OrdemServico.deletado_em.is_(None), OrdemServico.baixada_em.isnot(None)).count()
        for st in status_map}
    return render_template("pages/os_lista.html",
        active="os", os_list=pag.items, paginacao=pag,
        q=q, status_filtro=status_filtro, prio_filtro=prio_filtro,
        atendimento_filtro=atendimento_filtro,
        status_map=status_map, priority_options=priority_options,
        priority_map=priority_map, attendance_options=attendance_options,
        attendance_map=attendance_map, hoje_dt=_now_db(), pipeline_os=pipeline_os,
        baixadas=True)


@pages_bp.route("/os/kanban")
@login_required
def os_kanban():
    status_map = _configured_status_map()
    priority_map = _configured_priority_map()
    orders = _open_orders_query().order_by(OrdemServico.data_prev.asc(), OrdemServico.data_entrada.asc()).all()
    columns = {key: [] for key in status_map}
    for order in orders:
        columns.setdefault(order.status, []).append(order)
    return render_template(
        "pages/os_kanban.html",
        active="os_kanban",
        status_map=status_map,
        priority_map=priority_map,
        columns=columns,
        waiting_days=_order_waiting_days,
        hoje_dt=_now_db(),
    )


@pages_bp.route("/agenda")
@login_required
def agenda_tecnica():
    tecnico = sanitize_text(request.args.get("tecnico", ""), max_length=120)
    status_map = _configured_status_map()
    tecnicos = (
        Usuario.query
        .filter_by(ativo=True)
        .filter(Usuario.nivel.in_(["admin", "operacional"]))
        .order_by(Usuario.nome)
        .all()
    )
    query = _open_orders_query().filter(~OrdemServico.status.in_(["entregue", "cancelado"]))
    if tecnico:
        query = query.filter(OrdemServico.tecnico_nome == tecnico)
    orders = query.order_by(
        OrdemServico.data_prev.is_(None),
        OrdemServico.data_prev.asc(),
        OrdemServico.prio.desc(),
        OrdemServico.data_entrada.asc(),
    ).all()
    overdue = [item for item in orders if item.data_prev and item.data_prev.replace(tzinfo=None).date() < datetime.now().date()]
    today = [item for item in orders if item.data_prev and item.data_prev.replace(tzinfo=None).date() == datetime.now().date()]
    upcoming = [item for item in orders if item not in overdue and item not in today]
    return render_template(
        "pages/agenda_tecnica.html",
        active="agenda",
        tecnicos=tecnicos,
        tecnico=tecnico,
        status_map=status_map,
        overdue=overdue,
        today=today,
        upcoming=upcoming,
        waiting_days=_order_waiting_days,
    )


@pages_bp.route("/compras-pecas")
@page_nivel_required("admin", "operacional")
def compras_pecas():
    rows = db.session.execute(text(
        "SELECT op.os_id, op.peca_id, op.quantidade, op.valor_unitario, op.link_compra, "
        "p.nome AS peca_nome, p.codigo AS peca_codigo, p.quantidade AS estoque, "
        "p.estoque_minimo AS estoque_minimo, o.numero AS os_numero, o.status AS os_status, "
        "o.data_prev AS data_prev, c.nome AS cliente_nome "
        "FROM os_pecas op "
        "JOIN pecas p ON p.id = op.peca_id "
        "JOIN ordens_servico o ON o.id = op.os_id "
        "JOIN clientes c ON c.id = o.cliente_id "
        "WHERE o.deletado_em IS NULL AND o.baixada_em IS NULL AND p.organization_id=:org "
        "AND p.ativo = 1 AND p.deletado_em IS NULL "
        "ORDER BY o.data_prev IS NULL, o.data_prev ASC, o.data_entrada ASC"
    ), {"org": g.organization_id}).fetchall()
    suggestions = (
        _pecas_ativas_query()
        .filter(Peca.quantidade <= Peca.estoque_minimo)
        .order_by(Peca.quantidade.asc(), Peca.nome.asc())
        .all()
    )
    return render_template(
        "pages/compras_pecas.html",
        active="compras_pecas",
        rows=rows,
        suggestions=suggestions,
        status_map=_configured_status_map(),
    )


@pages_bp.route("/produtividade")
@page_nivel_required("admin", "operacional", "financeiro")
def produtividade():
    status_map = _configured_status_map()
    orders = (
        OrdemServico.query
        .filter(OrdemServico.deletado_em.is_(None))
        .options(joinedload(OrdemServico.cliente))
        .all()
    )
    payments = (
        Transacao.query
        .filter(Transacao.tipo == "receita", Transacao.status == "pago")
        .all()
    )
    revenue_by_os = {}
    for payment in payments:
        if payment.os_id:
            revenue_by_os[payment.os_id] = revenue_by_os.get(payment.os_id, 0) + float(payment.valor or 0)
    by_tech = {}
    for order in orders:
        tech = order.tecnico_nome or "Sem técnico"
        bucket = by_tech.setdefault(tech, {"total": 0, "abertas": 0, "entregues": 0, "atrasadas": 0, "receita": 0.0})
        bucket["total"] += 1
        if order.status == "entregue":
            bucket["entregues"] += 1
        elif not order.baixada:
            bucket["abertas"] += 1
        if order.data_prev and order.status not in {"entregue", "cancelado"}:
            if order.data_prev.replace(tzinfo=None).date() < datetime.now().date():
                bucket["atrasadas"] += 1
        bucket["receita"] += revenue_by_os.get(order.id, 0)
    status_counts = {key: 0 for key in status_map}
    for order in orders:
        status_counts[order.status] = status_counts.get(order.status, 0) + 1
    return render_template(
        "pages/produtividade.html",
        active="produtividade",
        by_tech=by_tech,
        status_counts=status_counts,
        status_map=status_map,
        total_open=sum(1 for item in orders if not item.baixada and item.status not in {"entregue", "cancelado"}),
        total_overdue=sum(
            1 for item in orders
            if item.data_prev and item.status not in {"entregue", "cancelado"}
            and item.data_prev.replace(tzinfo=None).date() < datetime.now().date()
        ),
    )


@pages_bp.route("/bancada")
@page_nivel_required("admin", "operacional")
def bancada():
    usuario = db.session.get(Usuario, session.get("usuario_id"))
    somente_minhas = request.args.get("minhas", "1") != "0"
    query = _open_orders_query().filter(OrdemServico.status.in_(["em_analise", "aguardando_aprovacao", "em_reparo", "pronto"]))
    if somente_minhas:
        query = query.filter(db.or_(OrdemServico.tecnico_nome == usuario.nome, OrdemServico.tecnico_nome.is_(None), OrdemServico.tecnico_nome == ""))
    orders = query.order_by(OrdemServico.data_prev.is_(None), OrdemServico.data_prev.asc(), OrdemServico.data_entrada.asc()).limit(80).all()
    return render_template(
        "pages/bancada.html",
        active="bancada",
        orders=orders,
        somente_minhas=somente_minhas,
        status_map=_configured_status_map(),
        waiting_days=_order_waiting_days,
    )


@pages_bp.route("/checklists")
@page_nivel_required("admin", "operacional")
def checklists_tecnicos():
    templates = (
        ServiceChecklistTemplate.query
        .order_by(ServiceChecklistTemplate.category.asc(), ServiceChecklistTemplate.version.desc())
        .all()
    )
    return render_template("pages/checklists.html", active="checklists", templates=templates)


@pages_bp.route("/checklists/criar", methods=["POST"])
@page_nivel_required("admin")
def checklist_criar_page():
    category = sanitize_text(request.form.get("category", ""), max_length=100).lower()
    raw_items = [sanitize_text(item, max_length=200) for item in request.form.getlist("items[]")]
    items = [item for item in raw_items if item]
    if not category or not items:
        flash("Informe o tipo de aparelho e ao menos um item.", "error")
        return redirect(url_for("pages.checklists_tecnicos"))
    previous = (
        ServiceChecklistTemplate.query
        .filter_by(category=category)
        .order_by(ServiceChecklistTemplate.version.desc())
        .first()
    )
    for old in ServiceChecklistTemplate.query.filter_by(category=category, active=True).all():
        old.active = False
    template = ServiceChecklistTemplate(
        organization_id=g.organization_id,
        category=category,
        version=(previous.version + 1 if previous else 1),
        items=items[:50],
        active=True,
    )
    db.session.add(template)
    registrar("criacao", "checklists", f"Checklist {category} v{template.version} criado")
    db.session.commit()
    flash("Checklist técnico atualizado.", "success")
    return redirect(url_for("pages.checklists_tecnicos"))


@pages_bp.route("/os/nova", methods=["GET"])
@pages_bp.route("/os/adicionar", methods=["GET"])
@login_required
def os_nova():
    return render_template("pages/os_form.html", **_os_form_context())


@pages_bp.route("/coleta", methods=["GET"])
@login_required
def coleta():
    return render_template("pages/coleta.html", **_coleta_form_context())


@pages_bp.route("/coletas/rota", methods=["GET"])
@login_required
def coleta_rota():
    cfg = Configuracao.get()
    coletas = _coletas_para_rota()
    return render_template(
        "pages/coleta_rota.html",
        active="coleta",
        cfg=cfg,
        endereco_assistencia=_endereco_assistencia(cfg),
        coletas=coletas,
        coletas_json=_coleta_rota_payload(coletas),
        status_coleta_labels=STATUS_COLETA_LABELS,
    )


@pages_bp.route("/coleta/agendar", methods=["POST"])
@page_nivel_required("admin", "operacional")
def coleta_agendar():
    data = request.form.to_dict()
    payload, erros = _coleta_cliente_payload(data)
    if erros:
        return _render_coleta_error(data, erros)

    cliente = _cliente_para_coleta(payload)
    coleta_obj = ColetaAgendada(
        cliente_id=cliente.id,
        usuario_id=session["usuario_id"],
        status="agendada",
        data_agendada=payload.get("data_agendada"),
        telefone_contato=payload.get("telefone") or cliente.telefone,
        cep=payload.get("cep"),
        endereco=payload.get("endereco"),
        numero_casa=payload.get("numero_casa"),
        cidade=payload.get("cidade"),
        uf=payload.get("uf"),
        observacoes=payload.get("observacoes"),
    )
    db.session.add(coleta_obj)
    registrar("criacao", "coleta", f"Coleta agendada para {cliente.nome}")
    db.session.commit()
    flash("Coleta agendada. Agora ela aparece para conclusao pelo celular.", "success")
    return redirect(url_for("pages.coleta"))


@pages_bp.route("/coletas/<int:id>/cancelar", methods=["POST"])
@page_nivel_required("admin", "operacional")
def coleta_cancelar(id):
    coleta_obj = db.get_or_404(ColetaAgendada, id)
    if coleta_obj.status == "concluida":
        flash("Coleta concluída não pode ser cancelada.", "error")
        return redirect(url_for("pages.coleta"))
    coleta_obj.status = "cancelada"
    registrar("status", "coleta", f"Coleta #{coleta_obj.id} cancelada")
    db.session.commit()
    flash("Coleta cancelada.", "success")
    return redirect(url_for("pages.coleta"))


@pages_bp.route("/coletas/<int:id>/concluir", methods=["GET"])
@login_required
def coleta_concluir(id):
    coleta_obj = (
        ColetaAgendada.query
        .options(joinedload(ColetaAgendada.cliente))
        .filter_by(id=id)
        .first_or_404()
    )
    if coleta_obj.status == "concluida" and coleta_obj.os_id:
        return redirect(url_for("pages.os_detalhe", id=coleta_obj.os_id))
    return render_template(
        "pages/coleta_concluir.html",
        active="coleta",
        coleta=coleta_obj,
        status_map=_configured_status_map(),
        priority_options=_configured_priority_options(),
        attendance_options=_configured_attendance_options(),
        form_data={},
        form_errors={},
        hoje_iso=_today(),
    )


def _render_coleta_concluir_error(coleta_obj, form_data, form_errors):
    _field, message = next(iter(form_errors.items()))
    flash(message, "error")
    return render_template(
        "pages/coleta_concluir.html",
        active="coleta",
        coleta=coleta_obj,
        status_map=_configured_status_map(),
        priority_options=_configured_priority_options(),
        attendance_options=_configured_attendance_options(),
        form_data=form_data,
        form_errors=form_errors,
        hoje_iso=_today(),
    ), 400


@pages_bp.route("/coletas/<int:id>/concluir", methods=["POST"])
@page_nivel_required("admin", "operacional")
def coleta_concluir_post(id):
    coleta_obj = (
        ColetaAgendada.query
        .options(joinedload(ColetaAgendada.cliente))
        .filter_by(id=id)
        .first_or_404()
    )
    if coleta_obj.status == "concluida" and coleta_obj.os_id:
        flash("Esta coleta já virou OS.", "warning")
        return redirect(url_for("pages.os_detalhe", id=coleta_obj.os_id))
    if coleta_obj.status == "cancelada":
        flash("Coleta cancelada não pode ser concluída.", "error")
        return redirect(url_for("pages.coleta"))

    data = request.form.to_dict()
    erros = {}
    tipo_aparelho = _normalizar_tipo_aparelho(data)
    marca = sanitize_text(data.get("marca", ""), max_length=100)
    modelo = sanitize_text(data.get("modelo", ""), max_length=100)
    defeito_alegado = sanitize_text(data.get("defeito_alegado", ""), max_length=5000)

    if not tipo_aparelho:
        erros["tipo_aparelho"] = "Informe o tipo do equipamento."
    if not marca:
        erros["marca"] = "Informe a marca."
    if not modelo:
        erros["modelo"] = "Informe o modelo."
    if not defeito_alegado:
        erros["defeito_alegado"] = "Informe o defeito alegado."

    fotos, foto_erros = _validar_fotos(request.files.getlist("fotos"))
    if foto_erros:
        erros["fotos"] = foto_erros[0]
    if erros:
        return _render_coleta_concluir_error(coleta_obj, data, erros)

    prio = _valid_or_default(data.get("prio", "normal"), _configured_priority_keys(), "normal")
    tipo_atendimento = _valid_or_default(
        data.get("tipo_atendimento", "coleta"),
        {item["key"] for item in _configured_attendance_options()},
        "coleta",
    )
    garantia_dias = 90
    try:
        garantia_dias = int(data.get("garantia_dias") or 90)
    except (ValueError, TypeError):
        erros["garantia_dias"] = "Garantia invalida."
        return _render_coleta_concluir_error(coleta_obj, data, erros)

    observacoes = sanitize_text(data.get("observacoes", ""), max_length=5000) or ""
    if coleta_obj.observacoes:
        observacoes = (observacoes + "\n\n" if observacoes else "") + f"Coleta: {coleta_obj.observacoes}"
    if coleta_obj.endereco_completo:
        observacoes = (observacoes + "\n\n" if observacoes else "") + f"Endereço da coleta: {coleta_obj.endereco_completo}"

    try:
        _check_order_limit()
    except PermissionError as exc:
        flash(str(exc), "error")
        return redirect(url_for("pages.coleta"))

    os_obj = OrdemServico(
        numero=proximo_numero_os(g.organization_id),
        organization_id=g.organization_id,
        cliente_id=coleta_obj.cliente_id,
        usuario_id=session["usuario_id"],
        tipo_aparelho=tipo_aparelho,
        marca=marca,
        modelo=modelo,
        numero_serie=sanitize_text(data.get("numero_serie", ""), max_length=100) or None,
        defeito_alegado=defeito_alegado,
        defeito_encontrado=sanitize_text(data.get("defeito_encontrado", ""), max_length=5000) or None,
        solucao=sanitize_text(data.get("solucao", ""), max_length=5000) or None,
        observacoes=observacoes or None,
        valor_servico=0,
        valor_pecas=0,
        desconto=0,
        status="recepcao",
        prio=prio,
        tipo_atendimento=tipo_atendimento,
        tecnico_nome=sanitize_text(data.get("tecnico_nome", ""), max_length=120) or None,
        garantia_dias=garantia_dias,
        data_entrada=_now(),
        data_prev=_safe_date(data.get("data_prev")),
    )
    db.session.add(os_obj)
    db.session.flush()
    _salvar_fotos_os(os_obj, coleta_obj, fotos)
    coleta_obj.status = "concluida"
    coleta_obj.os_id = os_obj.id
    db.session.add(OSHistorico(
        os_id=os_obj.id,
        usuario_id=session["usuario_id"],
        status_anterior=None,
        status_novo=os_obj.status,
    ))
    registrar("criacao", "os", f"OS #{os_obj.id:04d} criada a partir da coleta #{coleta_obj.id}")
    db.session.commit()
    flash("Coleta concluida e OS criada com fotos.", "success")
    return redirect(url_for("pages.os_detalhe", id=os_obj.id))


@pages_bp.route("/os/nova", methods=["POST"])
@pages_bp.route("/os/adicionar", methods=["POST"])
@page_nivel_required("admin", "operacional")
def os_criar():
    data = request.form

    try:
        _check_order_limit()
    except PermissionError as exc:
        flash(str(exc), "error")
        return _render_os_form_error("Limite do plano atingido.", "geral", data)

    # Bug #5: validação segura de cliente_id
    cliente_id_raw = data.get("cliente_id", "").strip()
    if not cliente_id_raw or not cliente_id_raw.isdigit():
        flash("Cliente inválido ou não selecionado.", "error")
        return _render_os_form_error("Erro de validacao na OS.", "geral", data)
    cliente_id = int(cliente_id_raw)
    if not Cliente.query.filter_by(id=cliente_id, ativo=True).first():
        flash("Cliente não encontrado.", "error")
        return _render_os_form_error("Erro de validacao na OS.", "geral", data)

    # Bug #6: validar status
    status_raw = data.get("status", "recepcao")
    status_final = _valid_or_default(status_raw, _configured_status_keys(), "recepcao")

    try:
        valor_servico = float(data.get("valor_servico") or 0)
        desconto      = float(data.get("desconto") or 0)
        horas_trabalho = float(data.get("horas_trabalho") or 0)
        custo_hora = float(data.get("custo_hora") or 0)
        garantia_dias = int(data.get("garantia_dias") or 90)
    except (ValueError, TypeError):
        flash("Valores numéricos inválidos no formulário.", "error")
        return _render_os_form_error("Erro de validacao na OS.", "geral", data)

    if not all(math.isfinite(value) for value in (valor_servico, desconto, horas_trabalho, custo_hora)):
        flash("Valores numéricos devem ser finitos.", "error")
        return _render_os_form_error("Erro de validacao na OS.", "geral", data)

    prio = _valid_or_default(data.get("prio", "normal"), _configured_priority_keys(), "normal")
    tipo_atendimento = _valid_or_default(
        data.get("tipo_atendimento", "balcao"),
        {item["key"] for item in _configured_attendance_options()},
        "balcao",
    )
    if valor_servico < 0 or desconto < 0 or horas_trabalho < 0 or custo_hora < 0:
        flash("Valores financeiros não podem ser negativos.", "error")
        return _render_os_form_error("Erro de validacao na OS.", "geral", data)
    if valor_servico > 999_999.99 or desconto > valor_servico:
        flash("Valores financeiros fora do intervalo permitido.", "error")
        return _render_os_form_error("Erro de validacao na OS.", "geral", data)
    tipo_aparelho = _normalizar_tipo_aparelho(data)
    if not tipo_aparelho:
        return _render_os_form_error("Informe o tipo do equipamento.", "tipo_aparelho", data)
    os_obj = OrdemServico(
        numero=proximo_numero_os(g.organization_id),
        organization_id=g.organization_id,
        cliente_id=cliente_id,
        usuario_id=session["usuario_id"],
        tipo_aparelho=tipo_aparelho,
        marca=sanitize_text(data.get("marca", ""), max_length=100) or None,
        modelo=sanitize_text(data.get("modelo", ""), max_length=100) or None,
        numero_serie=sanitize_text(data.get("numero_serie", ""), max_length=100) or None,
        defeito_alegado=sanitize_text(data.get("defeito_alegado", ""), max_length=5000) or None,
        defeito_encontrado=sanitize_text(data.get("defeito_encontrado", ""), max_length=5000) or None,
        solucao=sanitize_text(data.get("solucao", ""), max_length=5000) or None,
        observacoes=sanitize_text(data.get("observacoes", ""), max_length=5000) or None,
        valor_servico=valor_servico,
        valor_pecas=0,
        desconto=desconto,
        horas_trabalho=horas_trabalho,
        custo_hora=custo_hora,
        status=status_final,
        prio=prio,
        tipo_atendimento=tipo_atendimento,
        tecnico_nome=sanitize_text(data.get("tecnico_nome", ""), max_length=120) or None,
        garantia_dias=garantia_dias,
        data_entrada=(_safe_date(data.get("data_entrada")) or _now()),
        data_prev=_safe_date(data.get("data_prev")),
    )
    db.session.add(os_obj)
    db.session.flush()
    db.session.add(OSHistorico(
        os_id=os_obj.id,
        usuario_id=session["usuario_id"],
        status_anterior=None,
        status_novo=os_obj.status,
    ))
    registrar("criacao", "os", f"OS #{os_obj.id:04d} criada",
              f"Cliente: {os_obj.cliente.nome}")
    db.session.commit()
    flash("OS criada!", "success")
    return redirect(url_for("pages.os_detalhe", id=os_obj.id))


@pages_bp.route("/os/<int:id>/editar", methods=["GET"])
@pages_bp.route("/os/editar/<int:id>", methods=["GET"])
@login_required
def os_editar(id):
    # Bug #3: get_or_404 depreciado → db.get_or_404
    os_obj   = db.get_or_404(OrdemServico, id)
    return render_template("pages/os_form.html", **_os_form_context(os_obj))


@pages_bp.route("/os/<int:id>/editar", methods=["POST"])
@pages_bp.route("/os/editar/<int:id>", methods=["POST"])
@page_nivel_required("admin", "operacional")
def os_atualizar(id):
    os_obj = OrdemServico.query.filter_by(id=id).filter(
        OrdemServico.deletado_em.is_(None)).first_or_404()
    data = request.form
    ant  = os_obj.status

    tipo_aparelho = _normalizar_tipo_aparelho(data)
    if not tipo_aparelho:
        return _render_os_form_error("Informe o tipo do equipamento.", "tipo_aparelho", data, os_obj)
    os_obj.tipo_aparelho = tipo_aparelho
    _CAMPOS_CURTOS = ("marca", "modelo", "numero_serie", "tecnico_nome")
    _CAMPOS_LONGOS = ("defeito_alegado", "defeito_encontrado", "solucao", "observacoes")
    for campo in _CAMPOS_CURTOS:
        setattr(os_obj, campo, sanitize_text(data.get(campo, ""), max_length=120) or None)
    for campo in _CAMPOS_LONGOS:
        setattr(os_obj, campo, sanitize_text(data.get(campo, ""), max_length=5000) or None)
    prio = data.get("prio", os_obj.prio)
    os_obj.prio = prio if prio in _configured_priority_keys() else os_obj.prio
    tipo_atendimento = data.get("tipo_atendimento", os_obj.tipo_atendimento)
    attendance_keys = {item["key"] for item in _configured_attendance_options()}
    os_obj.tipo_atendimento = tipo_atendimento if tipo_atendimento in attendance_keys else os_obj.tipo_atendimento

    try:
        vs = float(data.get("valor_servico") or 0)
        dc = float(data.get("desconto") or 0)
        horas_trabalho = float(data.get("horas_trabalho") or 0)
        custo_hora = float(data.get("custo_hora") or 0)
        gd = int(data.get("garantia_dias") or 90)
    except (ValueError, TypeError):
        flash("Valores numéricos inválidos.", "error")
        return _render_os_form_error("Erro de validacao na OS.", "geral", data, os_obj)
    if not all(math.isfinite(value) for value in (vs, dc, horas_trabalho, custo_hora)):
        flash("Valores numéricos devem ser finitos.", "error")
        return _render_os_form_error("Erro de validacao na OS.", "geral", data, os_obj)
    if vs < 0 or dc < 0 or horas_trabalho < 0 or custo_hora < 0:
        flash("Valores financeiros não podem ser negativos.", "error")
        return _render_os_form_error("Erro de validacao na OS.", "geral", data, os_obj)
    if dc > vs:
        flash("Desconto não pode ser maior que o valor do serviço.", "error")
        return _render_os_form_error("Erro de validacao na OS.", "geral", data, os_obj)
    os_obj.valor_servico = vs
    os_obj.desconto      = dc
    os_obj.horas_trabalho = horas_trabalho
    os_obj.custo_hora = custo_hora
    os_obj.garantia_dias = gd

    # Bug #6: validar status na edição também
    novo_st_raw = data.get("status", os_obj.status)
    os_obj.status = novo_st_raw if novo_st_raw in _configured_status_keys() else os_obj.status

    if data.get("data_entrada"):
        d = _safe_date(data["data_entrada"])
        if d is None:
            flash("Data de entrada inválida.", "error")
            return _render_os_form_error("Erro de validacao na OS.", "geral", data, os_obj)
        os_obj.data_entrada = d
    if data.get("data_saida"):
        d = _safe_date(data["data_saida"])
        if d is None:
            flash("Data de saída inválida.", "error")
            return _render_os_form_error("Erro de validacao na OS.", "geral", data, os_obj)
        os_obj.data_saida = d
    if data.get("data_prev"):
        d = _safe_date(data["data_prev"])
        if d is None:
            flash("Data prevista inválida.", "error")
            return _render_os_form_error("Erro de validacao na OS.", "geral", data, os_obj)
        os_obj.data_prev = d

    if os_obj.status == "entregue" and not os_obj.data_saida:
        os_obj.data_saida = _now()
    if os_obj.status == "entregue" and ant != "entregue":
        pagamentos_info = _os_pagamentos_info(os_obj)
        if pagamentos_info["restante"] > 0:
            _registrar_pagamento_os(
                os_obj,
                pagamentos_info["restante"],
                None,
                f"Pagamento na entrega OS #{os_obj.codigo_os}",
            )

    registrar("edicao", "os", f"OS #{os_obj.id:04d} editada")
    db.session.commit()
    flash("OS atualizada!", "success")
    return redirect(url_for("pages.os_detalhe", id=id))


@pages_bp.route("/os/<int:id>")
@pages_bp.route("/os/visualizar/<int:id>")
@login_required
def os_detalhe(id):
    os_obj    = OrdemServico.query.filter_by(id=id).filter(
        OrdemServico.deletado_em.is_(None)).first_or_404()
    historico = (OSHistorico.query.filter_by(os_id=id)
                 .order_by(OSHistorico.criado_em.asc()).all())
    pecas_dict = os_obj.to_dict().get("pecas", [])
    pecas_estoque = _pecas_ativas_query().order_by(Peca.nome).all()
    pecas_estoque_json = _safe_json([
        {"id": p.id, "nome": p.nome, "codigo": p.codigo or "",
         "quantidade": p.quantidade,
         "preco_venda": float(p.preco_venda or p.custo or 0)}
        for p in pecas_estoque])
    laudos = (LaudoTecnico.query
              .filter_by(os_id=os_obj.id)
              .order_by(LaudoTecnico.criado_em.desc())
              .all())
    pagamentos_info = _os_pagamentos_info(os_obj)

    # Bug #8: nivel_usuario não era passado ao template → buttons admin sumiam
    nivel_usuario = session.get("nivel", "operacional")

    return render_template("pages/os_detalhe.html", active="os",
        os=os_obj, status_map=_configured_status_map(), historico=historico,
        pecas_dict=pecas_dict, pecas_estoque_json=pecas_estoque_json,
        pagamentos=pagamentos_info["pagamentos"],
        valor_pago=pagamentos_info["pago"],
        valor_restante=pagamentos_info["restante"],
        priority_map=_configured_priority_map(),
        attendance_map=_configured_attendance_map(),
        nivel_usuario=nivel_usuario, laudos=laudos,
        laudo_status_labels=LAUDO_STATUS_LABELS,
        laudo_tipo_labels=LAUDO_TIPOS_LABELS)


def _form_int(*names, default=None):
    for name in names:
        value = request.form.get(name)
        if value not in (None, ""):
            try:
                return int(value)
            except (TypeError, ValueError):
                return default
    return default


def _form_float(*names, default=0):
    for name in names:
        value = request.form.get(name)
        if value not in (None, ""):
            try:
                return float(str(value).replace(",", "."))
            except (TypeError, ValueError):
                return default
    return default


def _form_purchase_link(*names):
    for name in names:
        value = request.form.get(name)
        if value not in (None, ""):
            link = sanitize_text(value, max_length=1000)
            parsed = urlparse(link)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("Link de compra deve comecar com http:// ou https://")
            return link
    return ""


def _format_moeda(value):
    return f"R$ {float(value or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _wants_json():
    return request.is_json or "json" in (request.headers.get("Accept") or "").lower() or request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _json_or_redirect(os_obj, message, status=200):
    db.session.commit()
    if _wants_json():
        payload = os_obj.to_dict()
        payload.update({"result": True, "message": message})
        return jsonify(payload), status
    flash(message, "success")
    return redirect(url_for("pages.os_detalhe", id=os_obj.id))


def _json_or_error(message, redirect_id=None, status=400):
    if _wants_json():
        return jsonify({"result": False, "message": message, "erro": message}), status
    flash(message, "error")
    if redirect_id:
        return redirect(url_for("pages.os_detalhe", id=redirect_id))
    return redirect(url_for("pages.os_lista"))


def _recalcular_valor_pecas(os_obj):
    total_pecas = db.session.execute(
        text(
            "SELECT COALESCE(SUM(op.quantidade*op.valor_unitario),0) "
            "FROM os_pecas op "
            "JOIN pecas p ON p.id = op.peca_id "
            "WHERE op.os_id=:o AND p.organization_id=:org"
        ),
        {"o": os_obj.id, "org": g.organization_id},
    ).scalar()
    os_obj.valor_pecas = total_pecas or 0


def _os_pagamentos_info(os_obj):
    pagamentos = (
        Transacao.query
        .filter(
            Transacao.os_id == os_obj.id,
            Transacao.tipo == "receita",
            Transacao.status == "pago",
        )
        .order_by(Transacao.data_pagamento.desc(), Transacao.criado_em.desc())
        .all()
    )
    total = float(os_obj.valor_total or 0)
    pago = round(sum(float(item.valor or 0) for item in pagamentos), 2)
    restante = round(max(total - pago, 0), 2)
    return {"pagamentos": pagamentos, "total": total, "pago": pago, "restante": restante}


def _registrar_pagamento_os(os_obj, valor, forma_pagamento=None, descricao=None):
    valor = round(float(valor or 0), 2)
    if valor <= 0:
        raise ValueError("Informe um valor de pagamento maior que zero.")
    pagamento = Transacao(
        organization_id=os_obj.organization_id,
        os_id=os_obj.id,
        tipo="receita",
        categoria="servico",
        descricao=descricao or f"Pagamento OS #{os_obj.codigo_os}",
        valor=valor,
        status="pago",
        forma_pagamento=forma_pagamento,
        data_vencimento=_now(),
        data_pagamento=_now(),
    )
    db.session.add(pagamento)
    return pagamento


@pages_bp.route("/os/adicionarProduto", methods=["POST"])
@pages_bp.route("/os/adicionar-produto", methods=["POST"])
@page_nivel_required("admin", "operacional")
def os_adicionar_produto_alias():
    os_id = _form_int("idOsProduto", "idOs", "os_id")
    peca_id = _form_int("idProduto", "produto", "peca_id")
    quantidade = _form_int("quantidade", default=1)
    valor_unitario = _form_float("preco", "valor_unitario", default=0)
    try:
        link_compra = _form_purchase_link("link_compra", "link_compra_peca")
    except ValueError as exc:
        return _json_or_error(str(exc), os_id)
    if not os_id or not peca_id:
        return _json_or_error("Informe OS e produto.", os_id)
    if quantidade is None or quantidade <= 0:
        return _json_or_error("Quantidade deve ser maior que zero.", os_id)
    if valor_unitario < 0:
        return _json_or_error("Valor unitário não pode ser negativo.", os_id)

    os_obj = OrdemServico.query.filter_by(id=os_id).filter(OrdemServico.deletado_em.is_(None)).first_or_404()
    peca = _pecas_ativas_query().filter(Peca.id == peca_id).first_or_404()
    existente = db.session.execute(
        text(
            "SELECT op.quantidade FROM os_pecas op "
            "JOIN pecas p ON p.id = op.peca_id "
            "WHERE op.os_id=:o AND op.peca_id=:p AND p.organization_id=:org"
        ),
        {"o": os_obj.id, "p": peca.id, "org": g.organization_id},
    ).fetchone()
    quantidade_atual = existente.quantidade if existente else 0
    diferenca = quantidade - quantidade_atual
    if diferenca > 0 and peca.quantidade < diferenca:
        return _json_or_error(f"Estoque insuficiente. Disponível: {peca.quantidade}.", os_obj.id)
    if diferenca:
        antes = peca.quantidade
        peca.quantidade -= diferenca
        record_movement(
            peca,
            session["usuario_id"],
            "order_consumption" if diferenca > 0 else "order_return",
            antes,
            peca.quantidade,
            f"Produto atualizado na OS #{os_obj.id}",
            order_id=os_obj.id,
        )
    if existente:
        db.session.execute(
            text("UPDATE os_pecas SET quantidade=:q, valor_unitario=:v, link_compra=:l WHERE os_id=:o AND peca_id=:p"),
            {"q": quantidade, "v": valor_unitario, "l": link_compra or None, "o": os_obj.id, "p": peca.id},
        )
    else:
        db.session.execute(
            text("INSERT INTO os_pecas (os_id, peca_id, quantidade, valor_unitario, custo_unitario, link_compra) VALUES (:o, :p, :q, :v, :c, :l)"),
            {"o": os_obj.id, "p": peca.id, "q": quantidade, "v": valor_unitario, "c": float(peca.custo or 0), "l": link_compra or None},
        )
    os_obj.desconto = 0
    _recalcular_valor_pecas(os_obj)
    registrar("edicao", "os", f"Produto {peca.nome} atualizado na OS #{os_obj.id:04d}")
    return _json_or_redirect(os_obj, "Produto adicionado a OS.")


@pages_bp.route("/os/excluirProduto", methods=["POST"])
@pages_bp.route("/os/excluir-produto", methods=["POST"])
@page_nivel_required("admin", "operacional")
def os_excluir_produto_alias():
    os_id = _form_int("idOs", "idOsProduto", "os_id")
    peca_id = _form_int("idProduto", "produto", "peca_id")
    if not os_id or not peca_id:
        return _json_or_error("Informe OS e produto.", os_id)
    os_obj = OrdemServico.query.filter_by(id=os_id).filter(OrdemServico.deletado_em.is_(None)).first_or_404()
    linha = db.session.execute(
        text(
            "SELECT op.quantidade FROM os_pecas op "
            "JOIN pecas p ON p.id = op.peca_id "
            "WHERE op.os_id=:o AND op.peca_id=:p AND p.organization_id=:org"
        ),
        {"o": os_obj.id, "p": peca_id, "org": g.organization_id},
    ).fetchone()
    if not linha:
        return _json_or_error("Produto não encontrado nesta OS.", os_obj.id, 404)
    peca = db.get_or_404(Peca, peca_id)
    antes = peca.quantidade
    peca.quantidade += linha.quantidade
    record_movement(peca, session["usuario_id"], "order_return", antes, peca.quantidade, f"Produto removido da OS #{os_obj.id}", order_id=os_obj.id)
    db.session.execute(text("DELETE FROM os_pecas WHERE os_id=:o AND peca_id=:p"), {"o": os_obj.id, "p": peca_id})
    os_obj.desconto = 0
    _recalcular_valor_pecas(os_obj)
    registrar("edicao", "os", f"Produto {peca.nome} removido da OS #{os_obj.id:04d}")
    return _json_or_redirect(os_obj, "Produto removido da OS.")


@pages_bp.route("/os/adicionarServico", methods=["POST"])
@pages_bp.route("/os/adicionar-servico", methods=["POST"])
@page_nivel_required("admin", "operacional")
def os_adicionar_servico_alias():
    os_id = _form_int("idOsServico", "idOs", "os_id")
    quantidade = _form_int("quantidade", default=1)
    preco = _form_float("preco", "valor", "valor_unitario", default=0)
    descricao = sanitize_text(request.form.get("descricao") or request.form.get("servico") or "", max_length=300)
    servico_id = _form_int("idServico", "servico_id")
    if not os_id:
        return _json_or_error("Informe a OS.", os_id)
    if quantidade is None or quantidade <= 0 or preco < 0:
        return _json_or_error("Serviço, quantidade ou valor inválido.", os_id)
    if servico_id and not descricao:
        servico = _servicos_ativos_query().filter(DefeitoPadrao.id == servico_id).first_or_404()
        descricao = servico.sintoma or servico.solucao or f"Serviço #{servico.id}"
    os_obj = OrdemServico.query.filter_by(id=os_id).filter(OrdemServico.deletado_em.is_(None)).first_or_404()
    subtotal = round(quantidade * preco, 2)
    os_obj.valor_servico = float(os_obj.valor_servico or 0) + subtotal
    os_obj.desconto = 0
    if descricao:
        linha = f"Serviço: {descricao} ({quantidade} x R$ {preco:.2f})"
        os_obj.observacoes = f"{os_obj.observacoes or ''}\n{linha}".strip()
    registrar("edicao", "os", f"Serviço adicionado à OS #{os_obj.id:04d}")
    return _json_or_redirect(os_obj, "Serviço adicionado à OS.")


@pages_bp.route("/os/excluirServico", methods=["POST"])
@pages_bp.route("/os/excluir-servico", methods=["POST"])
@page_nivel_required("admin", "operacional")
def os_excluir_servico_alias():
    os_id = _form_int("idOs", "idOsServico", "os_id")
    valor = _form_float("valor", "preco", "subtotal", default=0)
    if not os_id:
        return _json_or_error("Informe a OS.", os_id)
    os_obj = OrdemServico.query.filter_by(id=os_id).filter(OrdemServico.deletado_em.is_(None)).first_or_404()
    os_obj.valor_servico = max(0, float(os_obj.valor_servico or 0) - max(0, valor))
    os_obj.desconto = 0
    registrar("edicao", "os", f"Serviço removido/abatido da OS #{os_obj.id:04d}")
    return _json_or_redirect(os_obj, "Serviço removido da OS.")


@pages_bp.route("/os/adicionarDesconto", methods=["POST"])
@pages_bp.route("/os/adicionar-desconto", methods=["POST"])
@page_nivel_required("admin", "operacional")
def os_adicionar_desconto_alias():
    os_id = _form_int("idOs", "os_id")
    desconto = _form_float("resultado", "valor_desconto", "desconto", default=0)
    tipo = (request.form.get("tipoDesconto") or request.form.get("tipo_desconto") or "valor").lower()
    if not os_id:
        return _json_or_error("Informe a OS.", os_id)
    os_obj = OrdemServico.query.filter_by(id=os_id).filter(OrdemServico.deletado_em.is_(None)).first_or_404()
    base = float(os_obj.valor_servico or 0) + float(os_obj.valor_pecas or 0)
    if tipo in {"porcentagem", "percentual", "%"}:
        desconto = round(base * desconto / 100, 2)
    if desconto < 0 or desconto > base:
        return _json_or_error("Desconto inválido para esta OS.", os_obj.id)
    os_obj.desconto = desconto
    registrar("edicao", "os", f"Desconto aplicado na OS #{os_obj.id:04d}")
    return _json_or_redirect(os_obj, "Desconto aplicado.")


@pages_bp.route("/os/faturar", methods=["POST"])
@page_nivel_required("admin", "financeiro", "operacional")
def os_faturar_alias():
    os_id = _form_int("idOs", "os_id")
    if not os_id:
        return _json_or_error("Informe a OS.", os_id)
    os_obj = OrdemServico.query.filter_by(id=os_id).filter(OrdemServico.deletado_em.is_(None)).first_or_404()
    status = request.form.get("status") or "pendente"
    if status not in {"pendente", "pago"}:
        status = "pendente"
    transacao = Transacao.query.filter_by(os_id=os_obj.id, tipo="receita").first()
    if not transacao:
        transacao = Transacao(organization_id=g.organization_id, os_id=os_obj.id, tipo="receita")
        db.session.add(transacao)
    transacao.categoria = "servico"
    transacao.descricao = sanitize_text(request.form.get("descricao") or f"OS #{os_obj.id:04d}", max_length=300)
    transacao.valor = os_obj.valor_total
    transacao.forma_pagamento = sanitize_text(request.form.get("forma_pagamento", ""), max_length=50) or None
    transacao.status = status
    transacao.data_vencimento = _safe_date(request.form.get("vencimento") or request.form.get("data_vencimento")) or _now()
    transacao.data_pagamento = _safe_date(request.form.get("recebimento") or request.form.get("data_pagamento")) if status == "pago" else None
    registrar("financeiro", "os", f"OS #{os_obj.id:04d} faturada")
    return _json_or_redirect(os_obj, "OS faturada.")


@pages_bp.route("/os/<int:id>/pagamento-parcial", methods=["POST"])
@page_nivel_required("admin", "financeiro", "operacional")
def os_pagamento_parcial(id):
    os_obj = OrdemServico.query.filter_by(id=id).filter(
        OrdemServico.deletado_em.is_(None)).first_or_404()
    valor = _form_float("valor", "valor_pago", "pagamento", default=0)
    info = _os_pagamentos_info(os_obj)
    if valor <= 0:
        return _json_or_error("Informe um valor de pagamento maior que zero.", os_obj.id)
    if valor > info["restante"] + 0.01:
        return _json_or_error(
            f"O valor informado é maior que o restante da OS ({_format_moeda(info['restante'])}).",
            os_obj.id,
        )
    forma = sanitize_text(request.form.get("forma_pagamento", ""), max_length=50) or None
    descricao = sanitize_text(
        request.form.get("descricao") or f"Pagamento parcial OS #{os_obj.codigo_os}",
        max_length=300,
    )
    _registrar_pagamento_os(os_obj, valor, forma, descricao)
    registrar("pagamento", "os", f"Pagamento parcial de {_format_moeda(valor)} na OS #{os_obj.codigo_os}")
    return _json_or_redirect(os_obj, "Pagamento parcial registrado.")


@pages_bp.route("/os/<int:id>/baixar", methods=["POST"])
@page_nivel_required("admin", "operacional")
def os_baixar(id):
    os_obj = OrdemServico.query.filter_by(id=id).filter(
        OrdemServico.deletado_em.is_(None)).first_or_404()
    if not os_obj.baixada_em:
        os_obj.baixada_em = _now()
        os_obj.baixada_por_id = session.get("usuario_id")
        os_obj.baixa_observacao = sanitize_text(request.form.get("observacao", ""), max_length=300) or None
        registrar("status", "os", f"OS #{os_obj.codigo_os} baixada")
        db.session.commit()
        flash("OS baixada e removida da lista principal.", "success")
    return redirect(url_for("pages.os_baixadas"))


@pages_bp.route("/os/<int:id>/restaurar", methods=["POST"])
@page_nivel_required("admin", "operacional")
def os_restaurar(id):
    os_obj = OrdemServico.query.filter_by(id=id).filter(
        OrdemServico.deletado_em.is_(None)).first_or_404()
    if os_obj.baixada_em:
        os_obj.baixada_em = None
        os_obj.baixada_por_id = None
        os_obj.baixa_observacao = None
        registrar("status", "os", f"OS #{os_obj.codigo_os} restaurada")
        db.session.commit()
        flash("OS restaurada para a lista principal.", "success")
    return redirect(url_for("pages.os_detalhe", id=id))


@pages_bp.route("/os/<int:id>/status", methods=["POST"])
@page_nivel_required("admin", "operacional")
def os_status(id):
    from app.services.message_templates import render_template as render_message_template
    from app.services.notifications import enqueue_email, enqueue_whatsapp, process_notification
    from app.utils.whatsapp import mensagem_os_pronta
    os_obj  = OrdemServico.query.filter_by(id=id).filter(
        OrdemServico.deletado_em.is_(None)).first_or_404()
    novo_st = request.form.get("status")
    antigo  = os_obj.status

    # Bug #6: rejeitar status inválido
    if novo_st and novo_st not in _configured_status_keys():
        flash(f"Status inválido: '{novo_st}'.", "error")
        return redirect(request.form.get("next") or url_for("pages.os_detalhe", id=id))

    if novo_st == "entregue" and antigo != "entregue":
        pagamentos_info = _os_pagamentos_info(os_obj)
        if pagamentos_info["restante"] > 0.01:
            flash(
                f"Esta OS ainda tem saldo em aberto ({_format_moeda(pagamentos_info['restante'])}). "
                "Registre o pagamento total antes de finalizar.",
                "error",
            )
            return redirect(request.form.get("next") or url_for("pages.os_detalhe", id=id))

    if novo_st and novo_st != antigo:
        os_obj.status = novo_st
        if novo_st == "entregue" and not os_obj.data_saida:
            os_obj.data_saida = _now()

        db.session.add(OSHistorico(
            os_id=os_obj.id, usuario_id=session["usuario_id"],
            status_anterior=antigo, status_novo=novo_st,
        ))

        # Cancelamento: devolve estoque
        if novo_st == "cancelado":
            from sqlalchemy import text as sqla_text
            rows = db.session.execute(
                sqla_text("SELECT peca_id, quantidade FROM os_pecas WHERE os_id=:id"),
                {"id": os_obj.id},
            ).fetchall()
            for row in rows:
                p = db.session.get(Peca, row.peca_id)
                if p:
                    p.quantidade += row.quantidade

        registrar("status", "os",
                  f"OS #{os_obj.id:04d}: {antigo} → {novo_st}")
        db.session.commit()

        context = {
            "cliente": os_obj.cliente.nome if os_obj.cliente else "cliente",
            "os_id": f"{os_obj.id:04d}",
            "status": STATUS_OS_LABELS.get(novo_st, novo_st),
            "equipamento": " ".join(filter(None, [os_obj.tipo_aparelho, os_obj.marca, os_obj.modelo])),
            "total": f"R$ {os_obj.valor_total:.2f}",
            "empresa": Configuracao.get().nome_empresa,
        }
        history_count = OSHistorico.query.filter_by(os_id=os_obj.id).count()
        if os_obj.cliente and os_obj.cliente.email:
            event_type = f"os_status_{novo_st}"
            subject, body = render_message_template(
                event_type, "email", context,
                default_subject=f"Atualizacao da OS #{os_obj.id:04d}",
                default_body=(
                    f"Ola, {os_obj.cliente.nome}.\n\n"
                    f"A OS #{os_obj.id:04d} agora esta em: {STATUS_OS_LABELS.get(novo_st, novo_st)}.\n"
                    "Entre em contato com a assistencia em caso de duvidas."
                ),
            )
            email_notification, _ = enqueue_email(
                os_obj.organization_id, os_obj.cliente.email, subject, body,
                event_type, f"os-email-{os_obj.id}-{history_count}",
            )
            process_notification(email_notification.id)

        # Notificação WhatsApp orientada por templates versionados.
        whatsapp_event = f"os_status_{novo_st}"
        whatsapp_message = None
        if novo_st in {"recepcao", "aguardando_aprovacao", "em_reparo", "pronto", "entregue"}:
            _subject, whatsapp_message = render_message_template(
                whatsapp_event, "whatsapp", context,
                default_body=mensagem_os_pronta(os_obj) if novo_st == "pronto" else (
                    f"Olá, {context['cliente']}! A OS #{context['os_id']} agora está em: {context['status']}."
                ),
            )

        if whatsapp_message and whatsapp_event:
            if os_obj.cliente and os_obj.cliente.telefone:
                notification, _created = enqueue_whatsapp(
                    os_obj.organization_id,
                    os_obj.cliente.telefone,
                    whatsapp_message,
                    whatsapp_event,
                    f"{whatsapp_event}-{os_obj.id}-{history_count}",
                )
                notification = process_notification(notification.id)
                resultado = notification.payload.get("last_result", {})
                if resultado["sucesso"]:
                    flash("Status atualizado! Cliente notificado via WhatsApp.", "success")
                elif resultado.get("modo") == "simulacao":
                    flash(
                        f'Status atualizado! <a href="{resultado["link"]}" '
                        f'target="_blank">Enviar WhatsApp manualmente →</a>',
                        "success",
                    )
                else:
                    flash(
                        f'Status atualizado! Falha no WhatsApp: {resultado.get("erro","")}'
                        f' — <a href="{resultado["link"]}" target="_blank">Enviar manualmente →</a>',
                        "warning",
                    )
            else:
                flash("Status atualizado! (Cliente sem telefone cadastrado)", "success")
        else:
            flash(f"Status: {STATUS_MAP.get(novo_st, novo_st)}", "success")

    return redirect(request.form.get("next") or url_for("pages.os_detalhe", id=id))


@pages_bp.route("/os/<int:id>/pdf")
@pages_bp.route("/os/imprimir/<int:id>")
@pages_bp.route("/os/imprimirTermica/<int:id>")
@login_required
def os_pdf(id):
    import io

    from flask import send_file

    from app.utils.pdf_gen import gerar_pdf_os
    os_obj = OrdemServico.query.filter_by(id=id).filter(
        OrdemServico.deletado_em.is_(None)).first_or_404()
    try:
        pdf = gerar_pdf_os(os_obj)
    except RuntimeError as e:
        flash(str(e), "error")
        return redirect(request.form.get("next") or url_for("pages.os_detalhe", id=id))
    return send_file(
        io.BytesIO(pdf), mimetype="application/pdf",
        as_attachment=False, download_name=f"OS_{os_obj.codigo_os}.pdf",
    )


@pages_bp.route("/os/<int:id>/imprimir")
@login_required
def os_print(id):
    os_obj = OrdemServico.query.filter_by(id=id).filter(
        OrdemServico.deletado_em.is_(None)).first_or_404()
    return render_template(
        "pages/os_print.html",
        active="os",
        os=os_obj,
        pdf_url=url_for("pages.os_pdf", id=id),
    )


@pages_bp.route("/uploads/os-fotos/<int:foto_id>")
@login_required
def os_foto(foto_id):
    foto = db.get_or_404(OSFoto, foto_id)
    base = Path(current_app.instance_path) / "uploads"
    target = (base / foto.filename).resolve()
    if not str(target).startswith(str(base.resolve())):
        abort(404)
    from app.services.object_storage import hydrate
    try:
        hydrate(foto.filename, target)
    except Exception:
        abort(404)
    if not target.exists():
        abort(404)
    return send_from_directory(base, foto.filename)


@pages_bp.route("/os/<int:id>/deletar", methods=["POST"])
@page_nivel_required("admin")
def os_deletar(id):
    os_obj = OrdemServico.query.filter_by(id=id).filter(
        OrdemServico.deletado_em.is_(None)).first_or_404()
    if session.get("nivel") != "admin":
        flash("Apenas administradores podem excluir OS.", "error")
        return redirect(url_for("pages.os_detalhe", id=id))

    from sqlalchemy import text as sqla_text
    rows = db.session.execute(
        sqla_text("SELECT peca_id, quantidade FROM os_pecas WHERE os_id=:id"),
        {"id": os_obj.id},
    ).fetchall()
    for row in rows:
        p = db.session.get(Peca, row.peca_id)
        if p:
            p.quantidade += row.quantidade

    registrar("exclusao", "os", f"OS #{os_obj.id:04d} excluída")
    os_obj.deletado_em = _now()
    db.session.commit()
    flash("OS removida.", "success")
    return redirect(url_for("pages.os_lista"))


# ══════════════════════════════════════════════════════════════
# CLIENTES
# ══════════════════════════════════════════════════════════════
@pages_bp.route("/clientes")
@pages_bp.route("/clientes/")
@login_required
def clientes():
    return _render_clientes_page()


@pages_bp.route("/clientes/adicionar")
@login_required
def clientes_adicionar_alias():
    return render_template(
        "pages/zokyo_cliente_form.html",
        active="clientes",
        cliente=None,
        action_url=url_for("pages.cliente_criar"),
    )


@pages_bp.route("/clientes/editar/<int:id>")
@login_required
def clientes_editar_alias(id):
    cliente = db.get_or_404(Cliente, id)
    return render_template(
        "pages/zokyo_cliente_form.html",
        active="clientes",
        cliente=cliente,
        action_url=url_for("pages.cliente_editar", id=id),
    )


@pages_bp.route("/clientes/visualizar/<int:id>")
@login_required
def clientes_visualizar_alias(id):
    cliente = db.get_or_404(Cliente, id)
    os_count = OrdemServico.query.filter_by(cliente_id=cliente.id).filter(
        OrdemServico.deletado_em.is_(None)).count()
    return render_template(
        "pages/zokyo_cliente_detalhe.html",
        active="clientes",
        cliente=cliente,
        os_count=os_count,
    )


def _render_clientes_page(cliente_form_state=None, status=200):
    q            = request.args.get("q", "").strip()
    ativo_filtro = request.args.get("ativo", "1")
    page         = request.args.get("page", 1, type=int)
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
        query = query.filter(db.or_(
            *filtros
        ))
    if ativo_filtro == "1":
        query = query.filter_by(ativo=True)
    if ativo_filtro == "0":
        query = query.filter_by(ativo=False)
    pag  = query.order_by(Cliente.nome).paginate(
        page=page, per_page=25, error_out=False)
    lista = pag.items
    for cli in lista:
        cli.os_count = OrdemServico.query.filter_by(
            cliente_id=cli.id).filter(
            OrdemServico.deletado_em.is_(None)).count()
    clientes_payload = []
    for c in lista:
        item = c.to_dict()
        item["os_count"] = c.os_count
        clientes_payload.append(item)
    clientes_json = _safe_json(clientes_payload)
    return render_template("pages/clientes.html", active="clientes",
        clientes=lista, paginacao=pag, clientes_json=clientes_json,
        cliente_form_state_json=_safe_json(cliente_form_state or {}),
        q=q, ativo_filtro=ativo_filtro), status


def _cliente_form_state(mode, form_data, form_errors, edit_id=None):
    raw_doc = (
        form_data.get("cpf_cnpj")
        or form_data.get("documento")
        or form_data.get("cpf")
        or form_data.get("cnpj")
        or ""
    )
    data = {
        "id": edit_id,
        "nome": form_data.get("nome", ""),
        "cpf_cnpj_raw": raw_doc,
        "telefone": form_data.get("telefone", ""),
        "cep": form_data.get("cep", ""),
        "endereco": form_data.get("endereco", ""),
        "numero_casa": form_data.get("numero_casa", ""),
        "cidade": form_data.get("cidade", ""),
        "uf": form_data.get("uf", ""),
        "ativo": str(form_data.get("ativo", "1")) != "0",
    }
    return {"mode": mode, "id": edit_id, "data": data, "errors": form_errors}


def _render_cliente_form_error(mode, form_data, form_errors, edit_id=None):
    _field, message = next(iter(form_errors.items()))
    flash(message, "error")
    return _render_clientes_page(
        cliente_form_state=_cliente_form_state(mode, form_data, form_errors, edit_id=edit_id),
        status=400,
    )


@pages_bp.route("/clientes/novo", methods=["POST"])
@pages_bp.route("/clientes/adicionar", methods=["POST"])
@page_nivel_required("admin", "operacional", "cadastro")
def cliente_criar():
    from app.routes.clientes import _duplicidade_cliente, _validar_e_sanitizar

    data = request.form.to_dict()
    d, erros = _validar_e_sanitizar(data)
    if erros:
        return _render_cliente_form_error("new", data, erros)

    field, msg = _duplicidade_cliente(d)
    if msg:
        return _render_cliente_form_error("new", data, {field: msg})

    c = Cliente(**d)
    db.session.add(c)
    registrar("criacao", "clientes", f"Cliente criado: {d['nome']}")
    db.session.commit()
    flash("Cliente salvo!", "success")
    return redirect(url_for("pages.clientes"))


@pages_bp.route("/clientes/<int:id>/editar", methods=["POST"])
@pages_bp.route("/clientes/editar/<int:id>", methods=["POST"])
@page_nivel_required("admin", "operacional", "cadastro")
def cliente_editar(id):
    from app.routes.clientes import _duplicidade_cliente, _validar_e_sanitizar

    c    = db.get_or_404(Cliente, id)
    data = request.form.to_dict()
    d, erros = _validar_e_sanitizar(data)
    if erros:
        return _render_cliente_form_error("edit", data, erros, edit_id=c.id)

    field, msg = _duplicidade_cliente(d, cliente_id=c.id)
    if msg:
        return _render_cliente_form_error("edit", data, {field: msg}, edit_id=c.id)

    for campo, valor in d.items():
        setattr(c, campo, valor)
    registrar("edicao", "clientes", f"Cliente editado: {c.nome}")
    db.session.commit()
    flash("Cliente atualizado!", "success")
    return redirect(url_for("pages.clientes"))


@pages_bp.route("/clientes/<int:id>/deletar", methods=["POST"])
@pages_bp.route("/clientes/excluir/<int:id>", methods=["POST"])
@page_nivel_required("admin")
def cliente_deletar(id):
    c = db.get_or_404(Cliente, id)
    c.ativo = False
    registrar("arquivamento", "clientes", f"Cliente arquivado: {c.nome}; histórico preservado.")
    db.session.commit()
    flash("Cliente arquivado. OS, laudos e financeiro foram preservados.", "success")
    return redirect(url_for("pages.clientes"))


# ══════════════════════════════════════════════════════════════
# ESTOQUE
# ══════════════════════════════════════════════════════════════
@pages_bp.route("/estoque")
@pages_bp.route("/produtos")
@pages_bp.route("/produtos/")
@login_required
def estoque():
    q              = request.args.get("q", "").strip()
    cat_filtro     = request.args.get("cat", "")
    critico_filtro = request.args.get("critico", "")
    page           = request.args.get("page", 1, type=int)
    query = _pecas_ativas_query()
    if q:
        qe = _escape_like(q)
        query = query.filter(db.or_(
            Peca.nome.ilike(f"%{qe}%"),
            Peca.codigo.ilike(f"%{qe}%"),
        ))
    if cat_filtro:
        query = query.filter_by(categoria=cat_filtro)
    if critico_filtro:
        query = query.filter(Peca.quantidade <= Peca.estoque_minimo)
    pag = query.order_by(Peca.nome).paginate(
        page=page, per_page=30, error_out=False)
    categorias  = [r[0] for r in db.session.query(
        Peca.categoria).filter(Peca.ativo.is_(True), Peca.deletado_em.is_(None)).distinct().all() if r[0]]
    valor_total = sum(
        float(p.custo or 0) * p.quantidade for p in _pecas_ativas_query().all())
    criticos    = _pecas_ativas_query().filter(
        Peca.quantidade <= Peca.estoque_minimo).all()
    pecas_json  = _safe_json([
        {"id": p.id, "nome": p.nome, "quantidade": p.quantidade,
         "estoque_minimo": p.estoque_minimo,
         "codigo": p.codigo or "", "categoria": p.categoria or "",
         "localizacao": p.localizacao or "", "margem": float(p.margem or 0),
         "custo": float(p.custo or 0)}
        for p in pag.items])
    return render_template("pages/estoque.html", active="estoque",
        pecas=pag.items, paginacao=pag, pecas_json=pecas_json,
        categorias=categorias, valor_total=valor_total, criticos=criticos,
        q=q, cat_filtro=cat_filtro, critico_filtro=critico_filtro,
        estoque_page_title="Produtos" if request.path.startswith("/produtos") else "Estoque",
        estoque_heading="Produtos" if request.path.startswith("/produtos") else "Estoque de peças")


@pages_bp.route("/produtos/adicionar")
@login_required
def produtos_adicionar_alias():
    return render_template(
        "pages/zokyo_produto_form.html",
        active="estoque",
        produto=None,
        action_url=url_for("pages.peca_criar"),
    )


@pages_bp.route("/produtos/editar/<int:id>")
@login_required
def produtos_editar_alias(id):
    produto = _pecas_ativas_query().filter(Peca.id == id).first_or_404()
    return render_template(
        "pages/zokyo_produto_form.html",
        active="estoque",
        produto=produto,
        action_url=url_for("pages.peca_editar", id=id),
    )


@pages_bp.route("/produtos/visualizar/<int:id>")
@login_required
def produtos_visualizar_alias(id):
    produto = _pecas_ativas_query().filter(Peca.id == id).first_or_404()
    return render_template(
        "pages/zokyo_produto_detalhe.html",
        active="estoque",
        produto=produto,
    )


@pages_bp.route("/arquivos")
@pages_bp.route("/arquivos/")
@page_nivel_required("admin", "operacional", "consulta")
def arquivos():
    q = request.args.get("q", "").strip().lower()
    rows = []

    os_fotos = (
        OSFoto.query
        .join(OrdemServico)
        .options(joinedload(OSFoto.os).joinedload(OrdemServico.cliente))
        .order_by(OSFoto.criado_em.desc())
        .limit(80)
        .all()
    )
    for foto in os_fotos:
        os_obj = foto.os
        cliente = os_obj.cliente.nome if os_obj and os_obj.cliente else "-"
        rows.append({
            "codigo": f"FOS{foto.id:04d}",
            "nome": foto.original_filename or "Foto da OS",
            "modulo": "OS",
            "referencia": f"OS #{foto.os_id:04d} - {cliente}",
            "data": foto.criado_em,
            "tamanho": f"{round((foto.tamanho_bytes or 0) / 1024, 1)} KB",
            "acoes": [
                {"label": "Ver", "title": "Visualizar Arquivo", "url": url_for("pages.arquivos_visualizar_alias", id=foto.id), "class": "btn-nwe"},
                {"label": "Abrir", "title": "Abrir Arquivo", "url": url_for("pages.os_foto", foto_id=foto.id), "class": "btn-nwe6", "target_blank": True},
            ],
        })

    laudo_fotos = (
        LaudoFoto.query
        .join(LaudoTecnico)
        .options(joinedload(LaudoFoto.laudo).joinedload(LaudoTecnico.cliente))
        .order_by(LaudoFoto.criado_em.desc())
        .limit(80)
        .all()
    )
    for foto in laudo_fotos:
        laudo = foto.laudo
        cliente = laudo.cliente.nome if laudo and laudo.cliente else "-"
        laudo_ref = laudo.numero or f"Laudo #{laudo.id}"
        rows.append({
            "codigo": f"FL{foto.id:04d}",
            "nome": foto.nome_original or foto.legenda or "Foto do laudo",
            "modulo": "Laudos",
            "referencia": f"{laudo_ref} - {cliente}",
            "data": foto.criado_em,
            "tamanho": f"{round((foto.tamanho_bytes or 0) / 1024, 1)} KB",
            "acao": "Abrir",
            "acao_url": url_for("laudos.foto", foto_id=foto.id),
        })

    laudos_pdf = (
        LaudoTecnico.query
        .filter(LaudoTecnico.pdf_path.isnot(None))
        .options(joinedload(LaudoTecnico.cliente))
        .order_by(LaudoTecnico.pdf_gerado_em.desc())
        .limit(80)
        .all()
    )
    for laudo in laudos_pdf:
        laudo_ref = laudo.numero or f"Laudo #{laudo.id}"
        rows.append({
            "codigo": f"PDF{laudo.id:04d}",
            "nome": f"{laudo_ref}.pdf",
            "modulo": "Laudos",
            "referencia": laudo.cliente.nome if laudo.cliente else "-",
            "data": laudo.pdf_gerado_em or laudo.finalizado_em,
            "tamanho": "-",
            "acao": "Baixar",
            "acao_url": url_for("laudos.baixar_pdf", id=laudo.id),
        })

    assinaturas = (
        OrderSignature.query
        .filter(OrderSignature.revoked_at.is_(None))
        .join(OrdemServico)
        .options(joinedload(OrderSignature.order).joinedload(OrdemServico.cliente))
        .order_by(OrderSignature.created_at.desc())
        .limit(80)
        .all()
    )
    for assinatura in assinaturas:
        os_obj = assinatura.order
        cliente = os_obj.cliente.nome if os_obj and os_obj.cliente else assinatura.signer_name
        rows.append({
            "codigo": f"ASS{assinatura.id:04d}",
            "nome": f"Assinatura OS #{assinatura.order_id:04d}",
            "modulo": "Assinaturas",
            "referencia": cliente,
            "data": assinatura.created_at,
            "tamanho": f"{round((assinatura.size_bytes or 0) / 1024, 1)} KB",
            "acao": "Abrir",
            "acao_url": url_for("os.baixar_assinatura", id=assinatura.order_id),
        })

    if q:
        rows = [
            row for row in rows
            if q in " ".join(str(value or "").lower() for value in row.values())
        ]
    rows = sorted(rows, key=lambda row: row["data"] or datetime.min, reverse=True)[:120]

    return render_template(
        "pages/zokyo_modulo.html",
        active="arquivos",
        title="Arquivos",
        breadcrumb="Arquivos",
        subtitle="Fotos, PDFs, comprovantes e assinaturas vinculados ao atendimento.",
        empty="Nenhum arquivo encontrado.",
        search=request.args.get("q", "").strip(),
        search_placeholder="Buscar arquivo, cliente ou referência...",
        add_label="Novo Arquivo",
        add_url=url_for("pages.arquivos_adicionar_alias"),
        columns=[
            {"key": "codigo", "label": "Cod."},
            {"key": "nome", "label": "Nome"},
            {"key": "modulo", "label": "Módulo", "badge": True},
            {"key": "referencia", "label": "Referência"},
            {"key": "data", "label": "Data", "date": True},
            {"key": "tamanho", "label": "Tamanho"},
            {"key": "acoes", "label": "Ações", "actions": "acoes"},
        ],
        rows=rows,
        pagination=None,
    )


@pages_bp.route("/arquivos/adicionar")
@login_required
def arquivos_adicionar_alias():
    ordens = (
        OrdemServico.query
        .filter(OrdemServico.deletado_em.is_(None))
        .options(joinedload(OrdemServico.cliente))
        .order_by(OrdemServico.id.desc())
        .limit(80)
        .all()
    )
    return render_template(
        "pages/zokyo_arquivo_form.html",
        active="arquivos",
        ordens=ordens,
    )


@pages_bp.route("/arquivos/adicionar", methods=["POST"])
@page_nivel_required("admin", "operacional")
def arquivos_adicionar_post():
    os_id = request.form.get("os_id", type=int)
    os_obj = (
        OrdemServico.query
        .filter_by(id=os_id)
        .filter(OrdemServico.deletado_em.is_(None))
        .first()
    )
    if not os_obj:
        flash("Selecione uma OS valida.", "error")
        return redirect(url_for("pages.arquivos_adicionar_alias"))
    fotos, erros = _validar_fotos(request.files.getlist("fotos"))
    if erros:
        flash(erros[0], "error")
        return redirect(url_for("pages.arquivos_adicionar_alias"))
    registros = _salvar_fotos_os(os_obj, None, fotos)
    descricao = sanitize_text(request.form.get("descricao", ""), max_length=200) or None
    for registro in registros:
        registro.descricao = descricao
    registrar("upload", "arquivos", f"{len(registros)} arquivo(s) adicionados na OS #{os_obj.id:04d}")
    db.session.commit()
    flash("Arquivo adicionado.", "success")
    return redirect(url_for("pages.arquivos"))


@pages_bp.route("/arquivos/visualizar/<int:id>")
@login_required
def arquivos_visualizar_alias(id):
    foto = (
        OSFoto.query
        .options(joinedload(OSFoto.os).joinedload(OrdemServico.cliente))
        .filter_by(id=id)
        .first()
    )
    if not foto:
        flash("Arquivo não encontrado.", "error")
        return redirect(url_for("pages.arquivos"))
    return render_template(
        "pages/zokyo_arquivo_detalhe.html",
        active="arquivos",
        arquivo=foto,
    )


@pages_bp.route("/arquivos/editar/<int:id>")
@pages_bp.route("/arquivos/download/<int:id>")
@login_required
def arquivos_alias(id=None):
    foto = db.session.get(OSFoto, id) if id else None
    if foto:
        return redirect(url_for("pages.os_foto", foto_id=foto.id))
    return redirect(url_for("pages.arquivos"))


@pages_bp.route("/estoque/movimentacoes")
@page_nivel_required("admin", "operacional")
def estoque_movimentacoes():
    page = max(request.args.get("page", 1, type=int), 1)
    pagination = InventoryMovement.query.order_by(InventoryMovement.created_at.desc()).paginate(
        page=page, per_page=50, error_out=False,
    )
    suggestions = [
        {"part": part, "quantity": max(part.estoque_minimo * 2 - part.quantidade_disponivel, 0)}
        for part in _pecas_ativas_query().order_by(Peca.nome).all()
        if part.quantidade_disponivel <= part.estoque_minimo
    ]
    return render_template(
        "pages/estoque_movimentacoes.html", active="estoque",
        movements=pagination.items, pagination=pagination, suggestions=suggestions,
    )


@pages_bp.route("/estoque/nova", methods=["POST"])
@pages_bp.route("/produtos/adicionar", methods=["POST"])
@page_nivel_required("admin", "operacional")
def peca_criar():
    data = request.form
    nome_peca = sanitize_text(data.get("nome", ""), max_length=200)
    if not nome_peca or len(nome_peca) < 2:
        flash("Nome da peça é obrigatório.", "error")
        return redirect(url_for("pages.estoque"))
    try:
        qtd = int(data.get("quantidade") or 0)
        est_min = int(data.get("estoque_minimo") or 5)
        custo_v = float(data.get("custo") or 0)
        margem_v = float(data.get("margem") or 0)
    except (ValueError, TypeError):
        flash("Valores numéricos inválidos.", "error")
        return redirect(url_for("pages.estoque"))
    if qtd < 0 or custo_v < 0 or margem_v < 0:
        flash("Valores numéricos não podem ser negativos.", "error")
        return redirect(url_for("pages.estoque"))
    p = Peca(
        nome=nome_peca,
        codigo=sanitize_text(data.get("codigo", ""), max_length=50) or None,
        categoria=sanitize_text(data.get("categoria", ""), max_length=100) or None,
        localizacao=sanitize_text(data.get("localizacao", ""), max_length=100) or None,
        quantidade=qtd,
        estoque_minimo=est_min,
        custo=custo_v,
        margem=margem_v,
    )
    db.session.add(p)
    db.session.flush()
    if qtd:
        record_movement(p, session["usuario_id"], "initial", 0, qtd, "Estoque inicial")
    registrar("criacao", "estoque", f"Peça criada: {nome_peca}")
    db.session.commit()
    flash("Peça salva!", "success")
    return redirect(url_for("pages.estoque"))


@pages_bp.route("/produtos/editar/<int:id>", methods=["POST"])
@pages_bp.route("/estoque/<int:id>/editar", methods=["POST"])
@page_nivel_required("admin", "operacional")
def peca_editar(id):
    p = _pecas_ativas_query().filter(Peca.id == id).first_or_404()
    data = request.form
    nome_peca = sanitize_text(data.get("nome", ""), max_length=200)
    if not nome_peca or len(nome_peca) < 2:
        flash("Nome da peça é obrigatório.", "error")
        return redirect(url_for("pages.estoque", editar=id))
    try:
        est_min = int(data.get("estoque_minimo") or p.estoque_minimo or 0)
        custo_v = float(data.get("custo") or 0)
        margem_v = float(data.get("margem") or 0)
    except (ValueError, TypeError):
        flash("Valores numéricos inválidos.", "error")
        return redirect(url_for("pages.estoque", editar=id))
    if est_min < 0 or custo_v < 0 or margem_v < 0:
        flash("Valores numéricos não podem ser negativos.", "error")
        return redirect(url_for("pages.estoque", editar=id))
    p.nome = nome_peca
    p.codigo = sanitize_text(data.get("codigo", ""), max_length=50) or None
    p.categoria = sanitize_text(data.get("categoria", ""), max_length=100) or None
    p.localizacao = sanitize_text(data.get("localizacao", ""), max_length=100) or None
    p.estoque_minimo = est_min
    p.custo = custo_v
    p.margem = margem_v
    registrar("edicao", "estoque", f"Peça editada: {p.nome}")
    db.session.commit()
    flash("Produto atualizado.", "success")
    return redirect(url_for("pages.estoque"))


@pages_bp.route("/estoque/<int:id>/movimentacao", methods=["POST"])
@page_nivel_required("admin", "operacional")
def peca_movimentar(id):
    p = _pecas_ativas_query().filter(Peca.id == id).first_or_404()
    tipo = request.form.get("tipo", "")
    if tipo not in ("entrada", "saida", "ajuste"):
        flash("Tipo de movimentação inválido.", "error")
        return redirect(url_for("pages.estoque"))
    try:
        qt = int(request.form.get("quantidade") or 0)
    except (ValueError, TypeError):
        flash("Quantidade inválida.", "error")
        return redirect(url_for("pages.estoque"))
    if qt < 0:
        flash("Quantidade não pode ser negativa.", "error")
        return redirect(url_for("pages.estoque"))
    if qt > 999_999:
        flash("Quantidade excede o limite máximo.", "error")
        return redirect(url_for("pages.estoque"))
    reason = sanitize_text(request.form.get("justificativa", ""), max_length=300)
    if len(reason) < 5:
        flash("Informe uma justificativa com pelo menos 5 caracteres.", "error")
        return redirect(url_for("pages.estoque"))
    before = p.quantidade
    if tipo == "entrada":
        p.quantidade = min(999_999, p.quantidade + qt)
    elif tipo == "saida":
        if qt > p.quantidade:
            flash(f"Estoque insuficiente. Disponível: {p.quantidade}.", "error")
            return redirect(url_for("pages.estoque"))
        p.quantidade -= qt
    elif tipo == "ajuste":
        p.quantidade = qt
    record_movement(p, session["usuario_id"], tipo, before, p.quantidade, reason)
    registrar("edicao", "estoque", f"Estoque {tipo}: {p.nome} ({qt})")
    db.session.commit()
    flash("Estoque atualizado!", "success")
    return redirect(url_for("pages.estoque"))


@pages_bp.route("/estoque/<int:id>/deletar", methods=["POST"])
@pages_bp.route("/produtos/excluir/<int:id>", methods=["POST"])
@page_nivel_required("admin")
def peca_deletar(id):
    p = db.get_or_404(Peca, id)
    if p.ordens or InventoryMovement.query.filter_by(part_id=p.id).first():
        p.ativo = False
        p.deletado_em = datetime.now(timezone.utc).replace(tzinfo=None)
        registrar("arquivamento", "estoque", f"Peca arquivada: {p.nome}")
        db.session.commit()
        flash("Produto removido da lista; historico preservado.", "success")
        return redirect(url_for("pages.estoque"))
    if p.ordens or InventoryMovement.query.filter_by(part_id=p.id).first():
        flash("Esta peça já possui histórico e deve ser preservada.", "error")
        return redirect(url_for("pages.estoque"))
    registrar("exclusao", "estoque", f"Peça removida: {p.nome}")
    db.session.delete(p)
    db.session.commit()
    flash("Peça removida.", "success")
    return redirect(url_for("pages.estoque"))


# ══════════════════════════════════════════════════════════════
# FORNECEDORES
# ══════════════════════════════════════════════════════════════
@pages_bp.route("/fornecedores")
@login_required
def fornecedores():
    q    = request.args.get("q", "").strip()
    page = request.args.get("page", 1, type=int)
    query = Fornecedor.query.filter_by(ativo=True)
    if q:
        qe = _escape_like(q)
        query = query.filter(db.or_(
            Fornecedor.nome.ilike(f"%{qe}%"),
            Fornecedor.cnpj.ilike(f"%{qe}%"),
        ))
    pag   = query.order_by(Fornecedor.nome).paginate(
        page=page, per_page=25, error_out=False)
    lista = pag.items
    fornecedores_json = _safe_json([
        {"id": f.id, "nome": f.nome, "cnpj": f.cnpj or "",
         "telefone": f.telefone or "", "email": f.email or "",
         "cep": f.cep or "", "endereco": f.endereco or "",
         "cidade": f.cidade or "", "ativo": f.ativo}
        for f in lista])
    return render_template("pages/fornecedores.html", active="fornecedores",
        fornecedores=lista, paginacao=pag,
        fornecedores_json=fornecedores_json, q=q)


@pages_bp.route("/fornecedores/adicionar")
@login_required
def fornecedores_adicionar_alias():
    return render_template(
        "pages/zokyo_fornecedor_form.html",
        active="fornecedores",
        fornecedor=None,
        action_url=url_for("pages.fornecedor_criar"),
    )


@pages_bp.route("/fornecedores/editar/<int:id>")
@login_required
def fornecedores_editar_alias(id):
    fornecedor = db.get_or_404(Fornecedor, id)
    return render_template(
        "pages/zokyo_fornecedor_form.html",
        active="fornecedores",
        fornecedor=fornecedor,
        action_url=url_for("pages.fornecedor_editar", id=id),
    )


@pages_bp.route("/fornecedores/visualizar/<int:id>")
@login_required
def fornecedores_visualizar_alias(id):
    fornecedor = db.get_or_404(Fornecedor, id)
    return render_template(
        "pages/zokyo_fornecedor_detalhe.html",
        active="fornecedores",
        fornecedor=fornecedor,
    )


@pages_bp.route("/fornecedores/novo", methods=["POST"])
@pages_bp.route("/fornecedores/adicionar", methods=["POST"])
@page_nivel_required("admin", "operacional")
def fornecedor_criar():
    from app.utils.sanitizers import sanitize_cnpj
    from app.utils.validators import validar_cnpj
    data = request.form
    nome = sanitize_text(data.get("nome", ""), max_length=200)
    if not nome or len(nome) < 2:
        flash("Nome do fornecedor é obrigatório.", "error")
        return redirect(url_for("pages.fornecedores"))
    cnpj_raw = sanitize_cnpj(data.get("cnpj", ""))
    if cnpj_raw and not validar_cnpj(cnpj_raw):
        flash("CNPJ inválido.", "error")
        return redirect(url_for("pages.fornecedores"))
    email = sanitize_email(data.get("email", ""))
    if email and not validar_email(email):
        flash("E-mail inválido.", "error")
        return redirect(url_for("pages.fornecedores"))
    cep_raw = sanitize_cep(data.get("cep", ""))
    if cep_raw and not validar_cep(cep_raw):
        flash("CEP inválido.", "error")
        return redirect(url_for("pages.fornecedores"))
    f = Fornecedor(
        nome     = nome,
        cnpj     = cnpj_raw or None,
        telefone = sanitize_phone(data.get("telefone", "")) or None,
        email    = email or None,
        cep      = cep_raw or None,
        endereco = sanitize_text(data.get("endereco", ""), max_length=300) or None,
        cidade   = sanitize_text(data.get("cidade", ""), max_length=100) or None,
    )
    db.session.add(f)
    registrar("criacao", "fornecedores", f"Fornecedor criado: {nome}")
    db.session.commit()
    flash("Fornecedor salvo!", "success")
    return redirect(url_for("pages.fornecedores"))


@pages_bp.route("/fornecedores/<int:id>/editar", methods=["POST"])
@pages_bp.route("/fornecedores/editar/<int:id>", methods=["POST"])
@page_nivel_required("admin", "operacional")
def fornecedor_editar(id):
    from app.utils.sanitizers import sanitize_cnpj
    from app.utils.validators import validar_cnpj
    f    = db.get_or_404(Fornecedor, id)
    data = request.form
    nome = sanitize_text(data.get("nome", ""), max_length=200)
    if not nome or len(nome) < 2:
        flash("Nome é obrigatório.", "error")
        return redirect(url_for("pages.fornecedores"))
    cnpj_raw = sanitize_cnpj(data.get("cnpj", ""))
    if cnpj_raw and not validar_cnpj(cnpj_raw):
        flash("CNPJ inválido.", "error")
        return redirect(url_for("pages.fornecedores"))
    email = sanitize_email(data.get("email", ""))
    if email and not validar_email(email):
        flash("E-mail inválido.", "error")
        return redirect(url_for("pages.fornecedores"))
    cep_raw = sanitize_cep(data.get("cep", ""))
    if cep_raw and not validar_cep(cep_raw):
        flash("CEP inválido.", "error")
        return redirect(url_for("pages.fornecedores"))
    f.nome     = nome
    f.cnpj     = cnpj_raw or None
    f.telefone = sanitize_phone(data.get("telefone", "")) or None
    f.email    = email or None
    f.cep      = cep_raw or None
    f.endereco = sanitize_text(data.get("endereco", ""), max_length=300) or None
    f.cidade   = sanitize_text(data.get("cidade", ""), max_length=100) or None
    registrar("edicao", "fornecedores", f"Fornecedor editado: {f.nome}")
    db.session.commit()
    flash("Fornecedor atualizado!", "success")
    return redirect(url_for("pages.fornecedores"))


@pages_bp.route("/fornecedores/<int:id>/deletar", methods=["POST"])
@pages_bp.route("/fornecedores/excluir/<int:id>", methods=["POST"])
@page_nivel_required("admin")
def fornecedor_deletar(id):
    f = db.get_or_404(Fornecedor, id)
    f.ativo = False
    registrar("arquivamento", "fornecedores", f"Fornecedor arquivado: {f.nome}")
    db.session.commit()
    flash("Fornecedor arquivado; peças e histórico foram preservados.", "success")
    return redirect(url_for("pages.fornecedores"))


# ══════════════════════════════════════════════════════════════
# FINANCEIRO
# ══════════════════════════════════════════════════════════════
@pages_bp.route("/financeiro")
@pages_bp.route("/financeiro/")
@pages_bp.route("/financeiro/lancamentos")
@pages_bp.route("/financeiro/lancamentos/")
@pages_bp.route("/lancamentos")
@pages_bp.route("/lancamentos/")
@page_nivel_required("admin", "financeiro")
def financeiro():
    from app.services.financial_analytics import monthly_summary, order_financial_rows
    hoje = _now()

    preset = request.args.get("preset", "")
    if preset == "semana":
        data_ini_def = (hoje - timedelta(days=7)).strftime("%Y-%m-%d")
        data_fim_def = hoje.strftime("%Y-%m-%d")
    elif preset == "ano":
        data_ini_def = hoje.strftime("%Y-01-01")
        data_fim_def = hoje.strftime("%Y-%m-%d")
    else:
        data_ini_def = hoje.strftime("%Y-%m-01")
        data_fim_def = hoje.strftime("%Y-%m-%d")

    data_ini      = request.args.get("data_ini", data_ini_def)
    data_fim      = request.args.get("data_fim", data_fim_def)
    tipo_filtro   = request.args.get("tipo", "")
    status_filtro = request.args.get("status", "")
    q             = request.args.get("q", "").strip()
    page          = request.args.get("page", 1, type=int)

    try:
        dt_ini = datetime.fromisoformat(data_ini)
        dt_fim = datetime.fromisoformat(data_fim).replace(
            hour=23, minute=59, second=59)
    except Exception:
        dt_ini = hoje.replace(day=1)
        dt_fim = hoje

    query = Transacao.query.filter(
        Transacao.criado_em >= dt_ini,
        Transacao.criado_em <= dt_fim,
    )
    if tipo_filtro:
        query = query.filter_by(tipo=tipo_filtro)
    if status_filtro:
        query = query.filter_by(status=status_filtro)
    if q:
        query = query.filter(Transacao.descricao.ilike(f"%{_escape_like(q)}%"))
    pag = query.order_by(Transacao.criado_em.desc()).paginate(
        page=page, per_page=25, error_out=False)

    def _s(tipo, st):
        return float(db.session.query(
            _coalesce_sum(Transacao.valor)).filter(
            Transacao.tipo == tipo, Transacao.status == st,
            Transacao.criado_em >= dt_ini,
            Transacao.criado_em <= dt_fim,
        ).scalar() or 0)

    periodo_label = (f"{dt_ini.strftime('%d/%m/%Y')} "
                     f"a {dt_fim.strftime('%d/%m/%Y')}")

    receitas_pagas = _s("receita", "pago")
    despesas_pagas = _s("despesa", "pago")
    os_financeiro = order_financial_rows(hoje, dt_ini, dt_fim)
    return render_template("pages/financeiro.html", active="financeiro",
        transacoes=pag.items, paginacao=pag,
        filtros={"data_ini": data_ini, "data_fim": data_fim,
                 "tipo": tipo_filtro, "status": status_filtro},
        periodo_label=periodo_label,
        receitas_pagas=receitas_pagas,
        despesas_pagas=despesas_pagas,
        lucro=receitas_pagas - despesas_pagas,
        a_receber=_s("receita", "pendente"),
        a_pagar=_s("despesa", "pendente"),
        comissoes=float(db.session.query(_coalesce_sum(Transacao.comissao_valor)).filter(
            Transacao.status == "pago", Transacao.criado_em >= dt_ini, Transacao.criado_em <= dt_fim,
        ).scalar() or 0),
        usuarios_comissao=Usuario.query.filter_by(ativo=True).order_by(Usuario.nome).all(),
        os_financeiro=os_financeiro,
        inadimplentes=[row for row in os_financeiro if row["overdue"] > 0],
        resumo_mensal=monthly_summary(os_financeiro, receitas_pagas, despesas_pagas),
    )


@pages_bp.route("/financeiro/adicionar")
@pages_bp.route("/lancamentos/adicionar")
@pages_bp.route("/cobrancas/adicionar")
@pages_bp.route("/financeiro/adicionarReceita")
@pages_bp.route("/financeiro/adicionarDespesa")
@pages_bp.route("/financeiro/adicionarReceita_parc")
@login_required
def financeiro_adicionar_alias():
    tipo = "despesa" if request.path.endswith("adicionarDespesa") else "receita" if request.path.startswith(("/cobrancas", "/vendas")) else request.args.get("tipo", "receita")
    if tipo not in ("receita", "despesa"):
        tipo = "receita"
    titulo = "Adicionar Despesa" if tipo == "despesa" else "Adicionar Cobrança" if request.path.startswith("/cobrancas") else "Adicionar Lançamento"
    return render_template(
        "pages/zokyo_transacao_form.html",
        active="financeiro",
        transacao=None,
        action_url=url_for("pages.transacao_criar"),
        tipo_padrao=tipo,
        titulo=titulo,
        voltar_url=url_for("pages.cobrancas") if request.path.startswith("/cobrancas") else url_for("pages.financeiro"),
    )


@pages_bp.route("/servicos")
@pages_bp.route("/servicos/")
@pages_bp.route("/servicos/index")
@page_nivel_required("admin", "operacional", "cadastro", "consulta")
def servicos():
    q = request.args.get("q", "").strip()
    page = request.args.get("page", 1, type=int)

    query = _servicos_ativos_query()
    if q:
        qe = _escape_like(q)
        query = query.filter(db.or_(
            DefeitoPadrao.tipo_aparelho.ilike(f"%{qe}%"),
            DefeitoPadrao.sintoma.ilike(f"%{qe}%"),
            DefeitoPadrao.causa.ilike(f"%{qe}%"),
            DefeitoPadrao.solucao.ilike(f"%{qe}%"),
        ))
    pag = query.order_by(DefeitoPadrao.tipo_aparelho, DefeitoPadrao.sintoma).paginate(
        page=page, per_page=25, error_out=False,
    )

    os_query = OrdemServico.query.filter(
        OrdemServico.deletado_em.is_(None),
        OrdemServico.valor_servico > 0,
    )
    if q:
        qe = _escape_like(q)
        os_query = os_query.filter(db.or_(
            OrdemServico.tipo_aparelho.ilike(f"%{qe}%"),
            OrdemServico.defeito_alegado.ilike(f"%{qe}%"),
            OrdemServico.solucao.ilike(f"%{qe}%"),
        ))
    servicos_os = os_query.order_by(OrdemServico.atualizado_em.desc()).limit(20).all()

    rows = [
        {
            "codigo": f"D{item.id:04d}",
            "nome": item.sintoma,
            "preco": None,
            "descricao": item.solucao or item.causa or "Padrão técnico",
            "origem": item.tipo_aparelho or "Geral",
            "acoes": [
                {"label": "Editar", "title": "Editar Serviço", "url": url_for("pages.servicos_editar_form", id=item.id), "class": "btn-nwe3"},
                {"label": "Excluir", "title": "Excluir Serviço", "url": url_for("pages.servicos_excluir_alias", id=item.id), "method": "POST", "confirm": "Excluir este serviço?", "class": "btn-nwe4"},
            ],
        }
        for item in pag.items
    ]
    if not rows:
        rows = [
            {
                "codigo": f"OS{item.id:04d}",
                "nome": item.defeito_alegado or item.tipo_aparelho or "Serviço",
                "preco": item.valor_servico,
                "descricao": item.solucao or item.observacoes or "Serviço executado em OS",
                "origem": item.tipo_aparelho or "OS",
                "acoes": [
                    {"label": "Ver", "title": "Visualizar OS", "url": url_for("pages.os_detalhe", id=item.id), "class": "btn-nwe"},
                    {"label": "Editar", "title": "Editar OS", "url": url_for("pages.os_editar", id=item.id), "class": "btn-nwe3"},
                ],
            }
            for item in servicos_os
        ]

    return render_template(
        "pages/zokyo_modulo.html",
        active="servicos",
        title="Serviços",
        breadcrumb="Serviços",
        subtitle="Serviços usados com frequência em ordens de serviço.",
        flow_hint="<strong>Use esta tela para padronizar serviços comuns.</strong> Assim o técnico digita menos e mantém os textos mais consistentes.",
        empty="Nenhum serviço cadastrado.",
        empty_hint="Cadastre serviços comuns, como troca de conector, limpeza, formatação ou diagnóstico.",
        search=q,
        search_placeholder="Buscar por nome ou descrição",
        add_label="Cadastrar serviço",
        add_url=url_for("pages.servicos_adicionar_alias"),
        columns=[
            {"key": "codigo", "label": "Código"},
            {"key": "nome", "label": "Nome"},
            {"key": "preco", "label": "Preço", "money": True},
            {"key": "descricao", "label": "Descrição"},
            {"key": "origem", "label": "Origem", "badge": True},
            {"key": "acoes", "label": "Opções", "actions": "acoes"},
        ],
        rows=rows,
        pagination=pag,
    )


@pages_bp.route("/servicos/adicionar")
@login_required
def servicos_adicionar_alias():
    return render_template(
        "pages/zokyo_servico_form.html",
        active="servicos",
        servico=None,
        action_url=url_for("pages.servicos_criar_alias"),
    )


@pages_bp.route("/servicos/adicionar", methods=["POST"])
@page_nivel_required("admin", "operacional", "cadastro")
def servicos_criar_alias():
    nome = sanitize_text(
        request.form.get("nome") or request.form.get("sintoma") or request.form.get("servico") or "",
        max_length=300,
    )
    if not nome:
        flash("Nome do serviço é obrigatório.", "error")
        return redirect(url_for("pages.servicos"))
    item = DefeitoPadrao(
        tipo_aparelho=sanitize_text(request.form.get("tipo_aparelho", ""), max_length=100) or None,
        sintoma=nome,
        causa=sanitize_text(request.form.get("causa", ""), max_length=5000) or None,
        solucao=sanitize_text(
            request.form.get("solucao") or request.form.get("descricao") or "",
            max_length=5000,
        ) or None,
    )
    db.session.add(item)
    registrar("criacao", "servicos", f"Serviço criado: {item.sintoma}")
    db.session.commit()
    flash("Serviço salvo.", "success")
    return redirect(url_for("pages.servicos"))


@pages_bp.route("/servicos/visualizar/<int:id>")
@login_required
def servicos_item_alias(id):
    item = _servicos_ativos_query().filter(DefeitoPadrao.id == id).first_or_404()
    return redirect(url_for("pages.servicos", q=item.sintoma))


@pages_bp.route("/servicos/editar/<int:id>")
@login_required
def servicos_editar_form(id):
    item = _servicos_ativos_query().filter(DefeitoPadrao.id == id).first_or_404()
    return render_template(
        "pages/zokyo_servico_form.html",
        active="servicos",
        servico=item,
        action_url=url_for("pages.servicos_editar_alias", id=item.id),
    )


@pages_bp.route("/servicos/editar/<int:id>", methods=["POST"])
@page_nivel_required("admin", "operacional", "cadastro")
def servicos_editar_alias(id):
    item = _servicos_ativos_query().filter(DefeitoPadrao.id == id).first_or_404()
    nome = sanitize_text(
        request.form.get("nome") or request.form.get("sintoma") or request.form.get("servico") or "",
        max_length=300,
    )
    if not nome:
        flash("Nome do serviço é obrigatório.", "error")
        return redirect(url_for("pages.servicos", q=item.sintoma))
    item.tipo_aparelho = sanitize_text(request.form.get("tipo_aparelho", ""), max_length=100) or None
    item.sintoma = nome
    item.causa = sanitize_text(request.form.get("causa", ""), max_length=5000) or None
    item.solucao = sanitize_text(
        request.form.get("solucao") or request.form.get("descricao") or "",
        max_length=5000,
    ) or None
    registrar("edicao", "servicos", f"Serviço editado: {item.sintoma}")
    db.session.commit()
    flash("Serviço atualizado.", "success")
    return redirect(url_for("pages.servicos"))


@pages_bp.route("/servicos/excluir/<int:id>", methods=["POST"])
@page_nivel_required("admin")
def servicos_excluir_alias(id):
    item = db.get_or_404(DefeitoPadrao, id)
    registrar("exclusao", "servicos", f"Serviço removido: {item.sintoma}")
    item.ativo = False
    item.deletado_em = datetime.now(timezone.utc).replace(tzinfo=None)
    db.session.commit()
    flash("Serviço removido.", "success")
    return redirect(url_for("pages.servicos"))


@pages_bp.route("/vendas")
@pages_bp.route("/vendas/")
@pages_bp.route("/vendas/index")
@page_nivel_required("admin", "operacional", "financeiro")
def vendas():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    page = request.args.get("page", 1, type=int)

    query = Transacao.query.filter(Transacao.tipo == "receita")
    if status:
        query = query.filter(Transacao.status == status)
    if q:
        qe = _escape_like(q)
        query = query.filter(Transacao.descricao.ilike(f"%{qe}%"))
    pag = query.order_by(Transacao.criado_em.desc()).paginate(page=page, per_page=25, error_out=False)

    rows = [
        {
            "numero": f"{item.id:04d}",
            "cliente": f"OS #{item.os_id:04d}" if item.os_id else "Venda direta",
            "vendedor": item.comissao_usuario_id or "-",
            "data": item.criado_em,
            "total": item.valor,
            "status": item.status,
            "faturado": "Sim" if item.status == "pago" else "Não",
            "acoes": [
                {"label": "Ver", "title": "Visualizar venda", "url": url_for("pages.vendas_item_alias", id=item.id), "class": "btn-nwe"},
                {"label": "Editar", "title": "Editar venda", "url": url_for("pages.vendas_editar_alias", id=item.id), "class": "btn-nwe3"},
                {"label": "Cancelar", "title": "Cancelar venda", "url": url_for("pages.transacao_deletar", id=item.id), "method": "POST", "confirm": "Cancelar esta venda?", "class": "btn-nwe4"},
            ],
        }
        for item in pag.items
    ]
    return render_template(
        "pages/zokyo_modulo.html",
        active="vendas",
        title="Vendas",
        breadcrumb="Vendas",
        subtitle="Vendas diretas e receitas registradas no caixa.",
        flow_hint="<strong>Use vendas para registrar recebimentos simples.</strong> Para serviço com equipamento, prefira abrir uma OS.",
        empty="Nenhuma venda encontrada.",
        empty_hint="Registre uma venda direta quando não precisar abrir uma ordem de serviço.",
        search=q,
        search_placeholder="Buscar por descrição da venda",
        add_label="Registrar venda",
        add_url=url_for("pages.vendas_adicionar_alias"),
        filters=[
            {"name": "status", "label": "Status", "value": status, "options": [
                ("", "Todos"), ("pendente", "Aberto"), ("pago", "Faturado"), ("cancelado", "Cancelado"),
            ]},
        ],
        columns=[
            {"key": "numero", "label": "Número"},
            {"key": "cliente", "label": "Cliente"},
            {"key": "vendedor", "label": "Vendedor"},
            {"key": "data", "label": "Data da venda", "date": True},
            {"key": "total", "label": "Valor total", "money": True},
            {"key": "status", "label": "Status", "badge": True},
            {"key": "faturado", "label": "Faturado"},
            {"key": "acoes", "label": "Opções", "actions": "acoes"},
        ],
        rows=rows,
        pagination=pag,
    )


@pages_bp.route("/vendas/adicionar")
@login_required
def vendas_adicionar_alias():
    return render_template(
        "pages/zokyo_transacao_form.html",
        active="vendas",
        transacao=None,
        action_url=url_for("pages.transacao_criar"),
        tipo_padrao="receita",
        titulo="Adicionar Venda",
        voltar_url=url_for("pages.vendas"),
    )


@pages_bp.route("/vendas/editar/<int:id>")
@login_required
def vendas_editar_alias(id):
    item = db.get_or_404(Transacao, id)
    return render_template(
        "pages/zokyo_transacao_form.html",
        active="vendas",
        transacao=item,
        action_url=url_for("pages.transacao_editar", id=id),
        tipo_padrao=item.tipo,
        titulo="Editar Venda",
        voltar_url=url_for("pages.vendas"),
    )


@pages_bp.route("/vendas/visualizar/<int:id>")
@login_required
def vendas_item_alias(id):
    item = db.get_or_404(Transacao, id)
    return render_template(
        "pages/zokyo_transacao_detalhe.html",
        active="vendas",
        transacao=item,
        titulo="Visualizar Venda",
        voltar_url=url_for("pages.vendas"),
    )


def _venda_pdf_response(item, titulo, filename):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    os_obj = OrdemServico.query.filter_by(id=item.os_id).first() if item.os_id else None
    cliente = os_obj.cliente if os_obj and os_obj.cliente else None
    cfg = Configuracao.get()
    output = io.BytesIO()
    document = SimpleDocTemplate(output, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm)
    styles = getSampleStyleSheet()
    valor = float(item.valor or 0)
    vencimento = item.data_vencimento.strftime("%d/%m/%Y") if item.data_vencimento else "-"
    pagamento = item.data_pagamento.strftime("%d/%m/%Y") if item.data_pagamento else "-"
    rows = [
        ["Lançamento", f"#{item.id:04d}"],
        ["Cliente", cliente.nome if cliente else "Cliente avulso"],
        ["Descrição", item.descricao or "-"],
        ["Status", item.status or "-"],
        ["Vencimento", vencimento],
        ["Pagamento", pagamento],
        ["Forma", item.forma_pagamento or "-"],
        ["Valor", f"R$ {valor:.2f}"],
    ]
    if os_obj:
        rows.insert(2, ["OS", f"#{os_obj.id:04d}"])
        rows.insert(3, ["Equipamento", " ".join(part for part in [os_obj.tipo_aparelho, os_obj.marca, os_obj.modelo] if part) or "-"])
    table = Table(rows, colWidths=[38 * mm, 132 * mm])
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story = [
        Paragraph(cfg.nome_empresa or "Zokyo", styles["Title"]),
        Paragraph(titulo, styles["Heading2"]),
        Spacer(1, 7 * mm),
        table,
        Spacer(1, 12 * mm),
        Paragraph("Documento gerado pelo Zokyo.", styles["Normal"]),
    ]
    document.build(story)
    output.seek(0)
    return send_file(output, mimetype="application/pdf", as_attachment=True, download_name=filename)


@pages_bp.route("/vendas/imprimir/<int:id>")
@pages_bp.route("/vendas/imprimirVenda/<int:id>")
@login_required
def vendas_imprimir_alias(id):
    item = db.get_or_404(Transacao, id)
    return _venda_pdf_response(item, "Comprovante de venda", f"venda-{item.id:04d}.pdf")


@pages_bp.route("/vendas/imprimirVendaOrcamento/<int:id>")
@pages_bp.route("/vendas/orcamento/<int:id>")
@login_required
def vendas_orcamento_alias(id):
    item = db.get_or_404(Transacao, id)
    return _venda_pdf_response(item, "Orçamento de venda", f"orcamento-venda-{item.id:04d}.pdf")


@pages_bp.route("/vendas/imprimirTermica/<int:id>")
@login_required
def vendas_termica_alias(id):
    item = db.get_or_404(Transacao, id)
    os_obj = OrdemServico.query.filter_by(id=item.os_id).first() if item.os_id else None
    cliente = os_obj.cliente if os_obj and os_obj.cliente else None
    linhas = [
        "ZOKYO",
        "COMPROVANTE DE VENDA",
        f"Venda: #{item.id:04d}",
        f"Cliente: {cliente.nome if cliente else 'Cliente avulso'}",
        f"Descrição: {item.descricao or '-'}",
        f"Status: {item.status or '-'}",
        f"Valor: R$ {float(item.valor or 0):.2f}",
        "-" * 32,
        "Obrigado pela preferência.",
        "",
    ]
    response = make_response("\n".join(linhas))
    response.headers["Content-Type"] = "text/plain; charset=utf-8"
    response.headers["Content-Disposition"] = f'attachment; filename="venda-{item.id:04d}-termica.txt"'
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@pages_bp.route("/cobrancas")
@pages_bp.route("/cobrancas/")
@pages_bp.route("/cobrancas/cobrancas")
@page_nivel_required("admin", "financeiro")
def cobrancas():
    q = request.args.get("q", "").strip()
    page = request.args.get("page", 1, type=int)
    query = Transacao.query.filter(Transacao.tipo == "receita", Transacao.status == "pendente")
    if q:
        qe = _escape_like(q)
        query = query.filter(Transacao.descricao.ilike(f"%{qe}%"))
    pag = query.order_by(Transacao.data_vencimento.asc(), Transacao.criado_em.desc()).paginate(
        page=page, per_page=25, error_out=False,
    )
    rows = [
        {
            "numero": f"{item.id:04d}",
            "cliente": f"OS #{item.os_id:04d}" if item.os_id else "Cliente avulso",
            "descricao": item.descricao,
            "vencimento": item.data_vencimento,
            "valor": item.valor,
            "status": item.status,
            "acoes": [
                {"label": "Ver", "title": "Visualizar Cobrança", "url": url_for("pages.cobrancas_visualizar_alias", id=item.id), "class": "btn-nwe"},
                {"label": "Marcar pago", "title": "Marcar cobrança como paga", "url": url_for("pages.transacao_pagar", id=item.id), "method": "POST", "confirm": "Marcar esta cobrança como paga?", "class": "btn-nwe3"},
                {"label": "Cancelar", "title": "Cancelar Cobrança", "url": url_for("pages.transacao_deletar", id=item.id), "method": "POST", "confirm": "Cancelar esta cobrança?", "class": "btn-nwe4"},
            ],
        }
        for item in pag.items
    ]
    return render_template(
        "pages/zokyo_modulo.html",
        active="cobrancas",
        title="Cobranças",
        breadcrumb="Cobranças",
        subtitle="Receitas pendentes para acompanhar cobranças em aberto.",
        empty="Nenhuma cobrança pendente.",
        search=q,
        search_placeholder="Buscar cobrança...",
        add_label="Nova Cobrança",
        add_url=url_for("pages.financeiro_adicionar_alias"),
        columns=[
            {"key": "numero", "label": "Nº"},
            {"key": "cliente", "label": "Cliente"},
            {"key": "descricao", "label": "Descrição"},
            {"key": "vencimento", "label": "Vencimento", "date": True},
            {"key": "valor", "label": "Valor", "money": True},
            {"key": "status", "label": "Status", "badge": True},
            {"key": "acoes", "label": "Ações", "actions": "acoes"},
        ],
        rows=rows,
        pagination=pag,
    )


@pages_bp.route("/cobrancas/visualizar/<int:id>")
@login_required
def cobrancas_visualizar_alias(id):
    item = db.get_or_404(Transacao, id)
    return render_template(
        "pages/zokyo_transacao_detalhe.html",
        active="cobrancas",
        transacao=item,
        titulo="Visualizar Cobrança",
        voltar_url=url_for("pages.cobrancas"),
    )


@pages_bp.route("/financeiro/visualizar/<int:id>")
@pages_bp.route("/lancamentos/visualizar/<int:id>")
@login_required
def transacao_visualizar_alias(id):
    item = db.get_or_404(Transacao, id)
    return render_template(
        "pages/zokyo_transacao_detalhe.html",
        active="financeiro",
        transacao=item,
        titulo="Visualizar Lançamento",
        voltar_url=url_for("pages.financeiro"),
    )


@pages_bp.route("/financeiro/editar/<int:id>")
@pages_bp.route("/lancamentos/editar/<int:id>")
@login_required
def transacao_editar_alias(id):
    item = db.get_or_404(Transacao, id)
    return render_template(
        "pages/zokyo_transacao_form.html",
        active="financeiro",
        transacao=item,
        action_url=url_for("pages.transacao_editar", id=id),
        tipo_padrao=item.tipo,
        titulo="Editar Lançamento",
        voltar_url=url_for("pages.financeiro"),
    )


@pages_bp.route("/garantias")
@pages_bp.route("/garantias/")
@pages_bp.route("/garantias/index")
@page_nivel_required("admin", "operacional", "consulta")
def garantias():
    q = request.args.get("q", "").strip()
    page = request.args.get("page", 1, type=int)
    query = OrdemServico.query.filter(
        OrdemServico.deletado_em.is_(None),
        OrdemServico.status == "entregue",
    ).options(joinedload(OrdemServico.cliente))
    if q:
        qe = _escape_like(q)
        query = query.join(Cliente).filter(db.or_(
            Cliente.nome.ilike(f"%{qe}%"),
            OrdemServico.tipo_aparelho.ilike(f"%{qe}%"),
            OrdemServico.marca.ilike(f"%{qe}%"),
            OrdemServico.modelo.ilike(f"%{qe}%"),
        ))
    pag = query.order_by(OrdemServico.data_saida.desc()).paginate(page=page, per_page=25, error_out=False)
    rows = [
        {
            "numero": f"OS #{item.id:04d}",
            "cliente": item.cliente.nome if item.cliente else "-",
            "equipamento": " ".join(part for part in [item.tipo_aparelho, item.marca, item.modelo] if part) or "-",
            "saida": item.data_saida,
            "garantia": f"{item.garantia_dias or 0} dias",
            "status": "Em garantia" if item.em_garantia else "Expirada",
            "acoes": [
                {"label": "Ver", "title": "Visualizar garantia", "url": url_for("pages.garantias_visualizar_alias", id=item.id), "class": "btn-nwe"},
                {"label": "PDF", "title": "Imprimir garantia", "url": url_for("pages.os_pdf", id=item.id), "class": "btn-nwe6", "target_blank": True},
                {"label": "Editar", "title": "Editar garantia", "url": url_for("pages.garantias_editar_alias", id=item.id), "class": "btn-nwe3"},
            ],
        }
        for item in pag.items
    ]
    return render_template(
        "pages/zokyo_modulo.html",
        active="garantias",
        title="Termos de garantia",
        breadcrumb="Garantias",
        subtitle="OS entregues com prazo de garantia e situação atual.",
        flow_hint="<strong>Use esta tela para consultar atendimentos em garantia.</strong> Para criar uma nova garantia, entregue uma OS com prazo configurado.",
        empty="Nenhuma garantia encontrada.",
        empty_hint="As garantias aparecem aqui depois que uma OS é entregue com prazo de garantia.",
        search=q,
        search_placeholder="Buscar cliente ou equipamento",
        add_label="Abrir OS",
        add_url=url_for("pages.os_nova"),
        columns=[
            {"key": "numero", "label": "Número"},
            {"key": "cliente", "label": "Cliente"},
            {"key": "equipamento", "label": "Equipamento"},
            {"key": "saida", "label": "Saída", "date": True},
            {"key": "garantia", "label": "Garantia"},
            {"key": "status", "label": "Status", "badge": True},
            {"key": "acoes", "label": "Opções", "actions": "acoes"},
        ],
        rows=rows,
        pagination=pag,
    )


@pages_bp.route("/garantias/adicionar")
@login_required
def garantias_adicionar_alias():
    ordens = (
        OrdemServico.query
        .filter(OrdemServico.deletado_em.is_(None))
        .options(joinedload(OrdemServico.cliente))
        .order_by(OrdemServico.id.desc())
        .limit(120)
        .all()
    )
    return render_template(
        "pages/zokyo_garantia_form.html",
        active="garantias",
        garantia=None,
        ordens=ordens,
        action_url=url_for("pages.garantias_adicionar_post"),
        today=_today(),
    )


@pages_bp.route("/garantias/adicionar", methods=["POST"])
@page_nivel_required("admin", "operacional")
def garantias_adicionar_post():
    os_id = request.form.get("os_id", type=int)
    os_obj = (
        OrdemServico.query
        .filter_by(id=os_id)
        .filter(OrdemServico.deletado_em.is_(None))
        .first()
    )
    if not os_obj:
        flash("Selecione uma OS valida.", "error")
        return redirect(url_for("pages.garantias_adicionar_alias"))
    return _salvar_garantia_os(os_obj, redirect_to="pages.garantias_visualizar_alias")


@pages_bp.route("/garantias/editar/<int:id>")
@login_required
def garantias_editar_alias(id):
    os_obj = (
        OrdemServico.query
        .filter_by(id=id)
        .filter(OrdemServico.deletado_em.is_(None))
        .options(joinedload(OrdemServico.cliente))
        .first_or_404()
    )
    return render_template(
        "pages/zokyo_garantia_form.html",
        active="garantias",
        garantia=os_obj,
        ordens=[],
        action_url=url_for("pages.garantias_editar_post", id=id),
        today=_today(),
    )


@pages_bp.route("/garantias/editar/<int:id>", methods=["POST"])
@page_nivel_required("admin", "operacional")
def garantias_editar_post(id):
    os_obj = (
        OrdemServico.query
        .filter_by(id=id)
        .filter(OrdemServico.deletado_em.is_(None))
        .first_or_404()
    )
    return _salvar_garantia_os(os_obj, redirect_to="pages.garantias_visualizar_alias")


def _salvar_garantia_os(os_obj, redirect_to):
    try:
        garantia_dias = int(request.form.get("garantia_dias") or os_obj.garantia_dias or 90)
    except (TypeError, ValueError):
        flash("Garantia invalida.", "error")
        return redirect(url_for("pages.garantias_editar_alias", id=os_obj.id))
    if garantia_dias < 0:
        flash("Garantia não pode ser negativa.", "error")
        return redirect(url_for("pages.garantias_editar_alias", id=os_obj.id))
    data_saida = _safe_date(request.form.get("data_saida")) if request.form.get("data_saida") else (os_obj.data_saida or _now())
    if data_saida is None:
        flash("Data de saida invalida.", "error")
        return redirect(url_for("pages.garantias_editar_alias", id=os_obj.id))

    os_obj.garantia_dias = garantia_dias
    os_obj.data_saida = data_saida
    os_obj.status = "entregue"
    observacao = sanitize_text(request.form.get("observacoes", ""), max_length=5000)
    if observacao:
        os_obj.observacoes = observacao
    registrar("edicao", "garantias", f"Garantia da OS #{os_obj.id:04d} atualizada")
    db.session.commit()
    flash("Garantia salva.", "success")
    return redirect(url_for(redirect_to, id=os_obj.id))


@pages_bp.route("/garantias/visualizar/<int:id>")
@login_required
def garantias_visualizar_alias(id):
    os_obj = (
        OrdemServico.query
        .filter_by(id=id)
        .filter(OrdemServico.deletado_em.is_(None))
        .options(joinedload(OrdemServico.cliente))
        .first_or_404()
    )
    return render_template(
        "pages/zokyo_garantia_detalhe.html",
        active="garantias",
        garantia=os_obj,
    )


@pages_bp.route("/garantias/imprimir/<int:id>")
@pages_bp.route("/garantias/imprimirGarantiaOs/<int:id>")
@login_required
def garantias_imprimir_alias(id):
    return redirect(url_for("pages.os_pdf", id=id))


@pages_bp.route("/financeiro/nova", methods=["POST"])
@pages_bp.route("/financeiro/adicionar", methods=["POST"])
@pages_bp.route("/lancamentos/adicionar", methods=["POST"])
@pages_bp.route("/cobrancas/adicionar", methods=["POST"])
@pages_bp.route("/vendas/adicionar", methods=["POST"])
@page_nivel_required("admin", "financeiro")
def transacao_criar():
    from app.models.transacao import STATUS_TRANSACAO, TIPOS_TRANSACAO
    data = request.form
    try:
        valor = float(data["valor"])
    except (ValueError, TypeError, KeyError):
        flash("Valor inválido.", "error")
        return redirect(url_for("pages.financeiro"))
    if valor < 0:
        flash("Valor não pode ser negativo.", "error")
        return redirect(url_for("pages.financeiro"))
    if data.get("tipo") not in TIPOS_TRANSACAO:
        flash("Tipo de transação inválido.", "error")
        return redirect(url_for("pages.financeiro"))
    status = data.get("status", "pendente")
    if status not in STATUS_TRANSACAO:
        status = "pendente"
    descricao_t = sanitize_text(data.get("descricao", ""), max_length=500)
    if not descricao_t:
        flash("Descrição é obrigatória.", "error")
        return redirect(url_for("pages.financeiro"))
    if valor > 9_999_999.99:
        flash("Valor excede o limite máximo permitido.", "error")
        return redirect(url_for("pages.financeiro"))
    try:
        parcelas = int(data.get("parcelas") or 1)
        comissao_percentual = float(data.get("comissao_percentual") or 0)
        comissao_usuario_id = int(data["comissao_usuario_id"]) if data.get("comissao_usuario_id") else None
        if comissao_usuario_id and not Usuario.query.filter_by(id=comissao_usuario_id, ativo=True).first():
            raise ValueError("Usuário de comissão inválido.")
        create_installments(
            organization_id=g.organization_id,
            installments=parcelas,
            recurrence=data.get("recorrencia"),
            tipo=data["tipo"],
            categoria=sanitize_text(data.get("categoria", ""), max_length=100) or None,
            descricao=descricao_t,
            valor=valor,
            status=status,
            data_vencimento=_safe_date(data.get("data_vencimento")),
            forma_pagamento=sanitize_text(data.get("forma_pagamento", ""), max_length=50) or None,
            comissao_usuario_id=comissao_usuario_id,
            comissao_percentual=comissao_percentual,
        )
    except (TypeError, ValueError) as exc:
        flash(str(exc), "error")
        return redirect(url_for("pages.financeiro"))
    registrar("criacao", "financeiro",
              f"Transação criada: {data.get('descricao', '')} R$ {valor}")
    db.session.commit()
    flash("Transação salva!", "success")
    return redirect(url_for("pages.financeiro"))


@pages_bp.route("/financeiro/editar/<int:id>", methods=["POST"])
@pages_bp.route("/lancamentos/editar/<int:id>", methods=["POST"])
@pages_bp.route("/vendas/editar/<int:id>", methods=["POST"])
@page_nivel_required("admin", "financeiro")
def transacao_editar(id):
    from app.models.transacao import STATUS_TRANSACAO, TIPOS_TRANSACAO

    t = db.get_or_404(Transacao, id)
    data = request.form
    try:
        valor = float(data["valor"])
    except (ValueError, TypeError, KeyError):
        flash("Valor inválido.", "error")
        return redirect(url_for("pages.transacao_editar_alias", id=id))
    if valor < 0:
        flash("Valor não pode ser negativo.", "error")
        return redirect(url_for("pages.transacao_editar_alias", id=id))
    tipo = data.get("tipo")
    if tipo not in TIPOS_TRANSACAO:
        flash("Tipo de transação inválido.", "error")
        return redirect(url_for("pages.transacao_editar_alias", id=id))
    status = data.get("status", "pendente")
    if status not in STATUS_TRANSACAO:
        status = "pendente"
    descricao_t = sanitize_text(data.get("descricao", ""), max_length=500)
    if not descricao_t:
        flash("Descrição e obrigatoria.", "error")
        return redirect(url_for("pages.transacao_editar_alias", id=id))
    if valor > 9_999_999.99:
        flash("Valor excede o limite maximo permitido.", "error")
        return redirect(url_for("pages.transacao_editar_alias", id=id))

    t.tipo = tipo
    t.categoria = sanitize_text(data.get("categoria", ""), max_length=100) or None
    t.descricao = descricao_t
    t.valor = valor
    t.status = status
    t.data_vencimento = _safe_date(data.get("data_vencimento"))
    t.forma_pagamento = sanitize_text(data.get("forma_pagamento", ""), max_length=50) or None
    try:
        t.comissao_percentual = float(data.get("comissao_percentual") or 0)
    except (TypeError, ValueError):
        t.comissao_percentual = 0
    if status == "pago" and not t.data_pagamento:
        t.data_pagamento = _now()
    if status != "pago":
        t.data_pagamento = None

    registrar("edicao", "financeiro", f"Transação #{id} editada")
    db.session.commit()
    flash("Transação atualizada.", "success")
    if request.path.startswith("/vendas"):
        return redirect(url_for("pages.vendas_item_alias", id=id))
    return redirect(url_for("pages.transacao_visualizar_alias", id=id))


@pages_bp.route("/financeiro/<int:id>/conciliar", methods=["POST"])
@page_nivel_required("admin", "financeiro")
def transacao_conciliar(id):
    t = db.get_or_404(Transacao, id)
    reference = sanitize_text(request.form.get("referencia", ""), max_length=120)
    if len(reference) < 3:
        flash("Informe uma referência para conciliação.", "error")
        return redirect(url_for("pages.financeiro"))
    t.conciliado_em = _now()
    t.conciliado_por_id = session["usuario_id"]
    t.conciliacao_ref = reference
    registrar("conciliacao", "financeiro", f"Transação #{id} conciliada: {reference}")
    db.session.commit()
    flash("Transação conciliada.", "success")
    return redirect(url_for("pages.financeiro"))


@pages_bp.route("/financeiro/<int:id>/pagar", methods=["POST"])
@page_nivel_required("admin", "financeiro")
def transacao_pagar(id):
    # Bug #9: get_or_404 depreciado
    t = db.get_or_404(Transacao, id)
    t.status        = "pago"
    t.data_pagamento= _now()
    registrar("pagamento", "financeiro",
              f"Transação #{id} marcada como paga")
    db.session.commit()
    flash("Pagamento registrado!", "success")
    return redirect(url_for("pages.financeiro"))


@pages_bp.route("/cobrancas/confirmarPagamento", methods=["POST"])
@page_nivel_required("admin", "financeiro")
def cobrancas_confirmar_pagamento_alias():
    transacao_id = _form_int("id", "idCobranca", "cobranca_id", "transacao_id")
    if not transacao_id:
        return _json_or_error("Informe a cobrança.")
    t = db.get_or_404(Transacao, transacao_id)
    t.status = "pago"
    t.data_pagamento = _safe_date(request.form.get("data_pagamento") or request.form.get("recebimento")) or _now()
    registrar("pagamento", "cobrancas", f"Cobrança #{t.id} marcada como paga")
    db.session.commit()
    if _wants_json():
        return jsonify({"result": True, "transacao": t.to_dict()})
    flash("Cobrança marcada como paga.", "success")
    return redirect(url_for("pages.cobrancas"))


@pages_bp.route("/cobrancas/cancelar", methods=["POST"])
@page_nivel_required("admin", "financeiro")
def cobrancas_cancelar_alias():
    transacao_id = _form_int("id", "idCobranca", "cobranca_id", "transacao_id")
    if not transacao_id:
        return _json_or_error("Informe a cobrança.")
    t = db.get_or_404(Transacao, transacao_id)
    t.status = "cancelado"
    registrar("cancelamento", "cobrancas", f"Cobrança #{t.id} cancelada")
    db.session.commit()
    if _wants_json():
        return jsonify({"result": True, "transacao": t.to_dict()})
    flash("Cobrança cancelada.", "success")
    return redirect(url_for("pages.cobrancas"))


@pages_bp.route("/cobrancas/atualizar", methods=["POST"])
@page_nivel_required("admin", "financeiro")
def cobrancas_atualizar_alias():
    transacao_id = _form_int("id", "idCobranca", "cobranca_id", "transacao_id")
    if not transacao_id:
        return _json_or_error("Informe a cobrança.")
    t = db.get_or_404(Transacao, transacao_id)
    descricao = sanitize_text(request.form.get("descricao", t.descricao or ""), max_length=300)
    valor = _form_float("valor", default=float(t.valor or 0))
    status = request.form.get("status") or t.status
    if valor < 0 or status not in {"pendente", "pago", "cancelado"}:
        return _json_or_error("Dados inválidos para atualizar cobrança.")
    t.descricao = descricao or t.descricao
    t.valor = valor
    t.status = status
    t.data_vencimento = _safe_date(request.form.get("data_vencimento") or request.form.get("vencimento")) or t.data_vencimento
    t.forma_pagamento = sanitize_text(request.form.get("forma_pagamento", t.forma_pagamento or ""), max_length=50) or None
    if status == "pago" and not t.data_pagamento:
        t.data_pagamento = _now()
    registrar("edicao", "cobrancas", f"Cobrança #{t.id} atualizada")
    db.session.commit()
    if _wants_json():
        return jsonify({"result": True, "transacao": t.to_dict()})
    flash("Cobrança atualizada.", "success")
    return redirect(url_for("pages.cobrancas"))


@pages_bp.route("/cobrancas/enviarEmail", methods=["POST"])
@page_nivel_required("admin", "financeiro")
def cobrancas_enviar_email_alias():
    transacao_id = _form_int("id", "idCobranca", "cobranca_id", "transacao_id")
    if not transacao_id:
        return _json_or_error("Informe a cobrança.")
    t = db.get_or_404(Transacao, transacao_id)
    cliente = None
    if t.os_id:
        os_obj = OrdemServico.query.filter_by(id=t.os_id).filter(OrdemServico.deletado_em.is_(None)).first()
        cliente = os_obj.cliente if os_obj else None
    if not cliente or not cliente.email:
        return _json_or_error("Esta cobrança não possui cliente com e-mail cadastrado.")
    from app.services.notifications import enqueue_email
    assunto = f"Cobrança #{t.id:04d} - Zokyo"
    vencimento = t.data_vencimento.strftime("%d/%m/%Y") if t.data_vencimento else "sem vencimento definido"
    mensagem = (
        f"Ola, {cliente.nome}.\n\n"
        f"Segue cobrança referente a {t.descricao or 'lançamento'}.\n"
        f"Valor: R$ {float(t.valor or 0):.2f}\n"
        f"Vencimento: {vencimento}\n\n"
        "Obrigado."
    )
    notification, _created = enqueue_email(
        g.organization_id,
        cliente.email,
        assunto,
        mensagem,
        "billing_charge",
        f"billing-charge-{g.organization_id}-{t.id}-{int(float(t.valor or 0) * 100)}",
    )
    registrar("email", "cobrancas", f"Cobrança #{t.id} enfileirada para {cliente.email}", f"Notificação #{notification.id}")
    db.session.commit()
    if _wants_json():
        return jsonify({"result": True, "message": "Cobrança enfileirada para envio.", "notification_id": notification.id})
    flash("Cobrança enfileirada para envio por e-mail.", "success")
    return redirect(url_for("pages.cobrancas"))


@pages_bp.route("/cobrancas/gerarPagamento", methods=["POST"])
@pages_bp.route("/cobrancas/gerar-pagamento", methods=["POST"])
@page_nivel_required("admin", "financeiro")
def cobrancas_gerar_pagamento_alias():
    transacao_id = _form_int("id", "idCobranca", "cobranca_id", "transacao_id")
    if not transacao_id:
        return _json_or_error("Informe a cobrança.")
    t = db.get_or_404(Transacao, transacao_id)
    try:
        from app.services.payment_gateways import apply_payment, generate_payment

        result = generate_payment(
            t,
            gateway=request.form.get("payment_gateway") or request.form.get("gateway") or "pix",
            method=request.form.get("payment_method") or request.form.get("metodo") or "pix",
            days=request.form.get("dias", 7, type=int),
        )
        apply_payment(t, result)
    except (TypeError, ValueError) as exc:
        return _json_or_error(str(exc))
    registrar("pagamento", "cobrancas", f"Pagamento gerado para cobrança #{t.id}", result.provider_id)
    db.session.commit()
    if _wants_json():
        return jsonify({"result": True, "transacao": t.to_dict(), "payment": result.to_dict()})
    flash("Pagamento da cobrança gerado.", "success")
    return redirect(url_for("pages.cobrancas_visualizar_alias", id=t.id))


@pages_bp.route("/api/v1/cobrancas/<int:id>/pagamento", methods=["GET", "POST"])
@nivel_required("admin", "financeiro")
def api_cobranca_pagamento(id):
    t = db.get_or_404(Transacao, id)
    if request.method == "GET":
        return jsonify({"result": True, "transacao": t.to_dict(), "payment": {
            "payment_gateway": t.payment_gateway,
            "payment_method": t.payment_method,
            "payment_provider_id": t.payment_provider_id,
            "payment_status": t.payment_status,
            "payment_url": t.payment_url,
            "link": t.payment_link,
            "barcode": t.payment_barcode,
            "payload": t.payment_payload,
            "expires_at": t.payment_expires_at.isoformat() if t.payment_expires_at else None,
        }})
    data = request.get_json(silent=True) or request.form
    try:
        from app.services.payment_gateways import apply_payment, generate_payment

        result = generate_payment(
            t,
            gateway=data.get("payment_gateway") or data.get("gateway") or "pix",
            method=data.get("payment_method") or data.get("metodo") or "pix",
            days=int(data.get("dias") or 7),
        )
        apply_payment(t, result)
    except (TypeError, ValueError) as exc:
        return jsonify({"result": False, "erro": str(exc)}), 400
    registrar("pagamento", "cobrancas", f"Pagamento gerado para cobrança #{t.id}", result.provider_id)
    db.session.commit()
    return jsonify({"result": True, "transacao": t.to_dict(), "payment": result.to_dict()})


@pages_bp.route("/financeiro/<int:id>/deletar", methods=["POST"])
@pages_bp.route("/financeiro/excluir/<int:id>", methods=["POST"])
@pages_bp.route("/lancamentos/excluir/<int:id>", methods=["POST"])
@pages_bp.route("/vendas/excluir/<int:id>", methods=["POST"])
@pages_bp.route("/cobrancas/excluir/<int:id>", methods=["POST"])
@page_nivel_required("admin", "financeiro")
def transacao_deletar(id):
    t = db.get_or_404(Transacao, id)
    t.status = "cancelado"
    registrar("exclusao", "financeiro", f"Transação #{id} cancelada")
    db.session.commit()
    flash("Transação cancelada.", "success")
    return redirect(url_for("pages.financeiro"))
