"""Healthchecks para deploy e observabilidade basica."""
from flask import Blueprint, jsonify
from sqlalchemy import text

from app.extensions import db

health_bp = Blueprint("health", __name__)


@health_bp.route("/healthz")
def healthz():
    return jsonify({"status": "ok"}), 200


@health_bp.route("/readyz")
def readyz():
    try:
        db.session.execute(text("SELECT 1"))
        return jsonify({"status": "ready", "database": "ok"}), 200
    except Exception:
        return jsonify({"status": "not_ready", "database": "error"}), 503
