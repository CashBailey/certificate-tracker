"""Backfill due_date for satisfied requirements.

When a certificate is approved and linked to a requirement, the due_date
should reflect issue_date + validity_period_days. Previously this was never
updated, so satisfied requirements retain their original (stale) due dates.

This migration recalculates due_date for all satisfied requirements that
have a linked verified record with an issue_date and a certificate type
with a non-null, positive validity_period_days.

Revision ID: 027
Revises: 026
Create Date: 2026-03-17
"""

from alembic import op

revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE certificates.requirement_assignments ra
        SET due_date = vcr.issue_date + (ct.validity_period_days * INTERVAL '1 day')
        FROM certificates.verified_certificate_records vcr,
             certificates.certificate_types ct
        WHERE ra.satisfied_by_id = vcr.id
          AND ra.certificate_type_id = ct.id
          AND vcr.issue_date IS NOT NULL
          AND ct.validity_period_days IS NOT NULL
          AND ct.validity_period_days > 0
        """
    )


def downgrade() -> None:
    # Cannot reliably restore original due_date values
    pass
