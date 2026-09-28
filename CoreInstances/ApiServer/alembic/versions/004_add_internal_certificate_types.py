"""Add internal certificate types for LMS, HIPAA, and Employee Policies

Revision ID: 004
Revises: 003
Create Date: 2026-02-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Insert new certificate types for internal documents."""

    # Insert certificate types for the new internal templates
    # Note: These certificates typically don't expire (validity_period_days is NULL)
    op.execute("""
        INSERT INTO certificates.certificate_types (name, description, validity_period_days)
        VALUES
            ('LMS Certificate of Completion', 'City of Laredo LMS training completion certificate', NULL),
            ('HIPAA Acknowledgment', 'HIPAA privacy and confidentiality acknowledgment form', NULL),
            ('Employee Policies Acknowledgment', 'Employee policies and procedures acknowledgment', NULL)
        ON CONFLICT (name) DO NOTHING
    """)


def downgrade() -> None:
    """Remove internal certificate types."""

    op.execute("""
        DELETE FROM certificates.certificate_types
        WHERE name IN (
            'LMS Certificate of Completion',
            'HIPAA Acknowledgment',
            'Employee Policies Acknowledgment'
        )
    """)
