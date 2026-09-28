"""Grant scheduler worker SELECT on certificate tables.

The scheduler worker needs to read verified_certificate_records and
certificate_types to generate expiration notifications.

Revision ID: 028
Revises: 027
Create Date: 2026-03-17
"""

from alembic import op

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "GRANT SELECT ON TABLE certificates.verified_certificate_records "
        "TO laredo_scheduler_worker;"
    )
    op.execute(
        "GRANT SELECT ON TABLE certificates.certificate_types "
        "TO laredo_scheduler_worker;"
    )


def downgrade() -> None:
    op.execute(
        "REVOKE SELECT ON TABLE certificates.certificate_types "
        "FROM laredo_scheduler_worker;"
    )
    op.execute(
        "REVOKE SELECT ON TABLE certificates.verified_certificate_records "
        "FROM laredo_scheduler_worker;"
    )
