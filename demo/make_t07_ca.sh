
#!/usr/bin/env bash
set -euo pipefail

# Generate an independent CA for the T07 negative control.
# It must NOT be the CA that signed the server certificate.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CA_DIR="$ROOT/certs/t07"
CA_CERT="$CA_DIR/ca.crt"
CA_KEY="$CA_DIR/ca.key"

TRUSTED_CA="$ROOT/certs/ca.crt"
SERVER_CERT="$ROOT/certs/server.crt"

mkdir -p "$CA_DIR"

# Check the original lab certificates first.
if [[ ! -f "$TRUSTED_CA" || ! -f "$SERVER_CERT" ]]; then
    echo "[FAIL] Original lab certificates are missing."
    echo "Prepare the normal server certificates first."
    exit 1
fi

# Generate the independent CA only when needed.
if [[ ! -f "$CA_CERT" ]]; then
    echo "[SETUP] Generating independent T07 CA..."

    trap 'rm -f "$CA_KEY"' EXIT

    openssl req -x509 \
        -newkey rsa:2048 \
        -sha256 \
        -nodes \
        -days 45 \
        -keyout "$CA_KEY" \
        -out "$CA_CERT" \
        -subj "/CN=ACW3 T07 Independent CA" \
        -addext "basicConstraints=critical,CA:TRUE" \
        -addext "keyUsage=critical,keyCertSign,cRLSign"

    # The private key is not needed after issuing the CA cert.
    rm -f "$CA_KEY"
    trap - EXIT
else
    echo "[SETUP] Existing T07 CA certificate found."
fi

echo
echo "[CHECK] Verifying original trusted chain..."

if ! openssl verify \
    -CAfile "$TRUSTED_CA" "$SERVER_CERT"; then
    echo "[FAIL] Original server certificate chain is invalid."
    exit 1
fi

echo
echo "[CHECK] Verifying that the T07 CA does NOT trust the server..."

if openssl verify \
    -CAfile "$CA_CERT" "$SERVER_CERT" >/dev/null 2>&1; then
    echo "[FAIL] T07 CA unexpectedly trusts the server certificate."
    exit 1
fi

echo
echo -e "\033[1;32m[T07 SETUP PASSED]\033[0m"
echo "Original CA: trusts the server certificate."
echo "T07 CA: does NOT trust the server certificate."
echo "T07 CA file: $CA_CERT"
echo "No CA private key needs to be shared."
