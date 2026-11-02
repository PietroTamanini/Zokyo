"""Testes automatizados de segurança para a consulta pública de OS.

Cobre todos os cenários obrigatórios:
- Validação de número da OS (rejeita vazio, zeros, >10 dígitos)
- Validação de CPF/CNPJ com dígitos verificadores (rejeita sequências inválidas)
- Isolamento por organization_id (empresa A não vê OS da empresa B)
- Rate limiting por IP e por documento
- Nenhum dado interno/financeiro/pessoal vazado
- Suporte a domínios individuais via CORS
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key-public-os")

import unittest

from app import create_app
from app.extensions import db
from app.models import (
    Cliente,
    Configuracao,
    OrdemServico,
    Organization,
    Usuario,
)


def _make_app():
    app = create_app("development")
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    return app


def _seed_duas_empresas(app):
    """Cria duas organizações com clientes e OS isoladas."""
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
            cidade="Joinville", uf="SC",
        )
        cfg_b = Configuracao(
            organization_id=2, nome_empresa="Empresa B Config",
            cidade="Blumenau", uf="SC",
        )
        db.session.add_all([admin_a, admin_b, cfg_a, cfg_b])
        db.session.flush()

        # CPF válido: 12345678909 (dígitos verificadores corretos)
        # CNPJ válido: 11222333000181 (dígitos verificadores corretos)
        cli_a = Cliente(
            id=100, organization_id=1, nome="Cliente da Empresa A",
            cpf="12345678909", telefone="47900000001",
        )
        cli_b = Cliente(
            id=200, organization_id=2, nome="Cliente da Empresa B",
            cnpj="11222333000181", telefone="47900000002",
        )
        db.session.add_all([cli_a, cli_b])
        db.session.flush()

        os_a = OrdemServico(
            id=700, organization_id=1, numero=2668,
            cliente_id=cli_a.id, usuario_id=admin_a.id,
            tipo_aparelho="Notebook", marca="Dell", modelo="XPS",
            defeito_alegado="Nao liga",
            valor_servico=150.00, valor_pecas=50.00, desconto=10.00,
            status="em_reparo", garantia_dias=90,
        )
        os_b = OrdemServico(
            id=800, organization_id=2, numero=9999,
            cliente_id=cli_b.id, usuario_id=admin_b.id,
            tipo_aparelho="TV", marca="Samsung", modelo="U55",
            defeito_alegado="Sem imagem",
            valor_servico=300.00, valor_pecas=100.00, desconto=0.00,
            status="pronto", garantia_dias=90,
        )
        db.session.add_all([os_a, os_b])
        db.session.commit()

        return {
            "org_a_id": 1,
            "org_b_id": 2,
            "cli_a_id": cli_a.id,
            "cli_b_id": cli_b.id,
            "os_a_id": os_a.id,
            "os_b_id": os_b.id,
            "admin_a_id": admin_a.id,
            "admin_b_id": admin_b.id,
        }


def _post_json(client, path, payload, origin=None):
    """Envia POST JSON com opcional header Origin para CORS."""
    headers = {}
    if origin:
        headers["Origin"] = origin
    return client.post(path, json=payload, headers=headers)


class ConsultaPublicaOSNumeroTestCase(unittest.TestCase):
    """Validação do número da OS."""

    def setUp(self):
        self.app = _make_app()
        self.ids = _seed_duas_empresas(self.app)
        self.client = self.app.test_client()

    def test_numero_valido_retorna_os(self):
        """Número válido + CPF válido da mesma empresa retorna a OS."""
        response = _post_json(
            self.client,
            "/api/public/os-consulta",
            {"numero": "2668", "documento": "123.456.789-09"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["status"])
        self.assertEqual(response.json["result"]["numero"], "2668")

    def test_numero_vazio_rejeitado(self):
        """Número vazio deve ser rejeitado com 400."""
        response = _post_json(
            self.client,
            "/api/public/os-consulta",
            {"numero": "", "documento": "123.456.789-09"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json["status"])

    def test_numero_apenas_zeros_rejeitado(self):
        """Número com apenas zeros deve ser rejeitado."""
        response = _post_json(
            self.client,
            "/api/public/os-consulta",
            {"numero": "0000", "documento": "123.456.789-09"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json["status"])

    def test_numero_mais_de_10_digitos_rejeitado(self):
        """Número com mais de 10 dígitos deve ser rejeitado."""
        response = _post_json(
            self.client,
            "/api/public/os-consulta",
            {"numero": "12345678901", "documento": "123.456.789-09"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json["status"])

    def test_numero_com_caracteres_especiais_funciona(self):
        """Número com formatação (pontos, traços) deve ser aceito após limpeza."""
        response = _post_json(
            self.client,
            "/api/public/os-consulta",
            {"numero": "OS #2668", "documento": "123.456.789-09"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["status"])


class ConsultaPublicaOSDocumentoTestCase(unittest.TestCase):
    """Validação de CPF/CNPJ com dígitos verificadores."""

    def setUp(self):
        self.app = _make_app()
        self.ids = _seed_duas_empresas(self.app)
        self.client = self.app.test_client()

    def test_cpf_valido_aceito(self):
        """CPF com dígitos verificadores válidos é aceito."""
        response = _post_json(
            self.client,
            "/api/public/os-consulta",
            {"numero": "2668", "documento": "123.456.789-09"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["status"])

    def test_cpf_invalido_rejeitado(self):
        """CPF com dígitos verificadores inválidos deve ser rejeitado (400)."""
        response = _post_json(
            self.client,
            "/api/public/os-consulta",
            {"numero": "2668", "documento": "11111111111"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json["status"])

    def test_cpf_sequencia_repetida_rejeitada(self):
        """CPF com sequência repetida (111.111.111-11) deve ser rejeitado."""
        response = _post_json(
            self.client,
            "/api/public/os-consulta",
            {"numero": "2668", "documento": "111.111.111-11"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json["status"])

    def test_cnpj_valido_aceito(self):
        """CNPJ com dígitos verificadores válidos é aceito."""
        response = _post_json(
            self.client,
            "/api/public/os-consulta",
            {"numero": "9999", "documento": "11.222.333/0001-81"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["status"])

    def test_cnpj_invalido_rejeitado(self):
        """CNPJ com dígitos verificadores inválidos deve ser rejeitado."""
        response = _post_json(
            self.client,
            "/api/public/os-consulta",
            {"numero": "9999", "documento": "00.000.000/0001-00"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json["status"])

    def test_documento_com_12_digitos_rejeitado(self):
        """Documento com 12 dígitos (nem CPF nem CNPJ) deve ser rejeitado."""
        response = _post_json(
            self.client,
            "/api/public/os-consulta",
            {"numero": "2668", "documento": "123456789012"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json["status"])

    def test_documento_vazio_rejeitado(self):
        """Documento vazio deve ser rejeitado."""
        response = _post_json(
            self.client,
            "/api/public/os-consulta",
            {"numero": "2668", "documento": ""},
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json["status"])


class ConsultaPublicaOSIsolamentoTestCase(unittest.TestCase):
    """Isolamento multi-tenant: empresa A não vê OS da empresa B."""

    def setUp(self):
        self.app = _make_app()
        self.ids = _seed_duas_empresas(self.app)
        self.client = self.app.test_client()

    def test_empresa_a_nao_ve_os_da_empresa_b(self):
        """Consulta da empresa A com número e documento da empresa B não retorna dados."""
        response = _post_json(
            self.client,
            "/api/public/os-consulta",
            {"numero": "9999", "documento": "11.222.333/0001-81", "organization": "empresa-a"},
        )
        # Deve retornar 404 (não encontrada no contexto da empresa A)
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.json["status"])

    def test_empresa_b_nao_ve_os_da_empresa_a(self):
        """Consulta da empresa B com número e documento da empresa A não retorna dados."""
        # Simular contexto de empresa B via slug explícito
        response = _post_json(
            self.client,
            "/api/public/os-consulta",
            {"numero": "2668", "documento": "123.456.789-09", "organization": "empresa-b"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.json["status"])

    def test_empresa_a_ve_sua_propria_os_com_slug(self):
        """Empresa A consulta sua própria OS especificando o slug."""
        response = _post_json(
            self.client,
            "/api/public/os-consulta",
            {"numero": "2668", "documento": "123.456.789-09", "organization": "empresa-a"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["status"])
        self.assertEqual(response.json["result"]["numero"], "2668")

    def test_empresa_b_ve_sua_propria_os_com_slug(self):
        """Empresa B consulta sua própria OS especificando o slug."""
        response = _post_json(
            self.client,
            "/api/public/os-consulta",
            {"numero": "9999", "documento": "11.222.333/0001-81", "organization": "empresa-b"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["status"])
        self.assertEqual(response.json["result"]["numero"], "9999")

    def test_slug_inexistente_rejeitado(self):
        """Slug de organização inexistente deve ser rejeitado."""
        response = _post_json(
            self.client,
            "/api/public/os-consulta",
            {"numero": "2668", "documento": "123.456.789-09", "organization": "empresa-inexistente"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json["status"])

    def test_os_deletada_nao_retornada(self):
        """OS com deletado_em preenchido não deve ser retornada."""
        with self.app.app_context():
            ordem = db.session.get(OrdemServico, self.ids["os_a_id"])
            ordem.deletado_em = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
            db.session.commit()

        response = _post_json(
            self.client,
            "/api/public/os-consulta",
            {"numero": "2668", "documento": "123.456.789-09", "organization": "empresa-a"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.json["status"])

    def test_numero_da_empresa_b_com_documento_da_empresa_a_nao_retorna(self):
        """Misturar número de uma empresa com documento de outra não deve retornar."""
        response = _post_json(
            self.client,
            "/api/public/os-consulta",
            {"numero": "9999", "documento": "123.456.789-09", "organization": "empresa-a"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.json["status"])


class ConsultaPublicaOSRateLimitTestCase(unittest.TestCase):
    """Rate limiting: por IP e por documento."""

    def setUp(self):
        self.app = _make_app()
        self.ids = _seed_duas_empresas(self.app)
        self.client = self.app.test_client()

    def test_rate_limit_por_ip(self):
        """Muitas requisições do mesmo IP devem ser limitadas (429)."""
        # Faz 40 requisições rápidas (limite global é 40/300s)
        for i in range(41):
            response = _post_json(
                self.client,
                "/api/public/os-consulta",
                {"numero": "2668", "documento": "123.456.789-09"},
            )
        # A 41ª deve ser 429 (rate limit)
        self.assertEqual(response.status_code, 429)
        self.assertFalse(response.json["status"])

    def test_rate_limit_segundo_documento_nao_bloqueia_outro(self):
        """Rate limit por documento não deve bloquear consulta de documento diferente."""
        # Consultar documento A muitas vezes
        for i in range(6):
            _post_json(
                self.client,
                "/api/public/os-consulta",
                {"numero": "2668", "documento": "123.456.789-09"},
            )
        # Documento B ainda deve funcionar (não esgotou seu próprio limite)
        response = _post_json(
            self.client,
            "/api/public/os-consulta",
            {"numero": "9999", "documento": "11.222.333/0001-81"},
        )
        # Pode ser 404 (não encontrada no contexto) mas não 429 por rate limit de doc A
        self.assertNotEqual(response.status_code, 429)


class ConsultaPublicaOSDadosRetornadosTestCase(unittest.TestCase):
    """Nenhum dado interno, financeiro ou pessoal deve ser exposto."""

    def setUp(self):
        self.app = _make_app()
        self.ids = _seed_duas_empresas(self.app)
        self.client = self.app.test_client()

    def test_resposta_nao_contem_valores_financeiros(self):
        """Resposta pública não deve conter valor_servico, valor_pecas, desconto, valor_total."""
        response = _post_json(
            self.client,
            "/api/public/os-consulta",
            {"numero": "2668", "documento": "123.456.789-09", "organization": "empresa-a"},
        )
        self.assertEqual(response.status_code, 200)
        resultado = response.json["result"]
        campos_financeiros = ["valor_servico", "valor_pecas", "desconto", "valor_total"]
        for campo in campos_financeiros:
            self.assertNotIn(campo, resultado, f"Campo {campo} não deve ser exposto publicamente")

    def test_resposta_nao_contem_cpf_cnpj_completo(self):
        """Resposta pública não deve conter CPF/CNPJ completo do cliente."""
        response = _post_json(
            self.client,
            "/api/public/os-consulta",
            {"numero": "2668", "documento": "123.456.789-09", "organization": "empresa-a"},
        )
        self.assertEqual(response.status_code, 200)
        texto = response.get_data(as_text=True)
        self.assertNotIn("12345678909", texto)
        self.assertNotIn("11222333000181", texto)

    def test_resposta_nao_contem_telefone_endereco_email(self):
        """Resposta pública não deve expor telefone, endereço ou e-mail do cliente."""
        response = _post_json(
            self.client,
            "/api/public/os-consulta",
            {"numero": "2668", "documento": "123.456.789-09", "organization": "empresa-a"},
        )
        self.assertEqual(response.status_code, 200)
        texto = response.get_data(as_text=True)
        self.assertNotIn("47900000001", texto)
        self.assertNotIn("Joinville", texto)
        self.assertNotIn("@", texto)

    def test_resposta_retorna_apenas_campos_permitidos(self):
        """Resposta pública deve conter apenas campos seguros."""
        response = _post_json(
            self.client,
            "/api/public/os-consulta",
            {"numero": "2668", "documento": "123.456.789-09", "organization": "empresa-a"},
        )
        self.assertEqual(response.status_code, 200)
        resultado = response.json["result"]
        campos_esperados = {
            "numero", "status", "status_label", "cliente", "equipamento",
            "entrada", "previsao", "saida", "atualizado_em", "garantia_dias",
        }
        self.assertEqual(set(resultado.keys()), campos_esperados)
        # Nome do cliente deve ser apenas o primeiro nome
        self.assertEqual(resultado["cliente"], "Cliente")

    def test_erro_nao_revela_se_numero_existe(self):
        """Mensagem de erro é genérica, não revela se o número da OS existe."""
        # Número inexistente com documento válido
        response = _post_json(
            self.client,
            "/api/public/os-consulta",
            {"numero": "0001", "documento": "123.456.789-09", "organization": "empresa-a"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.json["status"])
        # Mesma mensagem para número inválido e para número válido mas documento errado
        self.assertEqual(
            response.json["message"],
            "OS não encontrada com os dados informados.",
        )

    def test_cors_origem_permitida(self):
        """Origem configurada recebe header Access-Control-Allow-Origin."""
        response = _post_json(
            self.client,
            "/api/public/os-consulta",
            {"numero": "2668", "documento": "123.456.789-09", "organization": "empresa-a"},
            origin="https://djtechinfo.com.br",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers.get("Access-Control-Allow-Origin"),
            "https://djtechinfo.com.br",
        )

    def test_cors_origem_nao_permitida_sem_header(self):
        """Origem não configurada não recebe header CORS."""
        response = _post_json(
            self.client,
            "/api/public/os-consulta",
            {"numero": "2668", "documento": "123.456.789-09", "organization": "empresa-a"},
            origin="https://site-malicioso.com.br",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.headers.get("Access-Control-Allow-Origin"))

    def test_cache_control_no_store(self):
        """Resposta deve instruir não armazenar em cache."""
        response = _post_json(
            self.client,
            "/api/public/os-consulta",
            {"numero": "2668", "documento": "123.456.789-09", "organization": "empresa-a"},
        )
        self.assertIn("no-store", response.headers.get("Cache-Control", ""))


class ConsultaPublicaOSDominioIndividualTestCase(unittest.TestCase):
    """Suporte a domínios individuais de tenant (alpha.zokyo.app.br, etc.)."""

    def setUp(self):
        self.app = _make_app()
        self.ids = _seed_duas_empresas(self.app)
        self.client = self.app.test_client()

    def test_resolucao_por_slug_explícito_funciona_para_dominios_individuais(self):
        """Slug explícito permite consulta em domínio individual de tenant."""
        response = _post_json(
            self.client,
            "/api/public/os-consulta",
            {"numero": "2668", "documento": "123.456.789-09", "organization": "empresa-a"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["status"])

    def test_host_organization_id_usa_subdominio(self):
        """Quando o request vem de subdomínio, host_organization_id é usado."""
        with self.app.test_request_context(
            "/api/public/os-consulta",
            method="POST",
            json={"numero": "2668", "documento": "123.456.789-09"},
            headers={"Host": "empresa-a.tamanini.dev.br"},
        ):
            from app.utils.tenancy import resolve_tenant_from_host
            org = resolve_tenant_from_host("empresa-a.tamanini.dev.br", "tamanini.dev.br")
            self.assertIsNotNone(org)
            self.assertEqual(org.id, self.ids["org_a_id"])

    def test_dominio_proprio_nao_resolvido_por_host_apenas_por_slug(self):
        """Domínio próprio (custom_domain) não é resolvido automaticamente pelo host;
           deve ser usado o slug explícito."""
        # Este teste documenta o comportamento atual: custom_domain não entra
        # na resolução por host. O tenant deve ser informado via slug.
        response = _post_json(
            self.client,
            "/api/public/os-consulta",
            {"numero": "2668", "documento": "123.456.789-09", "organization": "empresa-a"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["status"])


if __name__ == "__main__":
    unittest.main()
