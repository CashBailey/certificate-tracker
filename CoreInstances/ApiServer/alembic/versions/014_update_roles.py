"""Ensure seeded admin user has Coordinator role

Safety migration for RBAC enforcement (Phase 3).
Ensures the seeded ADMIN001 user is promoted to Coordinator so they retain
full access after role checks are enabled.

Revision ID: 014
Revises: 013
"""

from alembic import op


# revision identifiers
revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE certificates.employees
        SET role = 'Coordinator'
        WHERE employee_number = 'ADMIN001' AND role = 'Admin'
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE certificates.employees
        SET role = 'Admin'
        WHERE employee_number = 'ADMIN001' AND role = 'Coordinator'
    """)
