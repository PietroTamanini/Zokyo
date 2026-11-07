"""Regressão dos formulários e das regras de conclusão da área de privacidade."""
import os
import io
import json
import hashlib
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from sqlalchemy import null, text

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "privacy-workflow-tests-only")
os.environ["REDIS_URL"] = ""
os.environ["SCHEDULER_ENABLED"] = "false"

from app import create_app
from app.extensions import db
from app.models import Cliente, DataSubjectRequest, DataSubjectRequestRevision, EventoLog, Organization, PlatformRetentionPolicy, PlatformSetting, PrivacyIncident, PrivacyIncidentRevision, RetentionPolicy, Usuario, registrar
from app.models.evento_log import AuditChainHead
from app.services.audit_integrity import assert_event_chain, verify_event_chain
from app.services.privacy_deadlines import monitor_privacy_deadlines


class PrivacyWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app("development")
        self.app.config.update(
            TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            RATE_LIMIT_ENABLED=False, REQUIRE_ADMIN_2FA=False,
        )
        with self.app.app_context():
            db.create_all()
            db.session.add(Organization(id=1, nome="Assistência", slug="assistencia"))
            admin = Usuario(
                id=50, organization_id=null(), nome="Super admin", email="platform@example.test",
                nivel="admin", ativo=True, is_platform_admin=True,
            )
            admin.set_senha("Senha!123")
            db.session.add(admin)
            tenant_admin = Usuario(
                id=51, organization_id=1, nome="Admin da assistência",
                email="tenant@example.test", nivel="admin", ativo=True,
            )
            tenant_admin.set_senha("Senha!123")
            db.session.add(tenant_admin)
            db.session.add(DataSubjectRequest(
                id=10, organization_id=1, request_type="access", requester_name="Titular",
                requester_email="titular@example.test", channel="public", status="open",
            ))
            db.session.add(PrivacyIncident(
                id=20, title="Teste de incidente", description="Descrição de teste", severity="medium",
                status="open", reported_by_id=50,
            ))
            db.session.commit()
        self.client = self.app.test_client()
        with self.client.session_transaction() as state:
            state.update({
                "usuario_id": 50, "nivel": "admin", "perfil": "admin",
                "usuario_nome": "Super admin", "_last_active": 9999999999,
                "_csrf_token": "privacy-workflow-csrf", "security_version": 1,
            })

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    def test_session_retention_is_visible_but_requires_explicit_approval(self):
        page = self.client.get("/privacidade/retencao?organization_id=1")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'name="active_user_sessions"', page.data)
        response = self.client.post("/privacidade/retencao", data={
            "_csrf_token": "privacy-workflow-csrf", "organization_id": "1",
            "active_user_sessions": "1", "days_user_sessions": "90",
        })
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            self.assertEqual(RetentionPolicy.query.count(), 0)

    def test_platform_session_retention_requires_approval_reference(self):
        page = self.client.get("/privacidade/retencao")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'name="platform_active"', page.data)
        data = {
            "_csrf_token": "privacy-workflow-csrf", "platform_days": "90",
            "platform_active": "1", "platform_legal_approval": "yes",
        }
        self.assertEqual(self.client.post("/privacidade/retencao/plataforma", data=data).status_code, 302)
        with self.app.app_context():
            self.assertEqual(PlatformRetentionPolicy.query.count(), 0)
        data["platform_approval_reference"] = "PRIV-2026-001"
        self.assertEqual(self.client.post("/privacidade/retencao/plataforma", data=data).status_code, 302)
        with self.app.app_context():
            policy = PlatformRetentionPolicy.query.one()
            self.assertTrue(policy.active)
            self.assertEqual(policy.retention_days, 90)
            self.assertEqual(policy.approved_by_id, 50)
            self.assertEqual(policy.approval_reference, "PRIV-2026-001")

    def test_policy_requires_real_approved_document_url(self):
        self.assertEqual(self.client.get("/privacidade/politica").status_code, 503)
        fields = {
            "_csrf_token": "privacy-workflow-csrf", "controller_name": "Exemplo Ltda",
            "controller_document": "00.000.000/0000-00", "controller_address": "Rua de teste",
            "dpo_email": "privacidade@example.test", "dpo_channel": "https://example.test/contato",
            "legal_approval": "1", "policy_published": "1",
        }
        self.assertEqual(self.client.post("/privacidade/configuracao", data=fields).status_code, 302)
        with self.app.app_context():
            self.assertNotEqual(PlatformSetting.get_value("privacy.policy_published"), "true")
        fields["privacy_policy_url"] = "javascript:alert(1)"
        self.client.post("/privacidade/configuracao", data=fields)
        with self.app.app_context():
            self.assertNotEqual(PlatformSetting.get_value("privacy.policy_published"), "true")
        fields["privacy_policy_url"] = "https://example.test/politica-v1"
        self.client.post("/privacidade/configuracao", data=fields)
        with self.app.app_context():
            self.assertEqual(PlatformSetting.get_value("privacy.policy_published"), "true")
        response = self.client.get("/privacidade/politica")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, fields["privacy_policy_url"])

    def test_subject_request_requires_identity_and_response_to_complete(self):
        listing = self.client.get("/privacidade/solicitacoes")
        self.assertEqual(listing.status_code, 200, listing.location)
        self.assertIn(b'action="/privacidade/solicitacoes/10"', listing.data)

        url = "/privacidade/solicitacoes/10"
        base = {"_csrf_token": "privacy-workflow-csrf", "status": "completed"}
        self.assertEqual(self.client.post(url, data=base).status_code, 302)
        with self.app.app_context():
            self.assertEqual(db.session.get(DataSubjectRequest, 10).status, "open")

        base["identity_verified"] = "1"
        self.client.post(url, data=base)
        with self.app.app_context():
            self.assertEqual(db.session.get(DataSubjectRequest, 10).status, "open")

        base["response_notes"] = "Resposta entregue por canal verificado."
        self.client.post(url, data=base)
        with self.app.app_context():
            self.assertEqual(db.session.get(DataSubjectRequest, 10).status, "open")

        base.update({
            "response_channel": "email", "delivery_reference": "Protocolo-123",
            "delivered_at": "2020-01-02T11:00:00-03:00",
        })
        self.client.post(url, data=base)
        with self.app.app_context():
            self.assertEqual(db.session.get(DataSubjectRequest, 10).status, "open")
        base.update({"identity_method": "email_reply", "identity_reference": "Verificacao-123"})
        self.client.post(url, data=base)
        with self.app.app_context():
            record = db.session.get(DataSubjectRequest, 10)
            self.assertEqual(record.status, "completed")
            self.assertTrue(record.identity_verified)
            self.assertEqual(record.identity_method, "email_reply")
            self.assertEqual(record.identity_reference, "Verificacao-123")
            self.assertIsNotNone(record.identity_verified_at)
            self.assertIsNotNone(record.concluido_em)
            self.assertEqual(record.delivery_reference, "Protocolo-123")
            revisions = DataSubjectRequestRevision.query.filter_by(request_id=10).order_by(DataSubjectRequestRevision.id).all()
            self.assertEqual(revisions[0].action, "created")
            self.assertEqual(revisions[-1].details["status"], "completed")
            self.assertEqual(revisions[-1].details["delivery_reference"], "Protocolo-123")
            self.assertEqual(revisions[-1].details["identity_reference"], "Verificacao-123")
            revisions[-1].snapshot = "{}"
            with self.assertRaises(RuntimeError):
                db.session.commit()
            db.session.rollback()

    def test_subject_request_link_requires_verified_identity_and_same_company(self):
        with self.app.app_context():
            db.session.add(Organization(id=2, nome="Outra empresa", slug="outra"))
            db.session.add(Cliente(id=100, organization_id=1, nome="Titular A"))
            db.session.add(Cliente(id=101, organization_id=2, nome="Titular B"))
            db.session.commit()
        url = "/privacidade/solicitacoes/10"
        form = {
            "_csrf_token": "privacy-workflow-csrf", "status": "in_progress",
            "organization_id": "1", "cliente_id": "100",
        }
        self.client.post(url, data=form)
        with self.app.app_context():
            self.assertIsNone(db.session.get(DataSubjectRequest, 10).cliente_id)
        form.update(identity_verified="1", identity_method="email_reply", identity_reference="protocolo-1")
        form["cliente_id"] = "101"
        self.client.post(url, data=form)
        with self.app.app_context():
            self.assertIsNone(db.session.get(DataSubjectRequest, 10).cliente_id)
        form["cliente_id"] = "100"
        self.client.post(url, data=form)
        with self.app.app_context():
            record = db.session.get(DataSubjectRequest, 10)
            self.assertEqual(record.organization_id, 1)
            self.assertEqual(record.cliente_id, 100)
            self.assertEqual(DataSubjectRequestRevision.query.filter_by(request_id=10).order_by(
                DataSubjectRequestRevision.id.desc(),
            ).first().details["cliente_id"], 100)
            raw_snapshot = db.session.execute(text(
                "SELECT snapshot FROM data_subject_request_revisions WHERE request_id = 10 ORDER BY id DESC LIMIT 1"
            )).scalar_one()
            self.assertTrue(raw_snapshot.startswith("zokyo-fernet:v1:"))
        form.update(organization_id="2", cliente_id="101")
        self.client.post(url, data=form)
        with self.app.app_context():
            self.assertEqual(db.session.get(DataSubjectRequest, 10).cliente_id, 100)

    def test_public_request_accepts_full_rights_catalog_and_rejects_unknown_type(self):
        page = self.client.get("/privacidade/solicitacao")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'value="confirmation"', page.data)
        self.assertIn(b'value="consent_revocation"', page.data)
        self.assertIn(b'value="automated_review"', page.data)

        base = {
            "_csrf_token": "privacy-workflow-csrf", "requester_name": "Titular público",
            "requester_email": "publico@example.test", "request_type": "blocking",
        }
        self.assertEqual(self.client.post("/privacidade/solicitacao", data=base).status_code, 200)
        with self.app.app_context():
            self.assertEqual(DataSubjectRequest.query.filter_by(request_type="blocking").count(), 1)
            record = DataSubjectRequest.query.filter_by(request_type="blocking").one()
            raw = db.session.execute(text(
                "SELECT requester_name, requester_email FROM data_subject_requests WHERE id = :id"
            ), {"id": record.id}).one()
            self.assertTrue(raw.requester_name.startswith("zokyo-fernet:v1:"))
            self.assertTrue(raw.requester_email.startswith("zokyo-fernet:v1:"))
            self.assertEqual(record.requester_email, "publico@example.test")

        base["request_type"] = "unknown"
        self.assertEqual(self.client.post("/privacidade/solicitacao", data=base).status_code, 400)
        base["request_type"] = "access"
        base["requester_email"] = "@"
        self.assertEqual(self.client.post("/privacidade/solicitacao", data=base).status_code, 400)
        with self.app.app_context():
            self.assertEqual(DataSubjectRequest.query.count(), 2)

    def test_public_request_has_dedicated_limit_without_leaking_submitted_data(self):
        self.app.config["RATE_LIMIT_ENABLED"] = True
        data = {
            "_csrf_token": "privacy-workflow-csrf", "request_type": "access",
            "requester_name": "Nome pessoal", "requester_email": "private@example.test",
        }

        def limited(_ip, bucket, _limit, _window):
            return 47 if bucket == "privacy:subject_request" else 0

        with patch("app.utils.rate_limit.hit_rate_limit", side_effect=limited) as limiter:
            page = self.client.get("/privacidade/solicitacao")
            self.assertEqual(page.status_code, 200)
            self.assertEqual(page.headers["Cache-Control"], "no-store, private")
            blocked = self.client.post("/privacidade/solicitacao", data=data)
            self.assertEqual(blocked.status_code, 429)
            self.assertEqual(blocked.headers["Retry-After"], "47")
            self.assertEqual(blocked.headers["Cache-Control"], "no-store, private")
            self.assertNotIn(b"private@example.test", blocked.data)
            self.assertTrue(any(call.args[1] == "privacy:subject_request" for call in limiter.call_args_list))
            privacy_calls = [call for call in limiter.call_args_list
                             if call.args[1] == "privacy:subject_request"]
            self.assertTrue(all(call.args[0].startswith("pr:") for call in privacy_calls))
            self.assertTrue(all(len(call.args[0]) <= 45 for call in privacy_calls))
        with self.app.app_context():
            self.assertEqual(DataSubjectRequest.query.count(), 1)

    def test_public_request_limit_is_shared_across_company_channels(self):
        self.app.config.update(RATE_LIMIT_ENABLED=True, PRIVACY_REQUEST_LIMIT_PER_HOUR=1)
        data = {
            "_csrf_token": "privacy-workflow-csrf", "request_type": "access",
            "requester_name": "Titular de teste", "requester_email": "test@example.test",
        }
        first = self.client.post("/privacidade/solicitacao", data=data)
        second = self.client.post("/privacidade/solicitacao/assistencia", data=data)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        self.assertGreater(int(second.headers["Retry-After"]), 0)
        with self.app.app_context():
            self.assertEqual(DataSubjectRequest.query.count(), 2)
            from app.utils.rate_limit import ApiRateLimit

            record = ApiRateLimit.query.filter_by(endpoint="privacy:subject_request").one()
            self.assertTrue(record.ip.startswith("ar:"))
            self.assertNotEqual(record.ip, "127.0.0.1")

    def test_incident_requires_decision_and_actions_to_close(self):
        listing = self.client.get("/privacidade/incidentes")
        self.assertEqual(listing.status_code, 200, listing.location)
        self.assertIn(b'action="/privacidade/incidentes/20"', listing.data)

        url = "/privacidade/incidentes/20"
        base = {"_csrf_token": "privacy-workflow-csrf", "status": "closed", "severity": "high"}
        self.client.post(url, data=base)
        with self.app.app_context():
            self.assertEqual(db.session.get(PrivacyIncident, 20).status, "open")
            self.assertEqual(PrivacyIncident.query.count(), 1)

        base.update({
            "notification_decision": "Decisão registrada para revisão jurídica.",
            "corrective_actions": "Contenção e revisão de permissões documentadas.",
        })
        self.client.post(url, data=base)
        with self.app.app_context():
            incident = db.session.get(PrivacyIncident, 20)
            self.assertEqual(incident.status, "closed")
            self.assertEqual(incident.severity, "high")
            self.assertIsNotNone(incident.closed_at)
            self.assertEqual(PrivacyIncident.query.count(), 1)
            revisions = PrivacyIncidentRevision.query.filter_by(incident_id=20).all()
            self.assertEqual(len(revisions), 1)
            self.assertEqual(revisions[0].details["notification_decision"], base["notification_decision"])
            revisions[0].action = "tampered"
            with self.assertRaises(RuntimeError):
                db.session.commit()
            db.session.rollback()

        updated = dict(base, notification_decision="Nova avaliação após investigação.")
        self.client.post(url, data=updated)
        with self.app.app_context():
            revisions = PrivacyIncidentRevision.query.filter_by(incident_id=20).order_by(PrivacyIncidentRevision.id).all()
            self.assertEqual(len(revisions), 2)
            self.assertEqual(revisions[0].details["notification_decision"], base["notification_decision"])
            self.assertEqual(revisions[1].details["notification_decision"], updated["notification_decision"])

    def test_incident_creation_records_initial_revision(self):
        response = self.client.post("/privacidade/incidentes", data={
            "_csrf_token": "privacy-workflow-csrf", "title": "Incidente novo",
            "description": "Acesso indevido sob investigação.", "severity": "high",
        })
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            incident = PrivacyIncident.query.filter(PrivacyIncident.id != 20).one()
            self.assertEqual(incident.title, "Incidente novo")
            revision = PrivacyIncidentRevision.query.filter_by(incident_id=incident.id).one()
            self.assertEqual(revision.action, "created")
            self.assertEqual(revision.details["description"], incident.description)
            raw = db.session.execute(text(
                "SELECT title, description FROM privacy_incidents WHERE id = :id"
            ), {"id": incident.id}).one()
            self.assertTrue(raw.title.startswith("zokyo-fernet:v1:"))
            self.assertTrue(raw.description.startswith("zokyo-fernet:v1:"))
            raw_snapshot = db.session.execute(text(
                "SELECT snapshot FROM privacy_incident_revisions WHERE id = :id"
            ), {"id": revision.id}).scalar_one()
            self.assertTrue(raw_snapshot.startswith("zokyo-fernet:v1:"))
        listing = self.client.get("/privacidade/incidentes")
        self.assertEqual(listing.status_code, 200)
        self.assertIn(b"Hist\xc3\xb3rico (1)", listing.data)

    def test_tenant_admin_cannot_update_global_privacy_records(self):
        with self.client.session_transaction() as state:
            state["usuario_id"] = 51
            state["usuario_nome"] = "Admin da assistência"
        response = self.client.post("/privacidade/incidentes/20", data={
            "_csrf_token": "privacy-workflow-csrf", "status": "closed", "severity": "high",
            "notification_decision": "Sim", "corrective_actions": "Feito",
        })
        self.assertIn(response.status_code, (302, 403))
        with self.app.app_context():
            self.assertEqual(db.session.get(PrivacyIncident, 20).status, "open")

    def test_incident_timeline_requires_explicit_timezone_and_order(self):
        url = "/privacidade/incidentes/20"
        base = {
            "_csrf_token": "privacy-workflow-csrf", "status": "investigating",
            "severity": "medium", "known_at": "2020-01-01T10:00:00",
        }
        self.client.post(url, data=base)
        with self.app.app_context():
            self.assertIsNone(db.session.get(PrivacyIncident, 20).known_at)

        base["known_at"] = "2020-01-01T10:00:00-03:00"
        base["anpd_notified_at"] = "2019-12-31T10:00:00-03:00"
        self.client.post(url, data=base)
        with self.app.app_context():
            self.assertIsNone(db.session.get(PrivacyIncident, 20).known_at)

        base["anpd_notified_at"] = "2020-01-02T11:00:00-03:00"
        base["notification_reference"] = "Protocolo de teste"
        self.client.post(url, data=base)
        with self.app.app_context():
            incident = db.session.get(PrivacyIncident, 20)
            self.assertEqual(incident.known_at, datetime(2020, 1, 1, 13, 0))
            self.assertEqual(incident.anpd_notified_at, datetime(2020, 1, 2, 14, 0))
            self.assertEqual(incident.notification_reference, "Protocolo de teste")

    def test_audit_head_follows_events_and_detects_deleted_tail(self):
        with self.app.app_context():
            registrar("sistema", "teste", "Primeiro evento", organization_id=1)
            registrar("sistema", "teste", "Segundo evento", organization_id=1)
            db.session.commit()
            events = EventoLog.query.execution_options(include_all_tenants=True).order_by(EventoLog.id).all()
            self.assertEqual(len(events), 2)
            self.assertEqual(events[1].previous_hash, events[0].integrity_hash)
            self.assertEqual(db.session.get(AuditChainHead, 1).last_hash, events[1].integrity_hash)
            self.assertEqual(verify_event_chain()["errors"], [])

            events[0].descricao = "Tentativa de alteração"
            with self.assertRaises(RuntimeError):
                db.session.commit()
            db.session.rollback()
            db.session.delete(events[0])
            with self.assertRaises(RuntimeError):
                db.session.commit()
            db.session.rollback()

            db.session.execute(text("DELETE FROM eventos_log WHERE id = :id"), {"id": events[1].id})
            db.session.commit()
            reasons = {item["reason"] for item in verify_event_chain()["errors"]}
            self.assertIn("chain_head_mismatch", reasons)
            with self.assertRaises(RuntimeError):
                assert_event_chain()

    def test_privacy_deadline_monitor_sends_counts_without_personal_data(self):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with self.app.app_context():
            request_record = db.session.get(DataSubjectRequest, 10)
            request_record.due_at = now - timedelta(hours=1)
            incident = db.session.get(PrivacyIncident, 20)
            incident.known_at = now - timedelta(hours=25)
            db.session.commit()
            overdue_page = self.client.get("/privacidade/solicitacoes?status=overdue")
            self.assertEqual(overdue_page.status_code, 200)
            self.assertIn(b"Prazo vencido", overdue_page.data)
            with patch("app.services.privacy_deadlines.emit_alert") as alert:
                counts = monitor_privacy_deadlines(now)
            self.assertEqual(counts["requests_overdue"], 1)
            self.assertEqual(counts["incidents_without_decision"], 1)
            self.assertEqual(alert.call_count, 2)
            for call in alert.call_args_list:
                message = call.args[2]
                self.assertNotIn("titular@example.test", message)
                self.assertNotIn("Teste de incidente", message)

            request_record.status = "completed"
            incident.notification_decision = "Comunicação sob avaliação."
            db.session.commit()
            with patch("app.services.privacy_deadlines.emit_alert") as alert:
                counts = monitor_privacy_deadlines(now)
            self.assertEqual(counts["requests_overdue"], 0)
            self.assertEqual(counts["incidents_without_decision"], 0)
            alert.assert_not_called()

    def test_platform_reads_are_audited_without_query_personal_data(self):
        settings = self.client.get("/platform/companies/1/settings")
        self.assertEqual(settings.status_code, 200)
        audit = self.client.get("/platform/audit?organization_id=1&q=titular%40example.test")
        self.assertEqual(audit.status_code, 200)
        with self.app.app_context():
            events = EventoLog.query.filter_by(tipo="acesso", modulo="platform_access").order_by(EventoLog.id).all()
            self.assertEqual(len(events), 2)
            self.assertEqual([event.organization_id for event in events], [1, 1])
            self.assertEqual({event.usuario_id for event in events}, {50})
            self.assertTrue(all("titular@example.test" not in event.descricao for event in events))
            self.assertEqual(verify_event_chain()["errors"], [])

        with self.client.session_transaction() as state:
            state.update(usuario_id=51, usuario_nome="Tenant", nivel="admin")
        denied = self.client.get("/platform/companies/1/settings")
        self.assertNotEqual(denied.status_code, 200)
        with self.app.app_context():
            self.assertEqual(EventoLog.query.filter_by(tipo="acesso", modulo="platform_access").count(), 2)

    def test_operations_shows_audit_not_yet_verified(self):
        response = self.client.get("/platform/operations")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Sem verificação".encode(), response.data)

    def test_company_privacy_clients_stay_in_selected_tenant_and_export_is_not_dsr_completion(self):
        with self.app.app_context():
            db.session.add(Organization(id=2, nome="Outra empresa", slug="outra"))
            db.session.add_all([
                Cliente(id=100, organization_id=1, nome="Titular A", email="a@example.test"),
                Cliente(id=101, organization_id=2, nome="Titular B", email="b@example.test"),
                Cliente(id=102, organization_id=1, nome="Cadastro duplicado", email="duplicate@example.test"),
            ])
            db.session.add(DataSubjectRequest(
                id=11, organization_id=1, cliente_id=100, request_type="deletion",
                requester_name="Titular A", requester_email="a@example.test",
                identity_verified=True, identity_method="email_reply", identity_reference="protocolo-11",
                status="in_progress",
            ))
            db.session.add(DataSubjectRequest(
                id=12, organization_id=2, cliente_id=101, request_type="access",
                requester_name="Titular B", requester_email="b@example.test",
                identity_verified=True, identity_method="email_reply", identity_reference="protocolo-12",
                status="in_progress",
            ))
            db.session.add(PrivacyIncident(
                id=21, organization_id=1, title="Teste da empresa", description="Incidente de teste",
                reported_by_id=50,
            ))
            db.session.add(PrivacyIncident(
                id=22, organization_id=2, title="Teste de outra empresa", description="Incidente de teste",
                reported_by_id=50,
            ))
            db.session.commit()

        listing = self.client.get("/platform/companies/1/settings/privacy/clients")
        self.assertEqual(listing.status_code, 200)
        self.assertIn(b"Titular A", listing.data)
        self.assertNotIn(b"Titular B", listing.data)
        detail = self.client.get("/platform/companies/1/settings/privacy/clients/100")
        self.assertEqual(detail.status_code, 200)
        self.assertNotIn(b'name="granted"', detail.data)
        self.assertIn(b'<option value="11">', detail.data)
        self.assertNotIn(b'<option value="12">', detail.data)
        self.assertIn(b'<option value="21">', detail.data)
        self.assertNotIn(b'<option value="22">', detail.data)
        self.assertEqual(self.client.get("/platform/companies/1/settings/privacy/clients/101").status_code, 404)

        export_url = "/platform/companies/1/settings/privacy/clients/100/export"
        self.assertNotEqual(self.client.get(export_url).status_code, 200)
        self.assertEqual(self.client.post(export_url, data={"reason": "subject_request"}).status_code, 400)
        self.assertEqual(self.client.post(export_url, data={"_csrf_token": "privacy-workflow-csrf"}).status_code, 400)
        self.assertEqual(self.client.post(export_url, data={
            "_csrf_token": "privacy-workflow-csrf", "reason": "invented",
        }).status_code, 400)
        self.assertEqual(self.client.post(export_url, data={
            "_csrf_token": "privacy-workflow-csrf", "reason": "subject_request", "request_id": "12",
        }).status_code, 400)
        self.assertEqual(self.client.post(export_url, data={
            "_csrf_token": "privacy-workflow-csrf", "reason": "incident_investigation", "incident_id": "22",
        }).status_code, 400)
        self.assertEqual(self.client.post("/platform/companies/1/settings/privacy/clients/101/export", data={
            "_csrf_token": "privacy-workflow-csrf", "reason": "subject_request",
        }).status_code, 404)
        exported = self.client.post(export_url, data={
            "_csrf_token": "privacy-workflow-csrf", "reason": "subject_request", "request_id": "11",
        })
        self.assertEqual(exported.status_code, 200)
        self.assertEqual(exported.headers["Cache-Control"], "no-store, private")
        self.assertEqual(exported.headers["X-Export-SHA256"], hashlib.sha256(exported.data).hexdigest())
        with zipfile.ZipFile(io.BytesIO(exported.data)) as archive:
            self.assertEqual(json.loads(archive.read("dados.json"))["cliente"]["nome"], "Titular A")
        requests_page = self.client.get("/privacidade/solicitacoes")
        self.assertEqual(requests_page.status_code, 200)
        self.assertIn(hashlib.sha256(exported.data).hexdigest().encode(), requests_page.data)
        with self.app.app_context():
            self.assertEqual(DataSubjectRequest.query.filter_by(request_type="export", status="completed").count(), 0)
            request_record = db.session.get(DataSubjectRequest, 11)
            self.assertEqual(request_record.prepared_export_sha256, hashlib.sha256(exported.data).hexdigest())
            self.assertIsNotNone(request_record.prepared_export_at)
            self.assertEqual(request_record.status, "in_progress")
            self.assertIsNone(request_record.delivered_at)
            revision = DataSubjectRequestRevision.query.filter_by(request_id=11).order_by(
                DataSubjectRequestRevision.id.desc()).first()
            self.assertEqual(revision.actor_id, 50)
            self.assertEqual(revision.details["prepared_export_sha256"], request_record.prepared_export_sha256)
            self.assertIsNotNone(revision.details["prepared_export_at"])
            event = EventoLog.query.filter_by(modulo="privacidade", tipo="acesso").order_by(EventoLog.id.desc()).first()
            self.assertEqual(event.descricao, (
                "motivo=subject_request;solicitacao_id=11;zip_sha256="
                + hashlib.sha256(exported.data).hexdigest()
            ))
            self.assertEqual(event.organization_id, 1)
            self.assertEqual(event.usuario_id, 50)
        investigated = self.client.post(export_url, data={
            "_csrf_token": "privacy-workflow-csrf", "reason": "incident_investigation", "incident_id": "21",
        })
        self.assertEqual(investigated.status_code, 200)
        self.assertEqual(investigated.headers["X-Export-SHA256"], hashlib.sha256(investigated.data).hexdigest())
        with self.app.app_context():
            self.assertEqual(db.session.get(DataSubjectRequest, 11).prepared_export_sha256,
                             hashlib.sha256(exported.data).hexdigest())
            event = EventoLog.query.filter_by(modulo="privacidade", tipo="acesso").order_by(EventoLog.id.desc()).first()
            self.assertEqual(event.descricao, (
                "motivo=incident_investigation;incidente_id=21;zip_sha256="
                + hashlib.sha256(investigated.data).hexdigest()
            ))

        self.assertEqual(self.client.post(export_url, data={
            "_csrf_token": "privacy-workflow-csrf", "reason": "support_request",
        }).status_code, 400)
        self.assertEqual(self.client.post(export_url, data={
            "_csrf_token": "privacy-workflow-csrf", "reason": "support_request",
            "protocol": "nome@example.test",
        }).status_code, 400)
        supported = self.client.post(export_url, data={
            "_csrf_token": "privacy-workflow-csrf", "reason": "support_request",
            "protocol": "SUP-1234",
        })
        self.assertEqual(supported.status_code, 200)
        with self.app.app_context():
            event = EventoLog.query.filter_by(modulo="privacidade", tipo="acesso").order_by(EventoLog.id.desc()).first()
            self.assertEqual(event.descricao, (
                "motivo=support_request;protocolo=SUP-1234;zip_sha256="
                + hashlib.sha256(supported.data).hexdigest()
            ))

        duplicate_url = "/platform/companies/1/settings/privacy/clients/102/remove-registration"
        self.assertEqual(self.client.post(duplicate_url, data={
            "_csrf_token": "privacy-workflow-csrf", "reason": "duplicate_record",
        }).status_code, 400)
        self.assertEqual(self.client.post(duplicate_url, data={
            "_csrf_token": "privacy-workflow-csrf", "reason": "duplicate_record", "protocol": "DUP-1234",
        }).status_code, 302)
        with self.app.app_context():
            duplicate = db.session.get(Cliente, 102)
            self.assertTrue(duplicate.nome.startswith("Cadastro sem identificação"))
            event = EventoLog.query.filter_by(modulo="privacidade", tipo="exclusao").order_by(EventoLog.id.desc()).first()
            self.assertEqual(event.descricao, "motivo=duplicate_record;protocolo=DUP-1234")

        removal_url = "/platform/companies/1/settings/privacy/clients/100/remove-registration"
        self.assertEqual(self.client.post(removal_url, data={
            "_csrf_token": "privacy-workflow-csrf",
        }).status_code, 400)
        self.assertEqual(self.client.post(removal_url, data={
            "_csrf_token": "privacy-workflow-csrf", "reason": "subject_request", "request_id": "12",
        }).status_code, 400)
        with self.app.app_context():
            self.assertEqual(db.session.get(Cliente, 100).nome, "Titular A")
        removed = self.client.post(removal_url, data={
            "_csrf_token": "privacy-workflow-csrf", "reason": "subject_request", "request_id": "11",
        })
        self.assertEqual(removed.status_code, 302)
        with self.app.app_context():
            self.assertTrue(db.session.get(Cliente, 100).nome.startswith("Cadastro sem identificação"))
            event = EventoLog.query.filter_by(modulo="privacidade", tipo="exclusao").order_by(EventoLog.id.desc()).first()
            self.assertEqual(event.descricao, "motivo=subject_request;solicitacao_id=11")
            self.assertEqual(verify_event_chain()["errors"], [])

        with self.client.session_transaction() as state:
            state.update(usuario_id=51, usuario_nome="Tenant", nivel="admin")
        with patch.dict(os.environ, {"PLATFORM_ADMIN_EMAILS": "tenant@example.test"}):
            self.assertNotEqual(self.client.get("/platform/companies/1/settings/privacy/clients").status_code, 200)


if __name__ == "__main__":
    unittest.main()
