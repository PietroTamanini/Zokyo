from datetime import datetime
from types import SimpleNamespace

import pytest

from app import create_app
from app.extensions import db
from app.models import Configuracao, Organization
from app.utils import pdf_gen


def test_pdf_os_reportlab_aceita_texto_com_marcacao(monkeypatch):
    app = create_app("development")
    app.config.update(TESTING=True)
    with app.app_context():
        db.drop_all()
        db.create_all()
        db.session.add(Organization(id=1, nome="Teste", slug="teste"))
        db.session.add(Configuracao(
            organization_id=1,
            nome_empresa="Empresa <Segura> & Cia",
            subtitulo_empresa="Assistência técnica",
            site_url="https://empresa.example",
            instagram_url="https://instagram.com/empresa",
            whatsapp_publico="47999999999",
        ))
        db.session.commit()
        order = SimpleNamespace(
            id=1, status="aberta", data_entrada=None,
            cliente=SimpleNamespace(nome="Cliente <Teste>", telefone="47999999999", email="cliente@example.com", documento="123"),
            tipo_aparelho="Notebook", marca="A&B", modelo="<Pro>", numero_serie="ABC<123",
            tecnico_nome="Tecnico & Cia", prio="normal", garantia_dias=90,
            defeito_alegado="Nao liga <script>", defeito_encontrado="Fonte & cabo",
            solucao="Troca > teste", valor_servico=100, valor_pecas=20, desconto=0, valor_total=120,
            checklist_snapshot=["Carcaca sem avarias"], checklist_answers={"Carcaca sem avarias": True},
            authorization_accepted_at=datetime(2026, 1, 1, 10, 30), authorization_accepted_by=None,
        )
        pdf = pdf_gen.gerar_pdf_os(order)
        assert pdf.startswith(b"%PDF")
        assert len(pdf) > 1000

        monkeypatch.setattr(pdf_gen, "_pdf_via_reportlab", lambda _order: (_ for _ in ()).throw(ImportError()))
        with pytest.raises(RuntimeError, match="ReportLab"):
            pdf_gen.gerar_pdf_os(order)

        monkeypatch.setattr(pdf_gen, "_pdf_via_reportlab", lambda _order: (_ for _ in ()).throw(ValueError("quebrou")))
        with pytest.raises(RuntimeError, match="quebrou"):
            pdf_gen.gerar_pdf_os(order)
