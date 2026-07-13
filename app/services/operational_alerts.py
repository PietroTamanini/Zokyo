"""Heartbeats, alertas deduplicados e entrega aos operadores."""
import hashlib
import ipaddress
import json
import os
import socket
import time
import urllib.parse
from datetime import datetime, timezone

import requests
from flask import current_app
from prometheus_client import Gauge

from app.extensions import db
from app.models import OperationalAlert, OperationalHeartbeat
from app.utils.email_delivery import send_email

JOB_LAST_SUCCESS = Gauge("zokyo_job_last_success_timestamp", "Ultimo sucesso da tarefa.", ("job",))
JOB_FAILURES = Gauge("zokyo_job_consecutive_failures", "Falhas consecutivas da tarefa.", ("job",))
OPEN_ALERTS = Gauge("zokyo_operational_open_alerts", "Alertas operacionais abertos.", ("severity",))


def _now():
    return datetime.now(timezone.utc)


def _safe_webhook(url):
    parsed = urllib.parse.urlparse(url)
    hostname = (parsed.hostname or "").lower()
    allowed = {item.strip().lower() for item in os.environ.get("ALERT_WEBHOOK_ALLOWED_HOSTS", "").split(",") if item.strip()}
    if parsed.scheme != "https" or hostname not in allowed or parsed.username or parsed.password or parsed.fragment:
        return False
    try:
        for result in socket.getaddrinfo(hostname, 443):
            address = ipaddress.ip_address(result[4][0])
            if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
                return False
    except (socket.gaierror, ValueError):
        return False
    return True


def emit_alert(severity, source, message):
    clean_message = str(message).replace("\n", " ")[:500]
    fingerprint = hashlib.sha256(f"{severity}:{source}:{clean_message}".encode()).hexdigest()
    alert = OperationalAlert.query.filter_by(fingerprint=fingerprint, resolved_at=None).first()
    if alert:
        alert.occurrences += 1
        alert.last_seen_at = _now()
    else:
        alert = OperationalAlert(
            severity=severity, source=source, message=clean_message, fingerprint=fingerprint,
        )
        db.session.add(alert)
    db.session.commit()
    OPEN_ALERTS.labels(severity).set(OperationalAlert.query.filter_by(severity=severity, resolved_at=None).count())

    recipient = current_app.config.get("ALERT_EMAIL")
    if recipient:
        send_email(recipient, f"[{severity.upper()}] Zokyo - {source}", clean_message)
    webhook = current_app.config.get("ALERT_WEBHOOK_URL")
    if webhook and _safe_webhook(webhook):
        try:
            requests.post(
                webhook, data=json.dumps({"severity": severity, "source": source, "message": clean_message}),
                headers={"Content-Type": "application/json"}, timeout=5, allow_redirects=False,
            )
        except requests.RequestException as exc:
            current_app.logger.warning("Falha ao entregar alerta por webhook: %s", exc)
    return alert


def run_job(job_name, function):
    heartbeat = OperationalHeartbeat.query.filter_by(job_name=job_name).first()
    if not heartbeat:
        heartbeat = OperationalHeartbeat(job_name=job_name)
        db.session.add(heartbeat)
    started = _now()
    heartbeat.last_started_at = started
    db.session.commit()
    timer = time.perf_counter()
    try:
        result = function()
    except Exception as exc:
        db.session.rollback()
        heartbeat = OperationalHeartbeat.query.filter_by(job_name=job_name).one()
        heartbeat.last_failure_at = _now()
        heartbeat.last_duration_ms = int((time.perf_counter() - timer) * 1000)
        heartbeat.consecutive_failures += 1
        heartbeat.last_error = str(exc)[:500]
        heartbeat.updated_at = _now()
        db.session.commit()
        JOB_FAILURES.labels(job_name).set(heartbeat.consecutive_failures)
        emit_alert("critical" if heartbeat.consecutive_failures >= 3 else "warning", job_name, str(exc))
        raise
    heartbeat.last_success_at = _now()
    heartbeat.last_duration_ms = int((time.perf_counter() - timer) * 1000)
    heartbeat.consecutive_failures = 0
    heartbeat.last_error = None
    heartbeat.updated_at = _now()
    db.session.commit()
    JOB_LAST_SUCCESS.labels(job_name).set(heartbeat.last_success_at.timestamp())
    JOB_FAILURES.labels(job_name).set(0)
    return result
