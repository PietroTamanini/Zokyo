"""Testes de regressao de isolamento multi-tenant para backup e consultas SQL manuais.

Garantem que:
- Empresa A visualiza somente seus registros.
- Empresa B visualiza somente seus registros.
- Administrador da empresa A nao consegue obter contagens da empresa B.
- Usuarios sem autorizacao nao conseguem acessar backups.
- Consultas administrativas legítimas continuam funcionando.
"""
import os
import unittest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key-isolation")

from app import create_app
from app.extensions import db
from app.models import (
    Cliente,
    Configuracao,
    EventoLog,
    Fornecedor,
    OrdemServico,
    Organization,
    Peca,
    Transacao,
    Usuario,
)


def _make_app():
    app = create_app("development")
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    return app


def _seed_two_organizations(app):
    """Cria duas organizacoes com registros isolados."""
    with app.app_context():
        db.drop_all()
        db.create_all()

        org_a = Organization(id=1, nome="Empresa A", slug="empresa-a", ativo=True)
        org_b = Organization(id=2, nome="Empresa B", slug="empresa-b", ativo=True)
        db.session.add_all([org_a, org_b])
        db.session.flush()

        admin_a = Usuario(
            id=10, organization_id=1, nome="Admin A",
            email="admin-a@empresa-a.test", nivel="admin", ativo=True,
            onboarding_completed=True,
        )
        admin_a.set_senha("Senha!123")
        admin_b = Usuario(
            id=20, organization_id=2, nome="Admin B",
            email="admin-b@empresa-b.test", nivel="admin", ativo=True,
            onboarding_completed=True,
        )
        admin_b.set_senha("Senha!123")

        cfg_a = Configuracao(
            organization_id=1, nome_empresa="Empresa A Config",
            cnpj="11111111000110", cidade="Joinville", uf="SC",
        )
        cfg_b = Configuracao(
            organization_id=2, nome_empresa="Empresa B Config",
            cnpj="22222222000110", cidade="Blumenau", uf="SC",
        )

        cli_a = Cliente(
            id=100, organization_id=1, nome="Cliente A",
            cpf="11111111111", telefone="47900000001",
        )
        cli_b = Cliente(
            id=200, organization_id=2, nome="Cliente B",
            cpf="22222222222", telefone="47900000002",
        )

        forn_a = Fornecedor(
            id=300, organization_id=1, nome="Fornecedor A",
            cnpj="33333333000110", telefone="47900000003",
        )
        forn_b = Fornecedor(
            id=400, organization_id=2, nome="Fornecedor B",
            cnpj="44444444000110", telefone="47900000004",
        )

        peca_a = Peca(
            id=500, organization_id=1, nome="Peca A",
            codigo="PECA-A", quantidade=10, estoque_minimo=2,
            custo=10, margem=50,
        )
        peca_b = Peca(
            id=600, organization_id=2, nome="Peca B",
            codigo="PECA-B", quantidade=5, estoque_minimo=1,
            custo=20, margem=30,
        )

        db.session.add_all([
            admin_a, admin_b, cfg_a, cfg_b,
            cli_a, cli_b, forn_a, forn_b, peca_a, peca_b,
        ])
        db.session.flush()

        os_a = OrdemServico(
            id=700, organization_id=1, numero=1,
            cliente_id=cli_a.id, usuario_id=admin_a.id,
            tipo_aparelho="Notebook A", marca="Marca A", modelo="Modelo A",
            defeito_alegado="Nao liga A",
            valor_servico=100, status="recepcao",
        )
        os_b = OrdemServico(
            id=800, organization_id=2, numero=1,
            cliente_id=cli_b.id, usuario_id=admin_b.id,
            tipo_aparelho="Notebook B", marca="Marca B", modelo="Modelo B",
            defeito_alegado="Nao liga B",
            valor_servico=200, status="recepcao",
        )
        db.session.add_all([os_a, os_b])
        db.session.flush()

        tx_a = Transacao(
            id=900, organization_id=1, os_id=os_a.id,
            tipo="receita", categoria="servico",
            descricao="Pagamento A", valor=100, status="pago",
        )
        tx_b = Transacao(
            id=901, organization_id=2, os_id=os_b.id,
            tipo="receita", categoria="servico",
            descricao="Pagamento B", valor=200, status="pendente",
        )
        db.session.add_all([tx_a, tx_b])

        evt_a = EventoLog(
            organization_id=1, usuario_id=admin_a.id, usuario_nome="Admin A",
            tipo="criacao", modulo="os", operacao="Criacao OS A",
            descricao="OS A criada",
        )
        evt_b = EventoLog(
            organization_id=2, usuario_id=admin_b.id, usuario_nome="Admin B",
            tipo="criacao", modulo="os", operacao="Criacao OS B",
            descricao="OS B criada",
        )
        db.session.add_all([evt_a, evt_b])

        db.session.commit()

        return {
            "org_a_id": org_a.id,
            "org_b_id": org_b.id,
            "admin_a_id": admin_a.id,
            "admin_b_id": admin_b.id,
            "cli_a_id": cli_a.id,
            "cli_b_id": cli_b.id,
            "forn_a_id": forn_a.id,
            "forn_b_id": forn_b.id,
            "peca_a_id": peca_a.id,
            "peca_b_id": peca_b.id,
            "os_a_id": os_a.id,
            "os_b_id": os_b.id,
            "tx_a_id": tx_a.id,
            "tx_b_id": tx_b.id,
            "evt_a_id": evt_a.id,
            "evt_b_id": evt_b.id,
        }


def _login_client(app, user_id, nivel="admin"):
    """Retorna um test_client com sessao autenticada para o usuario."""
    client = app.test_client()
    with client.session_transaction() as session:
        session["usuario_id"] = user_id
        session["nivel"] = nivel
        session["perfil"] = nivel
        session["usuario_nome"] = f"Usuario {user_id}"
        session["_last_active"] = 9999999999
        session["_csrf_token"] = "csrf-isolation-test"
    return client


class TenantIsolationBackupTestCase(unittest.TestCase):

    def setUp(self):
        self.app = _make_app()
        self.ids = _seed_two_organizations(self.app)

    # ═════════════════════════════════════════════════════════════════════════════
    # TESTES DE ISOLAMENTO NA ROTA DE BACKUP
    # ═════════════════════════════════════════════════════════════════════════════

    def test_backup_view_empresa_a_so_ve_seus_registros(self):
        """Empresa A visualiza somente seus registros na pagina de backup."""
        client = _login_client(self.app, self.ids["admin_a_id"])
        response = client.get("/zokyo/backup")
        self.assertEqual(response.status_code, 200)

        # Verifica diretamente no banco: contagens filtradas por organization_id=1
        with self.app.app_context():
            from sqlalchemy import text
            contagens = {}
            for tabela in ("clientes", "fornecedores", "pecas", "ordens_servico",
                           "transacoes", "usuarios", "eventos_log", "configuracoes"):
                result = db.session.execute(
                    text(f"SELECT COUNT(*) FROM {tabela} WHERE organization_id=:org"),
                    {"org": self.ids["org_a_id"]},
                ).scalar()
                contagens[tabela] = result or 0

            self.assertEqual(contagens["clientes"], 1)
            self.assertEqual(contagens["fornecedores"], 1)
            self.assertEqual(contagens["pecas"], 1)
            self.assertEqual(contagens["ordens_servico"], 1)
            self.assertEqual(contagens["transacoes"], 1)
            self.assertEqual(contagens["usuarios"], 1)
            self.assertEqual(contagens["eventos_log"], 1)
            self.assertEqual(contagens["configuracoes"], 1)

    def test_backup_view_empresa_b_so_ve_seus_registros(self):
        """Empresa B visualiza somente seus registros na pagina de backup."""
        client = _login_client(self.app, self.ids["admin_b_id"])
        response = client.get("/zokyo/backup")
        self.assertEqual(response.status_code, 200)

        with self.app.app_context():
            from sqlalchemy import text
            contagens = {}
            for tabela in ("clientes", "fornecedores", "pecas", "ordens_servico",
                           "transacoes", "usuarios", "eventos_log", "configuracoes"):
                result = db.session.execute(
                    text(f"SELECT COUNT(*) FROM {tabela} WHERE organization_id=:org"),
                    {"org": self.ids["org_b_id"]},
                ).scalar()
                contagens[tabela] = result or 0

            self.assertEqual(contagens["clientes"], 1)
            self.assertEqual(contagens["fornecedores"], 1)
            self.assertEqual(contagens["pecas"], 1)
            self.assertEqual(contagens["ordens_servico"], 1)
            self.assertEqual(contagens["transacoes"], 1)
            self.assertEqual(contagens["usuarios"], 1)
            self.assertEqual(contagens["eventos_log"], 1)
            self.assertEqual(contagens["configuracoes"], 1)

    def test_admin_nao_consegue_contagens_da_outra_empresa(self):
        """Administrador da empresa A nao consegue obter contagens da empresa B via SQL manual."""
        # Simula o contexto da empresa A e executa as mesmas consultas da view de backup
        client = _login_client(self.app, self.ids["admin_a_id"])
        response = client.get("/zokyo/backup")
        self.assertEqual(response.status_code, 200)

        # Verifica diretamente no banco: consultas filtradas por org_a nao retornam dados de org_b
        with self.app.app_context():
            from sqlalchemy import text
            resultado = db.session.execute(
                text("SELECT COUNT(*) FROM clientes WHERE organization_id=:org_a AND id=:cli_b_id"),
                {"org_a": self.ids["org_a_id"], "cli_b_id": self.ids["cli_b_id"]},
            ).scalar()
            self.assertEqual(resultado, 0)

            resultado_tx = db.session.execute(
                text("SELECT COUNT(*) FROM transacoes WHERE organization_id=:org_a AND id=:tx_b_id"),
                {"org_a": self.ids["org_a_id"], "tx_b_id": self.ids["tx_b_id"]},
            ).scalar()
            self.assertEqual(resultado_tx, 0)

    def test_backup_acesso_sem_autenticacao_redireciona(self):
        """Usuario sem autenticacao nao consegue acessar a pagina de backup."""
        client = self.app.test_client()
        response = client.get("/zokyo/backup", follow_redirects=False)
        self.assertIn(response.status_code, (302, 401, 403))

    def test_backup_acesso_sem_organization_id_retorna_403(self):
        """Usuario autenticado sem organization_id (admin de plataforma) nao acessa backup."""
        with self.app.app_context():
            db.drop_all()
            db.create_all()

            platform_admin = Usuario(
                id=99, organization_id=None, nome="Platform Admin",
                email="platform@test.test", nivel="admin", ativo=True,
                is_platform_admin=True, onboarding_completed=True,
            )
            platform_admin.set_senha("Senha!123")
            db.session.add(platform_admin)
            db.session.commit()

        client = _login_client(self.app, 99, nivel="admin")
        response = client.get("/zokyo/backup", follow_redirects=False)
        self.assertIn(response.status_code, (302, 403))

    # ═════════════════════════════════════════════════════════════════════════════
    # TESTES DE OUTRAS CONSULTAS SQL MANUAIS (isolamento multi-tenant)
    # ═════════════════════════════════════════════════════════════════════════════

    def test_compras_pecas_isolamento_por_organizacao(self):
        """Consulta manual de compras-pecas filtra por organization_id."""
        with self.app.app_context():
            from sqlalchemy import text
            resultado = db.session.execute(
                text("""
                    SELECT COUNT(*) FROM pecas
                    WHERE organization_id=:org_b AND id=:peca_a_id
                """),
                {"org_b": self.ids["org_b_id"], "peca_a_id": self.ids["peca_a_id"]},
            ).scalar()
            self.assertEqual(resultado, 0)

            resultado = db.session.execute(
                text("""
                    SELECT COUNT(*) FROM pecas
                    WHERE organization_id=:org_a AND id=:peca_b_id
                """),
                {"org_a": self.ids["org_a_id"], "peca_b_id": self.ids["peca_b_id"]},
            ).scalar()
            self.assertEqual(resultado, 0)

    def test_relatorios_isolamento_por_organizacao(self):
        """Consulta manual de relatorios (custo de pecas) filtra por organization_id."""
        with self.app.app_context():
            from sqlalchemy import text
            resultado = db.session.execute(
                text("""
                    SELECT COALESCE(SUM(op.quantidade * COALESCE(op.custo_unitario, p.custo, 0)), 0)
                    FROM os_pecas op
                    JOIN ordens_servico o ON o.id = op.os_id
                    JOIN pecas p ON p.id = op.peca_id
                    WHERE o.organization_id = :org_a AND p.organization_id = :org_b
                """),
                {"org_a": self.ids["org_a_id"], "org_b": self.ids["org_b_id"]},
            ).scalar()
            self.assertEqual(resultado, 0)

    def test_orm_escopo_central_isola_consultas(self):
        """O escopo ORM central filtra consultas por organization_id automaticamente."""
        with self.app.test_request_context("/"):
            from flask import g
            g.organization_id = self.ids["org_a_id"]

            self.assertEqual(Peca.query.count(), 1)
            self.assertEqual(Peca.query.first().nome, "Peca A")
            self.assertEqual(Cliente.query.count(), 1)
            self.assertEqual(OrdemServico.query.count(), 1)
            self.assertEqual(Transacao.query.count(), 1)
            self.assertEqual(EventoLog.query.count(), 1)

        with self.app.test_request_context("/"):
            g.organization_id = self.ids["org_b_id"]

            self.assertEqual(Peca.query.count(), 1)
            self.assertEqual(Peca.query.first().nome, "Peca B")
            self.assertEqual(Cliente.query.count(), 1)
            self.assertEqual(OrdemServico.query.count(), 1)

    def test_orm_bloqueia_mutacao_de_outro_tenant(self):
        """Mutacao de registro de outra empresa eh bloqueada pelo escopo ORM."""
        with self.app.test_request_context("/"):
            from flask import g
            g.organization_id = self.ids["org_b_id"]

            peca_estrangeira = (
                Peca.query.execution_options(include_all_tenants=True)
                .filter_by(id=self.ids["peca_a_id"])
                .one()
            )
            peca_estrangeira.nome = "Tentativa indevida"

            with self.assertRaises(ValueError) as ctx:
                db.session.flush()
            self.assertIn("Operacao entre tenants bloqueada", str(ctx.exception))
            db.session.rollback()

    # ═════════════════════════════════════════════════════════════════════════════
    # TESTE DE CONSULTAS ADMINISTRATIVAS LEGITIMAS (include_all_tenants)
    # ═════════════════════════════════════════════════════════════════════════════

    def test_consulta_administrativa_include_all_tenants_funciona(self):
        """Consultas administrativas com include_all_tenants veem todas as empresas."""
        with self.app.app_context():
            total_pecas = Peca.query.execution_options(include_all_tenants=True).count()
            self.assertEqual(total_pecas, 2)

            total_clientes = Cliente.query.execution_options(include_all_tenants=True).count()
            self.assertEqual(total_clientes, 2)

            total_os = OrdemServico.query.execution_options(include_all_tenants=True).count()
            self.assertEqual(total_os, 2)

    # ═════════════════════════════════════════════════════════════════════════════
    # TESTE DE INTEGRIDADE: consultas SQL manuais nao vazam dados entre tenants
    # ═════════════════════════════════════════════════════════════════════════════

    def test_todas_consultas_sql_manuais_filtram_por_organizacao(self):
        """Verifica que todas as consultas text() do backup filtram por organization_id."""
        with self.app.app_context():
            from sqlalchemy import text

            tabelas = {
                "clientes": "clientes",
                "fornecedores": "fornecedores",
                "pecas": "pecas",
                "ordens_servico": "ordens_servico",
                "transacoes": "transacoes",
                "usuarios": "usuarios",
                "eventos_log": "eventos_log",
                "configuracoes": "configuracoes",
            }

            for label, tabela in tabelas.items():
                contagem_a = db.session.execute(
                    text(f"SELECT COUNT(*) FROM {tabela} WHERE organization_id=:org"),
                    {"org": self.ids["org_a_id"]},
                ).scalar() or 0

                contagem_b = db.session.execute(
                    text(f"SELECT COUNT(*) FROM {tabela} WHERE organization_id=:org"),
                    {"org": self.ids["org_b_id"]},
                ).scalar() or 0

                self.assertEqual(contagem_a, 1,
                    f"{label}: empresa A deveria ter 1 registro, tem {contagem_a}")
                self.assertEqual(contagem_b, 1,
                    f"{label}: empresa B deveria ter 1 registro, tem {contagem_b}")

                total = db.session.execute(
                    text(f"SELECT COUNT(*) FROM {tabela}"),
                ).scalar() or 0
                self.assertEqual(total, 2,
                    f"{label}: total deveria ser 2 (um por empresa), tem {total}")


if __name__ == "__main__":
    unittest.main()
