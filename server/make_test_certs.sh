#!/usr/bin/env bash
set -e

mkdir -p certs
rm -f certs/*

echo "[+] Generating disposable Lab Root CA..."
openssl req -x509 -newkey rsa:2048 -sha256 -nodes -days 45 \
  -keyout certs/ca.key -out certs/ca.crt \
  -subj '/CN=ACW3 Test Root CA' \
  -addext 'basicConstraints=critical,CA:TRUE' \
  -addext 'keyUsage=critical,keyCertSign,cRLSign'

echo "[+] Generating server key and CSR for other.lab..."
openssl req -newkey rsa:2048 -nodes \
  -keyout certs/server.key -out certs/server.csr \
  -subj '/CN=other.lab'

cat > certs/server.ext << 'EXT'
subjectAltName=DNS:other.lab
basicConstraints=CA:FALSE
keyUsage=digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
EXT

echo "[+] Signing server certificate with Lab Root CA..."
openssl x509 -req -in certs/server.csr \
  -CA certs/ca.crt -CAkey certs/ca.key -CAcreateserial \
  -out certs/server.crt -days 45 -sha256 -extfile certs/server.ext

echo ""
echo "[+] Verifying certificate chain against CA:"
openssl verify -CAfile certs/ca.crt certs/server.crt

echo ""
echo "[+] Verifying Subject Alternative Name (SAN):"
openssl x509 -in certs/server.crt -noout -text | grep -A2 'Subject Alternative Name'
