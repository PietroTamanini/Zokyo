"""Configuracoes administrativas do sistema."""
import re

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from app.extensions import db
from app.models import Configuracao, MessageTemplate, Notification, registrar
from app.utils.auth import nivel_required, page_nivel_required
from app.utils.sanitizers import sanitize_cnpj, sanitize_email, sanitize_phone, sanitize_text
from app.utils.validators import validar_cnpj, validar_email, validar_telefone

cfg_bp = Blueprint("configuracoes", __name__)


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
        flash("Notificacao colocada novamente na fila.", "success")
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

    cfg.nome_empresa    = nome_emp
    cfg.cnpj            = cnpj_raw or None
    cfg.email           = email_emp or None
    cfg.telefone        = tel_emp or None
    cfg.endereco        = sanitize_text(data.get("endereco", ""), max_length=300) or None
    cfg.cidade          = sanitize_text(data.get("cidade", ""), max_length=100) or None
    cfg.uf              = sanitize_text(data.get("uf", ""), max_length=2).upper() or None
    for field, default in (("primary_color", "#2563eb"), ("accent_color", "#6366f1")):
        value = (data.get(field) or default).strip().lower()
        if not re.fullmatch(r"#[0-9a-f]{6}", value):
            flash("Cor de identidade visual invalida.", "error")
            return redirect(url_for("configuracoes.index"))
        setattr(cfg, field, value)
    cfg.dados_pagamento = sanitize_text(data.get("dados_pagamento", ""), max_length=2000) or None
    cfg.pix_chave       = sanitize_text(data.get("pix_chave", ""), max_length=200) or None
    try:
        cfg.dias_vencimento = int(data.get("dias_vencimento") or 30)
    except (ValueError, TypeError):
        pass

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
        cfg.meta_receita_mensal    = float(data.get("meta_receita_mensal")    or 0)
        cfg.alerta_caixa_minimo    = float(data.get("alerta_caixa_minimo")    or 0)
        cfg.alerta_estoque_minimo  = int(data.get("alerta_estoque_minimo")    or 5)
        cfg.alerta_vencimento_dias = int(data.get("alerta_vencimento_dias")   or 5)
    except (ValueError, TypeError):
        pass
    registrar("edicao", "configuracoes", "Configurações de dashboard salvas")
    db.session.commit()
    flash("Configurações de dashboard salvas!", "success")
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


@cfg_bp.route("/api/whatsapp/teste", methods=["POST"])
@nivel_required("admin")
def whatsapp_teste():
    """Envia mensagem de teste para o número informado."""
    from app.utils.whatsapp import enviar_whatsapp
    data   = request.get_json(silent=True) or {}
    numero = data.get("numero", "").strip()
    if not numero:
        return jsonify({"erro": "numero é obrigatório"}), 400
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
        return jsonify({"erro": "Evento, canal valido e mensagem sao obrigatorios"}), 400
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
