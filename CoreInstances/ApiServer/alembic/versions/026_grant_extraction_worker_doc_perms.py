"""Grant missing DB permissions for extraction and email-intake workers.

Migration 022 created worker roles but omitted grants on several tables:
- laredo_extraction_worker: certificate_documents (SELECT/UPDATE),
  email_intake_messages (SELECT), notifications schema USAGE
- laredo_email_intake_worker: certificate_documents (SELECT/INSERT + seq),
  email_intake_messages (SELECT/UPDATE — only INSERT was granted)

Revision ID: 026
Revises: 025
Create Date: 2026-03-17
"""

from alembic import op

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Extraction worker: missing grants
    # ------------------------------------------------------------------
    # certificate_documents: reads doc metadata, updates file_type
    op.execute(
        "GRANT SELECT, UPDATE ON TABLE certificates.certificate_documents "
        "TO laredo_extraction_worker;"
    )
    # notifications schema access for email threading on name-mismatch rejection
    op.execute(
        "GRANT USAGE ON SCHEMA notifications TO laredo_extraction_worker;"
    )
    op.execute(
        "GRANT SELECT ON TABLE notifications.email_intake_messages "
        "TO laredo_extraction_worker;"
    )

    # ------------------------------------------------------------------
    # Email intake worker: missing grants
    # ------------------------------------------------------------------
    # certificate_documents: SELECT for duplicate check, INSERT for new docs
    op.execute(
        "GRANT SELECT, INSERT ON TABLE certificates.certificate_documents "
        "TO laredo_email_intake_worker;"
    )
    op.execute(
        "GRANT USAGE ON SEQUENCE certificates.certificate_documents_id_seq "
        "TO laredo_email_intake_worker;"
    )
    # email_intake_messages: SELECT + UPDATE needed (only INSERT was granted in 022)
    op.execute(
        "GRANT SELECT, UPDATE ON TABLE notifications.email_intake_messages "
        "TO laredo_email_intake_worker;"
    )


def downgrade() -> None:
    # Email intake worker
    op.execute(
        "REVOKE SELECT, UPDATE ON TABLE notifications.email_intake_messages "
        "FROM laredo_email_intake_worker;"
    )
    op.execute(
        "REVOKE USAGE ON SEQUENCE certificates.certificate_documents_id_seq "
        "FROM laredo_email_intake_worker;"
    )
    op.execute(
        "REVOKE SELECT, INSERT ON TABLE certificates.certificate_documents "
        "FROM laredo_email_intake_worker;"
    )
    # Extraction worker
    op.execute(
        "REVOKE SELECT ON TABLE notifications.email_intake_messages "
        "FROM laredo_extraction_worker;"
    )
    op.execute(
        "REVOKE USAGE ON SCHEMA notifications FROM laredo_extraction_worker;"
    )
    op.execute(
        "REVOKE SELECT, UPDATE ON TABLE certificates.certificate_documents "
        "FROM laredo_extraction_worker;"
    )
