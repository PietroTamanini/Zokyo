"""
routes/configuracoes.py — Configurações do sistema e WhatsApp.

Fix: Evolution API removida — usa wpp-server.js.
     Status endpoint correto para o novo utils/whatsapp.py.
"""
from flask import (Blueprint, render_template, request,
                   redirect, url_for, flash, jsonify)
from app.extensions import db
from app.models import Configuracao, registrar
from app.utils.auth import page_nivel_required, api_login_required
from app.utils.sanitizers import sanitize_text, sanitize_email, sanitize_cnpj, sanitize_phone
from app.utils.validators import validar_email, validar_cnpj, validar_telefone

cfg_bp = Blueprint("configuracoes", __name__)


@cfg_bp.route("/configuracoes")
@page_nivel_required("admin")
def index():
    cfg = Configuracao.get()
    return render_template("pages/configuracoes.html",
                           active="configuracoes", cfg=cfg)


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
    cfg.dados_pagamento = sanitize_text(data.get("dados_pagamento", ""), max_length=2000) or None
    cfg.pix_chave       = sanitize_text(data.get("pix_chave", ""), max_length=200) or None
    # wkhtmltopdf_path: caminho de sistema — só sanitiza tamanho
    cfg.wkhtmltopdf_path = sanitize_text(data.get("wkhtmltopdf_path", ""), max_length=500) or None

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


# ── WhatsApp (wpp-server.js) ──────────────────────────────────
@cfg_bp.route("/configuracoes/whatsapp", methods=["POST"])
@page_nivel_required("admin")
def salvar_whatsapp():
    """Salva URL do wpp-server.js local."""
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
@api_login_required
def whatsapp_status():
    """Verifica se o wpp-server.js está online."""
    from app.utils.whatsapp import status_wpp
    return jsonify(status_wpp())


@cfg_bp.route("/api/whatsapp/teste", methods=["POST"])
@api_login_required
def whatsapp_teste():
    """Envia mensagem de teste para o número informado."""
    from app.utils.whatsapp import enviar_whatsapp
    data   = request.get_json(silent=True) or {}
    numero = data.get("numero", "").strip()
    if not numero:
        return jsonify({"erro": "numero é obrigatório"}), 400
    resultado = enviar_whatsapp(numero, "✅ Teste Zokyo — WhatsApp funcionando!")
    return jsonify(resultado)


@cfg_bp.route("/api/whatsapp/qr")
@api_login_required
def whatsapp_qr():
    """Busca QR code do wpp-server.js para exibir na interface."""
    from app.utils.whatsapp import _wpp_url, _wpp_headers, _is_safe_wpp_url
    import requests
    srv_url = _wpp_url()
    if not srv_url or not _is_safe_wpp_url(srv_url):
        return jsonify({"erro": "Servidor WhatsApp não configurado"}), 503
    try:
        resp = requests.get(f"{srv_url}/qr", headers=_wpp_headers(), timeout=5, allow_redirects=False)
        return jsonify(resp.json())
    except Exception as exc:
        return jsonify({"erro": str(exc)}), 503


@cfg_bp.route("/api/whatsapp/reconectar", methods=["POST"])
@api_login_required
def whatsapp_reconectar():
    """Envia comando de reconexão ao wpp-server.js."""
    from app.utils.whatsapp import _wpp_url, _wpp_headers, _is_safe_wpp_url
    import requests
    srv_url = _wpp_url()
    if not srv_url or not _is_safe_wpp_url(srv_url):
        return jsonify({"erro": "Servidor WhatsApp não configurado"}), 503
    try:
        resp = requests.post(f"{srv_url}/reconectar", headers=_wpp_headers(), timeout=5, allow_redirects=False)
        return jsonify(resp.json())
    except Exception as exc:
        return jsonify({"erro": str(exc)}), 503
