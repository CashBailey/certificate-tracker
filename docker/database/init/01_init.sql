-- ==============================================================================
-- City of Laredo Certificate Management System - Database Initialization
-- ==============================================================================

-- Create schemas for organization
CREATE SCHEMA IF NOT EXISTS certificates;
CREATE SCHEMA IF NOT EXISTS notifications;
CREATE SCHEMA IF NOT EXISTS audit;

-- Grant schema-level USAGE so laredo can resolve objects in each schema.
-- Table-level grants are intentionally restricted: no DDL, no TRUNCATE.
GRANT USAGE ON SCHEMA certificates TO laredo;
GRANT USAGE ON SCHEMA notifications TO laredo;
-- The audit schema is append-only: the app must never UPDATE or DELETE audit entries.
GRANT USAGE ON SCHEMA audit TO laredo;

-- Table-level grants applied to all current tables in each schema.
-- Alembic migrations (run as the superuser) manage DDL; the app user never needs it.
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA certificates TO laredo;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA notifications TO laredo;
-- Audit tables: INSERT to write entries, SELECT for reporting. No UPDATE or DELETE.
GRANT INSERT, SELECT ON ALL TABLES IN SCHEMA audit TO laredo;

-- Ensure future tables created by migrations inherit the same grants.
ALTER DEFAULT PRIVILEGES IN SCHEMA certificates GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO laredo;
ALTER DEFAULT PRIVILEGES IN SCHEMA notifications GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO laredo;
ALTER DEFAULT PRIVILEGES IN SCHEMA audit GRANT INSERT, SELECT ON TABLES TO laredo;

-- Note: Actual tables are managed by Alembic migrations in the API server
-- This script only sets up schemas and grants needed at database creation

-- ==============================================================================
-- Roundcube webmail database
-- Roundcube manages its own schema via its built-in initializer.
-- ==============================================================================
SELECT 'CREATE DATABASE roundcube OWNER ' || current_user
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'roundcube')\gexec
