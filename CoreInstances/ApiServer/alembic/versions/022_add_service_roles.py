"""Create per-service PostgreSQL roles with least-privilege grants (AUD-40)

Each background worker service gets its own login role restricted to only the
tables and sequences it actually needs.  The application API service continues
to use the owner role (POSTGRES_USER) which runs migrations and owns all objects.

Revision ID: 022
Revises: 021
Create Date: 2026-02-24
"""

from alembic import op

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Create roles (cluster-level objects — use DO block for idempotency)
    # ------------------------------------------------------------------
    op.execute("""
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'laredo_extraction_worker') THEN
    CREATE ROLE laredo_extraction_worker WITH LOGIN PASSWORD 'PLACEHOLDER_SET_VIA_ENV';
  END IF;
END $$;
""")

    op.execute("""
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'laredo_scheduler_worker') THEN
    CREATE ROLE laredo_scheduler_worker WITH LOGIN PASSWORD 'PLACEHOLDER_SET_VIA_ENV';
  END IF;
END $$;
""")

    op.execute("""
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'laredo_email_intake_worker') THEN
    CREATE ROLE laredo_email_intake_worker WITH LOGIN PASSWORD 'PLACEHOLDER_SET_VIA_ENV';
  END IF;
END $$;
""")

    # ------------------------------------------------------------------
    # Extraction worker grants
    # ------------------------------------------------------------------
    op.execute("GRANT CONNECT ON DATABASE laredo_certificates TO laredo_extraction_worker;")
    op.execute("GRANT USAGE ON SCHEMA certificates TO laredo_extraction_worker;")
    op.execute("GRANT USAGE ON SCHEMA audit        TO laredo_extraction_worker;")
    op.execute("GRANT SELECT, UPDATE ON TABLE certificates.extraction_runs               TO laredo_extraction_worker;")
    op.execute("GRANT SELECT, UPDATE ON TABLE certificates.requirement_assignments       TO laredo_extraction_worker;")
    op.execute("GRANT SELECT          ON TABLE certificates.employees                    TO laredo_extraction_worker;")
    op.execute("GRANT INSERT          ON TABLE certificates.verified_certificate_records TO laredo_extraction_worker;")
    op.execute("GRANT INSERT          ON TABLE audit.audit_logs                          TO laredo_extraction_worker;")
    op.execute("GRANT USAGE ON SEQUENCE certificates.verified_certificate_records_id_seq TO laredo_extraction_worker;")
    op.execute("GRANT USAGE ON SEQUENCE audit.audit_logs_id_seq                          TO laredo_extraction_worker;")

    # ------------------------------------------------------------------
    # Scheduler worker grants
    # ------------------------------------------------------------------
    op.execute("GRANT CONNECT ON DATABASE laredo_certificates TO laredo_scheduler_worker;")
    op.execute("GRANT USAGE ON SCHEMA certificates  TO laredo_scheduler_worker;")
    op.execute("GRANT USAGE ON SCHEMA notifications TO laredo_scheduler_worker;")
    op.execute("GRANT USAGE ON SCHEMA audit         TO laredo_scheduler_worker;")
    op.execute("GRANT SELECT                 ON TABLE certificates.employees               TO laredo_scheduler_worker;")
    op.execute("GRANT SELECT                 ON TABLE certificates.requirement_assignments TO laredo_scheduler_worker;")
    op.execute("GRANT SELECT, INSERT, UPDATE ON TABLE notifications.notification_events    TO laredo_scheduler_worker;")
    op.execute("GRANT SELECT, INSERT, UPDATE ON TABLE notifications.job_cursors             TO laredo_scheduler_worker;")
    op.execute("GRANT INSERT                 ON TABLE audit.audit_logs                     TO laredo_scheduler_worker;")
    op.execute("GRANT USAGE ON SEQUENCE notifications.notification_events_id_seq TO laredo_scheduler_worker;")
    op.execute("GRANT USAGE ON SEQUENCE audit.audit_logs_id_seq                  TO laredo_scheduler_worker;")

    # ------------------------------------------------------------------
    # Email intake worker grants
    # ------------------------------------------------------------------
    op.execute("GRANT CONNECT ON DATABASE laredo_certificates TO laredo_email_intake_worker;")
    op.execute("GRANT USAGE ON SCHEMA certificates  TO laredo_email_intake_worker;")
    op.execute("GRANT USAGE ON SCHEMA notifications TO laredo_email_intake_worker;")
    op.execute("GRANT USAGE ON SCHEMA audit         TO laredo_email_intake_worker;")
    op.execute("GRANT SELECT         ON TABLE certificates.gal_directory          TO laredo_email_intake_worker;")
    op.execute("GRANT SELECT, INSERT ON TABLE certificates.employees              TO laredo_email_intake_worker;")
    op.execute("GRANT INSERT         ON TABLE certificates.extraction_runs        TO laredo_email_intake_worker;")
    op.execute("GRANT INSERT         ON TABLE notifications.email_intake_messages TO laredo_email_intake_worker;")
    op.execute("GRANT INSERT         ON TABLE audit.audit_logs                    TO laredo_email_intake_worker;")
    op.execute("GRANT USAGE ON SEQUENCE certificates.employees_id_seq                TO laredo_email_intake_worker;")
    op.execute("GRANT USAGE ON SEQUENCE certificates.extraction_runs_id_seq          TO laredo_email_intake_worker;")
    op.execute("GRANT USAGE ON SEQUENCE notifications.email_intake_messages_id_seq   TO laredo_email_intake_worker;")
    op.execute("GRANT USAGE ON SEQUENCE audit.audit_logs_id_seq                      TO laredo_email_intake_worker;")


def downgrade() -> None:
    # Revoke all grants before dropping roles — PostgreSQL will refuse to drop
    # a role that still holds privileges on any database object.
    for role in (
        "laredo_extraction_worker",
        "laredo_scheduler_worker",
        "laredo_email_intake_worker",
    ):
        op.execute(f"REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA certificates FROM {role};")
        op.execute(f"REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA notifications FROM {role};")
        op.execute(f"REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA audit FROM {role};")
        op.execute(f"REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA certificates FROM {role};")
        op.execute(f"REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA notifications FROM {role};")
        op.execute(f"REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA audit FROM {role};")
        op.execute(f"REVOKE USAGE ON SCHEMA certificates FROM {role};")
        op.execute(f"REVOKE USAGE ON SCHEMA notifications FROM {role};")
        op.execute(f"REVOKE USAGE ON SCHEMA audit FROM {role};")
        op.execute(f"REVOKE CONNECT ON DATABASE laredo_certificates FROM {role};")
        op.execute(f"DROP ROLE IF EXISTS {role};")
