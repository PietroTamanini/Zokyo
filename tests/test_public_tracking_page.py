"""Testes do portal publico de acompanhamento de OS (Etapa 08)."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key_public_tracking")

import unittest

from app import create_app
from app.extensions import db
from app.models import Cliente, OrdemServico, Organization, OSHistorico, TenantSite, Usuario
from app.models.ordem_servico import status_visual


def _make_app():
    app = create_app("development")
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    return app


class PublicTrackingStatusVisualTestCase(unittest.TestCase):
    def test_status_visual_mapeia_status_reais_para_labels_operacionais(self):
        visual = status_visual("recepcao")
        self.assertEqual(visual["label"], "Recebida")
        self.assertEqual(visual["etapa"], 1)

        visual = status_visual("em_analise")
        self.assertEqual(visual["label"], "Em diagnóstico")
        self.assertEqual(visual["etapa"], 2)

        visual = status_visual("aguardando_aprovacao")
        self.assertEqual(visual["label"], "Aguardando aprovação")
        self.assertEqual(visual["etapa"], 3)

        visual = status_visual("em_reparo")
        self.assertEqual(visual["label"], "Em manutenção")
        self.assertEqual(visual["etapa"], 4)

        visual = status_visual("pronto")
        self.assertEqual(visual["label"], "Pronta para retirada")
        self.assertEqual(visual["etapa"], 5)

        visual = status_visual("entregue")
        self.assertEqual(visual["label"], "Entregue")
        self.assertEqual(visual["etapa"], 6)

        visual = status_visual("cancelado")
        self.assertEqual(visual["etapa"], 0)

        visual = status_visual("status_inexistente")
        self.assertEqual(visual["label"], "status_inexistente")

    def test_status_visual_retorna_dict_com_label_e_destino(self):
        visual = status_visual("pronto")
        self.assertIn("label", visual)
        self.assertIn("destino", visual)
        self.assertIn("etapa", visual)


class PublicTrackingPageRenderTestCase(unittest.TestCase):
    """Renderizacao publica do portal /consulta-os por tenant."""

    def setUp(self):
        self.app = _make_app()
        self.ids = {}
        with self.app.app_context():
            db.drop_all()
            db.create_all()

            org_a = Organization(id=1, nome="Empresa Alpha", slug="alpha", subdomain="alpha", ativo=True)
            org_b = Organization(id=2, nome="Empresa Beta", slug="beta", subdomain="beta", ativo=True)
            db.session.add_all([org_a, org_b])
            db.session.flush()
            self.ids["org_a_id"] = org_a.id
            self.ids["org_b_id"] = org_b.id

            site_a = TenantSite(organization_id=org_a.id, site_enabled=True)
            site_b = TenantSite(organization_id=org_b.id, site_enabled=True)
            db.session.add_all([site_a, site_b])
            db.session.commit()

    def test_portal_renderiza_para_org_alpha(self):
        client = self.app.test_client()
        response = client.get("/consulta-os", headers={"Host": "alpha.tamanini.dev.br"})
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("Consulta", body)
        self.assertIn("numero", body.lower())
        self.assertIn("Empresa Alpha", body)

    def test_portal_renderiza_para_org_beta_sem_vazar_conteudo_alpha(self):
        client = self.app.test_client()
        response = client.get("/consulta-os", headers={"Host": "beta.tamanini.dev.br"})
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("Consulta", body)
        self.assertIn("Empresa Beta", body)
        self.assertNotIn("Empresa Alpha", body)

    def test_portal_sem_tenant_retorna_404(self):
        client = self.app.test_client()
        response = client.get("/consulta-os", headers={"Host": "desconhecida.tamanini.dev.br"})
        self.assertEqual(response.status_code, 404)


class PublicTrackingAPISyncTestCase(unittest.TestCase):
    """Integracao com a API segura /api/public/os-consulta (logica existente)."""

    def setUp(self):
        self.app = _make_app()
        with self.app.app_context():
            db.drop_all()
            db.create_all()
            org = Organization(id=1, nome="Empresa Alpha", slug="alpha", subdomain="alpha", ativo=True)
            db.session.add(org)
            db.session.flush()
            usuario = Usuario(organization_id=1, nome="Tecnico", email="tec@example.com", nivel="admin", ativo=True)
            usuario.set_senha("Senha!123")
            db.session.add(usuario)
            db.session.flush()
            cliente = Cliente(organization_id=1, nome="Cliente Alpha", cpf="12345678909")
            db.session.add(cliente)
            db.session.flush()
            ordem = OrdemServico(
                organization_id=1,
                numero=2668,
                cliente_id=cliente.id,
                usuario_id=usuario.id,
                tipo_aparelho="Notebook",
                marca="Dell",
                modelo="XPS",
                status="em_reparo",
                orcamento_status="aprovado",
                valor_servico=150,
                valor_pecas=50,
                desconto=10,
                garantia_dias=90,
            )
            db.session.add(ordem)
            db.session.flush()
            historico = OSHistorico(
                organization_id=1,
                os_id=ordem.id,
                status_anterior="recepcao",
                status_novo="em_reparo",
            )
            db.session.add(historico)
            db.session.commit()

    def test_api_publica_retorna_timeline_e_orcamento(self):
        client = self.app.test_client()
        response = client.post(
            "/api/public/os-consulta",
            json={"numero": "2668", "documento": "123.456.789-09"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["status"])
        resultado = payload["result"]
        self.assertEqual(resultado["status"], "em_reparo")
        self.assertEqual(resultado["orcamento_status"], "aprovado")
        self.assertIn("status_label", resultado)
        self.assertIn("status_visual", resultado)
        self.assertIn("timeline", resultado)
        self.assertIsInstance(resultado["timeline"], list)
        self.assertEqual(len(resultado["timeline"]), 1)
        self.assertEqual(resultado["timeline"][0]["status_novo"], "em_reparo")
        self.assertEqual(resultado["status_visual"]["etapa"], 4)


if __name__ == "__main__":
    unittest.main()
