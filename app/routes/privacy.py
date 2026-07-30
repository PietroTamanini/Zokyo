"""Operacoes administrativas de privacidade por tenant."""
from flask import Blueprint, flash, redirect, render_template, request, send_file, session, url_for

from app.extensions import db
from app.models import Cliente, ConsentRecord, DataSubjectRequest, RetentionPolicy, Usuario, registrar
from app.services.privacy import anonymize_client, export_subject_data, register_consent
from app.services.retention import CATEGORIES, count_candidates
from app.utils.auth import page_nivel_required

privacy_bp = Blueprint("privacy", __name__, url_prefix="/privacidade")


@privacy_bp.route("/retencao", methods=["GET", "POST"])
@page_nivel_required("admin")
def retention():
    user = db.session.get(Usuario, session["usuario_id"])
    if request.method == "POST":
        approved = request.form.get("legal_approval") == "yes"
        if not approved and any(request.form.get(f"active_{key}") for key in CATEGORIES):
            flash("Confirme a aprovação da política antes de ativar a eliminação automática.", "error")
            return redirect(url_for("privacy.retention"))
        from datetime import datetime, timezone
        for category in CATEGORIES:
            try:
                days = int(request.form.get(f"days_{category}", "90"))
            except ValueError:
                days = 0
            if not 7 <= days <= 3650:
                flash("O prazo deve ficar entre 7 e 3650 dias.", "error")
                return redirect(url_for("privacy.retention"))
            policy = RetentionPolicy.query.filter_by(category=category).first()
            if not policy:
                policy = RetentionPolicy(organization_id=user.organization_id, category=category, retention_days=days)
                db.session.add(policy)
            policy.retention_days = days
            policy.active = bool(request.form.get(f"active_{category}"))
            policy.approved_by_id = user.id if policy.active else None
            policy.approved_at = datetime.now(timezone.utc) if policy.active else None
        registrar("retencao", "privacy", "Politicas de retencao atualizadas pelo administrador.")
        db.session.commit()
        flash("Politicas de retencao atualizadas.", "success")
        return redirect(url_for("privacy.retention"))
    policies = {item.category: item for item in RetentionPolicy.query.all()}
    rows = []
    for category, label in CATEGORIES.items():
        policy = policies.get(category)
        rows.append((category, label, policy, count_candidates(policy) if policy else 0))
    return render_template("pages/retention.html", active="retencao", rows=rows)


def _context(client_id):
    user = db.session.get(Usuario, session.get("usuario_id"))
    client = Cliente.query.filter_by(id=client_id, organization_id=user.organization_id).first_or_404()
    return user, client


@privacy_bp.route("/clientes/<int:client_id>")
@page_nivel_required("admin")
def client_privacy(client_id):
    _user, client = _context(client_id)
    return render_template(
        "pages/client_privacy.html", active="clientes", cliente=client,
        consents=ConsentRecord.query.filter_by(cliente_id=client.id).order_by(ConsentRecord.registrado_em.desc()).all(),
        requests=DataSubjectRequest.query.filter_by(cliente_id=client.id).order_by(DataSubjectRequest.solicitado_em.desc()).all(),
    )


@privacy_bp.route("/clientes/<int:client_id>/consent", methods=["POST"])
@page_nivel_required("admin")
def consent(client_id):
    user, client = _context(client_id)
    try:
        register_consent(
            client, user, request.form.get("purpose", ""),
            request.form.get("granted") == "true", "admin",
        )
        db.session.commit()
        flash("Registro de consentimento salvo.", "success")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "error")
    return redirect(url_for("privacy.client_privacy", client_id=client.id))


@privacy_bp.route("/clientes/<int:client_id>/export")
@page_nivel_required("admin")
def export(client_id):
    user, client = _context(client_id)
    archive = export_subject_data(client, user)
    db.session.commit()
    response = send_file(
        archive, mimetype="application/zip", as_attachment=True,
        download_name=f"titular-cliente-{client.id}.zip",
    )
    response.headers["Cache-Control"] = "no-store, private"
    return response


@privacy_bp.route("/clientes/<int:client_id>/anonymize", methods=["POST"])
@page_nivel_required("admin")
def anonymize(client_id):
    user, client = _context(client_id)
    try:
        anonymize_client(client, user)
        db.session.commit()
        flash("Cliente anonimizado.", "success")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "error")
    return redirect(url_for("privacy.client_privacy", client_id=client.id))
