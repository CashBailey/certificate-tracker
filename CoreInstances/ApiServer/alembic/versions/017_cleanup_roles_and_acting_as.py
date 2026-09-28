"""Remove Manager/Reviewer roles, simplify acting_as, revert ADMIN001 to Admin

Strips deprecated Manager and Reviewer roles from the system, tightening the
role model to just Admin, Coordinator, and Employee per HLSD Decision 14.
Simplifies acting_as to Self/Coordinator (Decision 14). Reverts ADMIN001 from
Coordinator back to Admin (its intended IT-only role).

Revision ID: 017
Revises: 016
"""

from alembic import op


# revision identifiers
revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- 1. Migrate any Manager/Reviewer employees to Employee ---
    op.execute("""
        UPDATE certificates.employees
        SET role = 'Employee'
        WHERE role IN ('Manager', 'Reviewer')
    """)

    # --- 2. Tighten role constraint ---
    op.drop_constraint(
        "ck_employees_role",
        "employees",
        schema="certificates",
    )
    op.create_check_constraint(
        "ck_employees_role",
        "employees",
        "role IN ('Coordinator', 'Admin', 'Employee')",
        schema="certificates",
    )

    # --- 3. Migrate acting_as values ---
    op.execute("""
        UPDATE certificates.certificate_documents
        SET acting_as = 'Coordinator'
        WHERE acting_as IN ('Admin', 'Manager')
    """)

    # --- 4. Tighten acting_as constraint ---
    op.drop_constraint(
        "ck_certificate_documents_acting_as",
        "certificate_documents",
        schema="certificates",
    )
    op.create_check_constraint(
        "ck_certificate_documents_acting_as",
        "certificate_documents",
        "acting_as IN ('Self', 'Coordinator')",
        schema="certificates",
    )

    # --- 5. Revert ADMIN001 to Admin role (undo migration 014) ---
    # Safety: only revert if at least one other Coordinator exists
    op.execute("""
        UPDATE certificates.employees
        SET role = 'Admin'
        WHERE employee_number = 'ADMIN001'
          AND role = 'Coordinator'
          AND (SELECT COUNT(*) FROM certificates.employees
               WHERE role = 'Coordinator' AND employee_number != 'ADMIN001') > 0
    """)


def downgrade() -> None:
    # --- 5r. Promote ADMIN001 back to Coordinator ---
    op.execute("""
        UPDATE certificates.employees
        SET role = 'Coordinator'
        WHERE employee_number = 'ADMIN001' AND role = 'Admin'
    """)

    # --- 4r. Restore acting_as constraint ---
    op.drop_constraint(
        "ck_certificate_documents_acting_as",
        "certificate_documents",
        schema="certificates",
    )
    op.create_check_constraint(
        "ck_certificate_documents_acting_as",
        "certificate_documents",
        "acting_as IN ('Self', 'Admin', 'Manager', 'Coordinator')",
        schema="certificates",
    )

    # --- 2r. Restore role constraint ---
    op.drop_constraint(
        "ck_employees_role",
        "employees",
        schema="certificates",
    )
    op.create_check_constraint(
        "ck_employees_role",
        "employees",
        "role IN ('Coordinator', 'Admin', 'Manager', 'Reviewer', 'Employee')",
        schema="certificates",
    )
