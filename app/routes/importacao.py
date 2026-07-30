"""Rotas admin de importação de bancos externos."""
import json
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, session, url_for

from app.extensions import db
from app.models import Usuario, registrar
from app.services.external_database_importer import (
    ExternalFirebirdImporter,
    ExternalImportError,
    FirebirdCredentials,
)
from app.utils.auth import nivel_required, page_nivel_required

importacao_bp = Blueprint("importacao", __name__)


def _credentials_from_request():
    data = request.get_json(silent=True) or request.form
    return FirebirdCredentials(
        database_path=(data.get("database_path") or "").strip(),
        user=(data.get("user") or "SYSDBA").strip(),
        password=data.get("password") or "",
        charset=(data.get("charset") or "WIN1252").strip() or "WIN1252",
    )


def _safe_error(exc):
    return jsonify({"success": False, "erro": str(exc), "message": str(exc)}), 400


def _public_log_payload(payload):
    if not isinstance(payload, dict):
        return payload
    sanitized = dict(payload)
    sanitized.pop("database_path", None)
    sanitized.setdefault("source_type", "firebird")
    return sanitized


@importacao_bp.route("/importacao/bancos", methods=["GET"])
@page_nivel_required("admin")
def bancos_page():
    return render_template("pages/importacao_bancos.html", active="importacao_bancos")


@importacao_bp.route("/importacao/<path:legacy_slug>", methods=["GET"])
@page_nivel_required("admin")
def bancos_legacy_page(legacy_slug):
    return redirect(url_for("importacao.bancos_page"), code=302)


@importacao_bp.route("/api/importacao/bancos/test", methods=["POST"])
@nivel_required("admin")
def bancos_test():
    try:
        result = ExternalFirebirdImporter(_credentials_from_request()).test_connection()
        return jsonify(result)
    except ExternalImportError as exc:
        return _safe_error(exc)


@importacao_bp.route("/api/importacao/bancos/schema", methods=["POST"])
@nivel_required("admin")
def bancos_schema():
    try:
        result = ExternalFirebirdImporter(_credentials_from_request()).inspect_schema()
        return jsonify({"success": True, "schema": result})
    except ExternalImportError as exc:
        return _safe_error(exc)


@importacao_bp.route("/api/importacao/bancos/mapping", methods=["GET", "POST"])
@nivel_required("admin")
def bancos_mapping():
    importer = ExternalFirebirdImporter(_credentials_from_request())
    return jsonify({
        "success": True,
        "mapped_fields": importer.mapping_report(),
        "ignored_fields": importer.ignored_fields_report(),
        "manual_confirmation": importer.manual_confirmation_report(),
    })


@importacao_bp.route("/api/importacao/bancos/preview", methods=["POST"])
@nivel_required("admin")
def bancos_preview():
    creds = _credentials_from_request()
    try:
        result = ExternalFirebirdImporter(creds).preview()
        session["external_import_preview"] = {
            "database_path": creds.database_path,
            "user": creds.user,
            "charset": creds.charset,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return jsonify(result)
    except ExternalImportError as exc:
        return _safe_error(exc)


@importacao_bp.route("/api/importacao/bancos/logs", methods=["GET"])
@nivel_required("admin")
def bancos_logs():
    folder = Path(current_app.instance_path) / "import_logs"
    if not folder.exists():
        return jsonify({"success": True, "logs": []})
    logs = []
    patterns = ("external_import_*.json",)
    for pattern in patterns:
        for path in sorted(folder.glob(pattern), reverse=True)[:50]:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = {"erro": "Log inválido"}
            logs.append({"file": path.name, "payload": _public_log_payload(payload)})
    return jsonify({"success": True, "logs": logs[:50]})


@importacao_bp.route("/api/importacao/bancos/commit", methods=["POST"])
@nivel_required("admin")
def bancos_commit():
    creds = _credentials_from_request()
    data = request.get_json(silent=True) or {}
    preview = session.get("external_import_preview") or {}
    same_preview = (
        preview.get("database_path") == creds.database_path
        and preview.get("user") == creds.user
        and preview.get("charset") == creds.charset
    )
    if not data.get("confirm") or not same_preview:
        return jsonify({
            "success": False,
            "erro": "Execute a prévia desta mesma conexão antes de confirmar a importação.",
        }), 400

    try:
        admin = db.session.get(Usuario, session.get("usuario_id"))
        admin_name = admin.email if admin else str(session.get("usuario_id"))
        result = ExternalFirebirdImporter(creds).commit(
            admin_user=admin_name,
            admin_user_id=session.get("usuario_id"),
        )
        registrar("importacao", "bancos_externos", "Importação de banco externo executada", str(result.get("created")))
        session.pop("external_import_preview", None)
        return jsonify(result)
    except ExternalImportError as exc:
        return _safe_error(exc)
