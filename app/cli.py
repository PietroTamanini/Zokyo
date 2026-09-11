"""Comandos administrativos executados fora das requisicoes web."""
import os

import click
from sqlalchemy.orm import attributes

from app.extensions import db
from app.models import Cliente, ColetaAgendada, Configuracao, Fornecedor, Plan, Usuario
from app.services.tenant_provisioning import TenantProvisioningError, provision_tenant


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
        """Provisiona uma organizacao, subdominio e primeiro administrador."""
        try:
            organization, _admin = provision_tenant(
                name=name,
                slug=slug,
                owner_name=admin_name,
                owner_email=admin_email,
                owner_password=password,
                provision_dns=False,
            )
            db.session.commit()
        except TenantProvisioningError as exc:
            db.session.rollback()
            raise click.ClickException(str(exc)) from exc
        click.echo(f"Organizacao criada: {organization.slug} (id={organization.id}, dominio={organization.custom_domain})")
