"""Add file hash for document deduplication

Revision ID: 009
Revises: 008
Create Date: 2026-02-03 00:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '009'
down_revision: Union[str, None] = '008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add file_hash column for attachment deduplication."""

    # Add file_hash column to certificate_documents
    # SHA-256 hash stored as 64-character hex string
    op.add_column(
        'certificate_documents',
        sa.Column('file_hash', sa.String(64), nullable=True),
        schema='certificates'
    )

    # Create index on file_hash for fast duplicate lookups
    op.create_index(
        'ix_certificate_documents_file_hash',
        'certificate_documents',
        ['file_hash'],
        schema='certificates'
    )

    # Create unique constraint on (employee_id, file_hash) to prevent
    # duplicate uploads for the same employee
    # Note: This allows the same file to be uploaded by different employees
    # (which is valid - they could both have the same certificate)
    op.create_index(
        'ix_certificate_documents_employee_file_hash',
        'certificate_documents',
        ['employee_id', 'file_hash'],
        unique=True,
        schema='certificates',
        postgresql_where=sa.text('file_hash IS NOT NULL AND deleted_at IS NULL')
    )


def downgrade() -> None:
    """Remove file_hash column and indexes."""

    op.drop_index(
        'ix_certificate_documents_employee_file_hash',
        table_name='certificate_documents',
        schema='certificates'
    )
    op.drop_index(
        'ix_certificate_documents_file_hash',
        table_name='certificate_documents',
        schema='certificates'
    )
    op.drop_column('certificate_documents', 'file_hash', schema='certificates')
