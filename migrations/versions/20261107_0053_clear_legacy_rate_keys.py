"""Drop short-lived API limit counters that stored raw IPs.

Revision ID: 20261107_0053
Revises: 20261107_0052
"""
from alembic import op

revision = "20261107_0053"
down_revision = "20261107_0052"
branch_labels = None
depends_on = None


def upgrade():
    # The old keys cannot be converted without a deployment secret. These are
    # ephemeral counters, so clear them once before pseudonymous keys are used.
    op.execute("DELETE FROM api_rate_limits")


def downgrade():
    # Expired counters and raw IPs are deliberately not recreated.
    pass
