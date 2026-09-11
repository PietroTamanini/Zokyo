"""add multi-tenant query indexes

Revision ID: 20260911_0021
Revises: 20260910_0020
Create Date: 2026-09-11 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = "20260911_0021"
down_revision = "20260910_0020"
branch_labels = None
depends_on = None


INDEXES = (
    ("ix_coletas_org_status_agendada_criado", "coletas_agendadas", ("organization_id", "status", "data_agendada", "criado_em")),
    ("ix_coletas_org_cliente_criado", "coletas_agendadas", ("organization_id", "cliente_id", "criado_em")),
    ("ix_laudos_org_status_tipo_criado", "laudos_tecnicos", ("organization_id", "status", "tipo", "criado_em")),
    ("ix_laudos_org_cliente_criado", "laudos_tecnicos", ("organization_id", "cliente_id", "criado_em")),
    ("ix_laudos_org_os_criado", "laudos_tecnicos", ("organization_id", "os_id", "criado_em")),
    ("ix_laudos_org_pdf_gerado", "laudos_tecnicos", ("organization_id", "pdf_gerado_em")),
    ("ix_laudo_fotos_org_criado", "laudo_fotos", ("organization_id", "criado_em")),
    ("ix_laudo_fotos_org_laudo_ordem", "laudo_fotos", ("organization_id", "laudo_id", "ordem")),
    ("ix_laudo_eventos_org_laudo_criado", "laudo_eventos", ("organization_id", "laudo_id", "criado_em")),
    ("ix_notifications_org_status_next", "notifications", ("organization_id", "status", "next_attempt_at", "id")),
    ("ix_notifications_org_status_created", "notifications", ("organization_id", "status", "created_at")),
    ("ix_notifications_org_event_created", "notifications", ("organization_id", "event_type", "created_at")),
    ("ix_os_org_open_prio_data", "ordens_servico", ("organization_id", "deletado_em", "baixada_em", "prio", "data_entrada")),
    ("ix_os_org_open_atendimento_data", "ordens_servico", ("organization_id", "deletado_em", "baixada_em", "tipo_atendimento", "data_entrada")),
    ("ix_os_org_open_tecnico_prev", "ordens_servico", ("organization_id", "deletado_em", "baixada_em", "tecnico_nome", "data_prev")),
    ("ix_os_org_deleted_atualizado", "ordens_servico", ("organization_id", "deletado_em", "atualizado_em")),
    ("ix_order_signatures_order_revoked_created", "order_signatures", ("order_id", "revoked_at", "created_at")),
    ("ix_order_signatures_org_created", "order_signatures", ("organization_id", "created_at")),
    ("ix_os_fotos_org_criado", "os_fotos", ("organization_id", "criado_em")),
    ("ix_os_fotos_org_os_criado", "os_fotos", ("organization_id", "os_id", "criado_em")),
    ("ix_os_fotos_org_coleta_criado", "os_fotos", ("organization_id", "coleta_id", "criado_em")),
    ("ix_consent_records_org_cliente_registrado", "consent_records", ("organization_id", "cliente_id", "registrado_em")),
    ("ix_data_subject_requests_org_cliente_solicitado", "data_subject_requests", ("organization_id", "cliente_id", "solicitado_em")),
    ("ix_data_subject_requests_org_status_solicitado", "data_subject_requests", ("organization_id", "status", "solicitado_em")),
    ("ix_saved_reports_org_user_name", "saved_reports", ("organization_id", "user_id", "name")),
    ("ix_saved_reports_org_active_next", "saved_reports", ("organization_id", "active", "next_run_at")),
    ("ix_transacoes_org_tipo_criado", "transacoes", ("organization_id", "tipo", "criado_em")),
    ("ix_transacoes_org_tipo_status_venc", "transacoes", ("organization_id", "tipo", "status", "data_vencimento")),
    ("ix_transacoes_org_pago_data", "transacoes", ("organization_id", "status", "data_pagamento")),
    ("ix_user_invites_org_email_open", "user_invites", ("organization_id", "email", "used_at", "revoked_at", "expires_at")),
    ("ix_user_sessions_user_last_seen", "user_sessions", ("user_id", "last_seen_at")),
    ("ix_user_sessions_org_user_active", "user_sessions", ("organization_id", "user_id", "revoked_at", "expires_at")),
    ("ix_usuarios_org_active_nome", "usuarios", ("organization_id", "ativo", "nome")),
    ("ix_usuarios_org_nivel_active", "usuarios", ("organization_id", "nivel", "ativo")),
)


def _existing_indexes(table):
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {idx["name"] for idx in inspector.get_indexes(table)}


def upgrade():
    cache = {}
    for name, table, columns in INDEXES:
        cache.setdefault(table, _existing_indexes(table))
        if name not in cache[table]:
            op.create_index(name, table, list(columns))
            cache[table].add(name)


def downgrade():
    cache = {}
    for name, table, _columns in reversed(INDEXES):
        cache.setdefault(table, _existing_indexes(table))
        if name in cache[table]:
            op.drop_index(name, table_name=table)
            cache[table].remove(name)
