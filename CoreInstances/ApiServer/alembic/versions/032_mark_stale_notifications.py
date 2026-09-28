"""Mark pre-digest undelivered notifications as delivered (backlog cleanup).

The digest system replaces the per-notification email pipeline. The 77K+
stale undelivered notifications should NOT be emailed as a giant digest.
They remain in the database for audit and in-app notification bell purposes
but are marked delivered so the digest pipeline starts fresh.

Date guard: only marks notifications created before 2026-03-20 (deployment
date). Adjust if deploying on a different date.

Revision ID: 032
Revises: 031
Create Date: 2026-03-19
"""

from alembic import op

revision = "032"
down_revision = "031"


def upgrade():
    op.execute("""
        UPDATE notifications.notification_events
        SET delivered = true,
            delivered_at = NOW()
        WHERE delivered = false
          AND created_at < '2026-03-20 00:00:00+00';
    """)


def downgrade():
    # Cannot reliably undo: notifications may have been genuinely delivered
    # after this migration ran. The stale notifications should not be emailed
    # regardless, so this is intentionally a no-op.
    pass
