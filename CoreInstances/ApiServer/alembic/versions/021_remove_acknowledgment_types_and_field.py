"""Remove acknowledgment certificate types and employee_id_extracted column

Revision ID: 021
Revises: 020
Create Date: 2026-02-24

Removes:
- HIPAA Acknowledgment and Employee Policies Acknowledgment certificate types
- employee_id_extracted column from verified_certificate_records
  (was added in 012 specifically for acknowledgment forms)
"""
import sqlalchemy as sa
from alembic import op

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Remove acknowledgment-form certificate types (seeded in migration 004).
    # Will raise IntegrityError if FK-referenced rows still exist — intentional.
    op.execute("""
        DELETE FROM certificates.certificate_types
        WHERE name IN ('HIPAA Acknowledgment', 'Employee Policies Acknowledgment')
    """)

    # Drop the column added in migration 012 for Employee Policies forms.
    op.drop_column("verified_certificate_records", "employee_id_extracted", schema="certificates")


def downgrade() -> None:
    # Restore employee_id_extracted column
    op.add_column(
        "verified_certificate_records",
        sa.Column("employee_id_extracted", sa.String(50), nullable=True),
        schema="certificates",
    )

    # Restore acknowledgment cert types
    op.execute("""
        INSERT INTO certificates.certificate_types (name, description, validity_period_days)
        VALUES
            ('HIPAA Acknowledgment', 'HIPAA privacy and confidentiality acknowledgment form', 365),
            ('Employee Policies Acknowledgment', 'Employee policies and procedures acknowledgment', 365)
        ON CONFLICT (name) DO NOTHING
    """)
