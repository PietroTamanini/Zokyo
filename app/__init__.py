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
import secrets
import threading
import time
from datetime import timedelta

from flask import Flask, abort, g, jsonify, redirect, request, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

from app.extensions import db, migrate
from config import config as config_map

# Lock para serializar o endpoint de primeiro acesso (fix M02)
_primeiro_acesso_lock = threading.Lock()

# V-09 FIX: flag em memória — evita SELECT a cada request após setup inicial
_tem_usuarios: bool = False


def create_app(config_name="default"):
    app = Flask(__name__)
    cfg_obj = config_map[config_name]
    app.config.from_object(cfg_obj)

    # Chama init_app da config (ProductionConfig valida segredos)
    if hasattr(cfg_obj, "init_app"):
        cfg_obj.init_app(app)

    from app.utils.logging_config import configure_logging
    from app.utils.observability import init_sentry, observe_response, start_request_metrics

    configure_logging(app)
    init_sentry(app)

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
    migrate.init_app(app, db)
    from app.utils.tenancy import register_tenant_scope
    register_tenant_scope()
    from app.cli import register_cli
    register_cli(app)

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

        from app.models import Configuracao, Usuario
        usuario = None
        if "usuario_id" in _s:
            try:
                usuario = db.session.get(Usuario, _s["usuario_id"])
            except Exception:
                app.logger.debug("Não foi possível carregar usuário do contexto.", exc_info=True)
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
        supplied_request_id = request.headers.get("X-Request-ID", "")
        if supplied_request_id and len(supplied_request_id) <= 64 and supplied_request_id.replace("-", "").isalnum():
            g.request_id = supplied_request_id
        else:
            g.request_id = secrets.token_hex(16)
        start_request_metrics()

    @app.before_request
    def aplicar_rate_limit_global():
        """Rate limit global para todas as rotas dinâmicas."""
        if not app.config.get("RATE_LIMIT_ENABLED", True):
            return
        endpoint = request.endpoint or ""
        if endpoint.startswith("static"):
            return
        if endpoint in {"health.healthz", "health.readyz", "health.metrics", "pages.service_worker"}:
            return

        from app.utils.rate_limit import hit_rate_limit

        is_api = (request.path or "").startswith("/api/")
        is_write = request.method in {"POST", "PUT", "PATCH", "DELETE"}
        window = app.config.get("RATE_LIMIT_WINDOW_SECONDS", 60)
        ip = request.remote_addr or "unknown"

        if is_api:
            global_limit = app.config.get("RATE_LIMIT_GLOBAL_API", 600)
            endpoint_limit = app.config.get("RATE_LIMIT_ENDPOINT_API", 240)
            global_bucket = "global:api"
        elif is_write:
            global_limit = app.config.get("RATE_LIMIT_GLOBAL_WRITE", 300)
            endpoint_limit = app.config.get("RATE_LIMIT_ENDPOINT_WRITE", 120)
            global_bucket = "global:write"
        else:
            global_limit = app.config.get("RATE_LIMIT_GLOBAL_GET", 1000)
            endpoint_limit = app.config.get("RATE_LIMIT_ENDPOINT_GET", 300)
            global_bucket = "global:get"

        remaining = hit_rate_limit(ip, global_bucket, global_limit, window)
        if not remaining:
            method_bucket = "write" if is_write else "read"
            remaining = hit_rate_limit(ip, f"endpoint:{method_bucket}:{endpoint}", endpoint_limit, window)
        if remaining:
            if is_api or request.accept_mimetypes.best == "application/json":
                response = jsonify({
                    "success": False,
                    "erro": "Muitas requisições. Aguarde alguns instantes e tente novamente.",
                    "retry_after": remaining,
                })
                response.status_code = 429
                response.headers["Retry-After"] = str(remaining)
                return response
            abort(429)

    @app.before_request
    def protect_csrf():
        """CSRF protection para métodos mutantes."""
        if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return
        if request.endpoint in app.config.get("CSRF_EXEMPT_ENDPOINTS", set()):
            return
        if (request.path or "").startswith("/api/v1/") and request.headers.get("Authorization", "").lower().startswith("bearer "):
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

        if not u.organization or not u.organization.ativo:
            session.clear()
            return redirect(url_for("auth.login_page"))

        if session.get("security_version") is None and app.config.get("ALLOW_LEGACY_SESSIONS"):
            session["security_version"] = u.security_version
        elif session.get("security_version") != u.security_version:
            session.clear()
            return redirect(url_for("auth.login_page"))

        from app.services.user_sessions import validate_session_record
        if session.get("session_token"):
            if not validate_session_record(u):
                session.clear()
                return redirect(url_for("auth.login_page"))
        elif not app.config.get("ALLOW_LEGACY_SESSIONS"):
            session.clear()
            return redirect(url_for("auth.login_page"))

        g.organization_id = u.organization_id

        # Sincroniza papel na sessão se foi alterado (promoção/rebaixamento)
        if session.get("nivel") != u.nivel:
            session["nivel"] = u.nivel

        if (
            app.config.get("REQUIRE_ADMIN_2FA")
            and u.nivel == "admin"
            and not u.totp_enabled
            and ep not in {"auth.two_factor_setup", "auth.logout"}
        ):
            return redirect(url_for("auth.two_factor_setup"))

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
                "auth.recuperar_senha", "auth.redefinir_senha",
                "usuarios.aceitar_convite", "portal.publico", "laudos.verificar",
                "client_api.consulta_os_publica",
                "pages.service_worker", "health.healthz", "health.readyz", "health.metrics",
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
            app.logger.debug("Verificacao de primeiro acesso ignorada por indisponibilidade do banco.", exc_info=True)

    @app.before_request
    def aplicar_rbac_abac():
        """Aplica RBAC/ABAC central em toda rota nao publica."""
        from app.utils.permissions import enforce_request_authorization

        return enforce_request_authorization()

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
        endpoint = request.endpoint or ""
        allow_same_origin_frame = endpoint in {"pages.os_pdf", "os.pdf"}

        # X-Frame-Options
        response.headers["X-Frame-Options"] = "SAMEORIGIN" if allow_same_origin_frame else "DENY"
        # Referrer-Policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # X-XSS-Protection (browsers legados)
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # Permissions-Policy
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), payment=()"
        )
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
        if session.get("usuario_id") and endpoint != "static" and "Cache-Control" not in response.headers:
            response.headers["Cache-Control"] = "no-store, private, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"

        # V-03 FIX: CSP com nonce — remove unsafe-inline de script-src
        # Templates devem usar: <script nonce="{{ csp_nonce }}">
        is_prod = app.config.get("SESSION_COOKIE_SECURE", False)
        upgrade = " upgrade-insecure-requests;" if is_prod else ""
        connect_src = "connect-src 'self' https://viacep.com.br;"
        if not is_prod:
            connect_src = "connect-src 'self' http://localhost:* ws://localhost:* https://viacep.com.br;"
        frame_ancestors = "frame-ancestors 'self';" if allow_same_origin_frame else "frame-ancestors 'none';"
        csp = (
            f"default-src 'self'; "
            f"script-src 'self' 'nonce-{nonce}'; "
            f"style-src 'self' 'nonce-{nonce}'; "
            f"font-src 'self'; "
            f"img-src 'self' data: https:; "
            f"{connect_src} "
            f"{frame_ancestors} "
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
        response.headers["X-Request-ID"] = getattr(g, "request_id", "")
        return observe_response(response)

    @app.teardown_request
    def rollback_on_error(exc):
        if exc is not None:
            try:
                db.session.rollback()
            except Exception:
                app.logger.debug("Rollback apos erro falhou.", exc_info=True)

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
        except (TypeError, ValueError, IndexError):
            return str(v)
        return str(v)

    # ── Blueprints ────────────────────────────────────────────────────────
    from app.routes.auth import auth_bp
    from app.routes.client_api import client_api_bp
    from app.routes.clientes import clientes_bp
    from app.routes.configuracoes import cfg_bp
    from app.routes.defeitos_padrao import defeitos_bp
    from app.routes.fornecedores import fornecedores_bp
    from app.routes.health import health_bp
    from app.routes.importacao import importacao_bp
    from app.routes.laudos import laudos_bp
    from app.routes.logs import logs_bp
    from app.routes.os import os_bp
    from app.routes.pages import pages_bp
    from app.routes.pecas import pecas_bp
    from app.routes.platform import platform_bp
    from app.routes.portal import portal_bp
    from app.routes.privacy import privacy_bp
    from app.routes.relatorios import relatorios_bp
    from app.routes.transacoes import transacoes_bp
    from app.routes.usuarios import usuarios_bp

    for bp in (
        auth_bp, pages_bp, clientes_bp, os_bp, pecas_bp,
        fornecedores_bp, transacoes_bp, usuarios_bp, defeitos_bp,
        cfg_bp, logs_bp, importacao_bp, laudos_bp, health_bp, portal_bp, relatorios_bp, platform_bp, privacy_bp,
        client_api_bp,
    ):
        app.register_blueprint(bp)


    # ── Handlers de excecao global ────────────────────────────────────────
    from flask import jsonify as _jsonify
    from flask import render_template as _render_template

    from app.utils.exceptions import AppError

    def _wants_json():
        if (request.path or "").startswith("/api/"):
            return True
        best = request.accept_mimetypes.best_match(["application/json", "text/html"])
        return best == "application/json" and request.accept_mimetypes[best] > request.accept_mimetypes["text/html"]

    def _error_response(code, message):
        request_id = getattr(g, "request_id", "")
        if _wants_json():
            return _jsonify({"success": False, "erro": message, "code": code, "request_id": request_id}), code
        template = f"errors/{code}.html" if code in {403, 404, 405, 500} else "errors/error.html"
        return _render_template(template, code=code, message=message, request_id=request_id), code

    @app.errorhandler(AppError)
    def handle_app_error(exc):
        if _wants_json():
            payload = exc.to_dict()
            payload.update(code=exc.code, request_id=getattr(g, "request_id", ""))
            return _jsonify(payload), exc.code
        return _error_response(exc.code, exc.message)

    @app.errorhandler(400)
    def bad_request(exc):
        return _error_response(400, "Não foi possível processar os dados enviados.")

    @app.errorhandler(401)
    def unauthorized(exc):
        return _error_response(401, "Sua sessão expirou ou a autenticação é necessária.")

    @app.errorhandler(403)
    def forbidden(exc):
        return _error_response(403, "Acesso negado.")

    @app.errorhandler(404)
    def not_found(exc):
        return _error_response(404, "Recurso não encontrado.")

    @app.errorhandler(405)
    def method_not_allowed(exc):
        return _error_response(405, "Método não permitido.")

    @app.errorhandler(422)
    def unprocessable(exc):
        return _error_response(422, "Os dados são válidos, mas violam uma regra da operação.")

    @app.errorhandler(429)
    def too_many_requests(exc):
        return _error_response(429, "Muitas tentativas. Aguarde alguns instantes e tente novamente.")

    @app.errorhandler(503)
    def unavailable(exc):
        return _error_response(503, "Serviço temporariamente indisponível. Tente novamente em instantes.")

    @app.errorhandler(500)
    def internal_error(exc):
        app.logger.error("Erro interno: %s", exc, exc_info=True)
        return _error_response(500, "Erro interno do servidor.")

    # ── V-06 FIX: APScheduler — limpeza periódica das tabelas de rate limit ──
    # Evita crescimento indefinido de login_attempts e api_rate_limits.
    try:
        from apscheduler.schedulers.background import BackgroundScheduler

        from app.services.notifications import process_pending_notifications
        from app.services.retention import apply_active_policies
        from app.services.scheduled_reports import process_scheduled_reports
        from app.utils.rate_limit import limpar_rate_limit_antigos

        scheduler = BackgroundScheduler(daemon=True)
        scheduler.add_job(
            func=lambda: _run_with_context(app, "limpar_rate_limit", limpar_rate_limit_antigos),
            trigger="interval",
            hours=24,
            id="limpar_rate_limit",
            replace_existing=True,
        )
        scheduler.add_job(
            func=lambda: _run_with_context(app, "processar_notificacoes", process_pending_notifications),
            trigger="interval",
            minutes=1,
            id="processar_notificacoes",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            func=lambda: _run_with_context(app, "aplicar_retencao", apply_active_policies),
            trigger="interval",
            hours=24,
            id="aplicar_retencao",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            func=lambda: _run_with_context(app, "processar_relatorios", process_scheduled_reports),
            trigger="interval", hours=1, id="processar_relatorios_agendados",
            replace_existing=True, max_instances=1, coalesce=True,
        )
        if app.config.get("SCHEDULER_ENABLED", False):
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

    @app.cli.command("run-scheduler")
    def run_scheduler_command():
        """Mantem o scheduler ativo em um processo dedicado."""
        import time

        if not app.config.get("SCHEDULER_ENABLED", False):
            raise RuntimeError("Defina SCHEDULER_ENABLED=true somente no processo dedicado.")
        while True:
            time.sleep(3600)

    # Expõe o lock para o blueprint de auth (fix M02)
    app._primeiro_acesso_lock = _primeiro_acesso_lock

    return app


def _run_with_context(app, job_name, func):
    """Executa função dentro do contexto da aplicação (necessário para DB)."""
    with app.app_context():
        try:
            from app.services.operational_alerts import run_job
            run_job(job_name, func)
        except Exception as exc:
            app.logger.error("[Scheduler] Erro na tarefa agendada: %s", exc)
