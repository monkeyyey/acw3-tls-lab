
#!/usr/bin/env bash
set -euo pipefail

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

VULNERABLE="$HOME/acw3/python-3.13.15/bin/python3.13"
PATCHED="$HOME/acw3/python-3.13.16/bin/python3.13"

echo "======================================"
echo " CVE-2026-19553 Preflight Check"
echo "======================================"

fail() {
    echo "[FAIL] $1" >&2
    exit 1
}

# Check vulnerable Python
[[ -x "$VULNERABLE" ]] || fail "Python 3.13.15 not found"

VERSION="$("$VULNERABLE" --version)"
[[ "$VERSION" == "Python 3.13.15" ]] || fail "Wrong vulnerable Python version"

echo "[PASS] Vulnerable Python: $VERSION"

# Check patched Python
[[ -x "$PATCHED" ]] || fail "Python 3.13.16 not found"

VERSION="$("$PATCHED" --version)"
[[ "$VERSION" == "Python 3.13.16" ]] || fail "Wrong patched Python version"

echo "[PASS] Patched Python: $VERSION"

# Check certificate files
[[ -f "$PROJECT/certs/ca.crt" ]] || fail "CA certificate missing"
[[ -f "$PROJECT/certs/server.crt" ]] || fail "Server certificate missing"
[[ -f "$PROJECT/certs/server.key" ]] || fail "Server private key missing"

echo "[PASS] Certificate files exist"

# Check certificate chain
if ! openssl verify \
    -CAfile "$PROJECT/certs/ca.crt" \
    "$PROJECT/certs/server.crt"; then
    fail "Certificate chain verification failed"
fi

echo "[PASS] Certificate chain verified"

# Check server certificate hostname
if ! openssl x509 \
    -in "$PROJECT/certs/server.crt" \
    -noout -ext subjectAltName | grep -F "DNS:other.lab"; then
    fail "Expected hostname other.lab not found"
fi

echo "[PASS] Certificate hostname verified"

# Check local server port
if ! ss -ltn | grep -F "127.0.0.1:8443" >/dev/null; then
    fail "No listener found on 127.0.0.1:8443"
fi

echo "[PASS] TLS server port is listening"

echo "======================================"
echo " PREFLIGHT CHECKS PASSED"
echo "======================================"
