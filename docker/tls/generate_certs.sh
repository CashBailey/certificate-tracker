#!/usr/bin/env bash
# ==============================================================================
# Generate self-signed CA and per-service TLS certificates for mTLS.
#
# Run once from the project root:
#   bash docker/tls/generate_certs.sh
# To stage/inspect a rotation without replacing active files:
#   TLS_OUTPUT_DIR=/tmp/laredo-tls bash docker/tls/generate_certs.sh
#
# Produces:
#   docker/tls/ca.crt            – CA certificate (mounted into every container)
#   docker/tls/ca.key            – CA private key (NEVER mounted; stays on host)
#   docker/tls/certs/<service>/  – server or client cert + key + ca.crt copy
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TLS_DIR="${TLS_OUTPUT_DIR:-$SCRIPT_DIR}"
CERTS_DIR="$TLS_DIR/certs"

CA_DAYS=3650   # 10-year CA
CERT_DAYS=365  # 1-year leaf certs

# ---------------------------------------------------------------------------
# Directory structure
# ---------------------------------------------------------------------------
mkdir -p \
    "$CERTS_DIR/postgres" \
    "$CERTS_DIR/redis" \
    "$CERTS_DIR/minio" \
    "$CERTS_DIR/api-client" \
    "$CERTS_DIR/extraction-worker-client" \
    "$CERTS_DIR/ocr-worker-client" \
    "$CERTS_DIR/scheduler-worker-client" \
    "$CERTS_DIR/email-intake-worker-client" \
    "$CERTS_DIR/caddy"

# ---------------------------------------------------------------------------
# Certificate Authority
# ---------------------------------------------------------------------------
echo "Generating CA key and certificate..."
openssl genrsa -out "$TLS_DIR/ca.key" 4096 2>/dev/null
openssl req -new -x509 \
    -days "$CA_DAYS" \
    -key "$TLS_DIR/ca.key" \
    -out "$TLS_DIR/ca.crt" \
    -subj "/C=US/ST=Texas/L=Laredo/O=City of Laredo/CN=Laredo Internal CA"
chmod 600 "$TLS_DIR/ca.key"
chmod 644 "$TLS_DIR/ca.crt"
echo "  CA cert: $TLS_DIR/ca.crt"

# ---------------------------------------------------------------------------
# Helper: generate a server certificate with SAN entries
#   $1 – short name (matches certs/ sub-directory)
#   $2 – Common Name
#   $3 – comma-separated DNS SANs (e.g. "postgres,localhost")
# ---------------------------------------------------------------------------
generate_server_cert() {
    local name="$1"
    local cn="$2"
    local dns_csv="$3"
    local dir="$CERTS_DIR/$name"

    echo "Generating server cert for $name..."

    openssl genrsa -out "$dir/server.key" 2048 2>/dev/null

    # Build OpenSSL config with SANs using a temp file
    local cfg
    cfg="$(mktemp)"
    cat > "$cfg" <<OPENSSL_CFG
[req]
req_extensions     = v3_req
distinguished_name = req_dn
[req_dn]
[v3_req]
basicConstraints = CA:FALSE
keyUsage         = nonRepudiation, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName   = @alt_names
[alt_names]
OPENSSL_CFG

    local i=1
    IFS=',' read -ra DNS_LIST <<< "$dns_csv"
    for dns in "${DNS_LIST[@]}"; do
        echo "DNS.$i = $dns" >> "$cfg"
        (( i++ )) || true
    done

    openssl req -new \
        -key    "$dir/server.key" \
        -out    "$dir/server.csr" \
        -subj   "/C=US/ST=Texas/L=Laredo/O=City of Laredo/CN=$cn" \
        -config "$cfg" 2>/dev/null

    openssl x509 -req \
        -days       "$CERT_DAYS" \
        -in         "$dir/server.csr" \
        -CA         "$TLS_DIR/ca.crt" \
        -CAkey      "$TLS_DIR/ca.key" \
        -CAcreateserial \
        -out        "$dir/server.crt" \
        -extensions v3_req \
        -extfile    "$cfg" 2>/dev/null

    rm -f "$cfg" "$dir/server.csr"
    chmod 600 "$dir/server.key"
    chmod 644 "$dir/server.crt"
    cp "$TLS_DIR/ca.crt" "$dir/ca.crt"
    echo "  $dir/server.crt"
}

# ---------------------------------------------------------------------------
# Helper: generate a client certificate
#   $1 – directory name under certs/
#   $2 – Common Name (service identity)
# ---------------------------------------------------------------------------
generate_client_cert() {
    local name="$1"
    local cn="$2"
    local dir="$CERTS_DIR/$name"

    echo "Generating client cert for $name..."

    openssl genrsa -out "$dir/client.key" 2048 2>/dev/null

    local cfg
    cfg="$(mktemp)"
    cat > "$cfg" <<OPENSSL_CFG
[req]
req_extensions     = v3_req
distinguished_name = req_dn
[req_dn]
[v3_req]
basicConstraints = CA:FALSE
keyUsage         = digitalSignature, keyEncipherment
extendedKeyUsage = clientAuth
OPENSSL_CFG

    openssl req -new \
        -key  "$dir/client.key" \
        -out  "$dir/client.csr" \
        -subj "/C=US/ST=Texas/L=Laredo/O=City of Laredo/CN=$cn" \
        -config "$cfg" 2>/dev/null

    openssl x509 -req \
        -days "$CERT_DAYS" \
        -in   "$dir/client.csr" \
        -CA   "$TLS_DIR/ca.crt" \
        -CAkey "$TLS_DIR/ca.key" \
        -CAcreateserial \
        -out  "$dir/client.crt" \
        -extensions v3_req \
        -extfile "$cfg" 2>/dev/null

    rm -f "$cfg" "$dir/client.csr"
    chmod 600 "$dir/client.key"
    chmod 644 "$dir/client.crt"
    cp "$TLS_DIR/ca.crt" "$dir/ca.crt"
    echo "  $dir/client.crt"
}

# ---------------------------------------------------------------------------
# Server certificates
# ---------------------------------------------------------------------------
generate_server_cert "postgres" "postgres" "postgres,localhost"
generate_server_cert "redis"    "redis"    "redis,localhost"

# MinIO uses filenames public.crt / private.key
echo "Generating server cert for minio..."
openssl genrsa -out "$CERTS_DIR/minio/private.key" 2048 2>/dev/null

cfg="$(mktemp)"
cat > "$cfg" <<MINIO_CFG
[req]
req_extensions     = v3_req
distinguished_name = req_dn
[req_dn]
[v3_req]
basicConstraints = CA:FALSE
keyUsage         = nonRepudiation, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName   = @alt_names
[alt_names]
DNS.1 = minio
DNS.2 = localhost
MINIO_CFG

openssl req -new \
    -key    "$CERTS_DIR/minio/private.key" \
    -out    "$CERTS_DIR/minio/minio.csr" \
    -subj   "/C=US/ST=Texas/L=Laredo/O=City of Laredo/CN=minio" \
    -config "$cfg" 2>/dev/null

openssl x509 -req \
    -days       "$CERT_DAYS" \
    -in         "$CERTS_DIR/minio/minio.csr" \
    -CA         "$TLS_DIR/ca.crt" \
    -CAkey      "$TLS_DIR/ca.key" \
    -CAcreateserial \
    -out        "$CERTS_DIR/minio/public.crt" \
    -extensions v3_req \
    -extfile    "$cfg" 2>/dev/null

rm -f "$cfg" "$CERTS_DIR/minio/minio.csr"
chmod 600 "$CERTS_DIR/minio/private.key"
chmod 644 "$CERTS_DIR/minio/public.crt"
cp "$TLS_DIR/ca.crt" "$CERTS_DIR/minio/ca.crt"
echo "  $CERTS_DIR/minio/public.crt"

# ---------------------------------------------------------------------------
# Client certificates
# ---------------------------------------------------------------------------
generate_client_cert "api-client"                  "api"
generate_client_cert "extraction-worker-client"    "extraction-worker"
generate_client_cert "ocr-worker-client"           "ocr-worker"
generate_client_cert "scheduler-worker-client"     "scheduler-worker"
generate_client_cert "email-intake-worker-client"  "email-intake-worker"

# ---------------------------------------------------------------------------
# Copy an api client cert into the redis directory so the redis container's
# healthcheck can present a valid client cert when connecting to itself.
# ---------------------------------------------------------------------------
# Caddy server certificate (for static_cert TLS mode only)
# ---------------------------------------------------------------------------
generate_server_cert "caddy" "${PUBLIC_HOSTNAME:-localhost}" "${PUBLIC_HOSTNAME:-localhost},localhost"

cp "$CERTS_DIR/api-client/client.crt" "$CERTS_DIR/redis/client.crt"
cp "$CERTS_DIR/api-client/client.key" "$CERTS_DIR/redis/client.key"
chmod 600 "$CERTS_DIR/redis/client.key"
echo "Copied api-client cert into redis dir (for healthcheck)"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "All certificates generated successfully."
echo ""
echo "CA cert : $TLS_DIR/ca.crt"
echo "CA key  : $TLS_DIR/ca.key  (keep secret — never mount into containers)"
echo "Certs   : $CERTS_DIR/"
echo ""
echo "Next: docker compose up --build"
