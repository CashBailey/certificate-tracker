"""Update acting_as constraint to include Coordinator

Revision ID: 007
Revises: 006
Create Date: 2026-02-03 00:03:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '007'
down_revision: Union[str, None] = '006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Update acting_as constraint to include Coordinator role."""

    # Drop old check constraint
    op.drop_constraint(
        'ck_certificate_documents_acting_as',
        'certificate_documents',
        schema='certificates'
    )

    # Add new check constraint with Coordinator
    op.create_check_constraint(
        'ck_certificate_documents_acting_as',
        'certificate_documents',
        "acting_as IN ('Self', 'Admin', 'Manager', 'Coordinator')",
        schema='certificates'
    )


def downgrade() -> None:
    """Revert acting_as constraint."""

    # Drop new check constraint
    op.drop_constraint(
        'ck_certificate_documents_acting_as',
        'certificate_documents',
        schema='certificates'
    )

    # Restore old check constraint
    op.create_check_constraint(
        'ck_certificate_documents_acting_as',
        'certificate_documents',
        "acting_as IN ('Self', 'Admin', 'Manager')",
        schema='certificates'
    )
