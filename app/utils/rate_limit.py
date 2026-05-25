"""
utils/rate_limit.py
-------------------
Rate limit persistido no banco — compatível com múltiplos workers Gunicorn.

Fix C04: o IP real já vem via ProxyFix (app/__init__.py).
         request.remote_addr é o IP confiável; não usar X-Forwarded-For diretamente.

Fix H03: além de login, expõe decorator rate_limit_route para uso em outros endpoints.

V-02 FIX: register_fail usa INSERT … ON DUPLICATE KEY UPDATE atômico no MySQL,
          eliminando o race condition TOCTOU que permitia bypass do bloqueio com
          requisições paralelas (múltiplos workers Gunicorn lendo falhas=4 ao
          mesmo tempo, ambos incrementando para 5 e commitando sem bloquear).
"""
from datetime import datetime, timezone, timedelta
from functools import wraps

from flask import request, jsonify, abort
from sqlalchemy import text

from app.extensions import db


class LoginAttempt(db.Model):
    """Controle de tentativas de login por IP."""
    __tablename__ = "login_attempts"

    ip            = db.Column(db.String(45), primary_key=True)
    falhas        = db.Column(db.Integer, default=0, nullable=False)
    bloqueado_ate = db.Column(db.DateTime, nullable=True)
    ultima_falha  = db.Column(db.DateTime, nullable=True)


class ApiRateLimit(db.Model):
    """Rate limit genérico por IP+endpoint para APIs críticas."""
    __tablename__ = "api_rate_limits"

    id            = db.Column(db.Integer, primary_key=True, autoincrement=True)
    ip            = db.Column(db.String(45), nullable=False, index=True)
    endpoint      = db.Column(db.String(100), nullable=False, index=True)
    hits          = db.Column(db.Integer, default=1, nullable=False)
    janela_inicio = db.Column(db.DateTime, nullable=False)

    __table_args__ = (db.UniqueConstraint("ip", "endpoint", name="uq_ip_endpoint"),)


def _now():
    return datetime.now(timezone.utc)


# ── Login rate limit ──────────────────────────────────────────────────────────

def check_lock(ip: str, max_fails: int = 5, window_minutes: int = 5,
               lock_seconds: int = 60):
    """Verifica bloqueio. Retorna (bloqueado, segundos_restantes)."""
    rec = db.session.get(LoginAttempt, ip)
    if not rec:
        return False, 0

    now = _now()

    if rec.bloqueado_ate:
        ba = rec.bloqueado_ate
        if ba.tzinfo is None:
            ba = ba.replace(tzinfo=timezone.utc)
        if ba > now:
            return True, int((ba - now).total_seconds())
        rec.bloqueado_ate = None
        rec.falhas = 0
        db.session.commit()

    if rec.ultima_falha:
        uf = rec.ultima_falha
        if uf.tzinfo is None:
            uf = uf.replace(tzinfo=timezone.utc)
        if now - uf > timedelta(minutes=window_minutes):
            rec.falhas = 0
            db.session.commit()

    return False, 0


def register_fail(ip: str, max_fails: int = 5, window_minutes: int = 5,
                  lock_seconds: int = 60) -> int:
    """
    V-02 FIX: registra falha de login com operação atômica no MySQL.

    Usa INSERT … ON DUPLICATE KEY UPDATE para que o incremento de falhas
    seja uma operação atômica no banco, eliminando o TOCTOU race condition
    onde múltiplos workers Gunicorn podiam ler/incrementar/commitar em paralelo
    sem que o bloqueio fosse acionado.

    Retorna segundos de bloqueio se atingiu o limite, 0 caso contrário.
    """
    now = _now()

    # Incremento atômico: se o registro já existe, incrementa falhas apenas
    # se a última falha for dentro da janela; caso contrário reinicia para 1.
    # A operação inteira é atômica no nível do storage engine do MySQL (InnoDB).
    db.session.execute(text("""
        INSERT INTO login_attempts (ip, falhas, ultima_falha)
        VALUES (:ip, 1, :now)
        ON DUPLICATE KEY UPDATE
            falhas       = IF(ultima_falha < DATE_SUB(:now, INTERVAL :win MINUTE),
                              1,
                              falhas + 1),
            ultima_falha = :now
    """), {"ip": ip, "now": now, "win": window_minutes})
    db.session.commit()

    # Leitura pós-atômica: verifica se atingiu o limite
    rec = db.session.get(LoginAttempt, ip)
    if rec and rec.falhas >= max_fails:
        rec.bloqueado_ate = now + timedelta(seconds=lock_seconds)
        rec.falhas = 0
        db.session.commit()
        return lock_seconds

    return 0


def clear_fails(ip: str):
    """Limpa falhas após login bem-sucedido."""
    rec = db.session.get(LoginAttempt, ip)
    if rec:
        rec.falhas = 0
        rec.bloqueado_ate = None
        db.session.commit()


# ── Rate limit genérico para APIs (H03) ───────────────────────────────────────

def rate_limit_route(max_hits: int = 30, window_seconds: int = 60,
                     abort_code: int = 429):
    """
    Decorator de rate limit para rotas de API.
    Ex: @rate_limit_route(max_hits=10, window_seconds=60)

    Usa o IP do request (já corrigido pelo ProxyFix).
    """
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            ip       = request.remote_addr or "unknown"
            endpoint = request.endpoint or "unknown"
            now      = _now()
            window   = timedelta(seconds=window_seconds)

            rec = ApiRateLimit.query.filter_by(ip=ip, endpoint=endpoint).first()
            if not rec:
                rec = ApiRateLimit(ip=ip, endpoint=endpoint,
                                   hits=1, janela_inicio=now)
                db.session.add(rec)
                db.session.commit()
                return f(*args, **kwargs)

            ji = rec.janela_inicio
            if ji.tzinfo is None:
                ji = ji.replace(tzinfo=timezone.utc)

            if now - ji > window:
                # Nova janela
                rec.hits = 1
                rec.janela_inicio = now
                db.session.commit()
                return f(*args, **kwargs)

            if rec.hits >= max_hits:
                remaining = int((ji + window - now).total_seconds())
                if abort_code == 429:
                    resp = jsonify({
                        "erro": "Muitas requisições. Tente novamente mais tarde.",
                        "retry_after": remaining,
                    })
                    resp.status_code = 429
                    resp.headers["Retry-After"] = str(remaining)
                    return resp
                abort(abort_code)

            rec.hits += 1
            db.session.commit()
            return f(*args, **kwargs)
        return wrapped
    return decorator


# ── Limpeza periódica (V-06) ──────────────────────────────────────────────────

def limpar_rate_limit_antigos():
    """
    V-06 FIX: remove registros antigos das tabelas de rate limit para
    evitar crescimento indefinido e degradação de performance.

    Chamado periodicamente via APScheduler em app/__init__.py.
    """
    cutoff_7d = _now() - timedelta(days=7)

    LoginAttempt.query.filter(
        LoginAttempt.ultima_falha < cutoff_7d,
        LoginAttempt.bloqueado_ate.is_(None),
    ).delete(synchronize_session=False)

    ApiRateLimit.query.filter(
        ApiRateLimit.janela_inicio < cutoff_7d,
    ).delete(synchronize_session=False)

    db.session.commit()
