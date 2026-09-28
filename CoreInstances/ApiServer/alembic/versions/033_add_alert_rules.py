"""Add alert_configuration table for managed notification configuration

Creates a singleton table in the notifications schema that stores
Coordinator-configurable alert settings: separate day offset lists for
requirements and certificates, daily overdue flag, and global send time
(hour + minute).

Seeds the current hardcoded values so the scheduler behaves identically
after migration.

Grants SELECT to laredo_scheduler_worker (read-only; only the API writes).

Revision ID: 033
Revises: 032
Create Date: 2026-03-26
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Clean up misnamed table from pre-fix migration run (was alert_rules, now alert_configuration)
    op.execute("DROP TABLE IF EXISTS notifications.alert_rules CASCADE")

    op.create_table(
        "alert_configuration",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "requirement_reminder_days",
            postgresql.ARRAY(sa.Integer()),
            nullable=False,
            server_default="{90,60,30,15,7,6,5,4,3,2,1}",
        ),
        sa.Column(
            "certificate_reminder_days",
            postgresql.ARRAY(sa.Integer()),
            nullable=False,
            server_default="{90,60,30,15,7,6,5,4,3,2,1}",
        ),
        sa.Column(
            "daily_overdue_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column(
            "global_send_hour",
            sa.Integer(),
            nullable=False,
            server_default="6",
        ),
        sa.Column(
            "global_send_minute",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column(
            "updated_by_id",
            sa.Integer(),
            sa.ForeignKey("certificates.employees.id"),
            nullable=True,
        ),
        schema="notifications",
    )

    # Seed the singleton row with current hardcoded values
    op.execute("""
        INSERT INTO notifications.alert_configuration
            (id, requirement_reminder_days, certificate_reminder_days,
             daily_overdue_enabled, global_send_hour, global_send_minute)
        VALUES
            (1, '{90,60,30,15,7,6,5,4,3,2,1}', '{90,60,30,15,7,6,5,4,3,2,1}',
             true, 6, 0)
    """)

    # Grant scheduler worker read-only access
    op.execute(
        "GRANT SELECT ON TABLE notifications.alert_configuration "
        "TO laredo_scheduler_worker;"
    )


def downgrade() -> None:
    # Handle both table names (pre-fix: alert_rules, post-fix: alert_configuration)
    op.execute("DROP TABLE IF EXISTS notifications.alert_configuration CASCADE")
    op.execute("DROP TABLE IF EXISTS notifications.alert_rules CASCADE")
