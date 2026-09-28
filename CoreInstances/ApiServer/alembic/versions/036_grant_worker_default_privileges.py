"""Catch-up grants and ALTER DEFAULT PRIVILEGES for worker roles.

Background: prior grant migrations (026, 028, 030, 031) granted privileges
on a per-table basis. Subsequent migrations that created or replaced tables
in `certificates`, `notifications`, and `audit` schemas left the new objects
without grants, breaking the workers (`InsufficientPrivilegeError`).

This migration:
1. Re-grants USAGE on the three schemas (idempotent).
2. Bulk-grants SELECT/INSERT/UPDATE on ALL existing tables in each schema —
   catches anything missed by per-table grants.
3. Bulk-grants USAGE/SELECT on ALL existing sequences.
4. Sets ALTER DEFAULT PRIVILEGES so any FUTURE tables/sequences created in
   these schemas (by future migrations or seed scripts running as `laredo`)
   automatically receive the same grants — eliminating the "new migration
   broke the workers" failure mode.

Note: ALTER DEFAULT PRIVILEGES is FOR ROLE-scoped — it applies to objects
created by `laredo` (the schema owner). If a future migration runs as a
different role, those objects still need explicit grants.

Revision ID: 036
Revises: 035
Create Date: 2026-04-19
"""

from alembic import op

revision = "036"
down_revision = "035"
branch_labels = None
depends_on = None

_WORKER_ROLES = [
    "laredo_email_intake_worker",
    "laredo_extraction_worker",
    "laredo_scheduler_worker",
]
_SCHEMAS = ["certificates", "notifications", "audit"]
_OWNER = "laredo"


def upgrade() -> None:
    roles = ", ".join(_WORKER_ROLES)
    for schema in _SCHEMAS:
        op.execute(f"GRANT USAGE ON SCHEMA {schema} TO {roles};")
        op.execute(
            f"GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA {schema} TO {roles};"
        )
        op.execute(
            f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {schema} TO {roles};"
        )
        op.execute(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {_OWNER} IN SCHEMA {schema} "
            f"GRANT SELECT, INSERT, UPDATE ON TABLES TO {roles};"
        )
        op.execute(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {_OWNER} IN SCHEMA {schema} "
            f"GRANT USAGE, SELECT ON SEQUENCES TO {roles};"
        )


def downgrade() -> None:
    roles = ", ".join(_WORKER_ROLES)
    for schema in _SCHEMAS:
        op.execute(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {_OWNER} IN SCHEMA {schema} "
            f"REVOKE SELECT, INSERT, UPDATE ON TABLES FROM {roles};"
        )
        op.execute(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {_OWNER} IN SCHEMA {schema} "
            f"REVOKE USAGE, SELECT ON SEQUENCES FROM {roles};"
        )
        op.execute(
            f"REVOKE SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA {schema} FROM {roles};"
        )
        op.execute(
            f"REVOKE USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {schema} FROM {roles};"
        )
        # Leave USAGE on schema in place — earlier migrations granted it
        # individually and revoking would break those.
