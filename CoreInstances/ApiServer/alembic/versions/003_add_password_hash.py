"""Add password_hash and is_active columns to employees

Revision ID: 003
Revises: 002
Create Date: 2026-02-02 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add authentication columns to employees table."""
    # Add password_hash column (nullable initially for existing users)
    op.add_column(
        'employees',
        sa.Column('password_hash', sa.String(255), nullable=True),
        schema='certificates'
    )

    # Add is_active column with default True
    op.add_column(
        'employees',
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        schema='certificates'
    )

    # Admin account starts with NULL password_hash.
    # Use POST /api/employees/{id}/send-setup-email or the forgot-password
    # flow to set the initial password after deployment (CRIT-01).


def downgrade() -> None:
    """Remove authentication columns from employees table."""
    op.drop_column('employees', 'is_active', schema='certificates')
    op.drop_column('employees', 'password_hash', schema='certificates')
