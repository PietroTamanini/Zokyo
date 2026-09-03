"""Cria notificacoes idempotentes a partir de eventos de ordem de servico."""

from app.models import STATUS_OS_LABELS, Configuracao
from app.services.message_templates import DEFAULT_TEMPLATES, active_template, render_template
from app.services.notifications import enqueue_email, enqueue_whatsapp


def _context(order) -> dict:
    customer = order.cliente
    config = Configuracao.query.execution_options(include_all_tenants=True).filter_by(
        organization_id=order.organization_id,
    ).first()
    return {
        "cliente": customer.nome if customer else "cliente",
        "os_id": order.codigo_os,
        "status": STATUS_OS_LABELS.get(order.status, order.status),
        "equipamento": " ".join(filter(None, [order.tipo_aparelho, order.marca, order.modelo])),
        "total": f"R$ {order.valor_total:.2f}",
        "empresa": config.nome_empresa if config else "Zokyo",
    }


def queue_order_event(order, event_type: str, idempotency_key: str) -> list:
    """Enfileira email/WhatsApp disponiveis sem realizar I/O externo na requisicao."""
    customer = order.cliente
    if not customer:
        return []

    context = _context(order)
    default_subject = f"Atualizacao da OS #{order.codigo_os}"
    default_body = (
        f"Ola, {context['cliente']}.\n\n"
        f"A OS #{context['os_id']} agora esta em: {context['status']}.\n"
        "Entre em contato com a assistencia em caso de duvidas."
    )
    queued = []
    default_channels = {
        channel for configured_event, channel, _subject, _body in DEFAULT_TEMPLATES
        if configured_event == event_type
    }
    email_enabled = (
        event_type.startswith("os_status_")
        or "email" in default_channels
        or active_template(event_type, "email", order.organization_id)
    )
    whatsapp_enabled = (
        "whatsapp" in default_channels
        or active_template(event_type, "whatsapp", order.organization_id)
    )
    if customer.email and email_enabled:
        subject, body = render_template(
            event_type, "email", context,
            default_subject=default_subject,
            default_body=default_body,
            organization_id=order.organization_id,
        )
        item, _created = enqueue_email(
            order.organization_id,
            customer.email,
            subject,
            body,
            event_type,
            f"{idempotency_key}-email",
        )
        queued.append(item)
    if customer.telefone and whatsapp_enabled:
        _subject, body = render_template(
            event_type, "whatsapp", context,
            default_body=default_body,
            organization_id=order.organization_id,
        )
        item, _created = enqueue_whatsapp(
            order.organization_id,
            customer.telefone,
            body,
            event_type,
            f"{idempotency_key}-whatsapp",
        )
        queued.append(item)
    return queued
