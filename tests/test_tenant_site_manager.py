"""Testes do gerenciador de sites publicos (modulo "Meu Site") - Etapa 06."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key-tenant-site-manager")

import unittest

from app import create_app
from app.extensions import db
from app.models import Organization, TenantSite
from app.services.domain_resolution import DomainResolutionError
from app.services.tenant_site_service import (
    TenantSiteError,
    get_or_create_site,
    get_site_content,
    update_site_config,
    update_tenant_subdomain,
)


def _make_app():
    app = create_app("development")
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    return app


class TenantSiteManagerTestCase(unittest.TestCase):
    """Conteudo do site publico, persistencia e configuracoes do tenant."""

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

            site_a = TenantSite(
                organization_id=org_a.id,
                site_enabled=True,
                custom_domain="alpha.empresa.com.br",
                custom_domain_validated=True,
            )
            site_b = TenantSite(
                organization_id=org_b.id,
                site_enabled=True,
                custom_domain="beta.empresa.com.br",
                custom_domain_validated=True,
            )
            db.session.add_all([site_a, site_b])
            db.session.commit()

    def test_atualizar_conteudo_publico_do_site(self):
        """Os campos do gerenciador sao persistidos e retornados no conteudo publico."""
        with self.app.app_context():
            update_site_config(
                self.ids["org_a_id"],
                {
                    "site_enabled": True,
                    "site_name": "Assistencia Alpha",
                    "tagline": "Tecnologia de qualidade",
                    "description": "Especialistas em informatica.",
                    "story": "Havíamos mais de 10 anos no mercado.",
                    "cover_image": "https://exemplo.com/capa.png",
                    "secondary_color": "#111111",
                    "services_json": '[{"nome": "Troca de tela"}]',
                    "socials_json": '{"instagram": "https://instagram.com/alpha"}',
                    "phone": "47999999999",
                    "whatsapp": "47999999998",
                    "address": "Joinville SC",
                    "hours": "Seg-Sex 8h-18h",
                    "seo_title": "Alpha - Assistencia Tecnica",
                    "seo_description": "Especialistas em informatica",
                    "seo_image": "https://exemplo.com/og.png",
                },
                current_user_id=1,
            )
            site = get_or_create_site(self.ids["org_a_id"])
            content = get_site_content(db.session.get(Organization, self.ids["org_a_id"]), site)

            self.assertEqual(content["name"], "Assistencia Alpha")
            self.assertEqual(content["tagline"], "Tecnologia de qualidade")
            self.assertEqual(content["description"], "Especialistas em informatica.")
            self.assertEqual(content["story"], "Havíamos mais de 10 anos no mercado.")
            self.assertEqual(content["services"], [{"nome": "Troca de tela"}])
            self.assertEqual(content["socials"]["instagram"], "https://instagram.com/alpha")
            self.assertEqual(content["phone"], "47999999999")
            self.assertEqual(content["whatsapp"], "47999999998")
            self.assertEqual(content["colors"]["secondary"], "#111111")
            self.assertEqual(content["seo"]["title"], "Alpha - Assistencia Tecnica")

    def test_conteudo_publico_reutiliza_dados_da_organizacao(self):
        """Campos vazios reutilizam os dados existentes da empresa (sem duplicar)."""
        with self.app.app_context():
            site = get_or_create_site(self.ids["org_b_id"])
            content = get_site_content(db.session.get(Organization, self.ids["org_b_id"]), site)
            self.assertEqual(content["name"], "Empresa Beta")
            self.assertEqual(content["tagline"], "beta")
            self.assertEqual(content["phone"], "")
            self.assertTrue(content["colors"]["primary"].startswith("#"))

    def test_atualizar_subdominio_valido_e_validacao_de_duplicidade(self):
        """Subdominio pode ser atualizado; duplicado entre empresas e rejeitado."""
        with self.app.app_context():
            organization = update_tenant_subdomain(self.ids["org_a_id"], "novo-site-alpha")
            self.assertEqual(organization.subdomain, "novo-site-alpha")

            with self.assertRaises(DomainResolutionError):
                update_tenant_subdomain(self.ids["org_b_id"], "novo-site-alpha")

            with self.assertRaises(Exception):
                update_tenant_subdomain(self.ids["org_b_id"], "-invalid-")

    def test_salvar_site_com_dominio_duplicado_gera_erro(self):
        """Dominio ja usado por outra empresa nao pode ser atribuido ao site."""
        with self.app.app_context():
            with self.assertRaises(TenantSiteError):
                update_site_config(
                    self.ids["org_b_id"],
                    {"custom_domain": "alpha.empresa.com.br", "site_enabled": True},
                    current_user_id=1,
                )


if __name__ == "__main__":
    unittest.main()
