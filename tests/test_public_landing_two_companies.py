"""Testes de renderizacao de landing pages publicas - Etapa 07.

Cria duas empresas com sites publicos distintos e verifica a renderizacao.
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key-public_landing")

import unittest

from app import create_app
from app.extensions import db
from app.models import Organization, TenantSite
from app.services.tenant_site_service import update_site_config


def _make_app():
    app = create_app("development")
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    return app


class PublicLandingTwoCompaniesTestCase(unittest.TestCase):
    """Renderizacao publica de duas landing pages diferentes."""

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

    def _publicar(self, organization_id: int, data: dict):
        update_site_config(
            organization_id,
            {
                "site_enabled": True,
                **data,
            },
            current_user_id=1,
        )
        db.session.commit()

    def _get_public_site(self, app, host: str):
        client = app.test_client()
        response = client.get("/", headers={"Host": host})
        return response

    def test_landing_da_empresa_alpha_renderiza_conteudo_diferente_da_empresa_beta(self):
        """Cada empresa renderiza sua propria landing page com conteudo separado."""
        with self.app.app_context():
            self._publicar(
                self.ids["org_a_id"],
                {
                    "site_name": "Assistencia Alpha",
                    "tagline": "Especialistas em hardware",
                    "description": "Assistencia tecnica especializada em hardware.",
                    "story": "Havíamos mais de 10 anos atendendo o mercado.",
                    "services_json": '[{"nome": "Troca de tela", "descricao": "Tela quebrada"}]',
                    "diferencias_json": '[{"nome": "Atendimento especializado"}]',
                    "phone": "47999999999",
                    "whatsapp": "47999999999",
                    "hours": "Seg-Sex 8h-18h",
                },
            )

        response = self._get_public_site(self.app, "alpha.tamanini.dev.br")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("Assistencia Alpha", body)
        self.assertNotIn("Empresa Beta", body)

    def test_landing_da_empresa_beta_renderiza_conteudo_diferente_da_empresa_alpha(self):
        """Conteudo da empresa Beta nao vaza na landing da empresa Alpha."""
        with self.app.app_context():
            self._publicar(
                self.ids["org_b_id"],
                {
                    "site_name": "Tecnica Beta",
                    "tagline": "Notebooks e redes",
                    "description": "Suporte em notebooks e redes.",
                    "story": "Atendemos redes locais e redes.",
                },
            )

        response = self._get_public_site(self.app, "beta.tamanini.dev.br")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("Tecnica Beta", body)
        self.assertNotIn("Assistencia Alpha", body)

    def test_landing_oculta_secoes_quando_conteudo_nao_preenchido(self):
        """Secoes sem conteudo nao sao renderizadas (sem dados ficticios)."""
        response = self._get_public_site(self.app, "alpha.tamanini.dev.br")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        # Org A nao publicou servicos/diferencas -> secoes devem ficar ocultas
        self.assertNotIn("Nossos serviços", body)
        self.assertNotIn("Diferenciais", body)
        # Sem contato preenchido, a secao de contato tambem deve ficar oculta
        self.assertNotIn('id="contato"', body)

    def test_landing_renderiza_secoes_quando_preenchidas(self):
        """Com conteudo publicado, as secoes esperadas aparecem."""
        with self.app.app_context():
            self._publicar(
                self.ids["org_a_id"],
                {
                    "site_name": "Assistencia Alpha",
                    "description": "Assistencia tecnica especializada em hardware.",
                    "services_json": '[{"nome": "Troca de tela", "descricao": "Tela quebrada"}]',
                    "diferencias_json": '[{"nome": "Atendimento especializado"}]',
                    "phone": "47999999999",
                    "whatsapp": "47999999999",
                    "address": "Joinville SC",
                    "hours": "Seg-Sex 8h-18h",
                },
            )

        response = self._get_public_site(self.app, "alpha.tamanini.dev.br")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("Nossos serviços", body)
        self.assertIn("Diferenciais", body)
        self.assertIn("Contato", body)
        self.assertIn("Joinville SC", body)


if __name__ == "__main__":
    unittest.main()
