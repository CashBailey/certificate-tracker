"""NULL the Admin123! password even if auto-upgraded to argon2id (CRIT-01)

Migration 024 used exact bcrypt hash matching. If the application's
password-hashing backend auto-upgraded the hash to argon2id on login,
the exact match missed it. This migration verifies the actual password
against whatever hash is stored and NULLs it if it is still Admin123!.

Revision ID: 025
Revises: 024
Create Date: 2026-02-27
"""
from typing import Sequence, Union

import argon2
import bcrypt
from alembic import op
from sqlalchemy import text

revision: str = "025"
down_revision: Union[str, None] = "024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ADMIN_EMAIL = "admin@ci.laredo.tx.us"
_KNOWN_PASSWORD = "Admin123!"


def _is_known_password(password_hash: str) -> bool:
    """Return True if *password_hash* verifies against the known default."""
    try:
        if password_hash.startswith("$argon2"):
            argon2.PasswordHasher().verify(password_hash, _KNOWN_PASSWORD)
            return True
        if password_hash.startswith("$2b$") or password_hash.startswith("$2a$"):
            return bcrypt.checkpw(
                _KNOWN_PASSWORD.encode(), password_hash.encode()
            )
    except argon2.exceptions.VerifyMismatchError:
        return False
    except ValueError:
        return False
    return False


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        text(
            "SELECT id, password_hash FROM certificates.employees "
            "WHERE email = :email AND password_hash IS NOT NULL"
        ),
        {"email": _ADMIN_EMAIL},
    ).fetchall()

    for row in rows:
        if _is_known_password(row[1]):
            conn.execute(
                text(
                    "UPDATE certificates.employees "
                    "SET password_hash = NULL "
                    "WHERE id = :id"
                ),
                {"id": row[0]},
            )


def downgrade() -> None:
    # Intentionally does NOT restore the hardcoded hash.
    # Same rationale as migration 024.
    pass
