"""
routes/auth.py — Login, logout, primeiro acesso.

Fixes:
  C04 — IP real via request.remote_addr (ProxyFix já aplicado)
  M02 — Lock de mutex no primeiro acesso (anti race condition)
  V-01 — validar_senha_forte() agora é chamada no primeiro acesso
"""
import time

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, session, url_for
from sqlalchemy import null

from app.extensions import db
from app.models import Usuario, registrar
from app.services.password_reset import consumir_token, criar_token, enviar_link, localizar_token
from app.services.two_factor import (
    consume_recovery_code,
    decrypt_secret,
    encrypt_secret,
    generate_recovery_codes,
    new_secret,
    provisioning_uri,
    qr_data_uri,
    verify_totp,
)
from app.utils.auth import (
    page_nivel_required,
    validar_senha_forte,  # V-01: importação necessária
)
from app.utils.rate_limit import rate_limit_route
from app.utils.sanitizers import sanitize_email, sanitize_text
from app.utils.validators import validar_email

auth_bp = Blueprint("auth", __name__)
SENHA_MIN = 8
BEARER_SCHEME = "Bearer"


def _ip():
    """IP real — ProxyFix já processou X-Forwarded-For de forma segura."""
    return request.remote_addr or "unknown"


def _login_user(usuario):
    session.clear()
    session.permanent = True
    session["usuario_id"] = usuario.id
    session["nivel"] = usuario.nivel
    session["perfil"] = usuario.nivel
    session["usuario_nome"] = usuario.nome
    session["security_version"] = usuario.security_version
    session["_last_active"] = time.time()
    from app.services.user_sessions import create_session_record
    create_session_record(usuario)
    registrar(
        "login", "sistema", f"Login: {usuario.nome}",
        usuario_id=usuario.id, usuario_nome=usuario.nome, organization_id=usuario.organization_id,
    )
    db.session.commit()
    if usuario.is_platform_admin and not usuario.organization_id:
        destination = "platform.index"
        return redirect(url_for(destination))
    else:
        destination = "pages.dashboard" if usuario.onboarding_completed else "pages.ajuda"
    return redirect(url_for(destination, onboarding=1))


# ── Rotas ──────────────────────────────────────────────────────────────────────

@auth_bp.route("/login", methods=["GET"])
def login_page():
    if "usuario_id" in session:
        return redirect(url_for("pages.dashboard"))
    return render_template("pages/login.html")


@auth_bp.route("/login", methods=["POST"])
def login_post():
    from app.utils.rate_limit import check_lock, clear_fails, register_fail
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
    if usuario.nivel == "admin" and usuario.totp_enabled:
        session.clear()
        session["2fa_user_id"] = usuario.id
        session["2fa_expires"] = time.time() + 300
        return redirect(url_for("auth.two_factor_challenge"))
    return _login_user(usuario)


def _api_login_payload(usuario):
    session.clear()
    session.permanent = True
    session["usuario_id"] = usuario.id
    session["nivel"] = usuario.nivel
    session["perfil"] = usuario.nivel
    session["usuario_nome"] = usuario.nome
    session["security_version"] = usuario.security_version
    session["_last_active"] = time.time()
    from app.services.user_sessions import create_session_record

    record = create_session_record(usuario)
    raw_token = session["session_token"]
    registrar(
        "login", "api", f"Login API: {usuario.nome}",
        usuario_id=usuario.id, usuario_nome=usuario.nome, organization_id=usuario.organization_id,
    )
    db.session.commit()
    return {
        "status": True,
        "message": "Login efetuado com sucesso",
        "token": raw_token,
        "token_type": BEARER_SCHEME,
        "expires_at": record.expires_at.isoformat(),
        "user": usuario.to_dict(),
    }


@auth_bp.route("/api/v1/login", methods=["POST"])
@rate_limit_route(max_hits=10, window_seconds=300)
def api_v1_login():
    data = request.get_json(silent=True) or {}
    email = sanitize_email(data.get("email", ""))
    senha = data.get("password") or data.get("senha") or ""
    if not email or not validar_email(email) or not senha:
        time.sleep(0.3)
        return jsonify({"status": False, "message": "Os dados de acesso estao incorretos"}), 401
    usuario = Usuario.query.filter_by(email=email, ativo=True).first()
    if not usuario or not usuario.check_senha(senha) or not usuario.organization or not usuario.organization.ativo:
        time.sleep(0.3)
        return jsonify({"status": False, "message": "Os dados de acesso estao incorretos"}), 401
    if usuario.totp_enabled or (current_app.config.get("REQUIRE_ADMIN_2FA") and usuario.nivel == "admin"):
        return jsonify({"status": False, "message": "Segundo fator obrigatório para login via API"}), 403
    return jsonify(_api_login_payload(usuario))


@auth_bp.route("/api/v1/reGenToken", methods=["POST"])
def api_v1_regen_token():
    from app.services.user_sessions import current_session_record, revoke_record
    from app.utils.auth import authenticate_bearer_session

    usuario = authenticate_bearer_session()
    if not usuario:
        return jsonify({"status": False, "message": "Token inválido ou expirado"}), 401
    old_record = current_session_record(usuario.id)
    payload = _api_login_payload(usuario)
    if old_record:
        revoke_record(old_record, "token regenerado")
        db.session.commit()
    return jsonify(payload)


@auth_bp.route("/2fa", methods=["GET", "POST"])
@rate_limit_route(max_hits=10, window_seconds=300)
def two_factor_challenge():
    user_id = session.get("2fa_user_id")
    if not user_id or session.get("2fa_expires", 0) < time.time():
        session.clear()
        return redirect(url_for("auth.login_page"))
    usuario = db.session.get(Usuario, user_id)
    secret = decrypt_secret(usuario.totp_secret_encrypted) if usuario else None
    if not usuario or not usuario.ativo or not usuario.totp_enabled or not secret:
        session.clear()
        return redirect(url_for("auth.login_page"))
    if request.method == "POST":
        code = request.form.get("codigo", "").strip().lower()
        if verify_totp(secret, code) or consume_recovery_code(usuario, code):
            registrar("login", "sistema", "Segundo fator validado.", usuario_id=usuario.id, usuario_nome=usuario.nome)
            db.session.commit()
            return _login_user(usuario)
        registrar("falha_login", "sistema", "Segundo fator inválido.", usuario_id=usuario.id, usuario_nome=usuario.nome)
        db.session.commit()
        flash("Código inválido.", "error")
    return render_template("pages/two_factor_challenge.html")


@auth_bp.route("/seguranca/2fa", methods=["GET", "POST"])
@page_nivel_required("admin")
def two_factor_setup():
    usuario = db.session.get(Usuario, session["usuario_id"])
    if request.method == "POST":
        secret = decrypt_secret(usuario.totp_secret_encrypted)
        if not secret or not verify_totp(secret, request.form.get("codigo", "")):
            flash("Código TOTP inválido. Confira o horário do dispositivo.", "error")
            return redirect(url_for("auth.two_factor_setup"))
        codes, hashes = generate_recovery_codes()
        usuario.totp_enabled = True
        usuario.recovery_codes_hash = hashes
        registrar("seguranca", "usuarios", "2FA ativado.", usuario_id=usuario.id, usuario_nome=usuario.nome)
        db.session.commit()
        return render_template("pages/two_factor_recovery.html", recovery_codes=codes)
    if usuario.totp_enabled:
        return render_template("pages/two_factor_setup.html", enabled=True)
    secret = new_secret()
    usuario.totp_secret_encrypted = encrypt_secret(secret)
    db.session.commit()
    uri = provisioning_uri(secret, usuario.email)
    return render_template("pages/two_factor_setup.html", enabled=False, secret=secret, qr=qr_data_uri(uri))


@auth_bp.route("/seguranca/2fa/desativar", methods=["POST"])
@page_nivel_required("admin")
def two_factor_disable():
    usuario = db.session.get(Usuario, session["usuario_id"])
    secret = decrypt_secret(usuario.totp_secret_encrypted)
    if not usuario.check_senha(request.form.get("senha", "")) or not secret or not verify_totp(secret, request.form.get("codigo", "")):
        flash("Senha ou código TOTP inválido.", "error")
        return redirect(url_for("auth.two_factor_setup"))
    usuario.totp_enabled = False
    usuario.totp_secret_encrypted = None
    usuario.recovery_codes_hash = None
    registrar("seguranca", "usuarios", "2FA desativado.", usuario_id=usuario.id, usuario_nome=usuario.nome)
    db.session.commit()
    flash("2FA desativado.", "success")
    return redirect(url_for("auth.two_factor_setup"))


@auth_bp.route("/logout", methods=["POST"])
def logout():
    uid, uname = session.get("usuario_id"), session.get("usuario_nome", "—")
    if uid:
        from app.services.user_sessions import current_session_record, revoke_record
        usuario = db.session.get(Usuario, uid)
        record = current_session_record(uid)
        if record:
            revoke_record(record, "logout")
        registrar("logout", "sistema", f"Logout: {uname}",
                  usuario_id=uid, usuario_nome=uname,
                  organization_id=usuario.organization_id if usuario else None)
        db.session.commit()
    session.clear()
    return redirect(url_for("auth.login_page"))


@auth_bp.route("/seguranca/sessoes")
@page_nivel_required("admin")
def sessions_page():
    from app.models import UserSession
    usuario = db.session.get(Usuario, session["usuario_id"])
    records = UserSession.query.filter_by(user_id=usuario.id).order_by(UserSession.last_seen_at.desc()).limit(100).all()
    current = session.get("session_token")
    from app.services.user_sessions import _hash
    current_hash = _hash(current) if current else None
    return render_template(
        "pages/security_sessions.html",
        active="security_sessions",
        records=records,
        current_hash=current_hash,
    )


@auth_bp.route("/seguranca/sessoes/<int:record_id>/revogar", methods=["POST"])
@page_nivel_required("admin")
def session_revoke(record_id):
    from app.models import UserSession
    from app.services.user_sessions import current_session_record, revoke_record
    record = UserSession.query.filter_by(id=record_id, user_id=session["usuario_id"]).first_or_404()
    current_record = current_session_record(session["usuario_id"])
    revoke_record(record, "revogacao pelo usuario")
    registrar("seguranca", "sessoes", f"Sessão #{record.id} revogada.")
    db.session.commit()
    if current_record and current_record.id == record.id:
        session.clear()
        return redirect(url_for("auth.login_page"))
    flash("Sessao encerrada.", "success")
    return redirect(url_for("auth.sessions_page"))


@auth_bp.route("/seguranca/sessoes/revogar-outras", methods=["POST"])
@page_nivel_required("admin")
def sessions_revoke_others():
    from app.services.user_sessions import current_session_record, revoke_all
    current_record = current_session_record(session["usuario_id"])
    count = revoke_all(
        session["usuario_id"],
        "revogação de outras sessões",
        except_id=current_record.id if current_record else None,
    )
    registrar("seguranca", "sessoes", f"{count} outra(s) sessão(ões) revogada(s).")
    db.session.commit()
    flash(f"{count} outra(s) sessão(ões) encerrada(s).", "success")
    return redirect(url_for("auth.sessions_page"))


@auth_bp.route("/recuperar-senha", methods=["GET", "POST"])
@rate_limit_route(max_hits=5, window_seconds=3600, methods={"POST"})
def recuperar_senha():
    if request.method == "POST":
        email = sanitize_email(request.form.get("email", ""))
        usuario = Usuario.query.filter_by(email=email, ativo=True).first() if validar_email(email) else None
        if usuario:
            _token, raw_token = criar_token(usuario, _ip())
            db.session.commit()
            try:
                enviar_link(usuario, raw_token)
            except Exception:
                current_app.logger.error("Falha ao enviar recuperação de senha.", exc_info=True)
        time.sleep(0.3)
        flash("Se o e-mail estiver cadastrado, enviaremos as instruções de recuperação.", "success")
        return redirect(url_for("auth.login_page"))
    return render_template("pages/password_forgot.html")


@auth_bp.route("/redefinir-senha/<token>", methods=["GET", "POST"])
def redefinir_senha(token):
    reset_token = localizar_token(token)
    if not reset_token:
        flash("Link inválido ou expirado. Solicite uma nova recuperação.", "error")
        return redirect(url_for("auth.recuperar_senha"))
    if request.method == "POST":
        senha = request.form.get("senha", "")
        if senha != request.form.get("confirmar_senha", ""):
            flash("As senhas não coincidem.", "error")
            return render_template("pages/password_reset.html", token=token)
        erros = validar_senha_forte(senha)
        if erros:
            for erro in erros:
                flash(erro, "error")
            return render_template("pages/password_reset.html", token=token)
        consumir_token(reset_token, senha)
        db.session.commit()
        session.clear()
        flash("Senha redefinida. Entre com sua nova senha.", "success")
        return redirect(url_for("auth.login_page"))
    return render_template("pages/password_reset.html", token=token)


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
                    nome=data.get("nome"), email=data.get("email"))

        if data["senha"] != data["confirmar_senha"]:
            flash("As senhas não coincidem.", "error")
            return render_template("pages/register.html",
                nome=data.get("nome"), email=data.get("email"))

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
        admin = Usuario(
            nome=nome_admin, email=email, nivel="admin",
            organization_id=null(), onboarding_completed=True,
            is_platform_admin=True,
        )
        admin.set_senha(data["senha"])
        db.session.add(admin)

        registrar("criacao", "sistema",
                  f"Primeiro acesso — admin criado: {nome_admin}",
                  usuario_nome=nome_admin, organization_id=None)
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
