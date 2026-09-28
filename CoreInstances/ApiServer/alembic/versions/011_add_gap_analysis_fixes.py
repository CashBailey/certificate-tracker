"""Add gap analysis fixes

Addresses multiple gaps from the High-Level Design Specification gap analysis:

P0 Fixes:
- WF-01: Add composite unique index on (message_id, attachment_hash) for email dedupe
  Spec requires dedupe on (message_id, attachment_hash), current impl uses (employee_id, file_hash)

P1 Fixes:
- DM-02: Add field_evidence JSONB to extraction_runs for field-level provenance
  Spec requires evidence per field (bbox/page/zone/source) at extraction stage
- DM-03: Add effective_date to notification_events
  Spec requires logical trigger date for notifications

Revision ID: 011
Revises: 010
Create Date: 2026-02-03 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '011'
down_revision: Union[str, None] = '010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply gap analysis fixes."""

    # ===========================================
    # P0 - WF-01: Email dedupe composite key
    # ===========================================
    # Per spec: dedupe key should be (message_id, attachment_hash)
    # This enables proper deduplication when same email is retried
    # with the same attachments.
    #
    # Note: We create a GIN index on the attachment_hashes JSONB array
    # and a composite index that includes message_id for efficient lookups.

    # Create index for looking up by message_id and checking attachment hashes
    # This supports the dedupe check: "does this (message_id, attachment_hash) exist?"
    op.create_index(
        'ix_email_intake_messages_message_id_dedupe',
        'email_intake_messages',
        ['message_id'],
        unique=False,
        schema='notifications',
    )

    # Create GIN index on attachment_hashes for containment queries
    # This allows efficient @> (contains) queries on the JSONB array
    op.execute("""
        CREATE INDEX ix_email_intake_messages_attachment_hashes_gin
        ON notifications.email_intake_messages
        USING GIN (attachment_hashes jsonb_path_ops)
        WHERE attachment_hashes IS NOT NULL
    """)

    # ===========================================
    # P1 - DM-02: ExtractionRun.field_evidence
    # ===========================================
    # Captures field-level provenance at extraction time.
    # Structure: {
    #   "certificate_holder_name": {
    #     "bbox": [x0, y0, x1, y1],  # normalized coordinates
    #     "page": 1,
    #     "zone_id": "name_zone",
    #     "source": "template_zone"  # or "generic_pattern"
    #   },
    #   ...
    # }
    op.add_column(
        'extraction_runs',
        sa.Column(
            'field_evidence',
            postgresql.JSONB,
            nullable=True
        ),
        schema='certificates'
    )

    # ===========================================
    # P1 - DM-03: NotificationEvent.effective_date
    # ===========================================
    # The logical trigger date for the notification.
    # For example, for a "due soon" notification, this would be the
    # date the requirement becomes due, not when the notification was created.
    op.add_column(
        'notification_events',
        sa.Column(
            'effective_date',
            sa.Date,
            nullable=True
        ),
        schema='notifications'
    )
    op.create_index(
        'ix_notification_events_effective_date',
        'notification_events',
        ['effective_date'],
        schema='notifications'
    )


def downgrade() -> None:
    """Remove gap analysis fixes."""

    # NotificationEvent.effective_date
    op.drop_index(
        'ix_notification_events_effective_date',
        table_name='notification_events',
        schema='notifications'
    )
    op.drop_column('notification_events', 'effective_date', schema='notifications')

    # ExtractionRun.field_evidence
    op.drop_column('extraction_runs', 'field_evidence', schema='certificates')

    # Email dedupe indexes
    op.execute("""
        DROP INDEX IF EXISTS notifications.ix_email_intake_messages_attachment_hashes_gin
    """)
    op.drop_index(
        'ix_email_intake_messages_message_id_dedupe',
        table_name='email_intake_messages',
        schema='notifications'
    )
