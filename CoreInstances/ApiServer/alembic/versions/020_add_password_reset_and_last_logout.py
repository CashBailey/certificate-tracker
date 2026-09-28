"""Add password_reset_tokens table and last_logout_at to employees

Adds last_logout_at for revocable refresh token support (SEC-09)
and password_reset_tokens for self-service password recovery (WF-10).

Revision ID: 020
Revises: 019
Create Date: 2026-02-23
"""

import sqlalchemy as sa
from alembic import op

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add last_logout_at to employees
    op.add_column(
        "employees",
        sa.Column("last_logout_at", sa.DateTime(timezone=True), nullable=True),
        schema="certificates",
    )

    # Create password_reset_tokens table
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "employee_id",
            sa.Integer(),
            sa.ForeignKey("certificates.employees.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema="certificates",
    )

    op.create_unique_constraint(
        "uq_password_reset_tokens_token_hash",
        "password_reset_tokens",
        ["token_hash"],
        schema="certificates",
    )

    op.create_index(
        "ix_password_reset_tokens_employee_id",
        "password_reset_tokens",
        ["employee_id"],
        schema="certificates",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_password_reset_tokens_employee_id",
        table_name="password_reset_tokens",
        schema="certificates",
    )
    op.drop_table("password_reset_tokens", schema="certificates")
    op.drop_column("employees", "last_logout_at", schema="certificates")
