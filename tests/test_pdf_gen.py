from types import SimpleNamespace

from app import create_app
from app.extensions import db
from app.models import Configuracao, Organization
from app.utils.pdf_gen import gerar_pdf_os


def test_pdf_os_reportlab_aceita_texto_com_marcacao():
    app = create_app("development")
    app.config.update(TESTING=True)
    with app.app_context():
        db.drop_all()
        db.create_all()
        db.session.add(Organization(id=1, nome="Teste", slug="teste"))
        db.session.add(Configuracao(organization_id=1, nome_empresa="Empresa <Segura> & Cia"))
        db.session.commit()
        order = SimpleNamespace(
            id=1, status="aberta", data_entrada=None,
            cliente=SimpleNamespace(nome="Cliente <Teste>", telefone="47999999999"),
            tipo_aparelho="Notebook", marca="A&B", modelo="<Pro>", numero_serie="ABC<123",
            tecnico_nome="Tecnico & Cia", prio="normal", garantia_dias=90,
            defeito_alegado="Nao liga <script>", defeito_encontrado="Fonte & cabo",
            solucao="Troca > teste", valor_servico=100, valor_pecas=20, desconto=0, valor_total=120,
            checklist_snapshot=["Carcaca sem avarias"], checklist_answers={"Carcaca sem avarias": True},
            authorization_accepted_at=None, authorization_accepted_by=None,
        )
        pdf = gerar_pdf_os(order)
        assert pdf.startswith(b"%PDF")
        assert len(pdf) > 1000
