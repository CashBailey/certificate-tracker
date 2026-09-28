"""Add email intake tracking

Revision ID: 006
Revises: 005
Create Date: 2026-02-03 00:02:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '006'
down_revision: Union[str, None] = '005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add email intake tracking columns and table."""

    # Add intake_channel column to certificate_documents
    op.add_column(
        'certificate_documents',
        sa.Column(
            'intake_channel',
            sa.String(20),
            nullable=False,
            server_default='MANUAL_UPLOAD'
        ),
        schema='certificates'
    )

    # Add source_email_message_id column to certificate_documents
    op.add_column(
        'certificate_documents',
        sa.Column(
            'source_email_message_id',
            sa.Integer(),
            nullable=True
        ),
        schema='certificates'
    )

    # Add check constraint for intake_channel
    op.create_check_constraint(
        'ck_certificate_documents_intake_channel',
        'certificate_documents',
        "intake_channel IN ('MANUAL_UPLOAD', 'EMAIL')",
        schema='certificates'
    )

    # Create email_intake_messages table in notifications schema
    op.create_table(
        'email_intake_messages',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('message_id', sa.String(255), nullable=False),
        sa.Column('from_address', sa.String(255), nullable=False),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('subject', sa.String(500), nullable=True),
        sa.Column('attachment_count', sa.Integer(), nullable=True),
        sa.Column('processing_state', sa.String(50), nullable=False),
        sa.Column('error_reason', sa.String(500), nullable=True),
        sa.Column('employee_id', sa.Integer(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('message_id', name='uq_email_intake_messages_message_id'),
        sa.ForeignKeyConstraint(
            ['employee_id'],
            ['certificates.employees.id'],
            name='fk_email_intake_messages_employee'
        ),
        sa.CheckConstraint(
            "processing_state IN ('PROCESSED', 'QUARANTINED', 'FAILED')",
            name='ck_email_intake_messages_state'
        ),
        schema='notifications'
    )

    # Create indexes for email_intake_messages
    op.create_index(
        'idx_email_intake_from',
        'email_intake_messages',
        ['from_address'],
        schema='notifications'
    )
    op.create_index(
        'idx_email_intake_state',
        'email_intake_messages',
        ['processing_state'],
        schema='notifications'
    )

    # Add foreign key from certificate_documents to email_intake_messages
    op.create_foreign_key(
        'fk_certificate_documents_email_message',
        'certificate_documents',
        'email_intake_messages',
        ['source_email_message_id'],
        ['id'],
        source_schema='certificates',
        referent_schema='notifications'
    )


def downgrade() -> None:
    """Remove email intake tracking."""

    # Drop foreign key from certificate_documents to email_intake_messages
    op.drop_constraint(
        'fk_certificate_documents_email_message',
        'certificate_documents',
        schema='certificates',
        type_='foreignkey'
    )

    # Drop indexes
    op.drop_index('idx_email_intake_state', table_name='email_intake_messages', schema='notifications')
    op.drop_index('idx_email_intake_from', table_name='email_intake_messages', schema='notifications')

    # Drop email_intake_messages table
    op.drop_table('email_intake_messages', schema='notifications')

    # Drop check constraint for intake_channel
    op.drop_constraint(
        'ck_certificate_documents_intake_channel',
        'certificate_documents',
        schema='certificates'
    )

    # Remove columns from certificate_documents
    op.drop_column('certificate_documents', 'source_email_message_id', schema='certificates')
    op.drop_column('certificate_documents', 'intake_channel', schema='certificates')
