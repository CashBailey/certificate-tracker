"""Add BULK_IMPORT to certificate_documents intake_channel constraint

Supports the day-one bulk import workflow where historical certificates
are imported directly as pre-verified records, bypassing extraction.

Revision ID: 016
Revises: 015
"""

from alembic import op


# revision identifiers
revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add BULK_IMPORT to intake_channel check constraint."""
    op.drop_constraint(
        "ck_certificate_documents_intake_channel",
        "certificate_documents",
        schema="certificates",
    )
    op.create_check_constraint(
        "ck_certificate_documents_intake_channel",
        "certificate_documents",
        "intake_channel IN ('MANUAL_UPLOAD', 'EMAIL', 'BULK_IMPORT')",
        schema="certificates",
    )


def downgrade() -> None:
    """Remove BULK_IMPORT from intake_channel check constraint."""
    op.drop_constraint(
        "ck_certificate_documents_intake_channel",
        "certificate_documents",
        schema="certificates",
    )
    op.create_check_constraint(
        "ck_certificate_documents_intake_channel",
        "certificate_documents",
        "intake_channel IN ('MANUAL_UPLOAD', 'EMAIL')",
        schema="certificates",
    )
