"""Restore per-worker PostgreSQL least privilege.

Revision 036 granted every worker SELECT, INSERT, and UPDATE on every table in
all application schemas.  That made a parser or scheduler compromise equivalent
to an API/database-owner compromise.  Replace those catch-all grants with the
smallest privileges exercised by each worker and remove the dangerous future-
table defaults.

Revision ID: 040
Revises: 039
Create Date: 2026-07-12
"""

from alembic import op


revision = "040"
down_revision = "039"
branch_labels = None
depends_on = None


WORKER_ROLES = (
    "laredo_email_intake_worker",
    "laredo_extraction_worker",
    "laredo_scheduler_worker",
)
SCHEMAS = ("certificates", "notifications", "audit")
OWNER_ROLE = "laredo"


def _roles_sql() -> str:
    return ", ".join(WORKER_ROLES)


def _remove_catch_all_grants() -> None:
    roles = _roles_sql()
    for schema in SCHEMAS:
        op.execute(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {OWNER_ROLE} IN SCHEMA {schema} "
            f"REVOKE SELECT, INSERT, UPDATE ON TABLES FROM {roles};"
        )
        op.execute(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {OWNER_ROLE} IN SCHEMA {schema} "
            f"REVOKE USAGE, SELECT ON SEQUENCES FROM {roles};"
        )
        op.execute(
            f"REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA {schema} FROM {roles};"
        )
        op.execute(
            f"REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA {schema} FROM {roles};"
        )
        op.execute(f"REVOKE ALL PRIVILEGES ON SCHEMA {schema} FROM {roles};")


def upgrade() -> None:
    _remove_catch_all_grants()

    # Email intake: resolve a City identity, store the original submission,
    # create a Processing extraction, track the message, and append audit rows.
    op.execute(
        "GRANT USAGE ON SCHEMA certificates, notifications, audit "
        "TO laredo_email_intake_worker;"
    )
    op.execute(
        "GRANT SELECT ON TABLE certificates.gal_directory "
        "TO laredo_email_intake_worker;"
    )
    op.execute(
        "GRANT SELECT ON TABLE certificates.employees "
        "TO laredo_email_intake_worker;"
    )
    op.execute(
        "GRANT INSERT (employee_number, first_name, last_name, email) "
        "ON TABLE certificates.employees TO laredo_email_intake_worker;"
    )
    op.execute(
        "GRANT SELECT, INSERT ON TABLE certificates.certificate_documents "
        "TO laredo_email_intake_worker;"
    )
    op.execute(
        "GRANT SELECT ON TABLE certificates.extraction_runs "
        "TO laredo_email_intake_worker;"
    )
    op.execute(
        "GRANT INSERT (document_id) ON TABLE certificates.extraction_runs "
        "TO laredo_email_intake_worker;"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON TABLE notifications.email_intake_messages "
        "TO laredo_email_intake_worker;"
    )
    op.execute(
        "GRANT SELECT, INSERT ON TABLE audit.audit_logs "
        "TO laredo_email_intake_worker;"
    )
    op.execute(
        "GRANT USAGE, SELECT ON SEQUENCE certificates.employees_id_seq, "
        "certificates.certificate_documents_id_seq, "
        "certificates.extraction_runs_id_seq, "
        "notifications.email_intake_messages_id_seq, audit.audit_logs_id_seq "
        "TO laredo_email_intake_worker;"
    )

    # A database default supplies the only role email intake may create.  The
    # worker lacks column privilege for role, password, active state, and token
    # fields, so a compromised intake process cannot provision a login account.
    op.alter_column(
        "employees",
        "role",
        server_default="Employee",
        schema="certificates",
    )

    # Extraction: read immutable source metadata/holder/email context and write
    # only the existing extraction run produced for that document.
    op.execute(
        "GRANT USAGE ON SCHEMA certificates, notifications "
        "TO laredo_extraction_worker;"
    )
    op.execute(
        "GRANT SELECT ON TABLE certificates.certificate_documents, "
        "certificates.employees, notifications.email_intake_messages "
        "TO laredo_extraction_worker;"
    )
    op.execute(
        "GRANT SELECT, UPDATE ON TABLE certificates.extraction_runs "
        "TO laredo_extraction_worker;"
    )

    # Scheduler: read compliance/configuration inputs; create and deliver only
    # notification/cursor rows; append delivery audit summaries.
    op.execute(
        "GRANT USAGE ON SCHEMA certificates, notifications, audit "
        "TO laredo_scheduler_worker;"
    )
    op.execute(
        "GRANT SELECT ON TABLE certificates.employees, "
        "certificates.requirement_assignments, certificates.certificate_types, "
        "certificates.verified_certificate_records, "
        "notifications.alert_configuration TO laredo_scheduler_worker;"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON TABLE notifications.notification_events, "
        "notifications.job_cursors TO laredo_scheduler_worker;"
    )
    op.execute(
        "GRANT SELECT, INSERT ON TABLE audit.audit_logs "
        "TO laredo_scheduler_worker;"
    )
    op.execute(
        "GRANT USAGE, SELECT ON SEQUENCE notifications.notification_events_id_seq, "
        "audit.audit_logs_id_seq TO laredo_scheduler_worker;"
    )


def downgrade() -> None:
    # Restores revision 036 exactly.  This reintroduces its security defect and
    # is provided only so a coordinated application rollback remains possible.
    roles = _roles_sql()
    for schema in SCHEMAS:
        op.execute(f"GRANT USAGE ON SCHEMA {schema} TO {roles};")
        op.execute(
            f"GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA {schema} "
            f"TO {roles};"
        )
        op.execute(
            f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {schema} TO {roles};"
        )
        op.execute(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {OWNER_ROLE} IN SCHEMA {schema} "
            f"GRANT SELECT, INSERT, UPDATE ON TABLES TO {roles};"
        )
        op.execute(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {OWNER_ROLE} IN SCHEMA {schema} "
            f"GRANT USAGE, SELECT ON SEQUENCES TO {roles};"
        )
    op.alter_column(
        "employees",
        "role",
        server_default=None,
        schema="certificates",
    )
