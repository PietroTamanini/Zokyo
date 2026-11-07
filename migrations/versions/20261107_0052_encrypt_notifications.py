"""Encrypt notification recipient, payload, and delivery error in place.

Revision ID: 20261107_0052
Revises: 20261107_0051
"""
import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

from app.utils.field_crypto import decrypt_value, encrypt_value, is_encrypted

revision = "20261107_0052"
down_revision = "20261107_0051"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("notifications") as batch:
        batch.alter_column(
            "recipient", existing_type=sa.String(length=80), type_=sa.Text(),
            existing_nullable=False,
        )
        batch.alter_column(
            "payload", existing_type=sa.JSON(),
            type_=sa.Text().with_variant(mysql.LONGTEXT(), "mysql"),
            existing_nullable=False,
        )

    connection = op.get_bind()
    rows = connection.execute(sa.text(
        "SELECT id, recipient, payload, last_error FROM notifications ORDER BY id"
    )).mappings()
    for row in rows:
        raw_payload = row["payload"]
        if isinstance(raw_payload, dict):
            raw_payload = json.dumps(raw_payload, ensure_ascii=False, separators=(",", ":"))
        decoded_payload = json.loads(decrypt_value(raw_payload))
        if not isinstance(decoded_payload, dict):
            raise ValueError(f"Payload da notificação #{row['id']} não é objeto JSON.")
        values = {"id": row["id"]}
        for column, raw in (("recipient", row["recipient"]),
                            ("payload", raw_payload), ("last_error", row["last_error"])):
            if raw and is_encrypted(raw):
                decrypt_value(raw)
            values[column] = encrypt_value(raw) if raw and not is_encrypted(raw) else raw
        connection.execute(sa.text(
            "UPDATE notifications SET recipient=:recipient, payload=:payload, "
            "last_error=:last_error WHERE id=:id"
        ), values)


def downgrade():
    raise RuntimeError(
        "Downgrade de notificações cifradas não é seguro. "
        "Use backup validado e migração explícita com revisão dos dados."
    )
