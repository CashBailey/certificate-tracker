"""Enforce audit.audit_logs append-only at the DB level.

Regression guard: T-AUD-040, T-AUD-041.

Prior state (documented by browser tests on 2026-04-20): role `laredo` had
UPDATE and DELETE grants on audit.audit_logs, so the API's DSN role could
silently tamper with audit rows. Worker roles had UPDATE without a legitimate
use case.

This migration:
  1. REVOKES UPDATE and DELETE on audit.audit_logs from the primary app
     role `laredo` and from every worker role.
  2. Installs a BEFORE UPDATE/DELETE trigger that raises an exception for
     any remaining caller. Superusers can still bypass at the instance
     level, but triggers prevent accidental tampering even when a
     privileged session is open.
  3. The trigger lives in a SECURITY DEFINER function so even if a new
     role is granted UPDATE/DELETE later, mutation attempts still abort.

Existing rows are untouched. INSERT and SELECT remain unaffected.

Revision ID: 038
Revises: 037
Create Date: 2026-04-20
"""

from alembic import op


# revision identifiers
revision = "038"
down_revision = "037"
branch_labels = None
depends_on = None


APP_ROLES = (
    "laredo",
    "laredo_email_intake_worker",
    "laredo_extraction_worker",
    "laredo_scheduler_worker",
)


def upgrade() -> None:
    # 1. Revoke UPDATE and DELETE from every known app / worker role.
    for role in APP_ROLES:
        op.execute(
            f"REVOKE UPDATE, DELETE ON audit.audit_logs FROM {role};"
        )

    # 2. Create the trigger function that raises for UPDATE or DELETE.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit.audit_logs_reject_mutation()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        SECURITY DEFINER
        AS $$
        BEGIN
            RAISE EXCEPTION
                'audit.audit_logs is append-only; % not permitted',
                TG_OP
                USING ERRCODE = 'insufficient_privilege';
        END;
        $$;
        """
    )

    # 3. Attach BEFORE UPDATE/DELETE trigger. asyncpg rejects multi-statement
    # prepared queries, so these must be separate op.execute calls.
    op.execute(
        "DROP TRIGGER IF EXISTS trg_audit_logs_append_only ON audit.audit_logs;"
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_logs_append_only
        BEFORE UPDATE OR DELETE ON audit.audit_logs
        FOR EACH ROW
        EXECUTE FUNCTION audit.audit_logs_reject_mutation();
        """
    )


def downgrade() -> None:
    # Remove trigger + function.
    op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_append_only ON audit.audit_logs;")
    op.execute("DROP FUNCTION IF EXISTS audit.audit_logs_reject_mutation();")
    # Re-grant UPDATE/DELETE (only for completeness; the original state was
    # a bug, so we do NOT normally want to re-grant).
    for role in APP_ROLES:
        op.execute(f"GRANT UPDATE, DELETE ON audit.audit_logs TO {role};")
