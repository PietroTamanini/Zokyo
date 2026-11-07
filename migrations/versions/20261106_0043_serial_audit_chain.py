"""Serialize audit event hashing through a transactional chain head.

Revision ID: 20261106_0043
Revises: 20261106_0042
"""
import sqlalchemy as sa
from alembic import op

revision = "20261106_0043"
down_revision = "20261106_0042"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    events = sa.table(
        "eventos_log",
        sa.column("id", sa.Integer()),
        sa.column("organization_id", sa.Integer()),
        sa.column("usuario_id", sa.Integer()),
        sa.column("usuario_nome", sa.String()),
        sa.column("tipo", sa.String()),
        sa.column("modulo", sa.String()),
        sa.column("operacao", sa.String()),
        sa.column("descricao", sa.Text()),
        sa.column("criado_em", sa.DateTime()),
        sa.column("previous_hash", sa.String()),
        sa.column("integrity_hash", sa.String()),
    )
    from app.models.evento_log import EventoLog

    previous = "GENESIS"
    rows = connection.execute(sa.select(events).order_by(events.c.id)).mappings().all()
    for row in rows:
        audit_event = EventoLog(
            organization_id=row["organization_id"], usuario_id=row["usuario_id"],
            usuario_nome=row["usuario_nome"], tipo=row["tipo"], modulo=row["modulo"],
            operacao=row["operacao"], descricao=row["descricao"], criado_em=row["criado_em"],
            previous_hash=previous,
        )
        digest = audit_event.calculate_integrity_hash()
        if row["integrity_hash"]:
            if row["previous_hash"] != previous or row["integrity_hash"] != digest:
                raise RuntimeError(
                    f"Cadeia de auditoria inconsistente no evento {row['id']}; "
                    "investigue antes de continuar a migration."
                )
        else:
            connection.execute(
                sa.update(events).where(events.c.id == row["id"]).values(
                    previous_hash=previous, integrity_hash=digest,
                )
            )
        previous = digest
    op.create_table(
        "audit_chain_head",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("last_hash", sa.String(length=64), nullable=False),
    )
    connection.execute(
        sa.text("INSERT INTO audit_chain_head (id, last_hash) VALUES (1, :last_hash)"),
        {"last_hash": previous},
    )


def downgrade():
    op.drop_table("audit_chain_head")
