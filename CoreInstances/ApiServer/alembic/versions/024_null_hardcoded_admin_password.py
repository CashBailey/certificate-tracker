"""NULL the hardcoded Admin123! password hash (CRIT-01)

Replaces the well-known bcrypt hash seeded in migration 003 with NULL,
forcing the admin to use the forgot-password / account-setup flow to set
a secure password.

Uses exact hash match -- only affects the specific Admin123! bcrypt hash.
Admins who already changed their password are untouched.

Revision ID: 024
Revises: 023
Create Date: 2026-02-27
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "024"
down_revision: Union[str, None] = "023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The exact bcrypt hash for "Admin123!" seeded in migration 003.
_HARDCODED_HASH = "$2b$12$mqmN5b4He23kiRNXyYfApe/qNJVWD48dALuwnvmNBG0VZZ4bz/vtS"


def upgrade() -> None:
    op.get_bind().execute(
        text(
            "UPDATE certificates.employees "
            "SET password_hash = NULL "
            "WHERE email = :email AND password_hash = :hash"
        ),
        {"email": "admin@ci.laredo.tx.us", "hash": _HARDCODED_HASH},
    )


def downgrade() -> None:
    # Intentionally does NOT restore the hardcoded hash.
    # Reverting this migration leaves password_hash as NULL -- the admin
    # must use the password-setup flow regardless.
    pass
