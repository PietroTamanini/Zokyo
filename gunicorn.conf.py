"""
gunicorn.conf.py — Configuração hardened do Gunicorn para produção.

Uso: gunicorn -c gunicorn.conf.py wsgi:app

Fix H03: workers suficientes para não afetar rate limiting de login.
V-13 FIX: post_fork() descarta conexões MySQL herdadas do processo master
          ao usar preload_app=True.

Problema (V-13):
  Com preload_app=True, a aplicação Flask é criada no processo master antes do
  fork dos workers. O engine SQLAlchemy cria conexões MySQL durante o preload.
  Após o fork(), múltiplos workers herdam as mesmas conexões — o que viola o
  protocolo MySQL (comunicação full-duplex em um único socket) e pode causar
  corrupção de respostas ("Packets out of order", respostas para a query errada).

  O pool_pre_ping=True detecta conexões mortas mas não resolve o fork sharing.
  A documentação do SQLAlchemy é explícita: "do not share connection objects
  across fork".

Solução:
  post_fork() chama db.engine.dispose() em cada worker filho imediatamente
  após o fork, descartando as conexões herdadas. O pool cria novas conexões
  limpa para cada worker conforme necessário.
"""
import multiprocessing
import os

# ── Workers ────────────────────────────────────────────────────────────────
# Fórmula recomendada: (2 * CPUs) + 1
workers = int(os.environ.get("GUNICORN_WORKERS", min((2 * multiprocessing.cpu_count()) + 1, 4)))
worker_class    = "sync"
worker_connections = 1000
threads         = 1

# ── Rede ──────────────────────────────────────────────────────────────────
# Escuta apenas no socket local; Nginx faz o proxy
bind            = os.environ.get("GUNICORN_BIND", "127.0.0.1:8000")
backlog         = 2048

# ── Timeouts ──────────────────────────────────────────────────────────────
timeout         = 30
keepalive       = 2
graceful_timeout = 30

# ── Limites de tamanho (anti DoS) ─────────────────────────────────────────
limit_request_line   = 4096
limit_request_fields = 100
limit_request_field_size = 8190

# ── Logs ──────────────────────────────────────────────────────────────────
accesslog   = os.environ.get("GUNICORN_ACCESSLOG", "/var/log/zokyo/gunicorn_access.log")
errorlog    = os.environ.get("GUNICORN_ERRORLOG",  "/var/log/zokyo/gunicorn_error.log")
loglevel    = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# ── Segurança ─────────────────────────────────────────────────────────────
forwarded_allow_ips = os.environ.get("GUNICORN_FORWARDED_IPS", "127.0.0.1")
proxy_protocol      = False
proxy_allow_from    = "127.0.0.1"

# ── PID ───────────────────────────────────────────────────────────────────
pidfile = "/var/run/zokyo/gunicorn.pid"

# ── Preload ───────────────────────────────────────────────────────────────
# preload_app=True melhora startup e uso de memória, mas exige post_fork()
# para evitar compartilhamento de conexões MySQL entre workers (V-13).
preload_app = True


# ── V-13 FIX: descarta conexões MySQL herdadas do fork ────────────────────
def post_fork(server, worker):
    """
    Chamado em cada worker filho imediatamente após o fork().

    db.engine.dispose() fecha todas as conexões herdadas do processo master
    e reinicializa o pool de conexões. Cada worker terá suas próprias
    conexões MySQL independentes — eliminando o risco de corrupção de
    protocolo por fork sharing.

    Referência: https://docs.sqlalchemy.org/en/20/core/connections.html
                #using-connection-pools-with-multiprocessing-or-os-fork
    """
    try:
        from app.extensions import db
        flask_app = worker.app.wsgi()
        with flask_app.app_context():
            db.engine.dispose()
        server.log.info("Worker %s: pool de conexões MySQL reinicializado (post_fork).", worker.pid)
    except Exception as exc:
        server.log.warning("Worker %s: erro no post_fork dispose: %s", worker.pid, exc)
