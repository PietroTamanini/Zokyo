"""Escopo central de tenant para consultas e novos registros ORM."""
from flask import g, has_request_context
from sqlalchemy import event
from sqlalchemy.orm import Session, with_loader_criteria

_registered = False


def register_tenant_scope():
    global _registered
    if _registered:
        return
    _registered = True

    from app.models import (
        Cliente,
        ColetaAgendada,
        Configuracao,
        ConsentRecord,
        DataSubjectRequest,
        DefeitoPadrao,
        EventoLog,
        Fornecedor,
        InventoryLot,
        InventoryMovement,
        LaudoCounter,
        LaudoEvento,
        LaudoFoto,
        LaudoTecnico,
        LaudoTemplate,
        MessageTemplate,
        Notification,
        OrdemServico,
        OrderSignature,
        OSFoto,
        OSHistorico,
        Peca,
        PortalToken,
        RetentionPolicy,
        SavedReport,
        ServiceChecklistTemplate,
        StockReservation,
        Transacao,
        UserInvite,
    )
    tenant_models = (
        Cliente, ColetaAgendada, Configuracao, ConsentRecord, DataSubjectRequest, DefeitoPadrao, EventoLog,
        Fornecedor, LaudoCounter, LaudoEvento, LaudoFoto, LaudoTemplate, LaudoTecnico, Notification, OrdemServico,
        OSFoto, OSHistorico, OrderSignature, Peca, PortalToken, RetentionPolicy, StockReservation, Transacao,
        InventoryLot, InventoryMovement, MessageTemplate, SavedReport, ServiceChecklistTemplate, UserInvite,
    )

    @event.listens_for(Session, "do_orm_execute")
    def add_tenant_filter(execute_state):
        organization_id = getattr(g, "organization_id", None) if has_request_context() else None
        if not organization_id or not execute_state.is_select or execute_state.execution_options.get("include_all_tenants"):
            return
        statement = execute_state.statement
        for model in tenant_models:
            statement = statement.options(
                with_loader_criteria(model, lambda cls: cls.organization_id == organization_id, include_aliases=True)
            )
        execute_state.statement = statement

    @event.listens_for(Session, "before_flush")
    def assign_tenant(session, _flush_context, _instances):
        organization_id = getattr(g, "organization_id", None) if has_request_context() else None
        if not organization_id:
            return
        for obj in session.new:
            if isinstance(obj, tenant_models):
                obj.organization_id = organization_id
        for obj in session.dirty.union(session.deleted):
            if isinstance(obj, tenant_models) and obj.organization_id != organization_id:
                raise ValueError(
                    f"Operacao entre tenants bloqueada para {type(obj).__name__}: "
                    f"tenant {obj.organization_id}, contexto {organization_id}."
                )
