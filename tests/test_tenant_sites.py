"""Testes de seguranca e resolucao do modulo de sites publicos por tenant (Etapa 05).

Cobre:
- Dominios validos e invalidos (hostname validation)
- Resolucao por subdominio (ex: alpha.tamanini.dev.br)
- Resolucao por dominio customizado validado (TenantSite.custom_domain)
- Rejeicao de dominio customizado nao validado
- Rejeicao de site desabilitado
- Duplicidade de dominio entre empresas
- Conflito de subdominio com base domain
- Empresas diferentes nao acessam ambientes umas das outras
"""
import os
import tempfile
import uuid

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key-tenant-sites")

import unittest

from app import create_app
from app.extensions import db
from app.models import Organization, TenantSite
from app.services.domain_resolution import (
    DomainResolutionError,
    is_valid_host,
    normalize_host,
    resolve_organization_from_host,
    validate_unique_domain,
)
from app.services.tenant_site_service import get_public_site_by_host


def _make_app():
    from config import config as config_map

    database_path = os.path.join(
        tempfile.gettempdir(), f"zokyo-tenant-sites-{os.getpid()}-{uuid.uuid4().hex}.sqlite"
    )
    development_config = config_map["development"]
    original_uri = development_config.SQLALCHEMY_DATABASE_URI
    development_config.SQLALCHEMY_DATABASE_URI = f"sqlite:///{database_path}"
    try:
        app = create_app("development")
    finally:
        development_config.SQLALCHEMY_DATABASE_URI = original_uri
    app.config.update(TESTING=True)
    app.config["TEST_DATABASE_PATH"] = database_path
    return app


class DomainNormalizationTestCase(unittest.TestCase):
    def test_normalize_host_remove_porta_minusculas_e_pontos_finais(self):
        self.assertEqual(normalize_host("Alpha.Tamanini.Dev.Br.:8080"), "alpha.tamanini.dev.br")
        self.assertEqual(normalize_host(""), "")

    def test_is_valid_host_aceita_hostname_normal(self):
        self.assertTrue(is_valid_host("alpha.tamanini.dev.br"))
        self.assertTrue(is_valid_host("tecnicasantos.empresa.com.br"))
        self.assertTrue(is_valid_host("localhost"))

    def test_is_valid_host_rejeita_host_com_espacos_ou_invalidos(self):
        self.assertFalse(is_valid_host("alpha_1.tamanini.dev.br"))
        self.assertFalse(is_valid_host("alpha .tamanini.dev.br"))
        self.assertFalse(is_valid_host("-alpha.tamanini.dev.br"))


class TenantSiteResolutionTestCase(unittest.TestCase):
    def setUp(self):
        self.app = _make_app()
        self.ids = {}
        with self.app.app_context():
            db.drop_all()
            db.create_all()

            org_a = Organization(id=1, nome="Empresa Alpha", slug="alpha", subdomain="alpha", ativo=True)
            org_b = Organization(id=2, nome="Empresa Beta", slug="beta", subdomain="beta", ativo=True)
            db.session.add_all([org_a, org_b])
            db.session.commit()
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

    def test_resolve_por_subdominio_valido(self):
        with self.app.app_context():
            org = resolve_organization_from_host("alpha.tamanini.dev.br", "tamanini.dev.br")
            self.assertIsNotNone(org)
            self.assertEqual(org.id, self.ids["org_a_id"])

            org_b = resolve_organization_from_host("beta.tamanini.dev.br", "tamanini.dev.br")
            self.assertIsNotNone(org_b)
            self.assertEqual(org_b.id, self.ids["org_b_id"])

    def test_resolve_host_da_base_domain_nao_retorna_org(self):
        with self.app.app_context():
            self.assertIsNone(resolve_organization_from_host("tamanini.dev.br", "tamanini.dev.br"))

    def test_resolve_subdominio_com_multiplos_labels_rejeitado(self):
        with self.app.app_context():
            self.assertIsNone(resolve_organization_from_host("a.b.tamanini.dev.br", "tamanini.dev.br"))

    def test_resolve_custom_domain_do_site_publico_validado(self):
        with self.app.app_context():
            org = resolve_organization_from_host("alpha.empresa.com.br", "tamanini.dev.br")
            self.assertIsNotNone(org)
            self.assertEqual(org.id, self.ids["org_a_id"])

    def test_resolve_custom_domain_nao_validado_retorna_none(self):
        with self.app.app_context():
            with self.app.test_request_context("/"):

                site = (
                    db.session.query(TenantSite)
                    .filter_by(custom_domain="gamma.empresa.com.br", custom_domain_validated=False)
                    .first()
                )
                if site is None:
                    site = db.session.query(TenantSite).filter_by(
                        organization_id=self.ids["org_a_id"]
                    ).first()
                    site.custom_domain = "gamma.empresa.com.br"
                    site.custom_domain_validated = False
                    db.session.commit()

            self.assertIsNone(resolve_organization_from_host("gamma.empresa.com.br", "tamanini.dev.br"))

    def test_resolve_site_publico_desabilitado_retorna_none(self):
        with self.app.app_context():
            site = (
                db.session.query(TenantSite)
                .filter_by(organization_id=self.ids["org_a_id"])
                .first()
            )
            site.site_enabled = False
            db.session.commit()

            org = resolve_organization_from_host("alpha.empresa.com.br", "tamanini.dev.br")
            self.assertIsNone(org)

            org_sub = resolve_organization_from_host("alpha.tamanini.dev.br", "tamanini.dev.br")
            self.assertIsNotNone(org_sub)
            self.assertEqual(org_sub.id, self.ids["org_a_id"])

    def test_get_public_site_by_host_retorna_org_e_site(self):
        with self.app.app_context():
            organization, site = get_public_site_by_host("alpha.tamanini.dev.br")
            self.assertIsNotNone(organization)
            self.assertEqual(organization.id, self.ids["org_a_id"])
            self.assertIsNotNone(site)
            self.assertTrue(site.site_enabled)

    def test_get_public_site_desabilitado_retorna_org_sem_site(self):
        with self.app.app_context():
            site = (
                db.session.query(TenantSite)
                .filter_by(organization_id=self.ids["org_a_id"])
                .first()
            )
            site.site_enabled = False
            db.session.commit()

            organization, site_ret = get_public_site_by_host("alpha.tamanini.dev.br")
            self.assertIsNotNone(organization)
            self.assertIsNone(site_ret)

    def test_empresa_diferente_nao_acessa_site_da_outra(self):
        with self.app.app_context():
            org_b = resolve_organization_from_host("beta.tamanini.dev.br", "tamanini.dev.br")
            self.assertIsNotNone(org_b)
            self.assertEqual(org_b.id, self.ids["org_b_id"])
            # Nunca deve retornar a organizacao A para o host da empresa B
            self.assertNotEqual(org_b.id, self.ids["org_a_id"])


class TenantDomainUniquenessTestCase(unittest.TestCase):
    def setUp(self):
        self.app = _make_app()
        with self.app.app_context():
            db.drop_all()
            db.create_all()
            org_a = Organization(id=1, nome="Empresa Alpha", slug="alpha", subdomain="alpha", custom_domain="alpha.empresa.com.br", ativo=True)
            org_b = Organization(id=2, nome="Empresa Beta", slug="beta", subdomain="beta", ativo=True)
            db.session.add_all([org_a, org_b])
            db.session.commit()
            self.ids = {"org_a_id": org_a.id, "org_b_id": org_b.id}

    def test_dominio_compartilhado_entre_empresas_e_rejeitado(self):
        with self.app.app_context():
            with self.assertRaises(DomainResolutionError):
                validate_unique_domain("alpha.empresa.com.br", organization_id=self.ids["org_b_id"], base_domain="tamanini.dev.br")

    def test_mesmo_organizacao_pode_manter_proprio_dominio(self):
        with self.app.app_context():
            hostname = validate_unique_domain("alpha.empresa.com.br", organization_id=self.ids["org_a_id"], base_domain="tamanini.dev.br")
            self.assertEqual(hostname, "alpha.empresa.com.br")

    def test_subdominio_em_uso_outro_org_e_rejeitado(self):
        with self.app.app_context():
            with self.assertRaises(DomainResolutionError):
                validate_unique_domain("beta.tamanini.dev.br", organization_id=self.ids["org_a_id"], base_domain="tamanini.dev.br")

    def test_dominio_invalido_e_rejeitado(self):
        with self.app.app_context():
            with self.assertRaises(DomainResolutionError):
                validate_unique_domain("alpha_1.!!invalido.com", organization_id=self.ids["org_a_id"], base_domain="tamanini.dev.br")


if __name__ == "__main__":
    unittest.main()
