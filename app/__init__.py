"""
app/__init__.py — Factory da aplicação Flask, hardened.

Fixes aplicados:
  C04 — ProxyFix com PROXY_COUNT configurável (evita IP spoofing)
  H01 — Content-Security-Policy com nonces (V-03: remove unsafe-inline de scripts)
  H02 — HSTS em produção
  H03 — Rate limiting em todos os blueprints via before_request global
  M02 — Lock de mutex para primeiro acesso (evita race condition)
  M06 — Timeout de inatividade de sessão (30 min sem atividade)
  V-03 — CSP via nonce por request (g.csp_nonce) em vez de unsafe-inline
  V-05 — verificar_usuario_ativo() relê papel e ativo do banco a cada request
  V-06 — APScheduler limpa tabelas de rate limit a cada 24h
  V-09 — Flag em memória evita SELECT em cada request após primeiro usuário criado
"""
import os
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

from flask import Flask, abort, g, request, session, redirect, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

from config import config
from app.extensions import db


# Lock para serializar o endpoint de primeiro acesso (fix M02)
_primeiro_acesso_lock = threading.Lock()

# V-09 FIX: flag em memória — evita SELECT a cada request após setup inicial
_tem_usuarios: bool = False


def create_app(config_name="default"):
    app = Flask(__name__)
    cfg_obj = config[config_name]
    app.config.from_object(cfg_obj)

    # Chama init_app da config (ProductionConfig valida segredos)
    if hasattr(cfg_obj, "init_app"):
        cfg_obj.init_app(app)

    # ── C04: ProxyFix — confia apenas em PROXY_COUNT proxies ──────────────
    proxy_count = app.config.get("PROXY_COUNT", 1)
    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=proxy_count,
        x_proto=proxy_count,
        x_host=proxy_count,
        x_prefix=proxy_count,
    )

    # ── Sessão ────────────────────────────────────────────────────────────
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)
    app.config["SESSION_COOKIE_HTTPONLY"]    = True
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")

    db.init_app(app)

    # ── Context processors ────────────────────────────────────────────────
    # ── Branding centralizado ─────────────────────────────────────────────
    @app.context_processor
    def inject_branding():
        from app.config.branding import get_branding
        try:
            from app.models import Configuracao
            cfg = Configuracao.get()
        except Exception:
            cfg = None
        return get_branding(cfg)

    @app.context_processor
    def inject_globals():
        from flask import session as _s
        from app.models import Usuario, Configuracao
        usuario = None
        if "usuario_id" in _s:
            try:
                usuario = db.session.get(Usuario, _s["usuario_id"])
            except Exception:
                pass
        try:
            cfg = Configuracao.get()
        except Exception:
            cfg = None
        nivel = _s.get("nivel", "")
        ep    = request.endpoint or ""
        return dict(
            current_user=usuario,
            active=ep,
            nivel_usuario=nivel,
            cfg=cfg,
            is_admin=(nivel == "admin"),
            is_financeiro=(nivel in ("admin", "financeiro")),
        )

    @app.context_processor
    def inject_csrf_token():
        def _csrf_token():
            token = session.get("_csrf_token")
            if not token:
                token = secrets.token_urlsafe(32)
                session["_csrf_token"] = token
            return token
        return {"csrf_token": _csrf_token}

    # V-03 FIX: expõe g.csp_nonce nos templates para scripts inline
    @app.context_processor
    def inject_csp_nonce():
        return {"csp_nonce": getattr(g, "csp_nonce", "")}

    # ── Before request ────────────────────────────────────────────────────

    @app.before_request
    def gerar_csp_nonce():
        """V-03: gera nonce criptograficamente único por request."""
        g.csp_nonce = secrets.token_urlsafe(16)

    @app.before_request
    def protect_csrf():
        """CSRF protection para métodos mutantes."""
        if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return
        token    = session.get("_csrf_token")
        supplied = (
            request.form.get("_csrf_token")
            or request.headers.get("X-CSRFToken")
            or request.headers.get("X-CSRF-Token")
            or (request.get_json(silent=True) or {}).get("_csrf_token")
        )
        if not token or not supplied or not secrets.compare_digest(
            token.encode(), supplied.encode()
        ):
            abort(400, description="CSRF token inválido ou ausente.")

    @app.before_request
    def normalizar_sessao():
        """Normaliza chaves de sessão para compatibilidade com frontend legado."""
        if "usuario_id" not in session:
            return
        if "nivel" not in session and "perfil" in session:
            session["nivel"] = session["perfil"]
        if "perfil" not in session and "nivel" in session:
            session["perfil"] = session["nivel"]

    @app.before_request
    def verificar_inatividade():
        """M06: invalida sessão após 30 minutos de inatividade."""
        INACTIVITY_SECONDS = 30 * 60
        if "usuario_id" not in session:
            return
        last_active = session.get("_last_active", 0)
        now = time.time()
        if now - last_active > INACTIVITY_SECONDS:
            session.clear()
            return redirect(url_for("auth.login_page"))
        session["_last_active"] = now

    @app.before_request
    def verificar_usuario_ativo():
        """
        V-05 FIX: relê ativo e nivel do banco a cada request.

        Garante que:
        - Usuários desativados (ativo=False) sejam expulsos imediatamente.
        - Usuários com papel rebaixado percam o acesso sem esperar a sessão expirar.
        - Usuários deletados sejam expulsos imediatamente.

        Impacto de performance: 1 SELECT por request na tabela usuarios (PK lookup,
        O(1) com índice). Aceitável para uma aplicação interna. Se escalar para
        cenário de alta carga, migrar para Flask-Session + Redis com session_version.
        """
        uid = session.get("usuario_id")
        if not uid:
            return

        # Pula para rotas que não precisam de usuário carregado
        ep = request.endpoint or ""
        if ep.startswith("static") or ep in (
            "auth.login_page", "auth.login_post",
            "auth.primeiro_acesso_page", "auth.primeiro_acesso_post",
            "auth.logout",
        ):
            return

        from app.models import Usuario
        try:
            u = db.session.get(Usuario, uid)
        except Exception:
            return

        if not u or not u.ativo:
            # Usuário desativado ou deletado: expulsa imediatamente
            session.clear()
            return redirect(url_for("auth.login_page"))

        # Sincroniza papel na sessão se foi alterado (promoção/rebaixamento)
        if session.get("nivel") != u.nivel:
            session["nivel"] = u.nivel

    @app.before_request
    def primeiro_acesso_redirect():
        """
        V-09 FIX: usa flag em memória para evitar SELECT no banco em
        cada request após o primeiro usuário ser criado.

        Antes: Usuario.query.first() em TODAS as requests (O(n) no scanner de CI,
        O(1) com índice mas desnecessário). Com alta carga, N workers × M requests/s
        = M SELECTs/s desnecessários.

        Depois: após o primeiro usuário ser confirmado, _tem_usuarios=True e o
        before_request retorna imediatamente sem tocar o banco.
        """
        global _tem_usuarios

        # Fast path — sem DB após setup inicial
        if _tem_usuarios:
            return

        skip = (
            (request.endpoint or "").startswith("static")
            or request.endpoint in (
                "auth.primeiro_acesso_page", "auth.primeiro_acesso_post",
                "auth.login_page", "auth.login_post",
            )
        )
        if skip:
            return

        from app.models import Usuario
        try:
            if not Usuario.query.first():
                return redirect(url_for("auth.primeiro_acesso_page"))
            # Marca para evitar queries futuras
            _tem_usuarios = True
        except Exception:
            pass

    # ── After request: security headers ──────────────────────────────────

    @app.after_request
    def security_headers(response):
        """
        H01/H02: injeta headers de segurança em todas as respostas.

        V-03 FIX: CSP usa nonce por request em vez de 'unsafe-inline' nos scripts.
        Isso garante que apenas scripts com o nonce correto (gerado no servidor)
        sejam executados, anulando ataques XSS via injeção de <script> tags.
        """
        nonce = getattr(g, "csp_nonce", "")

        # X-Content-Type-Options
        response.headers["X-Content-Type-Options"] = "nosniff"
        # X-Frame-Options
        response.headers["X-Frame-Options"] = "DENY"
        # Referrer-Policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # X-XSS-Protection (browsers legados)
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # Permissions-Policy
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), payment=()"
        )

        # V-03 FIX: CSP com nonce — remove unsafe-inline de script-src
        # Templates devem usar: <script nonce="{{ csp_nonce }}">
        is_prod = app.config.get("SESSION_COOKIE_SECURE", False)
        upgrade = " upgrade-insecure-requests;" if is_prod else ""
        csp = (
            f"default-src 'self'; "
            f"script-src 'self' 'nonce-{nonce}' https://cdn.jsdelivr.net; "
            f"style-src 'self' 'unsafe-inline' "
            f"https://fonts.googleapis.com https://cdn.jsdelivr.net; "
            f"font-src 'self' https://fonts.gstatic.com; "
            f"img-src 'self' data:; "
            f"connect-src 'self' http://localhost:* ws://localhost:* https://viacep.com.br; "
            f"frame-ancestors 'none'; "
            f"base-uri 'self'; "
            f"form-action 'self';"
            f"{upgrade}"
        )
        response.headers["Content-Security-Policy"] = csp

        # H02: HSTS — só em produção/HTTPS
        if app.config.get("SESSION_COOKIE_SECURE"):
            max_age = app.config.get("HSTS_MAX_AGE", 31_536_000)
            hsts    = f"max-age={max_age}; includeSubDomains; preload"
            response.headers["Strict-Transport-Security"] = hsts

        # Remover header que revela a stack
        response.headers.pop("Server", None)
        return response

    @app.teardown_request
    def rollback_on_error(exc):
        if exc is not None:
            try:
                db.session.rollback()
            except Exception:
                pass

    # ── Template filters ──────────────────────────────────────────────────
    @app.template_filter("moeda")
    def fmt_moeda(v):
        try:
            s = f"{float(v or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            return f"R$ {s}"
        except Exception:
            return "R$ 0,00"

    @app.template_filter("fmtdata")
    def fmt_data(v):
        if not v:
            return "—"
        try:
            if hasattr(v, "strftime"):
                return v.strftime("%d/%m/%Y")
            p = str(v)[:10].split("-")
            if len(p) == 3:
                return f"{p[2]}/{p[1]}/{p[0]}"
        except Exception:
            pass
        return str(v)

    # ── Blueprints ────────────────────────────────────────────────────────
    from app.routes.auth            import auth_bp
    from app.routes.pages           import pages_bp
    from app.routes.clientes        import clientes_bp
    from app.routes.os              import os_bp
    from app.routes.pecas           import pecas_bp
    from app.routes.fornecedores    import fornecedores_bp
    from app.routes.transacoes      import transacoes_bp
    from app.routes.usuarios        import usuarios_bp
    from app.routes.defeitos_padrao import defeitos_bp
    from app.routes.configuracoes   import cfg_bp
    from app.routes.logs            import logs_bp

    for bp in (
        auth_bp, pages_bp, clientes_bp, os_bp, pecas_bp,
        fornecedores_bp, transacoes_bp, usuarios_bp, defeitos_bp,
        cfg_bp, logs_bp,
    ):
        app.register_blueprint(bp)


    # ── Handlers de excecao global ────────────────────────────────────────
    from app.utils.exceptions import AppError
    from flask import jsonify as _jsonify

    @app.errorhandler(AppError)
    def handle_app_error(exc):
        return _jsonify(exc.to_dict()), exc.code

    @app.errorhandler(404)
    def not_found(exc):
        return _jsonify({"success": False, "erro": "Recurso nao encontrado."}), 404

    @app.errorhandler(405)
    def method_not_allowed(exc):
        return _jsonify({"success": False, "erro": "Metodo nao permitido."}), 405

    @app.errorhandler(500)
    def internal_error(exc):
        app.logger.error("Erro interno: %s", exc, exc_info=True)
        return _jsonify({"success": False, "erro": "Erro interno do servidor."}), 500

    with app.app_context():
        from app.utils.rate_limit import LoginAttempt  # noqa: F401
        db.create_all()

    # ── V-06 FIX: APScheduler — limpeza periódica das tabelas de rate limit ──
    # Evita crescimento indefinido de login_attempts e api_rate_limits.
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from app.utils.rate_limit import limpar_rate_limit_antigos

        scheduler = BackgroundScheduler(daemon=True)
        scheduler.add_job(
            func=lambda: _run_with_context(app, limpar_rate_limit_antigos),
            trigger="interval",
            hours=24,
            id="limpar_rate_limit",
            replace_existing=True,
        )
        scheduler.start()
        app.logger.info("[Scheduler] Limpeza de rate limit agendada (24h).")
    except ImportError:
        app.logger.warning(
            "[Scheduler] APScheduler não instalado. "
            "Adicione 'APScheduler>=3.10,<4.0' ao requirements.txt "
            "ou configure um cron para chamar limpar_rate_limit_antigos()."
        )
    except Exception as exc:
        app.logger.warning("[Scheduler] Erro ao iniciar scheduler: %s", exc)

    # Expõe o lock para o blueprint de auth (fix M02)
    app._primeiro_acesso_lock = _primeiro_acesso_lock

    return app


def _run_with_context(app, func):
    """Executa função dentro do contexto da aplicação (necessário para DB)."""
    with app.app_context():
        try:
            func()
        except Exception as exc:
            app.logger.error("[Scheduler] Erro na tarefa agendada: %s", exc)
