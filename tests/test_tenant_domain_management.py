"""Testes do gerenciamento de dominios personalizados - Etapa 09."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key_tenant_domains")

import unittest

from app import create_app
from app.extensions import db
from app.models import Organization, TenantSite
from app.services.tenant_site_service import (
    TenantSiteError,
    get_domain_status,
    set_custom_domain,
    verify_custom_domain,
)


def _make_app():
    app = create_app("development")
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:", TENANT_DNS_MODE="manual")
    return app


class TenantDomainManagementTestCase(unittest.TestCase):
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

            site_a = TenantSite(organization_id=org_a.id, site_enabled=True, custom_domain="alpha.empresa.com.br", custom_domain_validated=True)
            site_b = TenantSite(organization_id=org_b.id, site_enabled=True, custom_domain="beta.empresa.com.br", custom_domain_validated=True)
            db.session.add_all([site_a, site_b])
            db.session.commit()

    def test_cadastro_de_dominio_duplicado_e_rejeitado(self):
        """Dominio ja usado por outra empresa nao pode ser atribuido."""
        with self.app.app_context():
            with self.assertRaises(TenantSiteError):
                set_custom_domain(self.ids["org_b_id"], "alpha.empresa.com.br")

    def test_cadastro_de_dominio_define_status_pendente(self):
        """Ao cadastrar novo dominio, status e pendente ate verificacao de DNS."""
        with self.app.app_context():
            site = set_custom_domain(self.ids["org_a_id"], "respawn.tec.br")
            db.session.commit()
            self.assertEqual(site.custom_domain, "respawn.tec.br")
            self.assertFalse(site.custom_domain_validated)
            self.assertEqual(get_domain_status(self.ids["org_a_id"]), "pending")

            # Simulando verificacao DNS bem-sucedida
            site.custom_domain_validated = True
            org = db.session.get(Organization, self.ids["org_a_id"])
            org.dns_status = "active"
            db.session.commit()
            self.assertEqual(get_domain_status(self.ids["org_a_id"]), "active")

            # Simulando falha de verificacao DNS
            org.dns_status = "error"
            db.session.commit()
            self.assertEqual(get_domain_status(self.ids["org_a_id"]), "error")

    def test_remocao_e_substiticao_de_dominio(self):
        """Remocao libera o dominio; substituicao exige novo dominio unico."""
        with self.app.app_context():
            site = set_custom_domain(self.ids["org_a_id"], None)
            db.session.commit()
            self.assertIsNone(site.custom_domain)
            self.assertEqual(get_domain_status(self.ids["org_a_id"]), "none")

            site = set_custom_domain(self.ids["org_a_id"], "alpha2.tec.br")
            db.session.commit()
            self.assertEqual(site.custom_domain, "alpha2.tec.br")
            self.assertFalse(site.custom_domain_validated)
            self.assertEqual(get_domain_status(self.ids["org_a_id"]), "pending")

    def test_verify_custom_domain_sem_configuracao_retorna_false(self):
        """Sem configuracao Cloudflare ativa, verificacao nao deve falhar indevidamente."""
        with self.app.app_context():
            ok = verify_custom_domain(self.ids["org_a_id"])
            self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
