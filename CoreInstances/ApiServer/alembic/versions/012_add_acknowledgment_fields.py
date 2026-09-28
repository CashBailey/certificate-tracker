"""Add acknowledgment fields and update validity periods

Adds:
- employee_id_extracted column to verified_certificate_records for Employee Policies forms
- Updates validity_period_days to 365 for HIPAA and Employee Policies (annual renewal)

Revision ID: 012
Revises: 011
Create Date: 2026-02-03 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '012'
down_revision: Union[str, None] = '011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add employee_id_extracted column and update validity periods."""

    # ===========================================
    # Add employee_id_extracted column
    # ===========================================
    # For acknowledgment forms (like Employee Policies), the employee ID
    # may be printed on the form and extracted during OCR processing.
    op.add_column(
        'verified_certificate_records',
        sa.Column(
            'employee_id_extracted',
            sa.String(50),
            nullable=True
        ),
        schema='certificates'
    )

    # ===========================================
    # Update validity periods for acknowledgments
    # ===========================================
    # HIPAA and Employee Policies acknowledgments require annual renewal (365 days)
    op.execute("""
        UPDATE certificates.certificate_types
        SET validity_period_days = 365,
            updated_at = CURRENT_TIMESTAMP
        WHERE name IN ('HIPAA Acknowledgment', 'Employee Policies Acknowledgment')
    """)


def downgrade() -> None:
    """Remove employee_id_extracted column and revert validity periods."""

    # Revert validity periods to NULL (no expiration)
    op.execute("""
        UPDATE certificates.certificate_types
        SET validity_period_days = NULL,
            updated_at = CURRENT_TIMESTAMP
        WHERE name IN ('HIPAA Acknowledgment', 'Employee Policies Acknowledgment')
    """)

    # Remove employee_id_extracted column
    op.drop_column('verified_certificate_records', 'employee_id_extracted', schema='certificates')
