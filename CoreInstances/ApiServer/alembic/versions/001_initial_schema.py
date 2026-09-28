"""Initial database schema

Revision ID: 001
Revises:
Create Date: 2026-02-02 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all schemas and tables."""

    # Create schemas
    op.execute("CREATE SCHEMA IF NOT EXISTS certificates")
    op.execute("CREATE SCHEMA IF NOT EXISTS notifications")
    op.execute("CREATE SCHEMA IF NOT EXISTS audit")

    # ========== CERTIFICATES SCHEMA ==========

    # employees table
    op.create_table(
        'employees',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('employee_number', sa.String(50), nullable=False),
        sa.Column('first_name', sa.String(100), nullable=False),
        sa.Column('last_name', sa.String(100), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('manager_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_employees'),
        sa.UniqueConstraint('email', name='uq_employees_email'),
        sa.UniqueConstraint('employee_number', name='uq_employees_employee_number'),
        sa.ForeignKeyConstraint(['manager_id'], ['certificates.employees.id'], name='fk_employees_manager_id'),
        sa.CheckConstraint("role IN ('Admin', 'Manager', 'Reviewer', 'Employee')", name='ck_employees_role'),
        schema='certificates'
    )
    op.create_index('ix_employees_role', 'employees', ['role'], schema='certificates')
    op.create_index('ix_employees_manager_id', 'employees', ['manager_id'], schema='certificates')

    # certificate_types table
    op.create_table(
        'certificate_types',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('validity_period_days', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_certificate_types'),
        sa.UniqueConstraint('name', name='uq_certificate_types_name'),
        schema='certificates'
    )

    # requirement_assignments table
    op.create_table(
        'requirement_assignments',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('certificate_type_id', sa.Integer(), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='NotStarted'),
        sa.Column('satisfied_by_id', sa.Integer(), nullable=True),
        sa.Column('waived_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('waived_by_id', sa.Integer(), nullable=True),
        sa.Column('waiver_reason', sa.Text(), nullable=True),
        sa.Column('waiver_expiration', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_requirement_assignments'),
        sa.ForeignKeyConstraint(['employee_id'], ['certificates.employees.id'], name='fk_requirement_assignments_employee_id'),
        sa.ForeignKeyConstraint(['certificate_type_id'], ['certificates.certificate_types.id'], name='fk_requirement_assignments_certificate_type_id'),
        sa.ForeignKeyConstraint(['satisfied_by_id'], ['certificates.verified_certificate_records.id'], name='fk_requirement_assignments_satisfied_by_id', use_alter=True),
        sa.ForeignKeyConstraint(['waived_by_id'], ['certificates.employees.id'], name='fk_requirement_assignments_waived_by_id'),
        schema='certificates'
    )
    op.create_index('ix_requirement_assignments_employee_id', 'requirement_assignments', ['employee_id'], schema='certificates')
    op.create_index('ix_requirement_assignments_due_date', 'requirement_assignments', ['due_date'], schema='certificates')
    op.create_index('ix_requirement_assignments_status', 'requirement_assignments', ['status'], schema='certificates')

    # certificate_documents table
    op.create_table(
        'certificate_documents',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('storage_key', sa.String(500), nullable=False),
        sa.Column('file_name', sa.String(500), nullable=False),
        sa.Column('file_type', sa.String(100), nullable=False),
        sa.Column('file_size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('uploaded_by_id', sa.Integer(), nullable=False),
        sa.Column('acting_as', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_certificate_documents'),
        sa.UniqueConstraint('storage_key', name='uq_certificate_documents_storage_key'),
        sa.ForeignKeyConstraint(['employee_id'], ['certificates.employees.id'], name='fk_certificate_documents_employee_id'),
        sa.ForeignKeyConstraint(['uploaded_by_id'], ['certificates.employees.id'], name='fk_certificate_documents_uploaded_by_id'),
        sa.CheckConstraint("acting_as IN ('Self', 'Admin', 'Manager')", name='ck_certificate_documents_acting_as'),
        sa.CheckConstraint("file_type IN ('application/pdf', 'image/png', 'image/jpeg', 'image/tiff')", name='ck_certificate_documents_file_type'),
        schema='certificates'
    )
    op.create_index('ix_certificate_documents_employee_id', 'certificate_documents', ['employee_id'], schema='certificates')

    # extraction_runs table
    op.create_table(
        'extraction_runs',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('review_state', sa.String(20), nullable=False, server_default='PendingReview'),
        sa.Column('extracted_fields', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('needs_review', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('needs_review_reasons', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.Column('template_id', sa.String(100), nullable=True),
        sa.Column('template_version', sa.Integer(), nullable=True),
        sa.Column('template_match_evidence', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('review_assist', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('reviewed_by_id', sa.Integer(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('review_state_version', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_extraction_runs'),
        sa.ForeignKeyConstraint(['document_id'], ['certificates.certificate_documents.id'], name='fk_extraction_runs_document_id'),
        sa.ForeignKeyConstraint(['reviewed_by_id'], ['certificates.employees.id'], name='fk_extraction_runs_reviewed_by_id'),
        sa.CheckConstraint("review_state IN ('PendingReview', 'Approved', 'Rejected')", name='ck_extraction_runs_review_state'),
        schema='certificates'
    )
    op.create_index('ix_extraction_runs_document_id', 'extraction_runs', ['document_id'], schema='certificates')
    op.create_index('ix_extraction_runs_review_state', 'extraction_runs', ['review_state'], schema='certificates')
    op.create_index('ix_extraction_runs_created_at', 'extraction_runs', ['created_at'], schema='certificates')

    # verified_certificate_records table
    op.create_table(
        'verified_certificate_records',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('extraction_id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('certificate_holder_name', sa.String(200), nullable=True),
        sa.Column('certificate_type', sa.String(200), nullable=True),
        sa.Column('certificate_number', sa.String(100), nullable=True),
        sa.Column('issuing_authority', sa.String(200), nullable=True),
        sa.Column('issue_date', sa.Date(), nullable=True),
        sa.Column('expiration_date', sa.Date(), nullable=True),
        sa.Column('training_hours', sa.Float(), nullable=True),
        sa.Column('license_class', sa.String(50), nullable=True),
        sa.Column('endorsements', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_verified_certificate_records'),
        sa.UniqueConstraint('extraction_id', name='uq_verified_certificate_records_extraction_id'),
        sa.ForeignKeyConstraint(['extraction_id'], ['certificates.extraction_runs.id'], name='fk_verified_certificate_records_extraction_id'),
        sa.ForeignKeyConstraint(['document_id'], ['certificates.certificate_documents.id'], name='fk_verified_certificate_records_document_id'),
        sa.ForeignKeyConstraint(['employee_id'], ['certificates.employees.id'], name='fk_verified_certificate_records_employee_id'),
        schema='certificates'
    )
    op.create_index('ix_verified_certificate_records_employee_id', 'verified_certificate_records', ['employee_id'], schema='certificates')
    op.create_index('ix_verified_certificate_records_expiration_date', 'verified_certificate_records', ['expiration_date'], schema='certificates')

    # ========== NOTIFICATIONS SCHEMA ==========

    # notification_events table
    op.create_table(
        'notification_events',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('notification_type', sa.String(50), nullable=False),
        sa.Column('recipient_employee_id', sa.Integer(), nullable=False),
        sa.Column('subject', sa.String(500), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('dedupe_key', sa.String(500), nullable=False),
        sa.Column('related_requirement_id', sa.Integer(), nullable=True),
        sa.Column('related_certificate_id', sa.Integer(), nullable=True),
        sa.Column('delivered', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_notification_events'),
        sa.UniqueConstraint('dedupe_key', name='uq_notification_events_dedupe_key'),
        sa.ForeignKeyConstraint(['recipient_employee_id'], ['certificates.employees.id'], name='fk_notification_events_recipient_employee_id'),
        sa.CheckConstraint("notification_type IN ('RequirementDueSoon', 'RequirementDueTomorrow', 'RequirementOverdue', 'RequirementEscalation', 'CertificateExpiringSoon', 'CertificateExpired')", name='ck_notification_events_notification_type'),
        schema='notifications'
    )
    op.create_index('ix_notification_events_delivered', 'notification_events', ['delivered'], schema='notifications')
    op.create_index('ix_notification_events_created_at', 'notification_events', ['created_at'], schema='notifications')

    # job_cursors table
    op.create_table(
        'job_cursors',
        sa.Column('job_name', sa.String(100), nullable=False),
        sa.Column('last_success_date', sa.Date(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('job_name', name='pk_job_cursors'),
        schema='notifications'
    )

    # ========== AUDIT SCHEMA ==========

    # audit_logs table
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('actor_type', sa.String(20), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=True),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('target_type', sa.String(100), nullable=False),
        sa.Column('target_id', sa.String(100), nullable=False),
        sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('initiated_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id', name='pk_audit_logs'),
        sa.ForeignKeyConstraint(['employee_id'], ['certificates.employees.id'], name='fk_audit_logs_employee_id'),
        sa.ForeignKeyConstraint(['initiated_by_id'], ['certificates.employees.id'], name='fk_audit_logs_initiated_by_id'),
        sa.CheckConstraint("actor_type IN ('System', 'Employee')", name='ck_audit_logs_actor_type'),
        sa.CheckConstraint("(actor_type = 'System' AND employee_id IS NULL) OR (actor_type = 'Employee' AND employee_id IS NOT NULL)", name='ck_audit_logs_actor_constraints'),
        schema='audit'
    )
    op.create_index('ix_audit_logs_action', 'audit_logs', ['action'], schema='audit')
    op.create_index('ix_audit_logs_target', 'audit_logs', ['target_type', 'target_id'], schema='audit')
    op.create_index('ix_audit_logs_created_at', 'audit_logs', ['created_at'], schema='audit')


def downgrade() -> None:
    """Drop all tables and schemas."""

    # Drop tables in reverse order (respecting foreign keys)
    op.drop_table('audit_logs', schema='audit')
    op.drop_table('job_cursors', schema='notifications')
    op.drop_table('notification_events', schema='notifications')
    op.drop_table('verified_certificate_records', schema='certificates')
    op.drop_table('extraction_runs', schema='certificates')
    op.drop_table('certificate_documents', schema='certificates')
    op.drop_table('requirement_assignments', schema='certificates')
    op.drop_table('certificate_types', schema='certificates')
    op.drop_table('employees', schema='certificates')

    # Drop schemas
    op.execute("DROP SCHEMA IF EXISTS audit CASCADE")
    op.execute("DROP SCHEMA IF EXISTS notifications CASCADE")
    op.execute("DROP SCHEMA IF EXISTS certificates CASCADE")
