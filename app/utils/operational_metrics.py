"""Metricas operacionais coletadas sob demanda sem agente privilegiado."""
import os
import shutil
import time
from pathlib import Path

from flask import current_app
from prometheus_client import Gauge

from app.extensions import db
from app.models import Notification, OperationalAlert, OperationalHeartbeat

DISK_FREE = Gauge("zokyo_disk_free_bytes", "Espaco livre no filesystem da instancia.")
DISK_TOTAL = Gauge("zokyo_disk_total_bytes", "Espaco total no filesystem da instancia.")
LOAD_AVERAGE = Gauge("zokyo_system_load_average", "Load average do host.", ("period",))
NETWORK_BYTES = Gauge("zokyo_network_bytes_total", "Bytes de rede observados no host.", ("direction",))
DB_POOL = Gauge("zokyo_db_pool_connections", "Conexoes do pool SQLAlchemy.", ("state",))
NOTIFICATION_QUEUE = Gauge("zokyo_notification_queue", "Notificacoes por situacao.", ("status",))
HEARTBEAT_AGE = Gauge("zokyo_job_heartbeat_age_seconds", "Idade do ultimo sucesso da tarefa.", ("job",))
ALERT_COUNT = Gauge("zokyo_alerts_open", "Alertas abertos por severidade.", ("severity",))


def _network_totals():
    path = Path("/proc/net/dev")
    if not path.exists():
        return 0, 0
    received = sent = 0
    for line in path.read_text(encoding="utf-8").splitlines()[2:]:
        if ":" not in line:
            continue
        fields = line.split(":", 1)[1].split()
        if len(fields) >= 9:
            received += int(fields[0])
            sent += int(fields[8])
    return received, sent


def collect_operational_metrics():
    usage = shutil.disk_usage(current_app.instance_path)
    DISK_FREE.set(usage.free)
    DISK_TOTAL.set(usage.total)
    try:
        one, five, fifteen = os.getloadavg()
        for label, value in (("1m", one), ("5m", five), ("15m", fifteen)):
            LOAD_AVERAGE.labels(label).set(value)
    except (AttributeError, OSError):
        pass
    received, sent = _network_totals()
    NETWORK_BYTES.labels("received").set(received)
    NETWORK_BYTES.labels("sent").set(sent)
    pool = db.engine.pool
    for state, attribute in (("checked_out", "checkedout"), ("checked_in", "checkedin"), ("overflow", "overflow")):
        method = getattr(pool, attribute, None)
        if callable(method):
            DB_POOL.labels(state).set(method())
    for status in ("pending", "retry", "sent", "manual_required", "failed"):
        NOTIFICATION_QUEUE.labels(status).set(
            Notification.query.execution_options(include_all_tenants=True).filter_by(status=status).count()
        )
    now = time.time()
    for heartbeat in OperationalHeartbeat.query.all():
        if heartbeat.last_success_at:
            HEARTBEAT_AGE.labels(heartbeat.job_name).set(
                max(0, now - heartbeat.last_success_at.replace(tzinfo=None).timestamp())
            )
    for severity in ("info", "warning", "critical"):
        ALERT_COUNT.labels(severity).set(OperationalAlert.query.filter_by(severity=severity, resolved_at=None).count())
