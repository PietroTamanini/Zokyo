"""create laudos module tables

Revision ID: 20260711_0001
Revises: 20260710_0000
Create Date: 2026-07-11
"""
from alembic import op
import sqlalchemy as sa

revision = "20260711_0001"
down_revision = "20260710_0000"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "laudo_counters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("ano", sa.Integer(), nullable=False),
        sa.Column("proximo_numero", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("atualizado_em", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("organization_id", "ano", name="uq_laudo_counter_org_ano"),
    )
    op.create_table(
        "laudos_tecnicos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_uuid", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("os_id", sa.Integer(), nullable=False),
        sa.Column("cliente_id", sa.Integer(), nullable=False),
        sa.Column("equipamento_id", sa.Integer(), nullable=True),
        sa.Column("tipo", sa.String(length=30), nullable=False, server_default="diagnostico"),
        sa.Column("numero", sa.String(length=30), nullable=True),
        sa.Column("ano", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("emitido_em", sa.DateTime(), nullable=True),
        sa.Column("analisado_em", sa.DateTime(), nullable=True),
        sa.Column("tecnico_responsavel_id", sa.Integer(), nullable=True),
        sa.Column("tecnico_responsavel_nome", sa.String(length=120), nullable=True),
        sa.Column("criado_por_id", sa.Integer(), nullable=False),
        sa.Column("atualizado_por_id", sa.Integer(), nullable=True),
        sa.Column("versao", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("laudo_origem_id", sa.Integer(), nullable=True),
        sa.Column("defeito_relatado", sa.Text(), nullable=True),
        sa.Column("inspecao_visual", sa.Text(), nullable=True),
        sa.Column("testes_realizados", sa.Text(), nullable=True),
        sa.Column("instrumentos_metodos", sa.Text(), nullable=True),
        sa.Column("medicoes", sa.Text(), nullable=True),
        sa.Column("diagnostico_tecnico", sa.Text(), nullable=True),
        sa.Column("causa_provavel", sa.Text(), nullable=True),
        sa.Column("servicos_realizados", sa.Text(), nullable=True),
        sa.Column("pecas_utilizadas", sa.Text(), nullable=True),
        sa.Column("conclusao_tecnica", sa.Text(), nullable=True),
        sa.Column("estado_final", sa.String(length=120), nullable=True),
        sa.Column("recomendacoes", sa.Text(), nullable=True),
        sa.Column("riscos_limitacoes", sa.Text(), nullable=True),
        sa.Column("garantia", sa.String(length=200), nullable=True),
        sa.Column("observacoes", sa.Text(), nullable=True),
        sa.Column("motivo_cancelamento", sa.Text(), nullable=True),
        sa.Column("empresa_snapshot", sa.JSON(), nullable=True),
        sa.Column("cliente_snapshot", sa.JSON(), nullable=True),
        sa.Column("equipamento_snapshot", sa.JSON(), nullable=True),
        sa.Column("tecnico_snapshot", sa.JSON(), nullable=True),
        sa.Column("assinatura_tecnico_nome", sa.String(length=120), nullable=True),
        sa.Column("assinatura_tecnico_em", sa.DateTime(), nullable=True),
        sa.Column("assinatura_tecnico_metodo", sa.String(length=50), nullable=True),
        sa.Column("assinatura_cliente_nome", sa.String(length=120), nullable=True),
        sa.Column("assinatura_cliente_em", sa.DateTime(), nullable=True),
        sa.Column("assinatura_cliente_metodo", sa.String(length=50), nullable=True),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), nullable=False),
        sa.Column("finalizado_em", sa.DateTime(), nullable=True),
        sa.Column("cancelado_em", sa.DateTime(), nullable=True),
        sa.Column("pdf_path", sa.String(length=600), nullable=True),
        sa.Column("pdf_sha256", sa.String(length=64), nullable=True),
        sa.Column("pdf_gerado_em", sa.DateTime(), nullable=True),
        sa.Column("pdf_template_version", sa.String(length=30), nullable=True),
        sa.Column("verification_token", sa.String(length=80), nullable=True),
        sa.Column("verificacao_publica", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(["os_id"], ["ordens_servico.id"]),
        sa.ForeignKeyConstraint(["cliente_id"], ["clientes.id"]),
        sa.ForeignKeyConstraint(["tecnico_responsavel_id"], ["usuarios.id"]),
        sa.ForeignKeyConstraint(["criado_por_id"], ["usuarios.id"]),
        sa.ForeignKeyConstraint(["atualizado_por_id"], ["usuarios.id"]),
        sa.ForeignKeyConstraint(["laudo_origem_id"], ["laudos_tecnicos.id"]),
        sa.UniqueConstraint("public_uuid"),
        sa.UniqueConstraint("verification_token"),
        sa.UniqueConstraint("organization_id", "numero", name="uq_laudo_org_numero"),
    )
    op.create_index("ix_laudos_os_id", "laudos_tecnicos", ["os_id"])
    op.create_index("ix_laudos_cliente_id", "laudos_tecnicos", ["cliente_id"])
    op.create_index("ix_laudos_status", "laudos_tecnicos", ["status"])
    op.create_index("ix_laudos_emitido_em", "laudos_tecnicos", ["emitido_em"])
    op.create_index("ix_laudos_public_uuid", "laudos_tecnicos", ["public_uuid"])
    op.create_index("ix_laudos_verification_token", "laudos_tecnicos", ["verification_token"])

    op.create_table(
        "laudo_fotos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("laudo_id", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.String(length=30), nullable=False),
        sa.Column("legenda", sa.String(length=255), nullable=True),
        sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("nome_original", sa.String(length=255), nullable=True),
        sa.Column("storage_key", sa.String(length=600), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("tamanho_bytes", sa.Integer(), nullable=False),
        sa.Column("largura", sa.Integer(), nullable=True),
        sa.Column("altura", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["laudo_id"], ["laudos_tecnicos.id"]),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
    )
    op.create_index("ix_laudo_fotos_laudo_tipo", "laudo_fotos", ["laudo_id", "tipo"])

    op.create_table(
        "laudo_eventos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("laudo_id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=True),
        sa.Column("tipo", sa.String(length=30), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("dados", sa.JSON(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["laudo_id"], ["laudos_tecnicos.id"]),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
    )
    op.create_index("ix_laudo_eventos_laudo", "laudo_eventos", ["laudo_id", "criado_em"])


def downgrade():
    op.drop_index("ix_laudo_eventos_laudo", table_name="laudo_eventos")
    op.drop_table("laudo_eventos")
    op.drop_index("ix_laudo_fotos_laudo_tipo", table_name="laudo_fotos")
    op.drop_table("laudo_fotos")
    op.drop_index("ix_laudos_verification_token", table_name="laudos_tecnicos")
    op.drop_index("ix_laudos_public_uuid", table_name="laudos_tecnicos")
    op.drop_index("ix_laudos_emitido_em", table_name="laudos_tecnicos")
    op.drop_index("ix_laudos_status", table_name="laudos_tecnicos")
    op.drop_index("ix_laudos_cliente_id", table_name="laudos_tecnicos")
    op.drop_index("ix_laudos_os_id", table_name="laudos_tecnicos")
    op.drop_table("laudos_tecnicos")
    op.drop_table("laudo_counters")
