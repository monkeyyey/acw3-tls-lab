
#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

umask 077

for file in \
    certs/ca.crt \
    certs/ca.key \
    certs/server.crt \
    certs/server.key
do
    if [[ ! -f "$file" ]]; then
        echo "[FAIL] Missing prerequisite: $file"
        exit 1
    fi
done

echo "[CHECK] Existing attacker certificate..."

openssl verify -CAfile certs/ca.crt certs/server.crt

openssl x509 \
    -in certs/server.crt \
    -noout -ext subjectAltName |
    grep -Fq "DNS:other.lab" || {
        echo "[FAIL] Attacker certificate must identify other.lab"
        exit 1
    }

# Reuse an existing valid service.lab certificate.
if [[ -f certs/service.crt && -f certs/service.key ]]; then
    if openssl verify \
        -CAfile certs/ca.crt certs/service.crt \
        >/dev/null 2>&1 &&
       openssl x509 \
        -in certs/service.crt \
        -noout -ext subjectAltName |
        grep -Fq "DNS:service.lab"; then

        echo "[SETUP] Reusing existing service.lab certificate."
        exit 0
    fi
fi

echo "[SETUP] Generating legitimate service.lab certificate..."

openssl req \
    -new \
    -newkey rsa:2048 \
    -nodes \
    -keyout certs/service.key \
    -out certs/service.csr \
    -subj "/CN=service.lab"

cat > certs/service.ext <<'EOF'
subjectAltName=DNS:service.lab
basicConstraints=critical,CA:FALSE
keyUsage=digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
EOF

openssl x509 \
    -req \
    -in certs/service.csr \
    -CA certs/ca.crt \
    -CAkey certs/ca.key \
    -CAcreateserial \
    -out certs/service.crt \
    -days 30 \
    -sha256 \
    -extfile certs/service.ext

rm -f certs/service.csr certs/service.ext

echo
echo "[CHECK] Verifying legitimate certificate..."

openssl verify -CAfile certs/ca.crt certs/service.crt

openssl x509 \
    -in certs/service.crt \
    -noout -ext subjectAltName

echo
echo "[SETUP PASSED] Both server identities are ready."
echo "Attacker:    other.lab"
echo "Legitimate:  service.lab"
