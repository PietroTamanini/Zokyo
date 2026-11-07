"""Coverage and tenant isolation of the administrative subject export."""
import io
import hashlib
import json
import os
import unittest
import zipfile
from sqlalchemy import null

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "subject-export-tests-only")
os.environ["REDIS_URL"] = ""
os.environ["SCHEDULER_ENABLED"] = "false"

from app import create_app
from app.extensions import db
from app.models import (
    Cliente, ColetaAgendada, DataSubjectRequest, EventoLog, LaudoTecnico,
    OrdemServico, Organization, Transacao, Usuario,
)
from app.services.privacy import export_subject_data


class SubjectExportTests(unittest.TestCase):
    def test_export_covers_linked_records_without_cross_tenant_or_internal_fields(self):
        app = create_app("development")
        app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
        with app.app_context():
            db.create_all()
            db.session.add_all([
                Organization(id=1, nome="Empresa A", slug="empresa-a"),
                Organization(id=2, nome="Empresa B", slug="empresa-b"),
            ])
            admin = Usuario(
                id=50, organization_id=null(), nome="Admin global", email="admin@example.test",
                nivel="admin", ativo=True, is_platform_admin=True,
            )
            admin.set_senha("Senha!123")
            client = Cliente(id=100, organization_id=1, nome="Titular", email="titular@example.test")
            db.session.add_all([admin, client])
            db.session.flush()
            db.session.add_all([
                OrdemServico(
                    id=201, organization_id=1, cliente_id=100, usuario_id=50,
                    tipo_aparelho="Notebook", defeito_alegado="Tela quebrada",
                    tecnico_nome="Nome interno", custo_hora=90,
                ),
                OrdemServico(
                    id=202, organization_id=2, cliente_id=100, usuario_id=50,
                    tipo_aparelho="Registro de outra empresa",
                ),
                ColetaAgendada(
                    id=301, organization_id=1, cliente_id=100, usuario_id=50,
                    endereco="Rua do titular", telefone_contato="11999999999",
                ),
                ColetaAgendada(
                    id=302, organization_id=2, cliente_id=100, usuario_id=50,
                    endereco="Rua de outra empresa",
                ),
                DataSubjectRequest(
                    id=401, organization_id=1, cliente_id=100,
                    request_type="access", status="in_progress", response_notes="Resposta em preparo",
                ),
                DataSubjectRequest(
                    id=402, organization_id=2, cliente_id=100,
                    request_type="access", status="open",
                ),
                LaudoTecnico(
                    id=501, organization_id=1, os_id=201, cliente_id=100, criado_por_id=50,
                    tipo="diagnostico", status="draft", inspecao_visual="Marcas na tela",
                ),
                LaudoTecnico(
                    id=502, organization_id=2, os_id=202, cliente_id=100, criado_por_id=50,
                    tipo="diagnostico", status="draft", inspecao_visual="Outro laudo",
                ),
                Transacao(
                    id=601, organization_id=1, os_id=201, tipo="receita", valor=100,
                    descricao="Pagamento do serviço", payment_payload="segredo-interno",
                    comissao_valor=12,
                ),
                Transacao(
                    id=602, organization_id=2, os_id=201, tipo="receita", valor=900,
                    descricao="Transação de outra empresa",
                ),
            ])
            db.session.commit()

            with self.assertRaises(ValueError):
                export_subject_data(client, admin, target_organization_id=2)
            archive = export_subject_data(client, admin, target_organization_id=1)
            self.assertEqual(archive.export_sha256, hashlib.sha256(archive.getvalue()).hexdigest())
            db.session.commit()
            with zipfile.ZipFile(io.BytesIO(archive.getvalue())) as zipped:
                payload = json.loads(zipped.read("dados.json"))
            event = EventoLog.query.filter_by(modulo="privacidade", tipo="acesso").one()
            self.assertIn("zip_sha256=" + hashlib.sha256(archive.getvalue()).hexdigest(), event.descricao)
            self.assertEqual(payload["cliente"]["email"], "titular@example.test")
            self.assertEqual([item["id"] for item in payload["ordens_servico"]], [201])
            self.assertEqual([item["id"] for item in payload["coletas"]], [301])
            self.assertEqual([item["id"] for item in payload["solicitacoes"]], [401])
            self.assertEqual([item["id"] for item in payload["laudos"]], [501])
            self.assertEqual([item["id"] for item in payload["transacoes"]], [601])
            self.assertEqual(payload["laudos"][0]["inspecao_visual"], "Marcas na tela")
            self.assertNotIn("tecnico_nome", payload["ordens_servico"][0])
            self.assertNotIn("custo_hora", payload["ordens_servico"][0])
            self.assertNotIn("payment_payload", payload["transacoes"][0])
            self.assertNotIn("comissao_valor", payload["transacoes"][0])
            db.session.remove()
            db.drop_all()
            db.engine.dispose()


if __name__ == "__main__":
    unittest.main()
