"""Grant SELECT on audit.audit_logs to all worker roles.

Migration 022 granted INSERT on audit.audit_logs but not SELECT.
SQLAlchemy uses INSERT ... RETURNING which requires SELECT privilege
in PostgreSQL.  This migration adds the missing SELECT grant to all
three worker roles.  Also re-grants INSERT and USAGE as a safety net
for environments where grants may have been lost.

Revision ID: 030
Revises: 029
Create Date: 2026-03-19
"""

from alembic import op

revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None

_WORKER_ROLES = [
    "laredo_email_intake_worker",
    "laredo_extraction_worker",
    "laredo_scheduler_worker",
]


def upgrade() -> None:
    for role in _WORKER_ROLES:
        op.execute(f"GRANT USAGE ON SCHEMA audit TO {role};")
        op.execute(f"GRANT SELECT, INSERT ON TABLE audit.audit_logs TO {role};")
        op.execute(f"GRANT USAGE ON SEQUENCE audit.audit_logs_id_seq TO {role};")


def downgrade() -> None:
    for role in _WORKER_ROLES:
        op.execute(f"REVOKE SELECT ON TABLE audit.audit_logs FROM {role};")
