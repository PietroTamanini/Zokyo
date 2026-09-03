from app import create_app
from app.extensions import db
from app.models import Cliente, Configuracao, Notification, OrdemServico, Organization, Usuario
from app.services.order_notifications import queue_order_event


def _make_app():
    app = create_app("development")
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    with app.app_context():
        db.create_all()
        organization = Organization(id=1, nome="Teste", slug="notificacoes-os")
        user = Usuario(organization_id=1, nome="Admin", email="admin@notify.test", nivel="admin")
        user.set_senha("Senha!123")
        customer = Cliente(
            organization_id=1,
            nome="Ana",
            email="ana@example.test",
            telefone="47999999999",
        )
        config = Configuracao(organization_id=1, nome_empresa="Oficina Teste")
        db.session.add_all([organization, user, customer, config])
        db.session.flush()
        order = OrdemServico(
            organization_id=1,
            numero=12,
            cliente_id=customer.id,
            usuario_id=user.id,
            tipo_aparelho="Notebook",
            marca="Marca",
            status="pronto",
            valor_servico=150,
        )
        db.session.add(order)
        db.session.commit()
        order_id = order.id
    return app, order_id


def test_evento_de_os_enfileira_canais_com_contexto_e_idempotencia():
    app, order_id = _make_app()
    with app.app_context():
        order = db.session.get(OrdemServico, order_id)
        first = queue_order_event(order, "os_status_pronto", f"os-ready-{order.id}")
        repeated = queue_order_event(order, "os_status_pronto", f"os-ready-{order.id}")

        assert len(first) == 2
        assert len(repeated) == 2
        assert Notification.query.count() == 2
        email = Notification.query.filter_by(channel="email").one()
        whatsapp = Notification.query.filter_by(channel="whatsapp").one()
        assert email.event_type == "os_status_pronto"
        assert "0012" in email.payload["subject"]
        assert "Ana" in email.payload["message"]
        assert "0012" in whatsapp.payload["message"]


def test_evento_sem_destinatarios_nao_cria_notificacao():
    app, order_id = _make_app()
    with app.app_context():
        order = db.session.get(OrdemServico, order_id)
        order.cliente.email = None
        order.cliente.telefone = None
        db.session.commit()

        assert queue_order_event(order, "warranty_return", f"warranty-{order.id}") == []
        assert Notification.query.count() == 0


def test_eventos_especificos_respeitam_os_canais_configurados():
    app, order_id = _make_app()
    with app.app_context():
        order = db.session.get(OrdemServico, order_id)

        queue_order_event(order, "payment_due", f"payment-{order.id}")
        queue_order_event(order, "warranty_return", f"warranty-{order.id}")

        payment = Notification.query.filter_by(event_type="payment_due").all()
        warranty = Notification.query.filter_by(event_type="warranty_return").all()
        assert [item.channel for item in payment] == ["email"]
        assert [item.channel for item in warranty] == ["whatsapp"]


def test_template_de_outro_tenant_nao_e_usado():
    app, order_id = _make_app()
    with app.app_context():
        from app.models import MessageTemplate

        db.session.add(Organization(id=2, nome="Outra", slug="outra"))
        db.session.add(MessageTemplate(
            organization_id=2,
            event_type="payment_due",
            channel="email",
            version=2,
            subject="VAZAMENTO",
            body="VAZAMENTO",
        ))
        db.session.commit()

        order = db.session.get(OrdemServico, order_id)
        queue_order_event(order, "payment_due", f"tenant-payment-{order.id}")

        item = Notification.query.filter_by(event_type="payment_due").one()
        assert "VAZAMENTO" not in item.payload["subject"]
        assert "VAZAMENTO" not in item.payload["message"]
