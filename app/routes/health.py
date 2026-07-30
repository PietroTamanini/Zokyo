"""Healthchecks e metricas para deploy e observabilidade."""
import secrets

from flask import Blueprint, Response, current_app, jsonify, request, session
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from app.extensions import db
from app.models import Notification, OperationalAlert, OperationalHeartbeat
from app.utils.auth import nivel_required

health_bp = Blueprint("health", __name__)


@health_bp.route("/healthz")
def healthz():
    return jsonify({"status": "ok"}), 200


@health_bp.route("/api/v1")
@nivel_required("admin", "operacional", "consulta")
def api_v1_index():
    return jsonify({
        "status": True,
        "name": "Zokyo API",
        "version": "v1",
        "resources": [
            "clientes", "produtos", "servicos", "usuarios", "os",
            "emitente", "audit", "calendario",
        ],
    })


@health_bp.route("/readyz")
def readyz():
    try:
        db.session.execute(text("SELECT 1"))
        return jsonify({"status": "ready", "database": "ok"}), 200
    except Exception as exc:
        db.session.rollback()
        current_app.logger.warning("Readiness falhou: %s", exc)
        return jsonify({"status": "not_ready", "database": "error"}), 503


@health_bp.route("/metrics")
def metrics():
    configured = current_app.config.get("METRICS_TOKEN")
    supplied = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    token_ok = bool(configured and supplied and secrets.compare_digest(configured, supplied))
    if not token_ok and session.get("nivel") != "admin":
        return jsonify({"erro": "Acesso negado"}), 403
    from app.utils.operational_metrics import collect_operational_metrics
    collect_operational_metrics()
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


@health_bp.route("/api/operations/status")
@nivel_required("admin")
def operations_status():
    heartbeats = OperationalHeartbeat.query.order_by(OperationalHeartbeat.job_name).all()
    alerts = OperationalAlert.query.filter_by(resolved_at=None).order_by(OperationalAlert.last_seen_at.desc()).limit(100).all()
    failed_notifications = Notification.query.filter(Notification.status == "failed").count()
    return jsonify({
        "heartbeats": [{
            "job": item.job_name,
            "last_success_at": item.last_success_at.isoformat() if item.last_success_at else None,
            "last_failure_at": item.last_failure_at.isoformat() if item.last_failure_at else None,
            "duration_ms": item.last_duration_ms,
            "consecutive_failures": item.consecutive_failures,
            "last_error": item.last_error,
        } for item in heartbeats],
        "alerts": [{
            "id": item.id, "severity": item.severity, "source": item.source,
            "message": item.message, "occurrences": item.occurrences,
            "last_seen_at": item.last_seen_at.isoformat(),
        } for item in alerts],
        "failed_notifications": failed_notifications,
    })
