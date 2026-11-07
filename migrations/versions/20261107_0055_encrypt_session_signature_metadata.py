"""Encrypt legacy session and signature metadata in place.

Revision ID: 20261107_0055
Revises: 20261107_0054
"""
import sqlalchemy as sa
from alembic import op

from app.utils.field_crypto import decrypt_value, encrypt_value, is_encrypted

revision = "20261107_0055"
down_revision = "20261107_0054"
branch_labels = None
depends_on = None

FIELDS = {
    "user_sessions": ("ip_address", "user_agent"),
    "order_signatures": ("signer_name", "ip_address"),
}


def _encrypt_rows(connection, table, columns):
    last_id = 0
    field_list = ", ".join(columns)
    while True:
        rows = connection.execute(sa.text(
            f"SELECT id, {field_list} FROM {table} WHERE id > :last_id "
            "ORDER BY id LIMIT 200"
        ), {"last_id": last_id}).mappings().all()
        if not rows:
            break
        for row in rows:
            values = {"id": row["id"]}
            changed = False
            for column in columns:
                raw = row[column]
                if raw and is_encrypted(raw):
                    decrypt_value(raw)  # A bad key/ciphertext must fail the migration.
                    values[column] = raw
                else:
                    values[column] = encrypt_value(raw)
                    changed |= bool(raw)
            if changed:
                assignments = ", ".join(f"{column} = :{column}" for column in columns)
                connection.execute(sa.text(
                    f"UPDATE {table} SET {assignments} WHERE id = :id"
                ), values)
        last_id = rows[-1]["id"]


def upgrade():
    with op.batch_alter_table("user_sessions") as batch:
        batch.alter_column(
            "ip_address", existing_type=sa.String(length=45), type_=sa.Text(),
            existing_nullable=True,
        )
        batch.alter_column(
            "user_agent", existing_type=sa.String(length=300), type_=sa.Text(),
            existing_nullable=True,
        )
    with op.batch_alter_table("order_signatures") as batch:
        batch.alter_column(
            "signer_name", existing_type=sa.String(length=120), type_=sa.Text(),
            existing_nullable=False,
        )
        batch.alter_column(
            "ip_address", existing_type=sa.String(length=45), type_=sa.Text(),
            existing_nullable=True,
        )
    connection = op.get_bind()
    for table, columns in FIELDS.items():
        _encrypt_rows(connection, table, columns)


def downgrade():
    raise RuntimeError(
        "Downgrade de metadados cifrados pode truncar dados; restaure backup validado."
    )
