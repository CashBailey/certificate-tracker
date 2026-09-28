"""drop unused uuid-ossp and pg_trgm extensions

Revision ID: 039
Revises: 038
Create Date: 2026-04-22

These extensions were created by docker/database/init/01_init.sql but have
zero runtime consumers in the application:
  - uuid-ossp: UUIDs are generated in Python (shared/uuid_gen.py); no
    server_default=sa.text('uuid_generate_v4()'), no uuid_generate_v1() calls.
  - pg_trgm: fuzzy search at repository.py:591-607 uses plain ILIKE; no
    gin_trgm_ops / gist_trgm_ops indexes, no similarity() or op('%')/op('<->')
    operators anywhere in the codebase.

Drop with IF EXISTS so re-runs against a db that already lost the extensions
are a no-op. No app objects depend on them, so CASCADE is unnecessary.
"""

from alembic import op


# revision identifiers
revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('DROP EXTENSION IF EXISTS "uuid-ossp"')
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")


def downgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
