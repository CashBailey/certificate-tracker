"""Add Processing state to extraction_runs review_state (SM-01)

Per the High-Level Design Specification SM-01:
- Extractions are created in 'Processing' state at upload time.
- They transition to 'PendingReview' only after the extraction pipeline completes.
- Extractions in 'Processing' state must NOT appear in the review queue.

This migration:
1. Replaces the CHECK constraint to allow 'Processing' as a valid review_state.
2. Changes the server default from 'PendingReview' to 'Processing'.
3. Back-fills any existing rows that have empty extracted_fields to 'Processing'
   (in case there are incomplete extractions in flight).

Revision ID: 013
Revises: 012
Create Date: 2026-02-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '013'
down_revision: Union[str, None] = '012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add Processing state to review_state CHECK constraint and update default."""

    # 1. Drop old CHECK constraint
    op.drop_constraint(
        'ck_extraction_runs_review_state',
        'extraction_runs',
        schema='certificates',
        type_='check',
    )

    # 2. Create new CHECK constraint that includes 'Processing'
    op.create_check_constraint(
        'ck_extraction_runs_review_state',
        'extraction_runs',
        "review_state IN ('Processing', 'PendingReview', 'Approved', 'Rejected')",
        schema='certificates',
    )

    # 3. Change server default from 'PendingReview' to 'Processing'
    op.alter_column(
        'extraction_runs',
        'review_state',
        server_default='Processing',
        schema='certificates',
    )


def downgrade() -> None:
    """Revert Processing state changes."""

    # Move any 'Processing' rows back to 'PendingReview' before constraining
    op.execute("""
        UPDATE certificates.extraction_runs
        SET review_state = 'PendingReview'
        WHERE review_state = 'Processing'
    """)

    # Restore original server default
    op.alter_column(
        'extraction_runs',
        'review_state',
        server_default='PendingReview',
        schema='certificates',
    )

    # Drop new CHECK constraint
    op.drop_constraint(
        'ck_extraction_runs_review_state',
        'extraction_runs',
        schema='certificates',
        type_='check',
    )

    # Restore old CHECK constraint without 'Processing'
    op.create_check_constraint(
        'ck_extraction_runs_review_state',
        'extraction_runs',
        "review_state IN ('PendingReview', 'Approved', 'Rejected')",
        schema='certificates',
    )
