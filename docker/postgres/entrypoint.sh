#!/bin/sh
# Entrypoint wrapper for the Postgres container.
#
# This script runs as root so it can fix TLS certificate ownership and
# permissions, then drops privileges to the postgres user before handing off
# to the official docker-entrypoint.sh. The postgres database process never
# runs as root.
set -eu

TLS_SOURCE="/tls-source"
TLS_DEST="/var/lib/postgresql/tls"

# Copy TLS certificates from the read-only source mount and set ownership so
# the postgres process can read them.
if [ -d "$TLS_SOURCE" ]; then
    mkdir -p "$TLS_DEST"
    cp "$TLS_SOURCE"/* "$TLS_DEST/"
    chown -R postgres:postgres "$TLS_DEST"
    chmod 600 "$TLS_DEST"/server.key
    chmod 644 "$TLS_DEST"/server.crt "$TLS_DEST"/ca.crt
fi

# Drop privileges from root to postgres before starting the database server.
# gosu performs an execve — the postgres process runs as uid 70, not root.
exec gosu postgres docker-entrypoint.sh "$@"
