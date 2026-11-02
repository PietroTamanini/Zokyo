"""Comandos administrativos executados fora das requisicoes web."""
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import click
from sqlalchemy.orm import attributes

from app.extensions import db
from app.models import (
    Cliente,
    ColetaAgendada,
    Configuracao,
    Fornecedor,
    OrdemServico,
    Organization,
    Peca,
    Plan,
    Transacao,
    Usuario,
)
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

    @app.cli.command("seed-demo")
    @click.option("--reset", is_flag=True, help="Recria somente os dados demonstrativos das duas empresas.")
    def seed_demo(reset):
        """Cria duas empresas locais com usuarios e dados demonstrativos."""
        demo_password = "ZokyoDemo2026!"
        plans = {}
        for code, name, limits in (
            ("starter", "Starter", {"max_users": 3, "max_clients": 500, "max_open_orders": 100}),
            ("professional", "Professional", {"max_users": 10, "max_clients": 5000, "max_open_orders": 1000}),
            ("unlimited", "Unlimited", {}),
        ):
            plan = Plan.query.filter_by(code=code).first()
            if not plan:
                plan = Plan(code=code, nome=name, limites=limits, ativo=True)
                db.session.add(plan)
            plans[code] = plan
        db.session.flush()

        definitions = (
            ("demo-tecmais", "TecMais Assistência", "Marina Demo", "demo.tecmais@zokyo.local"),
            ("demo-oficinadigital", "Oficina Digital", "Rafael Demo", "demo.oficinadigital@zokyo.local"),
        )
        created = 0
        for index, (slug, name, owner_name, email) in enumerate(definitions, start=1):
            organization = Organization.query.execution_options(include_all_tenants=True).filter_by(slug=slug).first()
            if not organization:
                organization, _owner = provision_tenant(
                    name=name,
                    slug=slug,
                    owner_name=owner_name,
                    owner_email=email,
                    owner_password=demo_password,
                    plan_id=plans["professional"].id,
                    trial_days=30,
                    provision_dns=False,
                )
                created += 1
            owner = Usuario.query.execution_options(include_all_tenants=True).filter_by(
                organization_id=organization.id, email=email
            ).first()
            if not owner:
                owner = Usuario(
                    organization_id=organization.id,
                    nome=owner_name,
                    email=email,
                    nivel="admin",
                    ativo=True,
                    onboarding_completed=True,
                )
                owner.set_senha(demo_password)
                db.session.add(owner)
                db.session.flush()

            cfg = Configuracao.get(organization.id)
            cfg.nome_empresa = name
            cfg.cidade = "São Paulo" if index == 1 else "Curitiba"
            cfg.uf = "SP" if index == 1 else "PR"
            cfg.email = email
            cfg.telefone = "(11) 99999-0000" if index == 1 else "(41) 98888-0000"
            cfg.meta_receita_mensal = 15000
            cfg.alerta_estoque_minimo = 5

            marker = f"Demo {slug} "
            if reset:
                db.session.query(Transacao).filter(Transacao.organization_id == organization.id).delete(
                    synchronize_session=False
                )
                db.session.query(OrdemServico).filter(OrdemServico.organization_id == organization.id).delete(
                    synchronize_session=False
                )
                db.session.query(Peca).filter(Peca.organization_id == organization.id).delete(
                    synchronize_session=False
                )
                db.session.query(Fornecedor).filter(Fornecedor.organization_id == organization.id).delete(
                    synchronize_session=False
                )
                db.session.query(Cliente).filter(Cliente.organization_id == organization.id).delete(
                    synchronize_session=False
                )

            existing_demo = Cliente.query.execution_options(include_all_tenants=True).filter(
                Cliente.organization_id == organization.id, Cliente.nome.like(f"{marker}%")
            ).count()
            if existing_demo:
                continue

            suppliers = []
            for item in range(1, 7):
                supplier = Fornecedor(
                    organization_id=organization.id,
                    nome=f"{marker}Fornecedor {item:02d}",
                    cnpj=f"{index:02d}000000{item:04d}00",
                    telefone=f"1198888{index}{item:03d}",
                    email=f"fornecedor{item}.{slug}@zokyo.local",
                    cidade=cfg.cidade,
                    ativo=True,
                )
                db.session.add(supplier)
                suppliers.append(supplier)
            db.session.flush()

            parts = []
            catalog = (
                ("SSD 480GB", "Armazenamento", 12, 180),
                ("Memória 8GB DDR4", "Memória", 8, 95),
                ("Fonte ATX 500W", "Energia", 18, 140),
                ("Teclado USB", "Periféricos", 25, 45),
                ("Mouse óptico", "Periféricos", 4, 28),
                ("Tela 24 polegadas", "Monitores", 7, 620),
                ("Cabo HDMI 2m", "Cabos", 32, 22),
                ("Bateria notebook", "Baterias", 3, 210),
                ("Pasta térmica", "Manutenção", 16, 18),
                ("HD 1TB", "Armazenamento", 9, 230),
            )
            for item, (part_name, category, quantity, cost) in enumerate(catalog, start=1):
                part = Peca(
                    organization_id=organization.id,
                    nome=f"{marker}{part_name}",
                    codigo=f"{slug[:6].upper()}-{item:03d}",
                    categoria=category,
                    localizacao=f"Estante {chr(64 + ((item - 1) % 4) + 1)}",
                    quantidade=quantity,
                    estoque_minimo=5,
                    custo=Decimal(cost),
                    margem=35,
                    fornecedor=suppliers[(item - 1) % len(suppliers)],
                    ativo=True,
                )
                db.session.add(part)
                parts.append(part)
            db.session.flush()

            clients = []
            for item in range(1, 21):
                client = Cliente(
                    organization_id=organization.id,
                    nome=f"{marker}Cliente {item:02d}",
                    cpf=f"{index}{item:010d}"[-11:],
                    telefone=f"1197777{index}{item:03d}",
                    email=f"cliente{item}.{slug}@zokyo.local",
                    cidade=cfg.cidade,
                    uf=cfg.uf,
                    ativo=True,
                )
                db.session.add(client)
                clients.append(client)
            db.session.flush()

            statuses = ("recepcao", "em_analise", "aguardando_aprovacao", "em_reparo", "pronto", "entregue")
            devices = (("Notebook", "Dell", "Inspiron 15"), ("Desktop", "Lenovo", "ThinkCentre"), ("Celular", "Samsung", "Galaxy A54"))
            orders = []
            now = datetime.now(timezone.utc)
            for item in range(1, 31):
                device = devices[(item - 1) % len(devices)]
                order = OrdemServico(
                    organization_id=organization.id,
                    numero=item,
                    cliente_id=clients[(item - 1) % len(clients)].id,
                    usuario_id=owner.id,
                    tipo_aparelho=device[0],
                    marca=device[1],
                    modelo=device[2],
                    numero_serie=f"{slug[:4].upper()}-{item:06d}",
                    defeito_alegado="Equipamento apresenta falha intermitente e precisa de diagnóstico.",
                    defeito_encontrado="Componente com desgaste e necessidade de manutenção preventiva.",
                    solucao="Limpeza, testes de bancada e substituição do componente indicado.",
                    observacoes="Registro criado pelo seed local para testes.",
                    valor_servico=Decimal(120 + (item % 5) * 35),
                    valor_pecas=Decimal(40 + (item % 4) * 25),
                    desconto=Decimal(0 if item % 5 else 20),
                    horas_trabalho=Decimal("1.5"),
                    custo_hora=Decimal("60"),
                    prio="alta" if item % 7 == 0 else "normal",
                    tipo_atendimento="balcao",
                    tecnico_nome=owner_name,
                    garantia_dias=90,
                    data_prev=now + timedelta(days=(item % 10) - 2),
                    status=statuses[(item - 1) % len(statuses)],
                    data_entrada=now - timedelta(days=item),
                    data_saida=(now - timedelta(days=max(0, item - 3))) if item % 6 == 0 else None,
                )
                order.pecas.append(parts[(item - 1) % len(parts)])
                db.session.add(order)
                orders.append(order)
            db.session.flush()

            for item, order in enumerate(orders, start=1):
                db.session.add(Transacao(
                    organization_id=organization.id,
                    os_id=order.id,
                    tipo="receita",
                    categoria="servico",
                    descricao=f"OS #{order.numero:04d} - {order.tipo_aparelho}",
                    valor=order.valor_total,
                    forma_pagamento=("pix" if item % 3 == 0 else "cartao"),
                    status=("pago" if item % 4 else "pendente"),
                    data_vencimento=now + timedelta(days=item % 12),
                    data_pagamento=(now - timedelta(days=item)) if item % 4 else None,
                ))
            for item in range(1, 9):
                db.session.add(Transacao(
                    organization_id=organization.id,
                    tipo="despesa",
                    categoria="fornecedor",
                    descricao=f"{marker}Compra de reposição {item:02d}",
                    valor=Decimal(250 + item * 37),
                    forma_pagamento="transferencia",
                    status="pago" if item % 3 else "pendente",
                    data_vencimento=now + timedelta(days=item),
                    data_pagamento=now - timedelta(days=item) if item % 3 else None,
                ))

        db.session.commit()
        click.echo(
            "Seed demo concluido: 2 empresas, 2 usuarios admin e dados de clientes, "
            "fornecedores, estoque, OS e financeiro."
        )
        click.echo(f"Senha dos usuarios demo: {demo_password}")
