"""Add missing performance and security indexes

Revision ID: 023
Revises: 022
Create Date: 2026-02-26

Adds:
- Index on password_reset_tokens.expires_at (MED-16): purge queries that scan for
  expired tokens perform a full table scan without this index.
- Index on notification_events.recipient_employee_id (MED-04): queries that load all
  notifications for a user without a delivered filter perform a full table scan.
  (A compound index on (recipient_employee_id, delivered) was added in migration 018,
  but a standalone index on recipient_employee_id covers unfiltered per-user lookups.)
"""

import sqlalchemy as sa
from alembic import op

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # MED-16: index on expires_at to avoid full table scan when purging expired tokens.
    op.create_index(
        "ix_password_reset_tokens_expires_at",
        "password_reset_tokens",
        ["expires_at"],
        schema="certificates",
    )

    # MED-04: standalone index on recipient_employee_id for per-user notification
    # queries that do not filter on the delivered column.
    op.create_index(
        "ix_notification_events_recipient_employee_id",
        "notification_events",
        ["recipient_employee_id"],
        schema="notifications",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_notification_events_recipient_employee_id",
        table_name="notification_events",
        schema="notifications",
    )

    op.drop_index(
        "ix_password_reset_tokens_expires_at",
        table_name="password_reset_tokens",
        schema="certificates",
    )
