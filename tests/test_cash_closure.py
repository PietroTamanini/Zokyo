"""Testes do modulo de fechamento de caixa - Etapa 11.

Cobre:
- Abertura de caixa e idempotencia.
- Movimentacoes de entrada/saida/sangria/suprimento.
- Calculo do valor esperado e conferencia no fechamento.
- Bloqueio de fechamento duplicado.
- Validacoes de movimentacao.
- Isolamento multi-tenant.
- Auditoria do fechamento.
- Endpoints API de caixa.
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key_cash_closure")

import unittest

from app import create_app
from app.extensions import db
from app.models import EventoLog, Organization, Usuario
from app.services import cash as cash_service


def _make_app():
    app = create_app("development")
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    return app


def _make_orgs(app):
    with app.app_context():
        db.drop_all()
        db.create_all()
        org_a = Organization(id=1, nome="Empresa Alpha", slug="alpha", subdomain="alpha", ativo=True)
        org_b = Organization(id=2, nome="Empresa Beta", slug="beta", subdomain="beta", ativo=True)
        db.session.add_all([org_a, org_b])
        db.session.flush()
        user = Usuario(organization_id=org_a.id, nome="Gerente", email="gerente@alpha.test", nivel="admin", ativo=True)
        user.set_senha("Senha!123")
        db.session.add(user)
        db.session.commit()
        return {"org_a_id": org_a.id, "org_b_id": org_b.id, "user_id": user.id}


class CashClosureServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.app = _make_app()
        self.ids = _make_orgs(self.app)

    def test_abertura_de_caixa_e_idempotencia(self):
        with self.app.app_context():
            session_obj = cash_service.open_caixa(self.ids["org_a_id"], saldo_inicial=150.0, responsavel_id=self.ids["user_id"])
            self.assertEqual(session_obj.status, "aberto")
            self.assertEqual(float(session_obj.saldo_inicial), 150.0)

            again = cash_service.open_caixa(self.ids["org_a_id"], saldo_inicial=150.0)
            self.assertEqual(again.id, session_obj.id)

    def test_movimentacoes_acumulam_no_fechamento(self):
        with self.app.app_context():
            session_obj = cash_service.open_caixa(self.ids["org_a_id"], saldo_inicial=100.0)
            cash_service.add_caixa_movimento(self.ids["org_a_id"], session_obj.id, "entrada", 50.0)
            cash_service.add_caixa_movimento(self.ids["org_a_id"], session_obj.id, "saida", 20.0)
            cash_service.add_caixa_movimento(self.ids["org_a_id"], session_obj.id, "sangria", 10.0)
            cash_service.add_caixa_movimento(self.ids["org_a_id"], session_obj.id, "suprimento", 30.0)

            resumo = cash_service.caixa_resumo(self.ids["org_a_id"], sessao_id=session_obj.id)
            self.assertEqual(resumo["status"], "aberto")
            self.assertEqual(resumo["saldo_inicial"], 100.0)
            self.assertEqual(resumo["entradas"], 50.0)
            self.assertEqual(resumo["saidas"], 20.0)
            self.assertEqual(resumo["sangrias"], 10.0)
            self.assertEqual(resumo["suprimentos"], 30.0)
            # esperado = saldo_inicial + entradas - saidas - sangrias + suprimentos
            self.assertEqual(resumo["valor_fechado_esperado"], 150.0)

    def test_fechar_caixa_registra_conferencia_e_diferenca(self):
        with self.app.app_context():
            session_obj = cash_service.open_caixa(self.ids["org_a_id"], saldo_inicial=100.0)
            cash_service.add_caixa_movimento(self.ids["org_a_id"], session_obj.id, "entrada", 50.0)
            fechada = cash_service.close_caixa(self.ids["org_a_id"], session_obj.id, valor_conferido=160.0)
            self.assertEqual(fechada.status, "fechado")
            self.assertEqual(float(fechada.valor_fechado_esperado), 150.0)
            self.assertEqual(float(fechada.valor_conferido), 160.0)
            self.assertEqual(float(fechada.diferenca), 10.0)
            with self.assertRaises(ValueError):
                cash_service.close_caixa(self.ids["org_a_id"], session_obj.id, valor_conferido=160.0)

    def test_movimento_invalido_e_sem_sessao_rejeitados(self):
        with self.app.app_context():
            session_obj = cash_service.open_caixa(self.ids["org_a_id"], saldo_inicial=0.0)
            with self.assertRaises(ValueError):
                cash_service.add_caixa_movimento(self.ids["org_a_id"], session_obj.id, "tipo_invalido", 10.0)
            with self.assertRaises(ValueError):
                cash_service.add_caixa_movimento(self.ids["org_a_id"], session_obj.id, "entrada", 0.0)
            with self.assertRaises(ValueError):
                cash_service.add_caixa_movimento(self.ids["org_a_id"], session_obj.id, "entrada", -5.0)
            with self.assertRaises(ValueError):
                cash_service.add_caixa_movimento(self.ids["org_a_id"], 9999, "entrada", 10.0)

    def test_isolamento_multi_tenant_do_fechamento(self):
        with self.app.app_context():
            session_a = cash_service.open_caixa(self.ids["org_a_id"], saldo_inicial=50.0)
            session_b = cash_service.open_caixa(self.ids["org_b_id"], saldo_inicial=70.0)
            cash_service.add_caixa_movimento(self.ids["org_a_id"], session_a.id, "entrada", 25.0)
            cash_service.add_caixa_movimento(self.ids["org_b_id"], session_b.id, "saida", 15.0)

            resumo_a = cash_service.caixa_resumo(self.ids["org_a_id"], sessao_id=session_a.id)
            resumo_b = cash_service.caixa_resumo(self.ids["org_b_id"], sessao_id=session_b.id)
            self.assertEqual(resumo_a["saldo_inicial"], 50.0)
            self.assertEqual(resumo_a["entradas"], 25.0)
            self.assertEqual(resumo_b["saldo_inicial"], 70.0)
            self.assertEqual(resumo_b["saidas"], 15.0)

    def test_fechamento_gera_evento_de_auditoria(self):
        with self.app.app_context():
            session_obj = cash_service.open_caixa(self.ids["org_a_id"], saldo_inicial=0.0)
            cash_service.close_caixa(self.ids["org_a_id"], session_obj.id, valor_conferido=0.0)
            eventos = EventoLog.query.filter_by(modulo="financeiro", tipo="fechamento").all()
            self.assertEqual(len(eventos), 1)
            self.assertEqual(eventos[0].organization_id, self.ids["org_a_id"])


class CashClosureApiTestCase(unittest.TestCase):
    def setUp(self):
        self.app = _make_app()
        self.ids = _make_orgs(self.app)
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session["usuario_id"] = self.ids["user_id"]
            session["nivel"] = "admin"
            session["perfil"] = "admin"
            session["usuario_nome"] = "Gerente"
            session["_last_active"] = 9999999999
            session["_csrf_token"] = "csrf-caixa"

    def _json(self, method, path, payload=None):
        return self.client.open(method=method, path=path, json=payload, headers={"X-CSRFToken": "csrf-caixa"})

    def test_fluxo_abrir_movimentar_fechar_caixa(self):
        opened = self._json("POST", "/api/cash/sessoes/abrir", {"saldo_inicial": 100.0})
        self.assertEqual(opened.status_code, 201)
        sessao_id = opened.get_json()["sessao"]["id"]

        mov = self._json("POST", "/api/cash/movimentos", {"tipo": "entrada", "valor": 50.0})
        self.assertEqual(mov.status_code, 201)

        closed = self._json("POST", f"/api/cash/sessoes/{sessao_id}/fechar", {"valor_conferido": 150.0})
        self.assertEqual(closed.status_code, 200)
        self.assertEqual(closed.get_json()["sessao"]["status"], "fechado")

        again = self._json("POST", f"/api/cash/sessoes/{sessao_id}/fechar", {"valor_conferido": 150.0})
        self.assertEqual(again.status_code, 409)

        listing = self._json("GET", "/api/cash/sessoes")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(len(listing.get_json()["sessoes"]), 1)

    def test_movimento_sem_caixa_aberta_retorna_conflict(self):
        response = self._json("POST", "/api/cash/movimentos", {"tipo": "entrada", "valor": 10.0})
        self.assertEqual(response.status_code, 409)

    def test_relatorio_de_caixa(self):
        self._json("POST", "/api/cash/sessoes/abrir", {"saldo_inicial": 100.0})
        self._json("POST", "/api/cash/movimentos", {"tipo": "saida", "valor": 20.0})
        relatorio = self._json("GET", "/api/cash/relatorio", None)
        self.assertEqual(relatorio.status_code, 200)
        body = relatorio.get_json()
        self.assertEqual(body["status"], "aberto")
        self.assertEqual(body["saldo_inicial"], 100.0)
        self.assertEqual(body["saidas"], 20.0)


class CashClosurePermissionTestCase(unittest.TestCase):
    def setUp(self):
        self.app = _make_app()
        self.ids = _make_orgs(self.app)
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session["usuario_id"] = self.ids["user_id"]
            session["nivel"] = "consulta"
            session["perfil"] = "consulta"
            session["usuario_nome"] = "Leitor"
            session["_last_active"] = 9999999999
            session["_csrf_token"] = "csrf-caixa"

    def _json(self, method, path, payload=None):
        return self.client.open(method=method, path=path, json=payload, headers={"X-CSRFToken": "csrf-caixa"})

    def test_usuario_sem_permissao_nao_fecha_caixa(self):
        with self.app.app_context():
            session_obj = cash_service.open_caixa(self.ids["org_a_id"], saldo_inicial=0.0)
        response = self._json("POST", f"/api/cash/sessoes/{session_obj.id}/fechar", {"valor_conferido": 0.0})
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
