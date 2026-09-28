"""Grant email intake worker INSERT/SELECT on extraction_runs.

The email intake worker creates an initial extraction_runs record
(in Processing state) when storing a new document. This requires
INSERT and SELECT (for RETURNING) on the extraction_runs table.

Revision ID: 031
Revises: 030
Create Date: 2026-03-19
"""

from alembic import op

revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "GRANT SELECT, INSERT ON TABLE certificates.extraction_runs "
        "TO laredo_email_intake_worker;"
    )
    op.execute(
        "GRANT USAGE ON SEQUENCE certificates.extraction_runs_id_seq "
        "TO laredo_email_intake_worker;"
    )


def downgrade() -> None:
    op.execute(
        "REVOKE SELECT, INSERT ON TABLE certificates.extraction_runs "
        "FROM laredo_email_intake_worker;"
    )
    op.execute(
        "REVOKE USAGE ON SEQUENCE certificates.extraction_runs_id_seq "
        "FROM laredo_email_intake_worker;"
    )
