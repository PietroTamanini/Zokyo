"""Testes de SEO para landing pages publicas - Etapa 10."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret_key_public_seo")

import unittest

from app import create_app
from app.extensions import db
from app.models import Organization, TenantSite
from app.services.tenant_site_service import update_site_config


def _make_app():
    app = create_app("development")
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    return app


class PublicLandingSeoTestCase(unittest.TestCase):
    """SEO individual por tenant (title, OG, canonical, JSON-LD, sitemap, robots)."""

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

    def test_landing_org_alpha_completa_meta_seo(self):
        with self.app.app_context():
            self._publicar(
                self.ids["org_a_id"],
                {
                    "site_name": "Empresa Alpha",
                    "seo_title": "Empresa Alpha | Tecnologia",
                    "seo_description": "Assistencia tecnica especializada.",
                    "seo_image": "https://exemplo.com/og.png",
                },
            )

        client = self.app.test_client()
        response = client.get("/", headers={"Host": "alpha.tamanini.dev.br"})
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("<title>Empresa Alpha | Tecnologia</title>", body)
        self.assertIn('property="og:title" content="Empresa Alpha | Tecnologia"', body)
        self.assertIn('property="og:description"', body)
        self.assertIn('property="og:image"', body)
        self.assertIn('name="twitter:card" content="summary_large_image"', body)
        self.assertIn('rel="canonical"', body)
        self.assertIn("application/ld+json", body)
        # Ambiente de teste deve ser bloqueado para indexacao
        self.assertIn("noindex, nofollow", body)

    def test_landing_org_beta_meta_seo_diferente(self):
        with self.app.app_context():
            self._publicar(
                self.ids["org_b_id"],
                {
                    "site_name": "Empresa Beta",
                    "seo_title": "Empresa Beta Solucoes",
                    "seo_description": "Notebooks e redes.",
                },
            )

        client = self.app.test_client()
        response = client.get("/", headers={"Host": "beta.tamanini.dev.br"})
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("<title>Empresa Beta Solucoes</title>", body)
        self.assertNotIn("Empresa Alpha", body)

    def test_sitemap_xml_individuo_por_tenant(self):
        client = self.app.test_client()
        response = client.get("/sitemap.xml", headers={"Host": "alpha.tamanini.dev.br"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/xml")
        self.assertIn("http://alpha.tamanini.dev.br/", response.get_data(as_text=True))

    def test_robots_txt_individuo_por_tenant(self):
        client = self.app.test_client()
        response = client.get("/robots.txt", headers={"Host": "alpha.tamanini.dev.br"})
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("User-agent: *", body)
        self.assertIn("Allow: /", body)
        self.assertIn("Disallow: /consulta-os", body)


if __name__ == "__main__":
    unittest.main()
