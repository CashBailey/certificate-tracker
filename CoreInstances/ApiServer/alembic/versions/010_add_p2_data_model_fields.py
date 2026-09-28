"""Add P2 data model fields

Adds 8 missing fields from the High-Level Design Specification:
- Employee.lms_username_id
- RequirementAssignment.created_by_id
- RequirementAssignment.requested_by_id
- CertificateDocument.target_requirement_id
- EmailIntakeMessage.attachment_hashes
- VerifiedCertificateRecord.reviewed_by_id
- VerifiedCertificateRecord.reviewed_at
- VerifiedCertificateRecord.field_provenance

Revision ID: 010
Revises: 009
Create Date: 2026-02-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '010'
down_revision: Union[str, None] = '009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add P2 data model fields to various tables."""

    # ===========================================
    # 1. Employee.lms_username_id
    # ===========================================
    # LMS (Learning Management System) username/alias for integration
    op.add_column(
        'employees',
        sa.Column('lms_username_id', sa.String(100), nullable=True),
        schema='certificates'
    )
    op.create_index(
        'ix_employees_lms_username_id',
        'employees',
        ['lms_username_id'],
        unique=True,
        schema='certificates',
        postgresql_where=sa.text('lms_username_id IS NOT NULL')
    )

    # ===========================================
    # 2. RequirementAssignment.created_by_id
    # ===========================================
    # Coordinator who created the requirement assignment
    op.add_column(
        'requirement_assignments',
        sa.Column(
            'created_by_id',
            sa.Integer,
            sa.ForeignKey('certificates.employees.id'),
            nullable=True
        ),
        schema='certificates'
    )
    op.create_index(
        'ix_requirement_assignments_created_by_id',
        'requirement_assignments',
        ['created_by_id'],
        schema='certificates'
    )

    # ===========================================
    # 3. RequirementAssignment.requested_by_id
    # ===========================================
    # Optional: supervisor who requested the requirement (origin tracking)
    op.add_column(
        'requirement_assignments',
        sa.Column(
            'requested_by_id',
            sa.Integer,
            sa.ForeignKey('certificates.employees.id'),
            nullable=True
        ),
        schema='certificates'
    )
    op.create_index(
        'ix_requirement_assignments_requested_by_id',
        'requirement_assignments',
        ['requested_by_id'],
        schema='certificates'
    )

    # ===========================================
    # 4. CertificateDocument.target_requirement_id
    # ===========================================
    # Optional link to the requirement this document was uploaded to satisfy
    op.add_column(
        'certificate_documents',
        sa.Column(
            'target_requirement_id',
            sa.Integer,
            sa.ForeignKey('certificates.requirement_assignments.id'),
            nullable=True
        ),
        schema='certificates'
    )
    op.create_index(
        'ix_certificate_documents_target_requirement_id',
        'certificate_documents',
        ['target_requirement_id'],
        schema='certificates'
    )

    # ===========================================
    # 5. EmailIntakeMessage.attachment_hashes
    # ===========================================
    # JSONB array of SHA-256 hashes for all attachments in the email
    # Useful for tracking/forensics and preventing reprocessing
    op.add_column(
        'email_intake_messages',
        sa.Column(
            'attachment_hashes',
            postgresql.JSONB,
            nullable=True,
            server_default='[]'
        ),
        schema='notifications'
    )

    # ===========================================
    # 6. VerifiedCertificateRecord.reviewed_by_id
    # ===========================================
    # Employee who approved the extraction (reviewer attribution)
    op.add_column(
        'verified_certificate_records',
        sa.Column(
            'reviewed_by_id',
            sa.Integer,
            sa.ForeignKey('certificates.employees.id'),
            nullable=True
        ),
        schema='certificates'
    )
    op.create_index(
        'ix_verified_certificate_records_reviewed_by_id',
        'verified_certificate_records',
        ['reviewed_by_id'],
        schema='certificates'
    )

    # ===========================================
    # 7. VerifiedCertificateRecord.reviewed_at
    # ===========================================
    # Timestamp when the extraction was approved
    op.add_column(
        'verified_certificate_records',
        sa.Column(
            'reviewed_at',
            sa.DateTime(timezone=True),
            nullable=True
        ),
        schema='certificates'
    )

    # ===========================================
    # 8. VerifiedCertificateRecord.field_provenance
    # ===========================================
    # JSONB containing per-field provenance information:
    # {
    #   "certificate_holder_name": {
    #     "source_method": "machine_template",
    #     "entry_mode": "confirmed",
    #     "original_machine_value": "...",
    #     "original_machine_confidence": 0.95
    #   },
    #   ...
    # }
    op.add_column(
        'verified_certificate_records',
        sa.Column(
            'field_provenance',
            postgresql.JSONB,
            nullable=True
        ),
        schema='certificates'
    )


def downgrade() -> None:
    """Remove P2 data model fields."""

    # VerifiedCertificateRecord fields
    op.drop_column('verified_certificate_records', 'field_provenance', schema='certificates')
    op.drop_column('verified_certificate_records', 'reviewed_at', schema='certificates')
    op.drop_index(
        'ix_verified_certificate_records_reviewed_by_id',
        table_name='verified_certificate_records',
        schema='certificates'
    )
    op.drop_column('verified_certificate_records', 'reviewed_by_id', schema='certificates')

    # EmailIntakeMessage fields
    op.drop_column('email_intake_messages', 'attachment_hashes', schema='notifications')

    # CertificateDocument fields
    op.drop_index(
        'ix_certificate_documents_target_requirement_id',
        table_name='certificate_documents',
        schema='certificates'
    )
    op.drop_column('certificate_documents', 'target_requirement_id', schema='certificates')

    # RequirementAssignment fields
    op.drop_index(
        'ix_requirement_assignments_requested_by_id',
        table_name='requirement_assignments',
        schema='certificates'
    )
    op.drop_column('requirement_assignments', 'requested_by_id', schema='certificates')
    op.drop_index(
        'ix_requirement_assignments_created_by_id',
        table_name='requirement_assignments',
        schema='certificates'
    )
    op.drop_column('requirement_assignments', 'created_by_id', schema='certificates')

    # Employee fields
    op.drop_index(
        'ix_employees_lms_username_id',
        table_name='employees',
        schema='certificates'
    )
    op.drop_column('employees', 'lms_username_id', schema='certificates')
