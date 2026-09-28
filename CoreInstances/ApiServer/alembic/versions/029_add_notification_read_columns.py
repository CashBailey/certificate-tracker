"""Add read/read_at columns to notification_events.

Previously the API mapped 'delivered' to 'read' in the response layer.
This migration adds proper read tracking columns so read status is
independent of delivery status.

Revision ID: 029
Revises: 028
Create Date: 2026-03-17
"""

from alembic import op

revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE notifications.notification_events "
        "ADD COLUMN read BOOLEAN NOT NULL DEFAULT false;"
    )
    op.execute(
        "ALTER TABLE notifications.notification_events "
        "ADD COLUMN read_at TIMESTAMP WITH TIME ZONE;"
    )
    # Backfill: if already delivered, mark as read too
    op.execute(
        "UPDATE notifications.notification_events "
        "SET read = delivered, read_at = delivered_at "
        "WHERE delivered = true;"
    )
    op.execute(
        "CREATE INDEX ix_notification_events_recipient_read "
        "ON notifications.notification_events(recipient_employee_id, read);"
    )


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS notifications.ix_notification_events_recipient_read;"
    )
    op.execute(
        "ALTER TABLE notifications.notification_events DROP COLUMN read_at;"
    )
    op.execute(
        "ALTER TABLE notifications.notification_events DROP COLUMN read;"
    )
