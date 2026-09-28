"""Seed initial data

Revision ID: 002
Revises: 001
Create Date: 2026-02-02 12:01:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Insert seed data."""

    # Insert admin employee
    op.execute("""
        INSERT INTO certificates.employees (employee_number, first_name, last_name, email, role)
        VALUES ('ADMIN001', 'System', 'Administrator', 'admin@ci.laredo.tx.us', 'Admin')
        ON CONFLICT (email) DO NOTHING
    """)

    # Insert certificate types matching initial templates
    op.execute("""
        INSERT INTO certificates.certificate_types (name, description, validity_period_days)
        VALUES
            ('Commercial Driver License (CDL)', 'Texas Commercial Driver License required for operating commercial vehicles', 1825),
            ('First Aid & CPR Certification', 'American Red Cross or equivalent First Aid and CPR certification', 730),
            ('Hazmat Transportation Certification', 'DOT Hazardous Materials Transportation certification', 1095)
        ON CONFLICT (name) DO NOTHING
    """)


def downgrade() -> None:
    """Remove seed data."""

    op.execute("DELETE FROM certificates.certificate_types WHERE name IN ('Commercial Driver License (CDL)', 'First Aid & CPR Certification', 'Hazmat Transportation Certification')")
    op.execute("DELETE FROM certificates.employees WHERE employee_number = 'ADMIN001'")
