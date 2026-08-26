"""Configuracoes administrativas do sistema."""
import re
import unicodedata
from urllib.parse import urlparse

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from app.extensions import db
from app.models import Configuracao, MessageTemplate, Notification, registrar
from app.utils.auth import nivel_required, page_nivel_required
from app.utils.sanitizers import sanitize_cnpj, sanitize_email, sanitize_phone, sanitize_text
from app.utils.validators import validar_cnpj, validar_email, validar_telefone

cfg_bp = Blueprint("configuracoes", __name__)

PROTECTED_STATUS_KEYS = {"recepcao", "entregue", "cancelado"}


def _slug_option(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()
    return text[:50]


def _parse_options(prefix: str, *, protected_keys=()):
    keys = request.form.getlist(f"{prefix}_key[]")
    labels = request.form.getlist(f"{prefix}_label[]")
    options = []
    seen = set()
    for raw_key, raw_label in zip(keys, labels):
        label = sanitize_text(raw_label, max_length=80)
        key = _slug_option(raw_key) or _slug_option(label)
        if not key or not label or key in seen:
            continue
        options.append({"key": key, "label": label})
        seen.add(key)
    for key in protected_keys:
        if key not in seen:
            current_label = {
                "recepcao": "Recepção",
                "entregue": "Entregue",
                "cancelado": "Cancelado",
            }.get(key, key.title())
            options.append({"key": key, "label": current_label})
            seen.add(key)
    return options


def _public_url(value: str | None, *, max_length: int = 300, allow_static_path: bool = False) -> str | None:
    text = sanitize_text(value or "", max_length=max_length).strip()
    if not text:
        return None
    if allow_static_path and text.startswith("/static/") and not any(char in text for char in ("\r", "\n", "\\")):
        return text
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        return None
    return text


@cfg_bp.route("/configuracoes")
@page_nivel_required("admin")
def index():
    cfg = Configuracao.get()
    return render_template("pages/configuracoes.html",
                           active="configuracoes", cfg=cfg)


@cfg_bp.route("/configuracoes/notificacoes")
@page_nivel_required("admin")
def notificacoes():
    status = (request.args.get("status") or "").strip()
    page = max(request.args.get("page", 1, type=int), 1)
    query = Notification.query.order_by(Notification.created_at.desc())
    if status in {"pending", "retry", "sent", "manual_required", "failed"}:
        query = query.filter_by(status=status)
    pagination = query.paginate(page=page, per_page=30, error_out=False)
    return render_template(
        "pages/notificacoes.html", active="notificacoes",
        notifications=pagination.items, pagination=pagination, selected_status=status,
    )


@cfg_bp.route("/configuracoes/notificacoes/<int:notification_id>/retry", methods=["POST"])
@page_nivel_required("admin")
def notificacao_retry(notification_id):
    from flask import g

    from app.services.notifications import retry_notification

    try:
        retry_notification(notification_id, g.organization_id)
    except LookupError:
        return ("", 404)
    except ValueError as exc:
        flash(str(exc), "warning")
    else:
        registrar("retry", "notifications", f"Reenvio solicitado para notificacao #{notification_id}.")
        db.session.commit()
        flash("Notificação colocada novamente na fila.", "success")
    return redirect(url_for("configuracoes.notificacoes"))


@cfg_bp.route("/configuracoes/salvar", methods=["POST"])
@page_nivel_required("admin")
def salvar():
    cfg  = Configuracao.get()
    data = request.form

    nome_emp = sanitize_text(data.get("nome_empresa", ""), max_length=200)
    if not nome_emp:
        flash("Nome da empresa é obrigatório.", "error")
        return redirect(url_for("configuracoes.index"))

    cnpj_raw = sanitize_cnpj(data.get("cnpj", ""))
    if cnpj_raw and not validar_cnpj(cnpj_raw):
        flash("CNPJ da empresa inválido.", "error")
        return redirect(url_for("configuracoes.index"))

    email_emp = sanitize_email(data.get("email", ""))
    if email_emp and not validar_email(email_emp):
        flash("E-mail da empresa inválido.", "error")
        return redirect(url_for("configuracoes.index"))

    tel_emp = sanitize_phone(data.get("telefone", ""))
    if tel_emp and not validar_telefone(tel_emp):
        flash("Telefone da empresa inválido.", "error")
        return redirect(url_for("configuracoes.index"))

    try:
        dias_vencimento = int(data.get("dias_vencimento") or 30)
    except (ValueError, TypeError):
        flash("Dias para vencimento deve ser um numero inteiro.", "error")
        return redirect(url_for("configuracoes.index"))
    if dias_vencimento < 1:
        flash("Dias para vencimento deve ser maior que zero.", "error")
        return redirect(url_for("configuracoes.index"))

    cfg.nome_empresa    = nome_emp
    cfg.cnpj            = cnpj_raw or None
    cfg.email           = email_emp or None
    cfg.telefone        = tel_emp or None
    cfg.endereco        = sanitize_text(data.get("endereco", ""), max_length=300) or None
    cfg.cidade          = sanitize_text(data.get("cidade", ""), max_length=100) or None
    cfg.uf              = sanitize_text(data.get("uf", ""), max_length=2).upper() or None
    cfg.subtitulo_empresa = sanitize_text(data.get("subtitulo_empresa", ""), max_length=160) or None
    for field in ("logo_url", "site_url", "instagram_url"):
        value = _public_url(
            data.get(field),
            max_length=600 if field == "logo_url" else 300,
            allow_static_path=field == "logo_url",
        )
        if data.get(field) and not value:
            flash("Informe links públicos válidos começando com http:// ou https://.", "error")
            return redirect(url_for("configuracoes.index"))
        setattr(cfg, field, value)
    whatsapp_publico = sanitize_phone(data.get("whatsapp_publico", ""))
    if whatsapp_publico and not validar_telefone(whatsapp_publico):
        flash("WhatsApp público inválido.", "error")
        return redirect(url_for("configuracoes.index"))
    cfg.whatsapp_publico = whatsapp_publico or None
    for field, default in (("primary_color", "#2563eb"), ("accent_color", "#6366f1")):
        value = (data.get(field) or default).strip().lower()
        if not re.fullmatch(r"#[0-9a-f]{6}", value):
            flash("Cor de identidade visual invalida.", "error")
            return redirect(url_for("configuracoes.index"))
        setattr(cfg, field, value)
    cfg.dados_pagamento = sanitize_text(data.get("dados_pagamento", ""), max_length=2000) or None
    cfg.pix_chave       = sanitize_text(data.get("pix_chave", ""), max_length=200) or None
    cfg.dias_vencimento = dias_vencimento

    registrar("edicao", "configuracoes", "Configurações gerais salvas")
    db.session.commit()
    flash("Configurações salvas!", "success")
    return redirect(url_for("configuracoes.index"))


@cfg_bp.route("/configuracoes/dashboard", methods=["POST"])
@page_nivel_required("admin")
def salvar_dashboard():
    cfg  = Configuracao.get()
    data = request.form
    try:
        meta_receita_mensal = float(data.get("meta_receita_mensal") or 0)
        alerta_caixa_minimo = float(data.get("alerta_caixa_minimo") or 0)
        alerta_estoque_minimo = int(data.get("alerta_estoque_minimo") or 5)
        alerta_vencimento_dias = int(data.get("alerta_vencimento_dias") or 5)
    except (ValueError, TypeError):
        flash("Os indicadores do dashboard devem conter apenas numeros validos.", "error")
        return redirect(url_for("configuracoes.index"))
    if min(meta_receita_mensal, alerta_caixa_minimo, alerta_estoque_minimo, alerta_vencimento_dias) < 0:
        flash("Os indicadores do dashboard nao podem ser negativos.", "error")
        return redirect(url_for("configuracoes.index"))
    cfg.meta_receita_mensal = meta_receita_mensal
    cfg.alerta_caixa_minimo = alerta_caixa_minimo
    cfg.alerta_estoque_minimo = alerta_estoque_minimo
    cfg.alerta_vencimento_dias = alerta_vencimento_dias
    registrar("edicao", "configuracoes", "Configurações de dashboard salvas")
    db.session.commit()
    flash("Configurações de dashboard salvas!", "success")
    return redirect(url_for("configuracoes.index"))


@cfg_bp.route("/configuracoes/os-opcoes", methods=["POST"])
@page_nivel_required("admin")
def salvar_os_opcoes():
    cfg = Configuracao.get()
    status_options = _parse_options("status", protected_keys=PROTECTED_STATUS_KEYS)
    priority_options = _parse_options("priority")
    attendance_options = _parse_options("attendance")
    checklist_options = _parse_options("entry_checklist")
    if not status_options:
        flash("Informe pelo menos um status de OS.", "error")
        return redirect(url_for("configuracoes.index"))
    if not priority_options:
        flash("Informe pelo menos uma prioridade.", "error")
        return redirect(url_for("configuracoes.index"))
    if not attendance_options:
        flash("Informe pelo menos um tipo de atendimento.", "error")
        return redirect(url_for("configuracoes.index"))
    if not checklist_options:
        flash("Informe pelo menos um item no checklist de entrada.", "error")
        return redirect(url_for("configuracoes.index"))
    cfg.set_os_status_options(status_options)
    cfg.set_os_priority_options(priority_options)
    cfg.set_attendance_type_options(attendance_options)
    cfg.set_entry_checklist_options(checklist_options)
    registrar("edicao", "configuracoes", "Opções de OS salvas")
    db.session.commit()
    flash("Opções de OS salvas.", "success")
    return redirect(url_for("configuracoes.index"))


@cfg_bp.route("/configuracoes/whatsapp", methods=["POST"])
@page_nivel_required("admin")
def salvar_whatsapp():
    """Salva a URL de um gateway externo explicitamente permitido."""
    cfg = Configuracao.get()
    wpp_url = (request.form.get("wpp_server_url") or "").strip()
    if wpp_url:
        from app.utils.whatsapp import _is_safe_wpp_url
        if not _is_safe_wpp_url(wpp_url):
            flash("URL do servidor WhatsApp inválida ou não permitida.", "error")
            return redirect(url_for("configuracoes.index"))
        cfg.wpp_server_url = wpp_url[:300]
    else:
        cfg.wpp_server_url = None
    registrar("edicao", "configuracoes", "Configurações WhatsApp salvas")
    db.session.commit()
    flash("Configurações WhatsApp salvas!", "success")
    return redirect(url_for("configuracoes.index"))


@cfg_bp.route("/api/whatsapp/status")
@nivel_required("admin")
def whatsapp_status():
    """Verifica se o gateway externo esta online."""
    from app.utils.whatsapp import status_wpp
    return jsonify(status_wpp())


@cfg_bp.route("/api/v1/emitente")
@nivel_required("admin", "operacional", "consulta")
def emitente_v1():
    cfg = Configuracao.get()
    return jsonify({
        "id": cfg.id,
        "nome": cfg.nome_empresa or "",
        "nome_empresa": cfg.nome_empresa or "",
        "cnpj": cfg.cnpj or "",
        "telefone": cfg.telefone or "",
        "email": cfg.email or "",
        "endereco": cfg.endereco or "",
        "cidade": cfg.cidade or "",
        "uf": cfg.uf or "",
        "subtitulo_empresa": cfg.subtitulo_empresa or "",
        "logo_url": cfg.logo_url or "",
        "site_url": cfg.site_url or "",
        "instagram_url": cfg.instagram_url or "",
        "whatsapp_publico": cfg.whatsapp_publico or "",
        "dados_pagamento": cfg.dados_pagamento or "",
        "pix_chave": cfg.pix_chave or "",
    })


@cfg_bp.route("/api/whatsapp/teste", methods=["POST"])
@nivel_required("admin")
def whatsapp_teste():
    """Envia mensagem de teste para o número informado."""
    from app.utils.whatsapp import enviar_whatsapp
    data   = request.get_json(silent=True) or {}
    numero = data.get("numero", "").strip()
    if not numero:
        return jsonify({"erro": "número é obrigatório"}), 400
    resultado = enviar_whatsapp(numero, "✅ Teste Zokyo — WhatsApp funcionando!")
    return jsonify(resultado)


@cfg_bp.route("/api/message-templates", methods=["GET"])
@nivel_required("admin")
def message_templates_list():
    items = MessageTemplate.query.order_by(
        MessageTemplate.event_type, MessageTemplate.channel, MessageTemplate.version.desc(),
    ).all()
    return jsonify([{
        "id": item.id, "event_type": item.event_type, "channel": item.channel,
        "version": item.version, "subject": item.subject, "body": item.body, "active": item.active,
    } for item in items])


@cfg_bp.route("/api/message-templates", methods=["POST"])
@nivel_required("admin")
def message_templates_create():
    data = request.get_json(silent=True) or {}
    event_type = sanitize_text(data.get("event_type", ""), max_length=80)
    channel = sanitize_text(data.get("channel", ""), max_length=20)
    subject = sanitize_text(data.get("subject", ""), max_length=200) or None
    body = sanitize_text(data.get("body", ""), max_length=5000)
    if not event_type or channel not in {"email", "whatsapp"} or not body:
        return jsonify({"erro": "Evento, canal válido e mensagem são obrigatórios"}), 400
    previous = MessageTemplate.query.filter_by(event_type=event_type, channel=channel).order_by(
        MessageTemplate.version.desc(),
    ).first()
    for old in MessageTemplate.query.filter_by(event_type=event_type, channel=channel, active=True).all():
        old.active = False
    item = MessageTemplate(
        event_type=event_type, channel=channel, version=(previous.version + 1 if previous else 1),
        subject=subject, body=body,
    )
    db.session.add(item)
    registrar("criacao", "message_templates", f"Template {event_type}/{channel} v{item.version}")
    db.session.commit()
    return jsonify({"id": item.id, "version": item.version}), 201
