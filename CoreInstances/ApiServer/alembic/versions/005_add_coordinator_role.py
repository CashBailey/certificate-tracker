"""Add Coordinator role and update check constraint

Revision ID: 005
Revises: 004
Create Date: 2026-02-03 00:01:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '005'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add Coordinator role to check constraint and migrate Admin user."""

    # Drop old check constraint
    op.drop_constraint('ck_employees_role', 'employees', schema='certificates')

    # Add new check constraint with Coordinator role
    op.create_check_constraint(
        'ck_employees_role',
        'employees',
        "role IN ('Coordinator', 'Admin', 'Manager', 'Reviewer', 'Employee')",
        schema='certificates'
    )

    # Migrate existing Admin user to Coordinator
    op.execute("""
        UPDATE certificates.employees
        SET role = 'Coordinator'
        WHERE role = 'Admin'
    """)


def downgrade() -> None:
    """Revert Coordinator role changes."""

    # Migrate Coordinator back to Admin
    op.execute("""
        UPDATE certificates.employees
        SET role = 'Admin'
        WHERE role = 'Coordinator'
    """)

    # Drop new check constraint
    op.drop_constraint('ck_employees_role', 'employees', schema='certificates')

    # Restore old check constraint without Coordinator
    op.create_check_constraint(
        'ck_employees_role',
        'employees',
        "role IN ('Admin', 'Manager', 'Reviewer', 'Employee')",
        schema='certificates'
    )
