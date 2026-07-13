"""Comandos administrativos executados fora das requisicoes web."""
import re

import click

from app.extensions import db
from app.models import Configuracao, Organization, Plan, Usuario, registrar
from app.utils.auth import validar_senha_forte
from app.utils.sanitizers import sanitize_email, sanitize_text
from app.utils.validators import validar_email


def register_cli(app):
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

    @app.cli.command("create-organization")
    @click.option("--name", required=True, help="Nome da organizacao.")
    @click.option("--slug", required=True, help="Identificador URL em minusculas.")
    @click.option("--admin-name", required=True, help="Nome do administrador inicial.")
    @click.option("--admin-email", required=True, help="E-mail do administrador inicial.")
    @click.password_option("--password", confirmation_prompt=True)
    def create_organization(name, slug, admin_name, admin_email, password):
        """Provisiona uma organizacao e seu primeiro administrador."""
        name = sanitize_text(name, max_length=200)
        slug = slug.strip().lower()
        admin_name = sanitize_text(admin_name, max_length=120)
        admin_email = sanitize_email(admin_email)
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,78}[a-z0-9]", slug):
            raise click.ClickException("Slug invalido. Use 3-80 caracteres: letras minusculas, numeros e hifen.")
        if not validar_email(admin_email):
            raise click.ClickException("E-mail administrativo invalido.")
        password_errors = validar_senha_forte(password)
        if password_errors:
            raise click.ClickException("Senha invalida: " + " ".join(password_errors))
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
        registrar(
            "criacao", "organizations", "Organizacao provisionada por CLI.",
            usuario_id=admin.id, usuario_nome=admin.nome, organization_id=organization.id,
        )
        db.session.commit()
        click.echo(f"Organizacao criada: {organization.slug} (id={organization.id})")
