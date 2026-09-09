"""Populate synthetic data and benchmark critical Zokyo routes.

Usage:
  python scripts/benchmark_performance.py --clients 500 --orders 2000 --parts 300 --transactions 4000
"""
from __future__ import annotations

import argparse
import sys
import statistics
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app
from app.extensions import db
from app.models import Cliente, Configuracao, OrdemServico, Organization, Peca, Transacao, Usuario


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def ensure_base():
    org = Organization.query.filter_by(slug="bench").first()
    if not org:
        org = Organization(nome="Benchmark", slug="bench", ativo=True)
        db.session.add(org)
        db.session.flush()
    user = Usuario.query.filter_by(email="bench@zokyo.local").first()
    if not user:
        user = Usuario(
            organization_id=org.id,
            nome="Benchmark Admin",
            email="bench@zokyo.local",
            nivel="admin",
            ativo=True,
            onboarding_completed=True,
        )
        user.set_senha("Senha!123")
        db.session.add(user)
    if not Configuracao.query.filter_by(organization_id=org.id).first():
        db.session.add(Configuracao(organization_id=org.id, nome_empresa="Benchmark"))
    db.session.commit()
    return org, user


def populate(org, user, clients, parts, orders, transactions):
    existing_clients = Cliente.query.filter_by(organization_id=org.id).count()
    if existing_clients < clients:
        batch = []
        for idx in range(existing_clients, clients):
            batch.append(Cliente(
                organization_id=org.id,
                nome=f"Cliente Benchmark {idx:05d}",
                telefone=f"4799{idx % 100000:05d}",
                cidade="Joinville",
                uf="SC",
                ativo=True,
            ))
        db.session.add_all(batch)
        db.session.commit()

    existing_parts = Peca.query.filter_by(organization_id=org.id).count()
    if existing_parts < parts:
        batch = []
        for idx in range(existing_parts, parts):
            batch.append(Peca(
                organization_id=org.id,
                nome=f"Peca Benchmark {idx:05d}",
                codigo=f"PB{idx:05d}",
                categoria=f"Categoria {idx % 8}",
                quantidade=20 + idx % 80,
                estoque_minimo=5,
                custo=10 + idx % 120,
                margem=35,
                ativo=True,
            ))
        db.session.add_all(batch)
        db.session.commit()

    client_ids = [row[0] for row in db.session.query(Cliente.id).filter_by(organization_id=org.id).all()]
    existing_orders = OrdemServico.query.filter_by(organization_id=org.id).count()
    statuses = ["recepcao", "em_analise", "aguardando_aprovacao", "em_reparo", "pronto", "entregue"]
    if existing_orders < orders:
        start = _now() - timedelta(days=180)
        batch = []
        for idx in range(existing_orders, orders):
            status = statuses[idx % len(statuses)]
            closed = status == "entregue"
            batch.append(OrdemServico(
                organization_id=org.id,
                numero=idx + 1,
                cliente_id=client_ids[idx % len(client_ids)],
                usuario_id=user.id,
                tipo_aparelho="Notebook",
                marca=f"Marca {idx % 12}",
                modelo=f"Modelo {idx % 40}",
                defeito_alegado="Nao liga",
                valor_servico=80 + idx % 300,
                valor_pecas=30 + idx % 200,
                desconto=idx % 25,
                horas_trabalho=1 + idx % 5,
                custo_hora=35,
                status=status,
                prio="normal",
                data_entrada=start + timedelta(hours=idx),
                data_prev=start + timedelta(hours=idx, days=7),
                data_saida=start + timedelta(hours=idx, days=10) if closed else None,
                baixada_em=start + timedelta(hours=idx, days=10) if closed else None,
            ))
            if len(batch) >= 500:
                db.session.add_all(batch)
                db.session.commit()
                batch = []
        if batch:
            db.session.add_all(batch)
            db.session.commit()

    order_ids = [row[0] for row in db.session.query(OrdemServico.id).filter_by(organization_id=org.id).all()]
    existing_tx = Transacao.query.filter_by(organization_id=org.id).count()
    if existing_tx < transactions:
        start = _now() - timedelta(days=180)
        batch = []
        for idx in range(existing_tx, transactions):
            is_revenue = idx % 5 != 0
            paid = idx % 3 != 0
            due = start + timedelta(hours=idx)
            batch.append(Transacao(
                organization_id=org.id,
                os_id=order_ids[idx % len(order_ids)] if is_revenue else None,
                tipo="receita" if is_revenue else "despesa",
                categoria="servico" if is_revenue else "fornecedor",
                descricao=f"Transacao Benchmark {idx:05d}",
                valor=50 + idx % 500,
                status="pago" if paid else "pendente",
                criado_em=due,
                data_vencimento=due,
                data_pagamento=due if paid else None,
                comissao_valor=5 if is_revenue and paid else 0,
            ))
            if len(batch) >= 500:
                db.session.add_all(batch)
                db.session.commit()
                batch = []
        if batch:
            db.session.add_all(batch)
            db.session.commit()


def login_session(client, user):
    with client.session_transaction() as session:
        session["usuario_id"] = user.id
        session["usuario_nome"] = user.nome
        session["nivel"] = user.nivel
        session["perfil"] = user.nivel


def measure(client, path, rounds):
    times = []
    status = None
    size = 0
    for _ in range(rounds):
        start = time.perf_counter()
        response = client.get(path)
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed)
        status = response.status_code
        size = len(response.get_data())
    return {
        "path": path,
        "status": status,
        "avg_ms": statistics.mean(times),
        "p95_ms": sorted(times)[max(0, int(rounds * 0.95) - 1)],
        "min_ms": min(times),
        "max_ms": max(times),
        "bytes": size,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--clients", type=int, default=500)
    parser.add_argument("--parts", type=int, default=300)
    parser.add_argument("--orders", type=int, default=2000)
    parser.add_argument("--transactions", type=int, default=4000)
    parser.add_argument("--rounds", type=int, default=8)
    args = parser.parse_args()

    app = create_app("development")
    with app.app_context():
        org, user = ensure_base()
        populate(org, user, args.clients, args.parts, args.orders, args.transactions)
        client = app.test_client()
        login_session(client, user)
        targets = [
            "/",
            "/clientes",
            "/os",
            "/os/baixadas",
            "/estoque",
            "/financeiro",
            "/api/os?per_page=50",
            "/api/clientes?q=Cliente&limit=8",
            "/api/pecas?q=PB&limit=10",
        ]
        print("path,status,avg_ms,p95_ms,min_ms,max_ms,bytes")
        for target in targets:
            row = measure(client, target, args.rounds)
            print(
                f"{row['path']},{row['status']},{row['avg_ms']:.2f},{row['p95_ms']:.2f},"
                f"{row['min_ms']:.2f},{row['max_ms']:.2f},{row['bytes']}"
            )


if __name__ == "__main__":
    main()
