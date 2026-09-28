"""Add GAL directory table for city employee lookup

Creates certificates.gal_directory to store Global Address List entries
for auto-creating employees on first email submission (INV-09).

Revision ID: 015
Revises: 014
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gal_directory",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column(
            "is_person",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_gal_directory_email"),
        schema="certificates",
    )
    op.create_index(
        "ix_gal_directory_email",
        "gal_directory",
        ["email"],
        schema="certificates",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_gal_directory_email",
        table_name="gal_directory",
        schema="certificates",
    )
    op.drop_table("gal_directory", schema="certificates")
