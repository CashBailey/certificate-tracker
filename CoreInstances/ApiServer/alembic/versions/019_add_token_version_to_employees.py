"""Add token_version column to employees for session invalidation

When a user changes their password, token_version is incremented.
All existing JWTs carrying an older token_version are rejected,
effectively invalidating every active session for that account.

Revision ID: 019
Revises: 018
"""

import sqlalchemy as sa
from alembic import op

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "employees",
        sa.Column(
            "token_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        schema="certificates",
    )


def downgrade() -> None:
    op.drop_column("employees", "token_version", schema="certificates")
