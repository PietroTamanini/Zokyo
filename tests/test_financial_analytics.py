from datetime import datetime, timezone

from app import create_app
from app.extensions import db
from app.models import Cliente, OrdemServico, Organization, Peca, Transacao, Usuario, os_pecas
from app.services.financial_analytics import order_financial_rows, period_summary


def _financial_app():
    app = create_app("development")
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    with app.app_context():
        db.create_all()
        organization = Organization(id=1, nome="Teste", slug="teste-financeiro")
        user = Usuario(organization_id=1, nome="Admin", email="financeiro@test.local", nivel="admin")
        user.set_senha("Senha!123")
        customer = Cliente(organization_id=1, nome="Cliente Financeiro")
        part = Peca(organization_id=1, nome="Peca", custo=99, quantidade=10)
        db.session.add_all([organization, user, customer, part])
        db.session.flush()
        order = OrdemServico(
            organization_id=1,
            numero=1,
            cliente_id=customer.id,
            usuario_id=user.id,
            valor_servico=180,
            valor_pecas=50,
            desconto=30,
            horas_trabalho=2,
            custo_hora=30,
            data_entrada=datetime(2026, 9, 1),
        )
        db.session.add(order)
        db.session.flush()
        db.session.execute(os_pecas.insert().values(
            os_id=order.id,
            peca_id=part.id,
            quantidade=2,
            valor_unitario=25,
            custo_unitario=20,
        ))
        due = datetime(2026, 9, 2, 12)
        db.session.add_all([
            Transacao(organization_id=1, os_id=order.id, tipo="receita", valor=80, status="pago", comissao_valor=8),
            Transacao(organization_id=1, os_id=order.id, tipo="receita", valor=50, status="pendente", data_vencimento=due),
            Transacao(organization_id=1, os_id=order.id, tipo="receita", valor=70, status="cancelado", data_vencimento=due),
            Transacao(organization_id=1, os_id=order.id, tipo="despesa", valor=10, status="pago", comissao_valor=99),
        ])
        db.session.commit()
    return app


def test_consolida_pagamento_custos_lucro_e_inadimplencia_com_data_utc():
    app = _financial_app()
    with app.app_context():
        rows = order_financial_rows(
            now=datetime(2026, 9, 3, tzinfo=timezone.utc),
            start=datetime(2026, 9, 1),
            end=datetime(2026, 9, 30),
        )

        assert len(rows) == 1
        row = rows[0]
        assert row["total"] == 200
        assert row["paid"] == 80
        assert row["pending"] == 50
        assert row["uncovered"] == 70
        assert row["overdue"] == 50
        assert row["oldest_due"] == datetime(2026, 9, 2, 12)
        assert row["part_cost"] == 40
        assert row["labor_cost"] == 60
        assert row["commissions"] == 8
        assert row["profit"] == 92


def test_resumo_reflete_apenas_as_linhas_do_periodo():
    rows = [
        {"total": 200, "pending": 50, "uncovered": 70, "overdue": 50, "profit": 92},
        {"total": 100, "pending": 0, "uncovered": 0, "overdue": 0, "profit": 35},
    ]

    summary = period_summary(rows, paid_revenue=180.126, paid_expenses=40.125)

    assert summary == {
        "orders": 2,
        "billed": 300,
        "received": 180.13,
        "expenses": 40.12,
        "outstanding": 120,
        "overdue": 50,
        "order_profit": 127,
    }


def test_vencimento_futuro_nao_e_inadimplencia():
    app = _financial_app()
    with app.app_context():
        rows = order_financial_rows(now=datetime(2026, 9, 1, tzinfo=timezone.utc))
        assert rows[0]["overdue"] == 0
        assert rows[0]["oldest_due"] is None
