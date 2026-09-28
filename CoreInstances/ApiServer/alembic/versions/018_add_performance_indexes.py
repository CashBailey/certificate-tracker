"""Add performance indexes for reports and notification queries

Adds indexes to support:
- Monthly report: verified_certificate_records.created_at for date-range queries
- Notification queue: compound index on (recipient_employee_id, delivered)

Revision ID: 018
Revises: 017
"""

from alembic import op


# revision identifiers
revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Index for monthly report: list_verified_records_created_between
    op.create_index(
        "ix_verified_certificate_records_created_at",
        "verified_certificate_records",
        ["created_at"],
        schema="certificates",
    )
    # Compound index for notification queue processing
    op.create_index(
        "ix_notification_events_recipient_delivered",
        "notification_events",
        ["recipient_employee_id", "delivered"],
        schema="notifications",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_notification_events_recipient_delivered",
        table_name="notification_events",
        schema="notifications",
    )
    op.drop_index(
        "ix_verified_certificate_records_created_at",
        table_name="verified_certificate_records",
        schema="certificates",
    )
