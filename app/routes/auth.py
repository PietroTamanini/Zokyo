"""
routes/auth.py — Login, logout, primeiro acesso.

Fixes:
  C04 — IP real via request.remote_addr (ProxyFix já aplicado)
  M02 — Lock de mutex no primeiro acesso (anti race condition)
  V-01 — validar_senha_forte() agora é chamada no primeiro acesso
"""
import time

from flask import (Blueprint, current_app, request, session,
                   redirect, url_for, render_template, flash)
from app.extensions import db
from app.models import Usuario, registrar
from app.utils.auth import validar_senha_forte  # V-01: importação necessária
from app.utils.sanitizers import sanitize_text, sanitize_email
from app.utils.validators import validar_email

auth_bp = Blueprint("auth", __name__)
SENHA_MIN = 8


def _ip():
    """IP real — ProxyFix já processou X-Forwarded-For de forma segura."""
    return request.remote_addr or "unknown"


# ── Rotas ──────────────────────────────────────────────────────────────────────

@auth_bp.route("/login", methods=["GET"])
def login_page():
    if "usuario_id" in session:
        return redirect(url_for("pages.dashboard"))
    return render_template("pages/login.html")


@auth_bp.route("/login", methods=["POST"])
def login_post():
    from app.utils.rate_limit import check_lock, register_fail, clear_fails
    ip = _ip()

    bloqueado, remaining = check_lock(ip)
    if bloqueado:
        flash(f"Muitas tentativas. Aguarde {remaining}s.", "error")
        return render_template("pages/login.html"), 429

    email = sanitize_email(request.form.get("email", ""))
    senha = request.form.get("senha", "")
    if not email or not validar_email(email):
        time.sleep(0.3)
        flash("E-mail ou senha incorretos.", "error")
        return render_template("pages/login.html")

    # Busca sempre (não revelar se e-mail existe via timing)
    usuario = Usuario.query.filter_by(email=email, ativo=True).first()

    # Timing constante independente de o usuário existir ou não
    if not usuario or not usuario.check_senha(senha):
        secs = register_fail(ip)
        if secs:
            flash(f"Conta bloqueada por {secs}s por excesso de tentativas.", "error")
        else:
            flash("E-mail ou senha incorretos.", "error")
        # Pausa artificial para dificultar timing attacks
        time.sleep(0.3)
        return render_template("pages/login.html", email=email)

    clear_fails(ip)
    session.clear()
    session.permanent       = True
    session["usuario_id"]   = usuario.id
    session["nivel"]        = usuario.nivel
    session["perfil"]       = usuario.nivel
    session["usuario_nome"] = usuario.nome
    session["_last_active"] = time.time()   # M06: inicializa timestamp de atividade

    registrar("login", "sistema", f"Login: {usuario.nome}",
              usuario_id=usuario.id, usuario_nome=usuario.nome)
    db.session.commit()
    return redirect(url_for("pages.dashboard"))


@auth_bp.route("/logout", methods=["POST"])
def logout():
    uid, uname = session.get("usuario_id"), session.get("usuario_nome", "—")
    if uid:
        registrar("logout", "sistema", f"Logout: {uname}",
                  usuario_id=uid, usuario_nome=uname)
        db.session.commit()
    session.clear()
    return redirect(url_for("auth.login_page"))


@auth_bp.route("/primeiro-acesso", methods=["GET"])
def primeiro_acesso_page():
    if Usuario.query.first():
        return redirect(url_for("auth.login_page"))
    return render_template("pages/register.html")


@auth_bp.route("/primeiro-acesso", methods=["POST"])
def primeiro_acesso_post():
    """
    M02: usa lock de processo para evitar race condition.
    Se duas requisições chegarem simultaneamente, apenas uma cria o admin.
    """
    lock = getattr(current_app, "_primeiro_acesso_lock", None)

    def _processar():
        # Verifica dentro do lock
        if Usuario.query.first():
            return redirect(url_for("auth.login_page"))

        data = request.form
        for campo in ("nome", "email", "senha", "confirmar_senha"):
            if not data.get(campo):
                flash(f"Campo obrigatório: {campo.replace('_', ' ')}.", "error")
                return render_template("pages/register.html",
                    nome=data.get("nome"), email=data.get("email"),
                    empresa_nome=data.get("empresa_nome"))

        if data["senha"] != data["confirmar_senha"]:
            flash("As senhas não coincidem.", "error")
            return render_template("pages/register.html",
                nome=data.get("nome"), email=data.get("email"),
                empresa_nome=data.get("empresa_nome"))

        # ── V-01 FIX: aplica política de senha forte ──────────────────────
        erros = validar_senha_forte(data["senha"])
        if erros:
            for erro in erros:
                flash(erro, "error")
            return render_template("pages/register.html")
        # ─────────────────────────────────────────────────────────────────

        email = sanitize_email(data.get("email", ""))
        if not validar_email(email):
            flash("E-mail inválido.", "error")
            return render_template("pages/register.html")
        nome_admin = sanitize_text(data.get("nome", ""), max_length=120)
        if not nome_admin or len(nome_admin) < 2:
            flash("Nome deve ter pelo menos 2 caracteres.", "error")
            return render_template("pages/register.html")
        admin = Usuario(nome=nome_admin, email=email, nivel="admin")
        admin.set_senha(data["senha"])
        db.session.add(admin)

        from app.models import Configuracao
        if not Configuracao.query.first():
            cfg = Configuracao(
                nome_empresa=data.get("empresa_nome", "Zokyo Platform"))
            db.session.add(cfg)

        registrar("criacao", "sistema",
                  f"Primeiro acesso — admin criado: {nome_admin}",
                  usuario_nome=nome_admin)
        db.session.commit()
        flash("Conta criada! Faça login.", "success")
        return redirect(url_for("auth.login_page"))

    if lock:
        with lock:
            return _processar()
    return _processar()


@auth_bp.route("/register")
def register_page():
    return redirect(url_for("auth.primeiro_acesso_page"))
