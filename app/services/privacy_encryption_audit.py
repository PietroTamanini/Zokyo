"""Read-only inventory and authentication check of privacy ciphertexts.

Never returns field values. The scan covers the current database, not backups.
"""
from sqlalchemy import text

from app.extensions import db
from app.utils.field_crypto import FieldDecryptionError, PREFIX, decrypt_value


PRIVACY_ENCRYPTED_COLUMNS = {
    "data_subject_requests": (
        "observacoes", "requester_name", "requester_email",
        "identity_reference", "response_notes", "delivery_reference",
    ),
    "data_subject_request_revisions": ("snapshot",),
    "privacy_incidents": (
        "title", "description", "affected_data", "notification_reference",
        "notification_decision", "corrective_actions",
    ),
    "privacy_incident_revisions": ("snapshot",),
    "notifications": ("recipient", "payload", "last_error"),
    "user_sessions": ("ip_address", "user_agent"),
    "order_signatures": ("signer_name", "ip_address"),
}


def scan_privacy_encryption():
    """Return plaintext and unreadable counts across every tenant, without PII."""
    plaintext = {}
    unreadable = {}
    for table, columns in PRIVACY_ENCRYPTED_COLUMNS.items():
        for column in columns:
            count = db.session.execute(text(
                f"SELECT COUNT(*) FROM {table} WHERE {column} IS NOT NULL "
                f"AND {column} <> '' AND {column} NOT LIKE :prefix"
            ), {"prefix": f"{PREFIX}%"}).scalar_one()
            key = f"{table}.{column}"
            plaintext[key] = int(count)
            unreadable[key] = 0
            rows = db.session.execute(text(
                f"SELECT {column} FROM {table} WHERE {column} LIKE :prefix"
            ), {"prefix": f"{PREFIX}%"}).yield_per(200)
            for (value,) in rows:
                # MariaDB may compare LIKE case-insensitively; the marker is
                # intentionally case-sensitive in decrypt_value.
                if not value.startswith(PREFIX):
                    plaintext[key] += 1
                    continue
                try:
                    decrypted = decrypt_value(value)
                    if decrypted.startswith(PREFIX):
                        unreadable[key] += 1
                except FieldDecryptionError:
                    unreadable[key] += 1
    return {"plaintext": plaintext, "unreadable": unreadable}


def count_privacy_plaintext():
    """Compatibility helper for callers needing only legacy plaintext counts."""
    return scan_privacy_encryption()["plaintext"]
