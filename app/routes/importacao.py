"""Rotas admin de importação de bancos externos."""
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, current_app, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.utils import secure_filename

from app.admin.organizations import get_organization_or_404
from app.extensions import db
from app.models import Usuario, registrar
from app.services.external_database_importer import (
    ExternalFirebirdImporter,
    ExternalImportError,
    FirebirdCredentials,
    GenericExternalImporter,
)
from app.utils.auth import platform_controlled_api_required, platform_controlled_page_required
from app.utils.import_files import cleanup_expired_imports, delete_import_file

importacao_bp = Blueprint("importacao", __name__)


def _credentials_from_request():
    data = request.get_json(silent=True) or request.form
    try:
        port = int(data.get("port") or 0) or None
    except (TypeError, ValueError):
        port = None
    return FirebirdCredentials(
        database_path=(data.get("database_path") or "").strip(),
        user=(data.get("user") or "SYSDBA").strip(),
        password=data.get("password") or "",
        charset=(data.get("charset") or "WIN1252").strip() or "WIN1252",
        source_type=(data.get("database_type") or "firebird").strip().lower(),
        host=(data.get("host") or "").strip(),
        port=port,
        database=(data.get("database") or "").strip(),
        profile=(data.get("profile") or "auto").strip().lower(),
        delimiter=(data.get("delimiter") or ",")[:1],
        sheet=(data.get("sheet") or "").strip(),
    )


def _importer(credentials):
    if credentials.source_type == "firebird":
        return ExternalFirebirdImporter(credentials)
    return GenericExternalImporter(credentials)


def _set_import_target(data=None, *, required=True):
    data = data if data is not None else (request.get_json(silent=True) or request.form)
    raw_id = data.get("organization_id") or request.args.get("organization_id") or session.get("external_import_organization_id")
    if not raw_id:
        if required:
            raise ExternalImportError("Selecione a empresa de destino nas configurações do super admin.")
        return None
    try:
        organization = get_organization_or_404(int(raw_id))
    except (TypeError, ValueError):
        raise ExternalImportError("Empresa de destino inválida.")
    g.organization_id = organization.id
    session["external_import_organization_id"] = organization.id
    return organization


def _safe_error(exc):
    return jsonify({"success": False, "erro": str(exc), "message": str(exc)}), 400


@importacao_bp.route("/api/importacao/bancos/upload", methods=["POST"])
@platform_controlled_api_required
def bancos_upload():
    try:
        _set_import_target()
    except ExternalImportError as exc:
        return _safe_error(exc)
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        return jsonify({"success": False, "erro": "Selecione um arquivo de exportação."}), 400
    suffix = Path(uploaded.filename).suffix.lower()
    if suffix not in {".fdb", ".sqlite", ".sqlite3", ".db", ".csv", ".xlsx", ".xlsm", ".zip"}:
        return jsonify({"success": False, "erro": "Formato não suportado. Use FDB, SQLite, CSV, XLSX ou ZIP."}), 400
    folder = Path(current_app.instance_path) / "import_uploads"
    folder.mkdir(parents=True, exist_ok=True)
    cleanup_expired_imports(folder)
    safe_name = secure_filename(uploaded.filename) or f"import{suffix}"
    path = folder / f"{uuid4().hex}_{safe_name}"
    uploaded.save(path)
    return jsonify({"success": True, "database_path": str(path), "filename": safe_name})


def _public_log_payload(payload):
    if not isinstance(payload, dict):
        return payload
    sanitized = dict(payload)
    sanitized.pop("database_path", None)
    sanitized.setdefault("source_type", "firebird")
    return sanitized


@importacao_bp.route("/importacao/bancos", methods=["GET"])
@platform_controlled_page_required
def bancos_page():
    organization_id = request.args.get("organization_id", type=int)
    if organization_id:
        return redirect(url_for("platform.company_settings_importacao", organization_id=organization_id))
    return redirect(url_for("platform.companies"))


@importacao_bp.route("/importacao/<path:legacy_slug>", methods=["GET"])
@platform_controlled_page_required
def bancos_legacy_page(legacy_slug):
    return redirect(url_for("importacao.bancos_page"), code=302)


@importacao_bp.route("/api/importacao/bancos/test", methods=["POST"])
@platform_controlled_api_required
def bancos_test():
    try:
        _set_import_target()
        result = _importer(_credentials_from_request()).test_connection()
        return jsonify(result)
    except ExternalImportError as exc:
        return _safe_error(exc)


@importacao_bp.route("/api/importacao/bancos/schema", methods=["POST"])
@platform_controlled_api_required
def bancos_schema():
    try:
        _set_import_target()
        result = _importer(_credentials_from_request()).inspect_schema()
        return jsonify({"success": True, "schema": result})
    except ExternalImportError as exc:
        return _safe_error(exc)


@importacao_bp.route("/api/importacao/bancos/mapping", methods=["GET", "POST"])
@platform_controlled_api_required
def bancos_mapping():
    try:
        _set_import_target()
        importer = _importer(_credentials_from_request())
        return jsonify({
            "success": True,
            "mapped_fields": importer.mapping_report(),
            "ignored_fields": importer.ignored_fields_report(),
            "manual_confirmation": importer.manual_confirmation_report(),
        })
    except ExternalImportError as exc:
        return _safe_error(exc)


@importacao_bp.route("/api/importacao/bancos/preview", methods=["POST"])
@platform_controlled_api_required
def bancos_preview():
    creds = _credentials_from_request()
    try:
        organization = _set_import_target()
        result = _importer(creds).preview()
        session["external_import_preview"] = {
            "database_path": creds.database_path,
            "user": creds.user,
            "charset": creds.charset,
            "source_type": creds.source_type,
            "host": creds.host,
            "port": creds.port,
            "database": creds.database,
            "profile": creds.profile,
            "delimiter": creds.delimiter,
            "sheet": creds.sheet,
            "organization_id": organization.id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return jsonify(result)
    except ExternalImportError as exc:
        return _safe_error(exc)


@importacao_bp.route("/api/importacao/bancos/logs", methods=["GET"])
@platform_controlled_api_required
def bancos_logs():
    try:
        folder = Path(current_app.instance_path) / "import_logs"
        if not folder.exists():
            return jsonify({"success": True, "logs": []})
        logs = []
        organization = _set_import_target(required=False)
        organization_id = organization.id if organization else getattr(g, "organization_id", None)
        patterns = ("external_import_*.json",)
        for pattern in patterns:
            for path in sorted(folder.glob(pattern), reverse=True):
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    payload = {"erro": "Log inválido"}
                payload_org = payload.get("organization_id") if isinstance(payload, dict) else None
                if organization_id and payload_org != organization_id:
                    continue
                logs.append({"file": path.name, "payload": _public_log_payload(payload)})
                if len(logs) >= 50:
                    break
        return jsonify({"success": True, "logs": logs[:50]})
    except ExternalImportError as exc:
        return _safe_error(exc)


@importacao_bp.route("/api/importacao/bancos/commit", methods=["POST"])
@platform_controlled_api_required
def bancos_commit():
    creds = _credentials_from_request()
    data = request.get_json(silent=True) or {}
    try:
        organization = _set_import_target(data)
    except ExternalImportError as exc:
        return _safe_error(exc)
    preview = session.get("external_import_preview") or {}
    same_preview = (
        preview.get("database_path") == creds.database_path
        and preview.get("user") == creds.user
        and preview.get("charset") == creds.charset
        and preview.get("source_type") == creds.source_type
        and preview.get("host") == creds.host
        and preview.get("port") == creds.port
        and preview.get("database") == creds.database
        and preview.get("profile") == creds.profile
        and preview.get("delimiter") == creds.delimiter
        and preview.get("sheet") == creds.sheet
        and preview.get("organization_id") == organization.id
    )
    if not data.get("confirm") or not same_preview:
        return jsonify({
            "success": False,
            "erro": "Execute a prévia desta mesma conexão antes de confirmar a importação.",
        }), 400

    try:
        admin = db.session.get(Usuario, session.get("usuario_id"))
        admin_name = admin.email if admin else str(session.get("usuario_id"))
        result = _importer(creds).commit(
            admin_user=admin_name,
            admin_user_id=session.get("usuario_id"),
        )
        registrar("importacao", "bancos_externos", "Importação de banco externo executada", str(result.get("created")))
        session.pop("external_import_preview", None)
        try:
            delete_import_file(Path(current_app.instance_path) / "import_uploads", creds.database_path)
        except OSError:
            current_app.logger.warning("Não foi possível remover um upload temporário após importação.")
        return jsonify(result)
    except ExternalImportError as exc:
        return _safe_error(exc)
