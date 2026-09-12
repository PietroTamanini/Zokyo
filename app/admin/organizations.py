"""Acoes de empresas e admins de tenant no admin global."""

from flask import abort, flash

from app.admin.constants import SUBSCRIPTION_STATUSES
from app.admin.security import temporary_password
from app.extensions import db
from app.models import Organization, OrganizationSubscription, Plan, Usuario
from app.services.tenant_provisioning import TenantProvisioningError, provision_tenant, sync_tenant_dns, tenant_hostname
from app.utils.sanitizers import sanitize_text
from app.utils.validators import validar_email


def create_organization_from_form(form) -> tuple[bool, str]:
    plan_id = form.get("plan_id", type=int)
    if plan_id and not db.session.get(Plan, plan_id):
        abort(400)
    provided_password = (form.get("owner_password") or "").strip()
    owner_password = provided_password or temporary_password()
    try:
        organization, _owner = provision_tenant(
            name=form.get("name", ""),
            slug=form.get("slug", ""),
            owner_name=form.get("owner_name", ""),
            owner_email=form.get("owner_email", ""),
            owner_password=owner_password,
            plan_id=plan_id,
            trial_days=form.get("trial_days", 14, type=int) or 14,
            active=form.get("active") == "on",
            provision_dns=bool(form.get("provision_dns")),
        )
        db.session.commit()
    except TenantProvisioningError as exc:
        db.session.rollback()
        return False, str(exc)
    message = f"Empresa criada: {organization.custom_domain}."
    if not provided_password:
        message += f" Senha inicial do dono: {owner_password}"
    return True, message


def update_organization_from_form(organization_id: int, form) -> None:
    organization = get_organization_or_404(organization_id)
    name = sanitize_text(form.get("name", ""), max_length=200)
    if name:
        organization.nome = name
    organization.ativo = form.get("active") == "on"
    _apply_subscription(organization, form)
    if form.get("sync_dns") == "on":
        ensure_domain(organization)
        sync_tenant_dns(organization)
    db.session.commit()


def create_tenant_admin_from_form(organization_id: int, form) -> None:
    organization = get_organization_or_404(organization_id)
    name = sanitize_text(form.get("owner_name", ""), max_length=120)
    email = (form.get("owner_email") or "").strip().lower()
    password = (form.get("owner_password") or "").strip() or temporary_password()
    if len(name) < 2 or not validar_email(email):
        flash("Nome ou e-mail do admin invalido.", "error")
        return
    if Usuario.query.execution_options(include_all_tenants=True).filter_by(email=email).first():
        flash("E-mail ja cadastrado.", "error")
        return
    user = Usuario(
        organization_id=organization.id,
        nome=name,
        email=email,
        nivel="admin",
        ativo=True,
        onboarding_completed=False,
    )
    user.set_senha(password)
    db.session.add(user)
    db.session.commit()
    flash(f"Admin criado para {organization.nome}. Senha temporaria: {password}", "success")


def reset_tenant_admin_password(user_id: int) -> Usuario:
    user = db.session.execute(
        db.select(Usuario)
        .where(Usuario.id == user_id, Usuario.organization_id.is_not(None))
        .execution_options(include_all_tenants=True)
    ).scalar_one_or_none()
    if not user:
        abort(404)
    password = temporary_password()
    user.set_senha(password)
    user.security_version += 1
    from app.services.user_sessions import revoke_all

    revoke_all(user.id, "reset pelo admin global")
    db.session.commit()
    flash(f"Senha temporaria de {user.nome}: {password}", "success")
    return user


def sync_organization_dns(organization_id: int) -> None:
    organization = get_organization_or_404(organization_id)
    ensure_domain(organization)
    sync_tenant_dns(organization)
    db.session.commit()


def get_organization_or_404(organization_id: int) -> Organization:
    organization = db.session.execute(
        db.select(Organization).where(Organization.id == organization_id).execution_options(include_all_tenants=True)
    ).scalar_one_or_none()
    if not organization:
        abort(404)
    return organization


def ensure_domain(organization: Organization) -> None:
    if not organization.custom_domain and organization.subdomain:
        organization.custom_domain = tenant_hostname(organization.subdomain)


def _apply_subscription(organization: Organization, form) -> None:
    plan_id = form.get("plan_id", type=int)
    status = sanitize_text(form.get("status") or "", max_length=30)
    if not plan_id:
        return
    if status not in SUBSCRIPTION_STATUSES:
        abort(400)
    plan = db.session.get(Plan, plan_id)
    if not plan or not plan.ativo:
        abort(400)
    subscription = OrganizationSubscription.query.filter_by(organization_id=organization.id).first()
    if subscription:
        subscription.plan_id = plan.id
        subscription.status = status
        subscription.provider = subscription.provider or "sandbox"
    else:
        db.session.add(OrganizationSubscription(
            organization_id=organization.id,
            plan_id=plan.id,
            provider="sandbox",
            status=status,
        ))
