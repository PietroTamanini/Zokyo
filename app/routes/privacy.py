"""Operações administrativas de privacidade e atendimento ao titular."""
from datetime import datetime, timezone
import hashlib
import hmac
import json
import re
from urllib.parse import urlsplit
from flask import Blueprint, current_app, flash, make_response, redirect, render_template, request, send_file, session, url_for
from flask import abort

from app.extensions import db
from app.models import Cliente, ConsentRecord, DataSubjectRequest, DataSubjectRequestRevision, Organization, PlatformRetentionPolicy, PlatformSetting, PrivacyIncident, PrivacyIncidentRevision, RetentionPolicy, Usuario, registrar
from app.services.privacy import REQUEST_TYPE_LABELS, anonymize_client, create_subject_request, export_subject_data, register_consent
from app.services.retention import CATEGORIES, count_candidates, count_platform_candidates
from app.utils.auth import platform_controlled_page_required
from app.utils.blind_index import blind_index_key
from app.utils.sanitizers import sanitize_email, sanitize_text
from app.utils.validators import validar_email

privacy_bp = Blueprint("privacy", __name__, url_prefix="/privacidade")

REQUEST_TYPES = REQUEST_TYPE_LABELS


def _subject_request_rate_key(ip):
    """Stable, purpose-scoped pseudonym that fits the existing IP column."""
    digest = hmac.new(
        blind_index_key(),
        b"privacy-subject-request-rate-v1:" + ip.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return "pr:" + digest[:40]


def _record_incident_revision(incident, actor_id, action):
    fields = (
        "title", "description", "status", "severity", "affected_data",
        "affected_subjects", "known_at", "anpd_notified_at", "subjects_notified_at",
        "notification_reference", "notification_decision", "corrective_actions", "closed_at",
    )
    snapshot = {
        field: value.isoformat() if isinstance(value := getattr(incident, field), datetime) else value
        for field in fields
    }
    db.session.add(PrivacyIncidentRevision(
        incident_id=incident.id, actor_id=actor_id, action=action,
        snapshot=json.dumps(snapshot, ensure_ascii=False),
    ))


def _incident_timestamp(value, label):
    """Converte ISO 8601 com fuso explícito para UTC armazenado no banco."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError(f"{label}: informe data e hora no formato ISO 8601 com fuso.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label}: inclua o fuso horário, por exemplo -03:00.")
    utc_value = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    if utc_value > datetime.now(timezone.utc).replace(tzinfo=None):
        raise ValueError(f"{label}: a data não pode estar no futuro.")
    return utc_value


@privacy_bp.route("/politica", methods=["GET"])
def public_privacy_policy():
    """Encaminha somente ao documento que o responsável aprovou."""
    if PlatformSetting.get_value("privacy.policy_published", "false") != "true":
        abort(503, description="A política de privacidade ainda não foi publicada.")
    policy_url = PlatformSetting.get_value("privacy.privacy_policy_url", "") or ""
    if not _approved_policy_url(policy_url):
        abort(503, description="A política de privacidade está em preparação.")
    return redirect(policy_url, code=302)


def _approved_policy_url(value):
    try:
        parsed = urlsplit(value or "")
        return bool(parsed.scheme == "https" and parsed.hostname and not parsed.username
                    and not parsed.password and not any(char.isspace() for char in value))
    except ValueError:
        return False


def _subject_request(organization=None):
    if request.method == "POST":
        if current_app.config.get("RATE_LIMIT_ENABLED", True):
            from app.utils.rate_limit import hit_rate_limit

            remaining = hit_rate_limit(
                _subject_request_rate_key(request.remote_addr or "unknown"),
                "privacy:subject_request",
                current_app.config["PRIVACY_REQUEST_LIMIT_PER_HOUR"], 3600,
            )
            if remaining:
                response = make_response(render_template(
                    "privacy/subject_request.html", organization=organization,
                    request_types=REQUEST_TYPES,
                    error="Muitas solicitações deste acesso. Aguarde e tente novamente.", form={},
                ), 429)
                response.headers["Retry-After"] = str(remaining)
                response.headers["Cache-Control"] = "no-store, private"
                return response
        try:
            record = create_subject_request(
                request_type=request.form.get("request_type", ""),
                requester_name=request.form.get("requester_name", ""),
                requester_email=request.form.get("requester_email", ""),
                organization_id=organization.id if organization else None,
                description=request.form.get("description", ""),
                channel="public",
            )
            db.session.commit()
        except ValueError as exc:
            db.session.rollback()
            response = make_response(render_template(
                "privacy/subject_request.html", organization=organization,
                request_types=REQUEST_TYPES, error=str(exc), form=request.form,
            ), 400)
            response.headers["Cache-Control"] = "no-store, private"
            return response
        response = make_response(render_template("privacy/subject_request_received.html", record=record))
        response.headers["Cache-Control"] = "no-store, private"
        return response
    response = make_response(render_template(
        "privacy/subject_request.html", organization=organization,
        request_types=REQUEST_TYPES, error=None, form={},
    ))
    response.headers["Cache-Control"] = "no-store, private"
    return response


@privacy_bp.route("/solicitacao", methods=["GET", "POST"])
def subject_request():
    return _subject_request()


@privacy_bp.route("/solicitacao/<slug>", methods=["GET", "POST"])
def subject_request_for_organization(slug):
    organization = Organization.query.execution_options(include_all_tenants=True).filter_by(
        slug=slug, ativo=True,
    ).first_or_404()
    return _subject_request(organization)


@privacy_bp.route("/incidentes", methods=["GET", "POST"])
@platform_controlled_page_required
def incidents():
    user = db.session.get(Usuario, session["usuario_id"])
    if request.method == "POST":
        title = sanitize_text(request.form.get("title", ""), max_length=200)
        description = sanitize_text(request.form.get("description", ""), max_length=10000)
        severity = request.form.get("severity", "medium")
        affected_subjects_raw = request.form.get("affected_subjects", "").strip()
        try:
            affected_subjects = int(affected_subjects_raw) if affected_subjects_raw else None
        except ValueError:
            affected_subjects = -1
        try:
            known_at = _incident_timestamp(
                request.form.get("known_at", ""), "Conhecimento da afetação",
            )
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("privacy.incidents"))
        if (not title or not description or severity not in {"low", "medium", "high", "critical"}
                or (affected_subjects is not None and affected_subjects < 0)):
            flash("Informe título, descrição, severidade e quantidade estimada válidos.", "error")
            return redirect(url_for("privacy.incidents"))
        incident = PrivacyIncident(
            title=title, description=description, severity=severity,
            known_at=known_at,
            affected_data=sanitize_text(request.form.get("affected_data", ""), max_length=2000) or None,
            affected_subjects=affected_subjects,
            reported_by_id=user.id,
        )
        db.session.add(incident)
        db.session.flush()
        _record_incident_revision(incident, user.id, "created")
        registrar("criacao", "privacidade", f"Incidente #{incident.id} registrado", usuario_id=user.id, usuario_nome=user.nome)
        db.session.commit()
        flash("Incidente registrado e preservado para investigação.", "success")
        return redirect(url_for("privacy.incidents"))
    rows = PrivacyIncident.query.order_by(PrivacyIncident.created_at.desc()).limit(100).all()
    revisions = PrivacyIncidentRevision.query.filter(
        PrivacyIncidentRevision.incident_id.in_([item.id for item in rows])
    ).order_by(PrivacyIncidentRevision.id.desc()).all() if rows else []
    revision_map = {}
    for revision in revisions:
        revision_map.setdefault(revision.incident_id, []).append(revision)
    return render_template("pages/privacy_incidents.html", active="privacidade", incidents=rows, revisions=revision_map)


@privacy_bp.route("/incidentes/<int:incident_id>", methods=["POST"])
@platform_controlled_page_required
def incident_update(incident_id):
    incident = PrivacyIncident.query.get_or_404(incident_id)
    actor_id = session["usuario_id"]
    status = request.form.get("status", "").strip()
    severity = request.form.get("severity", "").strip()
    if status not in {"open", "investigating", "contained", "closed"}:
        flash("Status de incidente inválido.", "error")
        return redirect(url_for("privacy.incidents"))
    if severity not in {"low", "medium", "high", "critical"}:
        flash("Severidade de incidente inválida.", "error")
        return redirect(url_for("privacy.incidents"))
    notification_decision = sanitize_text(
        request.form.get("notification_decision", ""), max_length=5000,
    ) or None
    corrective_actions = sanitize_text(
        request.form.get("corrective_actions", ""), max_length=5000,
    ) or None
    try:
        known_at = _incident_timestamp(
            request.form.get("known_at", ""), "Conhecimento da afetação",
        ) or incident.known_at
        anpd_notified_at = _incident_timestamp(
            request.form.get("anpd_notified_at", ""), "Comunicação à ANPD",
        ) or incident.anpd_notified_at
        subjects_notified_at = _incident_timestamp(
            request.form.get("subjects_notified_at", ""), "Comunicação aos titulares",
        ) or incident.subjects_notified_at
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("privacy.incidents"))
    if ((anpd_notified_at or subjects_notified_at) and not known_at
            or (known_at and anpd_notified_at and anpd_notified_at < known_at)
            or (known_at and subjects_notified_at and subjects_notified_at < known_at)):
        flash("Registre o conhecimento antes das comunicações; confira a ordem das datas.", "error")
        return redirect(url_for("privacy.incidents"))
    if status == "closed" and (not notification_decision or not corrective_actions):
        flash("Documente a decisão de comunicação e as ações corretivas antes de encerrar.", "error")
        return redirect(url_for("privacy.incidents"))
    incident.status = status
    incident.severity = severity
    incident.known_at = known_at
    incident.anpd_notified_at = anpd_notified_at
    incident.subjects_notified_at = subjects_notified_at
    incident.notification_reference = sanitize_text(
        request.form.get("notification_reference", ""), max_length=200,
    ) or incident.notification_reference
    incident.notification_decision = notification_decision
    incident.corrective_actions = corrective_actions
    incident.closed_at = datetime.now(timezone.utc) if status == "closed" else None
    _record_incident_revision(incident, actor_id, "updated")
    registrar(
        "edicao", "privacidade",
        f"Incidente #{incident.id} atualizado; status={status}; "
        f"conhecimento={'sim' if known_at else 'nao'}; "
        f"ANPD={'sim' if anpd_notified_at else 'nao'}; "
        f"titulares={'sim' if subjects_notified_at else 'nao'}",
    )
    db.session.commit()
    flash("Incidente atualizado. Guarde também os comprovantes das comunicações realizadas.", "success")
    return redirect(url_for("privacy.incidents"))


@privacy_bp.route("/solicitacoes", methods=["GET"])
@platform_controlled_page_required
def subject_requests():
    status = request.args.get("status", "").strip()
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    query = DataSubjectRequest.query
    if status in {"open", "in_progress", "completed", "rejected"}:
        query = query.filter_by(status=status)
    if status == "overdue":
        query = query.filter(
            DataSubjectRequest.status.in_(("open", "in_progress")),
            DataSubjectRequest.due_at.is_not(None),
            DataSubjectRequest.due_at < now_utc,
        ).order_by(DataSubjectRequest.due_at.asc())
    else:
        query = query.order_by(DataSubjectRequest.solicitado_em.desc())
    records = query.limit(200).all()
    revisions = DataSubjectRequestRevision.query.filter(
        DataSubjectRequestRevision.request_id.in_([item.id for item in records])
    ).order_by(DataSubjectRequestRevision.id.desc()).all() if records else []
    revision_map = {}
    for revision in revisions:
        revision_map.setdefault(revision.request_id, []).append(revision)
    return render_template(
        "pages/privacy_requests.html", active="privacidade",
        requests=records, selected_status=status,
        now_utc=now_utc, revisions=revision_map,
    )


@privacy_bp.route("/solicitacoes/<int:request_id>", methods=["POST"])
@platform_controlled_page_required
def subject_request_update(request_id):
    record = DataSubjectRequest.query.get_or_404(request_id)
    status = request.form.get("status", "").strip()
    if status not in {"open", "in_progress", "completed", "rejected"}:
        flash("Status de solicitação inválido.", "error")
        return redirect(url_for("privacy.subject_requests"))
    identity_verified = request.form.get("identity_verified") == "1"
    identity_method = request.form.get("identity_method", "").strip()
    identity_reference = sanitize_text(request.form.get("identity_reference", ""), max_length=200) or None
    response_notes = sanitize_text(request.form.get("response_notes", ""), max_length=5000) or None
    response_channel = request.form.get("response_channel", "").strip()
    delivery_reference = sanitize_text(request.form.get("delivery_reference", ""), max_length=200) or None
    try:
        delivered_at = _incident_timestamp(request.form.get("delivered_at", ""), "Entrega da resposta")
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("privacy.subject_requests"))
    if response_channel and response_channel not in {"email", "portal", "in_person", "other"}:
        flash("Canal de resposta inválido.", "error")
        return redirect(url_for("privacy.subject_requests"))
    if identity_verified and (identity_method not in {"email_reply", "portal_authenticated", "in_person", "other"}
                              or not identity_reference):
        flash("Registre o método e o protocolo de verificação da identidade, sem anexar documento pessoal.", "error")
        return redirect(url_for("privacy.subject_requests"))
    organization_value = request.form.get("organization_id", "").strip()
    client_value = request.form.get("cliente_id", "").strip()
    if client_value:
        if not identity_verified or not organization_value.isdecimal() or not client_value.isdecimal():
            flash("Valide a identidade e informe IDs válidos da empresa e do cliente antes de vincular.", "error")
            return redirect(url_for("privacy.subject_requests"))
        organization_id, client_id = int(organization_value), int(client_value)
        if ((record.organization_id and record.organization_id != organization_id)
                or (record.cliente_id and record.cliente_id != client_id)):
            flash("O pedido já pertence a outra empresa ou cliente.", "error")
            return redirect(url_for("privacy.subject_requests"))
        linked_client = Cliente.query.execution_options(include_all_tenants=True).filter_by(
            id=client_id, organization_id=organization_id,
        ).first()
        if not linked_client:
            flash("Cliente não encontrado na empresa informada.", "error")
            return redirect(url_for("privacy.subject_requests"))
        record.organization_id = organization_id
        record.cliente_id = client_id
    elif organization_value and (not organization_value.isdecimal()
                                 or record.organization_id != int(organization_value)):
        flash("Para vincular uma empresa, informe também o cliente verificado.", "error")
        return redirect(url_for("privacy.subject_requests"))
    if status == "completed" and not identity_verified:
        flash("Valide a identidade antes de concluir a solicitação.", "error")
        return redirect(url_for("privacy.subject_requests"))
    if status in {"completed", "rejected"} and not response_notes:
        flash("Registre a resposta ou o motivo da recusa antes de finalizar.", "error")
        return redirect(url_for("privacy.subject_requests"))
    if status in {"completed", "rejected"} and not (response_channel and delivery_reference and delivered_at):
        flash("Registre canal, horário e referência de entrega da resposta antes de finalizar.", "error")
        return redirect(url_for("privacy.subject_requests"))
    record.status = status
    record.identity_verified = identity_verified
    record.identity_method = identity_method if identity_verified else None
    record.identity_reference = identity_reference if identity_verified else None
    record.identity_verified_at = (record.identity_verified_at or datetime.now(timezone.utc)) if identity_verified else None
    record.response_notes = response_notes
    record.response_channel = response_channel or record.response_channel
    record.delivery_reference = delivery_reference or record.delivery_reference
    record.delivered_at = delivered_at or record.delivered_at
    record._revision_actor_id = session["usuario_id"]
    if status in {"completed", "rejected"}:
        record.concluido_em = record.concluido_em or datetime.now(timezone.utc)
    else:
        record.concluido_em = None
    registrar("edicao", "privacidade", f"Solicitação de titular #{record.id} atualizada; status={status}")
    db.session.commit()
    flash("Solicitação atualizada.", "success")
    return redirect(url_for("privacy.subject_requests"))


PRIVACY_SETTING_FIELDS = {
    "controller_name": ("Nome jurídico do controlador", 200),
    "controller_document": ("CNPJ do controlador", 30),
    "controller_address": ("Endereço do controlador", 300),
    "controller_site": ("Site oficial", 300),
    "dpo_name": ("Nome do encarregado", 160),
    "dpo_email": ("E-mail do encarregado", 254),
    "dpo_channel": ("Canal de privacidade", 300),
    "privacy_policy_url": ("URL da política aprovada", 300),
    "data_residency": ("Região principal de hospedagem", 120),
}


@privacy_bp.route("/configuracao", methods=["GET", "POST"])
@platform_controlled_page_required
def privacy_settings():
    if request.method == "POST":
        values = {}
        for key, (_label, max_length) in PRIVACY_SETTING_FIELDS.items():
            values[key] = sanitize_text(request.form.get(key, ""), max_length=max_length) or None
        if values["dpo_email"] and not validar_email(values["dpo_email"]):
            flash("O e-mail do encarregado é inválido.", "error")
            return redirect(url_for("privacy.privacy_settings"))
        publish_requested = request.form.get("policy_published") == "1"
        if publish_requested:
            required = ("controller_name", "controller_document", "controller_address", "dpo_email", "dpo_channel", "privacy_policy_url")
            if any(not values.get(key) for key in required):
                flash("Preencha controlador, CNPJ, endereço, encarregado, canal e URL da política aprovada antes de publicar.", "error")
                return redirect(url_for("privacy.privacy_settings"))
            if not _approved_policy_url(values["privacy_policy_url"]):
                flash("A URL da política aprovada deve usar HTTPS e apontar para o documento revisado.", "error")
                return redirect(url_for("privacy.privacy_settings"))
            if request.form.get("legal_approval") != "1":
                flash("A publicação exige confirmação de revisão jurídica.", "error")
                return redirect(url_for("privacy.privacy_settings"))
        for key, value in values.items():
            PlatformSetting.set_value(f"privacy.{key}", value)
        PlatformSetting.set_value("privacy.policy_published", "true" if publish_requested else "false")
        PlatformSetting.set_value("privacy.policy_version", sanitize_text(request.form.get("policy_version", "1.0"), max_length=20) or "1.0")
        registrar("edicao", "privacidade", "Configurações de governança de privacidade atualizadas")
        db.session.commit()
        flash("Configurações de privacidade salvas.", "success")
        return redirect(url_for("privacy.privacy_settings"))
    values = {
        key: PlatformSetting.get_value(f"privacy.{key}", "") or ""
        for key in PRIVACY_SETTING_FIELDS
    }
    values["policy_published"] = PlatformSetting.get_value("privacy.policy_published", "false") == "true"
    values["policy_version"] = PlatformSetting.get_value("privacy.policy_version", "1.0") or "1.0"
    return render_template("pages/privacy_settings.html", active="privacidade", values=values, fields=PRIVACY_SETTING_FIELDS)


@privacy_bp.route("/retencao", methods=["GET", "POST"])
@platform_controlled_page_required
def retention():
    user = db.session.get(Usuario, session["usuario_id"])
    organizations = Organization.query.execution_options(include_all_tenants=True).filter_by(ativo=True).order_by(Organization.nome).all()
    selected_id = request.values.get("organization_id", type=int) or getattr(user, "organization_id", None)
    if not selected_id and organizations:
        selected_id = organizations[0].id
    selected = next((item for item in organizations if item.id == selected_id), None)
    if not selected and request.method == "POST":
        flash("Crie ou selecione uma assistência antes de configurar a retenção.", "error")
        return redirect(url_for("platform.index", view="organizations"))
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
            policy = RetentionPolicy.query.filter_by(organization_id=selected.id, category=category).first()
            if not policy:
                policy = RetentionPolicy(organization_id=selected.id, category=category, retention_days=days)
                db.session.add(policy)
            policy.retention_days = days
            policy.active = bool(request.form.get(f"active_{category}"))
            policy.approved_by_id = user.id if policy.active else None
            policy.approved_at = datetime.now(timezone.utc) if policy.active else None
        registrar("retencao", "privacy", "Politicas de retencao atualizadas pelo administrador.")
        db.session.commit()
        flash("Politicas de retencao atualizadas.", "success")
        return redirect(url_for("privacy.retention", organization_id=selected.id))
    policies = ({item.category: item for item in RetentionPolicy.query.filter_by(
        organization_id=selected.id
    ).all()} if selected else {})
    rows = []
    for category, label in CATEGORIES.items():
        policy = policies.get(category)
        rows.append((category, label, policy, count_candidates(policy) if policy else 0))
    platform_policy = PlatformRetentionPolicy.query.execution_options(
        include_all_tenants=True
    ).filter_by(category="user_sessions").first()
    return render_template(
        "pages/retention.html", active="retencao", rows=rows,
        organizations=organizations, selected_organization_id=selected.id if selected else None,
        platform_policy=platform_policy,
        platform_candidates=count_platform_candidates(platform_policy),
    )


@privacy_bp.route("/retencao/plataforma", methods=["POST"])
@platform_controlled_page_required
def platform_retention():
    try:
        days = int(request.form.get("platform_days", ""))
    except ValueError:
        days = 0
    if not 7 <= days <= 3650:
        flash("O prazo deve ficar entre 7 e 3650 dias.", "error")
        return redirect(url_for("privacy.retention"))
    enabled = request.form.get("platform_active") == "1"
    approved = request.form.get("platform_legal_approval") == "yes"
    reference = (request.form.get("platform_approval_reference") or "").strip().upper()
    if enabled and (not approved or not re.fullmatch(r"[A-Z0-9-]{4,40}", reference)):
        flash("Para ativar, confirme a aprovação e informe um código de protocolo válido.", "error")
        return redirect(url_for("privacy.retention"))
    policy = PlatformRetentionPolicy.query.execution_options(
        include_all_tenants=True
    ).filter_by(category="user_sessions").first()
    if policy is None:
        policy = PlatformRetentionPolicy(category="user_sessions", retention_days=days)
        db.session.add(policy)
    user_id = session["usuario_id"]
    policy.retention_days = days
    policy.active = enabled
    policy.approval_reference = reference if enabled else None
    policy.approved_by_id = user_id if enabled else None
    policy.approved_at = datetime.now(timezone.utc) if enabled else None
    registrar(
        "retencao", "privacy", "Política global de retenção atualizada",
        f"categoria=user_sessions;ativo={int(enabled)};prazo_dias={days};referencia={reference if enabled else '-'}",
        organization_id=None,
    )
    db.session.commit()
    flash("Política global de sessões atualizada.", "success")
    return redirect(url_for("privacy.retention"))


def _context(client_id):
    user = db.session.get(Usuario, session.get("usuario_id"))
    client = Cliente.query.filter_by(id=client_id, organization_id=user.organization_id).first_or_404()
    return user, client


@privacy_bp.route("/clientes/<int:client_id>")
@platform_controlled_page_required
def client_privacy(client_id):
    _user, client = _context(client_id)
    return render_template(
        "pages/client_privacy.html", active="clientes", cliente=client,
        consents=ConsentRecord.query.filter_by(cliente_id=client.id).order_by(ConsentRecord.registrado_em.desc()).all(),
        requests=DataSubjectRequest.query.filter_by(cliente_id=client.id).order_by(DataSubjectRequest.solicitado_em.desc()).all(),
    )


@privacy_bp.route("/clientes/<int:client_id>/consent", methods=["POST"])
@platform_controlled_page_required
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
@platform_controlled_page_required
def export(client_id):
    user, client = _context(client_id)
    archive = export_subject_data(client, user)
    db.session.commit()
    response = send_file(
        archive, mimetype="application/zip", as_attachment=True,
        download_name=f"titular-cliente-{client.id}.zip",
    )
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["X-Export-SHA256"] = archive.export_sha256
    return response


@privacy_bp.route("/clientes/<int:client_id>/anonymize", methods=["POST"])
@platform_controlled_page_required
def anonymize(client_id):
    user, client = _context(client_id)
    try:
        anonymize_client(client, user)
        db.session.commit()
        flash("Dados cadastrais removidos. Históricos e registros de auditoria permanecem sujeitos à retenção.", "success")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "error")
    return redirect(url_for("privacy.client_privacy", client_id=client.id))
