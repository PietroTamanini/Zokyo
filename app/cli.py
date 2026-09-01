"""Comandos administrativos executados fora das requisicoes web."""
import os
import re

import click
from sqlalchemy.orm import attributes

from app.extensions import db
from app.models import Cliente, ColetaAgendada, Configuracao, Fornecedor, Organization, Plan, Usuario, registrar
from app.utils.auth import validar_senha_forte
from app.utils.sanitizers import sanitize_email, sanitize_text
from app.utils.validators import validar_email


def register_cli(app):
    @app.cli.command("production-check")
    @click.option(
        "--strict-integrations",
        is_flag=True,
        help="Trata integracoes externas ausentes como erro.",
    )
    def production_check(strict_integrations):
        """Valida configuracoes obrigatorias antes de publicar em producao."""
        from app.utils.production_readiness import check_production_readiness

        issues = check_production_readiness(
            dict(os.environ),
            strict_integrations=strict_integrations,
        )
        for issue in issues:
            click.echo(
                f"{issue.severity.upper()} {issue.code}: {issue.message}",
                err=issue.severity == "error",
            )
        if any(issue.severity == "error" for issue in issues):
            raise click.ClickException("Prontidao de producao reprovada.")
        click.echo("Prontidao de producao aprovada.")

    @app.cli.command("seed-system")
    def seed_system():
        """Cria ou atualiza dados globais seguros e idempotentes."""
        defaults = (
            ("starter", "Starter", {"max_users": 3, "max_clients": 500, "max_open_orders": 100}),
            ("professional", "Professional", {"max_users": 10, "max_clients": 5000, "max_open_orders": 1000}),
            ("unlimited", "Unlimited", {}),
        )
        for code, name, limits in defaults:
            plan = Plan.query.filter_by(code=code).first()
            if not plan:
                plan = Plan(code=code)
                db.session.add(plan)
            plan.nome = name
            plan.limites = limits
            plan.ativo = True
        db.session.commit()
        click.echo("Seed concluido: 3 planos globais ativos.")

    @app.cli.command("encrypt-sensitive-fields")
    def encrypt_sensitive_fields():
        """Regrava campos sensiveis para aplicar criptografia transparente."""
        targets = (
            (Cliente, ("endereco", "numero_casa")),
            (Fornecedor, ("endereco",)),
            (ColetaAgendada, ("telefone_contato", "endereco", "numero_casa", "observacoes")),
            (Configuracao, ("endereco", "dados_pagamento", "pix_chave")),
        )
        touched = 0
        fields = 0
        for model, names in targets:
            for obj in model.query.execution_options(include_all_tenants=True).all():
                changed = False
                for name in names:
                    value = getattr(obj, name, None)
                    if value:
                        attributes.flag_modified(obj, name)
                        changed = True
                        fields += 1
                if changed:
                    touched += 1
        db.session.commit()
        click.echo(f"Criptografia reaplicada: {touched} registros, {fields} campos.")

    @app.cli.command("rebuild-blind-indexes")
    def rebuild_blind_indexes():
        """Reconstrui hashes HMAC usados em buscas exatas de dados sensiveis."""
        targets = (Cliente, Fornecedor, Usuario)
        touched = 0
        for model in targets:
            for obj in model.query.execution_options(include_all_tenants=True).all():
                obj.refresh_blind_indexes()
                touched += 1
        db.session.commit()
        click.echo(f"Indices cegos reconstruidos: {touched} registros.")

    @app.cli.command("create-organization")
    @click.option("--name", required=True, help="Nome da organizacao.")
    @click.option("--slug", required=True, help="Identificador URL em minusculas.")
    @click.option("--admin-name", required=True, help="Nome do administrador inicial.")
    @click.option("--admin-email", required=True, help="E-mail do administrador inicial.")
    @click.password_option("--password", confirmation_prompt=True)
    def create_organization(name, slug, admin_name, admin_email, password):
        """Provisiona uma organização e seu primeiro administrador."""
        name = sanitize_text(name, max_length=200)
        slug = slug.strip().lower()
        admin_name = sanitize_text(admin_name, max_length=120)
        admin_email = sanitize_email(admin_email)
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,78}[a-z0-9]", slug):
            raise click.ClickException("Slug inválido. Use 3-80 caracteres: letras minúsculas, números e hífen.")
        if not validar_email(admin_email):
            raise click.ClickException("E-mail administrativo inválido.")
        password_errors = validar_senha_forte(password)
        if password_errors:
            raise click.ClickException("Senha inválida: " + " ".join(password_errors))
        if Organization.query.filter_by(slug=slug).first():
            raise click.ClickException("Slug ja cadastrado.")
        if Usuario.query.filter_by(email=admin_email).first():
            raise click.ClickException("E-mail ja cadastrado.")
        organization = Organization(nome=name, slug=slug)
        db.session.add(organization)
        db.session.flush()
        admin = Usuario(
            organization_id=organization.id,
            nome=admin_name,
            email=admin_email,
            nivel="admin",
            ativo=True,
            onboarding_completed=False,
        )
        admin.set_senha(password)
        db.session.add(admin)
        db.session.flush()
        db.session.add(Configuracao(organization_id=organization.id, nome_empresa=name))
        from app.services.message_templates import seed_default_templates
        seed_default_templates(organization.id)
        from app.services.billing import ensure_trial_subscription
        ensure_trial_subscription(organization.id)
        registrar(
            "criacao", "organizations", "Organizacao provisionada por CLI.",
            usuario_id=admin.id, usuario_nome=admin.nome, organization_id=organization.id,
        )
        db.session.commit()
        click.echo(f"Organizacao criada: {organization.slug} (id={organization.id})")
