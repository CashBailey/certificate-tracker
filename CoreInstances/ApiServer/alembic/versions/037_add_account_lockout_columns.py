"""Add account lockout escalation columns to employees.

Adds 5 columns to certificates.employees to support DB-authoritative
progressive lockout (replacing the Redis-only single-level lockout in
auth/service.py). Schema-only — safe to deploy before application code.
Existing rows get server_default values (lockout_level=0, counters=0,
nullable timestamps NULL).

The partial index `ix_employees_locked_until WHERE locked_until IS NOT NULL`
keeps the upcoming "list locked accounts" admin query cheap without
penalizing the much more common case where nothing is locked.

Column semantics (full design at docs/design/auth-lockout.md when shipped):
  - locked_until:           NULL = active. Future ts = locked until then.
                             Sentinel 9999-12-31 = permanent (level 5, admin
                             unlock required).
  - lockout_level:          0–5. Increments each lockout. Decays to 0 after
                             24h with no further lockouts on next successful
                             login.
  - failed_login_count:     Counter since last successful login or unlock.
                             Resets on success.
  - last_failed_login_at:   Used to age out stale counter (>15 min idle
                             resets failed_login_count).
  - last_lockout_at:        Used for the 24h level-decay rule.

Revision ID: 037
Revises: 036
Create Date: 2026-04-19
"""

from alembic import op
import sqlalchemy as sa

revision = "037"
down_revision = "036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "employees",
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        schema="certificates",
    )
    op.add_column(
        "employees",
        sa.Column(
            "lockout_level",
            sa.SmallInteger(),
            nullable=False,
            server_default="0",
        ),
        schema="certificates",
    )
    op.add_column(
        "employees",
        sa.Column(
            "failed_login_count",
            sa.SmallInteger(),
            nullable=False,
            server_default="0",
        ),
        schema="certificates",
    )
    op.add_column(
        "employees",
        sa.Column(
            "last_failed_login_at", sa.DateTime(timezone=True), nullable=True
        ),
        schema="certificates",
    )
    op.add_column(
        "employees",
        sa.Column(
            "last_lockout_at", sa.DateTime(timezone=True), nullable=True
        ),
        schema="certificates",
    )
    op.create_index(
        "ix_employees_locked_until",
        "employees",
        ["locked_until"],
        schema="certificates",
        postgresql_where=sa.text("locked_until IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_employees_locked_until",
        table_name="employees",
        schema="certificates",
    )
    for col in (
        "last_lockout_at",
        "last_failed_login_at",
        "failed_login_count",
        "lockout_level",
        "locked_until",
    ):
        op.drop_column("employees", col, schema="certificates")
