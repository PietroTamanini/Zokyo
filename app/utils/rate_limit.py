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
from datetime import datetime, timedelta, timezone
from functools import wraps
from hashlib import sha256
from time import sleep

from flask import abort, current_app, jsonify, request
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

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


def _dialect_name():
    """Retorna o dialeto efetivo da aplicacao, sem depender de mocks do ORM."""
    return db.engine.dialect.name


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

    if db.session.get_bind().dialect.name == "sqlite":
        rec = db.session.get(LoginAttempt, ip)
        if not rec:
            rec = LoginAttempt(ip=ip, falhas=1, ultima_falha=now)
            db.session.add(rec)
        else:
            ultima = rec.ultima_falha
            if ultima and ultima.tzinfo is None:
                ultima = ultima.replace(tzinfo=timezone.utc)
            rec.falhas = 1 if not ultima or now - ultima > timedelta(minutes=window_minutes) else rec.falhas + 1
            rec.ultima_falha = now
        db.session.commit()
        if rec.falhas >= max_fails:
            rec.bloqueado_ate = now + timedelta(seconds=lock_seconds)
            rec.falhas = 0
            db.session.commit()
            return lock_seconds
        return 0

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

def _endpoint_key(raw: str) -> str:
    if len(raw) <= 100:
        return raw
    digest = sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{raw[:80]}:{digest}"


def hit_rate_limit(ip: str, endpoint: str, max_hits: int, window_seconds: int) -> int:
    """Registra um hit. Retorna 0 se permitido ou segundos de espera se bloqueado."""
    endpoint = _endpoint_key(endpoint or "unknown")
    ip = ip or "unknown"
    now = _now()
    window = timedelta(seconds=window_seconds)

    redis_url = current_app.config.get("REDIS_URL")
    if redis_url:
        try:
            import redis
            client = redis.Redis.from_url(redis_url, socket_connect_timeout=1, socket_timeout=1)
            bucket = int(now.timestamp()) // window_seconds
            key = f"zokyo:rate:{endpoint}:{sha256(ip.encode()).hexdigest()[:24]}:{bucket}"
            hits = client.incr(key)
            if hits == 1:
                client.expire(key, window_seconds + 2)
            if hits > max_hits:
                ttl = client.ttl(key)
                return max(1, ttl if ttl > 0 else window_seconds)
            return 0
        except (redis.RedisError, OSError):
            # O banco continua sendo o backend seguro quando o Redis falha.
            current_app.logger.warning("Redis indisponível para rate limit; usando MariaDB.")

    # O limitador global e executado por todos os workers antes de cada
    # requisicao. No MySQL/MariaDB, ler o registro e depois altera-lo pelo ORM
    # permite que workers concorrentes atualizem a mesma linha e pode causar o
    # erro 1020 ("Record has changed since last read"). O upsert abaixo faz o
    # reset da janela ou o incremento em uma unica operacao atomica.
    if _dialect_name() in {"mysql", "mariadb"}:
        statement = text("""
                INSERT INTO api_rate_limits (ip, endpoint, hits, janela_inicio)
                VALUES (:ip, :endpoint, 1, :now)
                ON DUPLICATE KEY UPDATE
                    hits = IF(
                        janela_inicio < DATE_SUB(:now, INTERVAL :window_seconds SECOND),
                        1,
                        hits + 1
                    ),
                    janela_inicio = IF(
                        janela_inicio < DATE_SUB(:now, INTERVAL :window_seconds SECOND),
                        :now,
                        janela_inicio
                    )
            """)
        params = {
            "ip": ip,
            "endpoint": endpoint,
            "now": now,
            "window_seconds": window_seconds,
        }
        for attempt in range(8):
            try:
                db.session.execute(statement, params)
                db.session.commit()
                break
            except OperationalError as exc:
                db.session.rollback()
                error_code = exc.orig.args[0] if getattr(exc, "orig", None) and exc.orig.args else None
                if error_code not in {1020, 1205, 1213} or attempt == 7:
                    raise
                # MariaDB pode devolver 1020 mesmo em um upsert atomico quando
                # ha forte disputa pela mesma chave. Uma espera curta e
                # limitada preserva a requisicao sem esconder outros erros.
                sleep(0.002 * (attempt + 1))
        db.session.expire_all()
        rec = ApiRateLimit.query.filter_by(ip=ip, endpoint=endpoint).one()
        if rec.hits <= max_hits:
            return 0
        ji = rec.janela_inicio
        if ji.tzinfo is None:
            ji = ji.replace(tzinfo=timezone.utc)
        return max(1, int((ji + window - now).total_seconds()))

    rec = ApiRateLimit.query.filter_by(ip=ip, endpoint=endpoint).first()
    if not rec:
        rec = ApiRateLimit(ip=ip, endpoint=endpoint, hits=1, janela_inicio=now)
        db.session.add(rec)
        db.session.commit()
        return 0

    ji = rec.janela_inicio
    if ji.tzinfo is None:
        ji = ji.replace(tzinfo=timezone.utc)

    if now - ji > window:
        rec.hits = 1
        rec.janela_inicio = now
        db.session.commit()
        return 0

    if rec.hits >= max_hits:
        return max(1, int((ji + window - now).total_seconds()))

    rec.hits += 1
    db.session.commit()
    return 0


def rate_limit_route(max_hits: int = 30, window_seconds: int = 60,
                     abort_code: int = 429, methods: set[str] | None = None):
    """
    Decorator de rate limit para rotas de API.
    Ex: @rate_limit_route(max_hits=10, window_seconds=60)

    Usa o IP do request (já corrigido pelo ProxyFix).
    """
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if methods is not None and request.method not in methods:
                return f(*args, **kwargs)
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

    Chamado periodicamente pelo processo de scheduler dedicado.
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
