"""Extend audit_logs with dual timestamps, role, correlation, and service columns

Renames created_at → occurred_at_utc and adds recorded_at_utc for dual-timestamp
pattern (when the event happened vs when the row was persisted). Adds actor_role,
correlation_id, source_service, outcome, and ip_address columns needed by the
updated audit logging pipeline.

All new columns are nullable — safe to apply to a live table with existing rows.

Revision ID: 034
Revises: 033
Create Date: 2026-03-30
"""

from alembic import op
import sqlalchemy as sa

revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the old index before renaming the column (avoids stale index name)
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs", schema="audit")

    # Rename created_at → occurred_at_utc (metadata-only in Postgres)
    op.alter_column(
        "audit_logs",
        "created_at",
        new_column_name="occurred_at_utc",
        schema="audit",
    )

    # Add recorded_at_utc (when the row was inserted)
    op.add_column(
        "audit_logs",
        sa.Column(
            "recorded_at_utc",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        schema="audit",
    )

    # Backfill recorded_at_utc from occurred_at_utc for existing rows
    op.execute(
        "UPDATE audit.audit_logs SET recorded_at_utc = occurred_at_utc"
    )

    # Add new nullable columns
    op.add_column(
        "audit_logs",
        sa.Column("actor_role", sa.String(20), nullable=True),
        schema="audit",
    )
    op.add_column(
        "audit_logs",
        sa.Column("correlation_id", sa.String(36), nullable=True),
        schema="audit",
    )
    op.add_column(
        "audit_logs",
        sa.Column("source_service", sa.String(50), nullable=True),
        schema="audit",
    )
    op.add_column(
        "audit_logs",
        sa.Column("outcome", sa.String(20), nullable=True),
        schema="audit",
    )
    op.add_column(
        "audit_logs",
        sa.Column("ip_address", sa.String(45), nullable=True),
        schema="audit",
    )

    # Add indexes matching ORM model
    op.create_index(
        "ix_audit_logs_occurred_at_utc",
        "audit_logs",
        ["occurred_at_utc"],
        schema="audit",
    )
    op.create_index(
        "ix_audit_logs_recorded_at_utc",
        "audit_logs",
        ["recorded_at_utc"],
        schema="audit",
    )
    op.create_index(
        "ix_audit_logs_correlation_id",
        "audit_logs",
        ["correlation_id"],
        schema="audit",
    )
    op.create_index(
        "ix_audit_logs_source_service",
        "audit_logs",
        ["source_service"],
        schema="audit",
    )


def downgrade() -> None:
    op.drop_index("ix_audit_logs_source_service", table_name="audit_logs", schema="audit")
    op.drop_index("ix_audit_logs_correlation_id", table_name="audit_logs", schema="audit")
    op.drop_index("ix_audit_logs_recorded_at_utc", table_name="audit_logs", schema="audit")
    op.drop_index("ix_audit_logs_occurred_at_utc", table_name="audit_logs", schema="audit")

    op.drop_column("audit_logs", "ip_address", schema="audit")
    op.drop_column("audit_logs", "outcome", schema="audit")
    op.drop_column("audit_logs", "source_service", schema="audit")
    op.drop_column("audit_logs", "correlation_id", schema="audit")
    op.drop_column("audit_logs", "actor_role", schema="audit")
    op.drop_column("audit_logs", "recorded_at_utc", schema="audit")

    op.alter_column(
        "audit_logs",
        "occurred_at_utc",
        new_column_name="created_at",
        schema="audit",
    )

    # Recreate the original index with the old name
    op.create_index(
        "ix_audit_logs_created_at",
        "audit_logs",
        ["created_at"],
        schema="audit",
    )
