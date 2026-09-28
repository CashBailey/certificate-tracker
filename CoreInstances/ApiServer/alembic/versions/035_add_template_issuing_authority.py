"""Add template_issuing_authority column to extraction_runs

When the extraction pipeline matches a document to a template, it stamps
the template's known issuing authority into this column. The review/approval
flow uses this as the authoritative value instead of relying on OCR/LLM
extraction for the issuing_authority field.

NULL means the template did not specify an issuing authority, or no
template was matched.

Revision ID: 036
Revises: 035
Create Date: 2026-03-26
"""

from alembic import op
import sqlalchemy as sa

revision = "035"
down_revision = "034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "extraction_runs",
        sa.Column("template_issuing_authority", sa.String(200), nullable=True),
        schema="certificates",
    )


def downgrade() -> None:
    op.drop_column(
        "extraction_runs",
        "template_issuing_authority",
        schema="certificates",
    )
