"""Rotas admin de importacao CPlus/Firebird."""
from datetime import datetime, timezone

from flask import Blueprint, jsonify, render_template, request, session

from app.models import Usuario, registrar
from app.services.cplus_firebird_importer import (
    CPlusFirebirdImporter,
    CPlusImportError,
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


@importacao_bp.route("/importacao/cplus", methods=["GET"])
@page_nivel_required("admin")
def cplus_page():
    return render_template("pages/importacao_cplus.html", active="importacao_cplus")


@importacao_bp.route("/api/importacao/cplus/test", methods=["POST"])
@nivel_required("admin")
def cplus_test():
    try:
        result = CPlusFirebirdImporter(_credentials_from_request()).test_connection()
        return jsonify(result)
    except CPlusImportError as exc:
        return _safe_error(exc)


@importacao_bp.route("/api/importacao/cplus/preview", methods=["POST"])
@nivel_required("admin")
def cplus_preview():
    creds = _credentials_from_request()
    try:
        result = CPlusFirebirdImporter(creds).preview()
        session["cplus_preview"] = {
            "database_path": creds.database_path,
            "user": creds.user,
            "charset": creds.charset,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return jsonify(result)
    except CPlusImportError as exc:
        return _safe_error(exc)


@importacao_bp.route("/api/importacao/cplus/commit", methods=["POST"])
@nivel_required("admin")
def cplus_commit():
    creds = _credentials_from_request()
    data = request.get_json(silent=True) or {}
    preview = session.get("cplus_preview") or {}
    same_preview = (
        preview.get("database_path") == creds.database_path
        and preview.get("user") == creds.user
        and preview.get("charset") == creds.charset
    )
    if not data.get("confirm") or not same_preview:
        return jsonify({
            "success": False,
            "erro": "Execute o preview desta mesma conexao antes de confirmar a importacao."
        }), 400

    try:
        admin = Usuario.query.get(session.get("usuario_id"))
        admin_name = admin.email if admin else str(session.get("usuario_id"))
        result = CPlusFirebirdImporter(creds).commit(
            admin_user=admin_name,
            admin_user_id=session.get("usuario_id"),
        )
        registrar("importacao", "cplus", "Importacao CPlus executada", str(result.get("created")))
        session.pop("cplus_preview", None)
        return jsonify(result)
    except CPlusImportError as exc:
        return _safe_error(exc)
