"""Add retention and legal hold fields

Revision ID: 008
Revises: 007
Create Date: 2026-02-03 00:04:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '008'
down_revision: Union[str, None] = '007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add retention fields to documents and records, create tombstones table."""

    # Add retention fields to certificate_documents
    op.add_column(
        'certificate_documents',
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        schema='certificates'
    )
    op.add_column(
        'certificate_documents',
        sa.Column('legal_hold', sa.Boolean(), server_default='false', nullable=False),
        schema='certificates'
    )
    op.add_column(
        'certificate_documents',
        sa.Column('retention_expires_at', sa.DateTime(timezone=True), nullable=True),
        schema='certificates'
    )

    # Create index for soft delete queries
    op.create_index(
        'ix_certificate_documents_deleted_at',
        'certificate_documents',
        ['deleted_at'],
        schema='certificates'
    )

    # Create index for retention purge queries
    op.create_index(
        'ix_certificate_documents_retention_expires_at',
        'certificate_documents',
        ['retention_expires_at'],
        schema='certificates',
        postgresql_where=sa.text('deleted_at IS NOT NULL AND retention_expires_at IS NOT NULL')
    )

    # Add retention fields to verified_certificate_records
    op.add_column(
        'verified_certificate_records',
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        schema='certificates'
    )
    op.add_column(
        'verified_certificate_records',
        sa.Column('legal_hold', sa.Boolean(), server_default='false', nullable=False),
        schema='certificates'
    )

    # Create index for soft delete queries on verified records
    op.create_index(
        'ix_verified_certificate_records_deleted_at',
        'verified_certificate_records',
        ['deleted_at'],
        schema='certificates'
    )

    # Create deletion tombstones table in audit schema
    op.create_table(
        'deletion_tombstones',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('entity_type', sa.String(100), nullable=False),
        sa.Column('entity_id', sa.Integer(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column('deleted_by_id', sa.Integer(), nullable=True),
        sa.Column('deletion_reason', sa.String(500), nullable=True),
        sa.Column('entity_metadata', postgresql.JSONB(), nullable=True),
        schema='audit'
    )

    # Create indexes for tombstone queries
    op.create_index(
        'ix_deletion_tombstones_entity',
        'deletion_tombstones',
        ['entity_type', 'entity_id'],
        schema='audit'
    )
    op.create_index(
        'ix_deletion_tombstones_deleted_at',
        'deletion_tombstones',
        ['deleted_at'],
        schema='audit'
    )


def downgrade() -> None:
    """Remove retention fields and tombstones table."""

    # Drop tombstones table and indexes
    op.drop_index('ix_deletion_tombstones_deleted_at', table_name='deletion_tombstones', schema='audit')
    op.drop_index('ix_deletion_tombstones_entity', table_name='deletion_tombstones', schema='audit')
    op.drop_table('deletion_tombstones', schema='audit')

    # Drop verified_certificate_records columns and indexes
    op.drop_index('ix_verified_certificate_records_deleted_at', table_name='verified_certificate_records', schema='certificates')
    op.drop_column('verified_certificate_records', 'legal_hold', schema='certificates')
    op.drop_column('verified_certificate_records', 'deleted_at', schema='certificates')

    # Drop certificate_documents columns and indexes
    op.drop_index('ix_certificate_documents_retention_expires_at', table_name='certificate_documents', schema='certificates')
    op.drop_index('ix_certificate_documents_deleted_at', table_name='certificate_documents', schema='certificates')
    op.drop_column('certificate_documents', 'retention_expires_at', schema='certificates')
    op.drop_column('certificate_documents', 'legal_hold', schema='certificates')
    op.drop_column('certificate_documents', 'deleted_at', schema='certificates')
