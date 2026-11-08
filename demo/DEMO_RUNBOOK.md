
# CVE-2026-19553 — TLS Hostname Verification Bypass Demo Runbook

## 1. Demonstration Overview

This demonstration reproduces CVE-2026-19553 using vulnerable CPython 3.13.15 and compares its behaviour with patched CPython 3.13.16.

The client application always intends to communicate with `service.lab`.

| Endpoint | Address | Certificate identity | Role |
|---|---|---|---|
| Attacker | `127.0.0.1:8443` | `other.lab` | Simulated unintended server |
| Legitimate | `127.0.0.1:8444` | `service.lab` | Intended server |

Both endpoints are managed by `demo/impact_server.py` inside one Ubuntu VM. Both server certificates are signed by the same local test CA.

T01 demonstrates the hostname-verification bypass. T02 and T04 demonstrate the relevant security protections. T03 and T06 demonstrate normal communication with the legitimate server. T07 confirms that certificate-chain verification remains active.

All HTTP requests and session tokens are synthetic. The test simulates an unintended TLS endpoint; it does not perform real network interception.

## 2. Environment Requirements

- Ubuntu 24.04 LTS inside VMware Workstation
- Vulnerable CPython 3.13.15
- Patched CPython 3.13.16
- OpenSSL installed
- GitHub repository at `~/acw3-github`
- TCP ports 8443 and 8444 available

Python interpreters:

```bash
$HOME/acw3/python-3.13.15/bin/python3.13
$HOME/acw3/python-3.13.16/bin/python3.13
```

Always run the commands from the repository root unless stated otherwise.

## 3. Certificate Preparation

The main test CA and `other.lab` server certificate must already exist.

If these files are absent, stop the TLS server and run the original certificate-generation script from the repository root:

```bash
cd ~/acw3-github
bash server/make_test_certs.sh
```

**Warning:** This original script regenerates certificates and removes existing generated files. Do not run it unnecessarily or while the server is running.

Generate or verify the legitimate `service.lab` certificate:

```bash
bash demo/make_service_cert.sh
```

Generate or verify the independent T07 CA:

```bash
bash demo/make_t07_ca.sh
```

Verify both server certificates:

```bash
openssl verify -CAfile certs/ca.crt certs/server.crt
openssl verify -CAfile certs/ca.crt certs/service.crt
```

Expected:

```text
certs/server.crt: OK
certs/service.crt: OK
```

Check both server identities:

```bash
openssl x509 -in certs/server.crt -noout -ext subjectAltName
openssl x509 -in certs/service.crt -noout -ext subjectAltName
```

Expected identities:

- `server.crt`: `DNS:other.lab`
- `service.crt`: `DNS:service.lab`

T07 uses a separate CA at `certs/t07/ca.crt`. This CA must not trust the server certificate.

## 4. Terminal 1 — Start the TLS Server

Open the first Ubuntu terminal:

```bash
cd ~/acw3-github
python3 -u demo/impact_server.py
```

Expected:

```text
[READY] ATTACKER    other.lab   127.0.0.1:8443
[READY] LEGITIMATE  service.lab 127.0.0.1:8444
```

Leave this terminal running.

The server will display the HTTP requests received by the attacker or legitimate endpoint.

Do not start `server/tls_server.py` simultaneously, because it also uses port 8443.

## 5. Terminal 2 — Preflight Checks

Open another Ubuntu terminal:

```bash
cd ~/acw3-github

bash demo/preflight.sh
```

Expected:

```text
PREFLIGHT CHECKS PASSED
```

The existing preflight script checks the original port 8443. Confirm both demonstration endpoints separately:

```bash
ss -ltn | grep -E '127\.0\.0\.1:(8443|8444)'
```

Both ports must be listening.

## 6. Terminal 2 — Execute T01 to T07

### T01 — Vulnerable Missing Hostname

```bash
"$HOME/acw3/python-3.13.15/bin/python3.13" \
demo/impact_client.py --mode missing
```

Expected:

- Intended server: `service.lab`
- Client `server_hostname`: `None`
- Server certificate: `other.lab`
- TLS handshake successful
- Red hostname-verification bypass message
- Attacker endpoint receives the synthetic session token

### T02 — Vulnerable Wrong Hostname

```bash
"$HOME/acw3/python-3.13.15/bin/python3.13" \
demo/impact_client.py --mode wrong
```

Expected:

- Client `server_hostname`: `service.lab`
- Server certificate: `other.lab`
- Hostname mismatch blocked
- No HTTP request sent

### T03 — Vulnerable Python, Legitimate Server

```bash
"$HOME/acw3/python-3.13.15/bin/python3.13" \
demo/impact_client.py --mode correct
```

Expected:

- Client `server_hostname`: `service.lab`
- Server certificate: `service.lab`
- TLS handshake successful
- Legitimate endpoint receives the synthetic session token

### T04 — Patched Missing Hostname

```bash
"$HOME/acw3/python-3.13.16/bin/python3.13" \
demo/impact_client.py --mode missing
```

Expected:

- Missing hostname rejected
- `ValueError` handled by the client
- No TLS connection established
- No HTTP request sent

### T05 — Patched Wrong Hostname

```bash
"$HOME/acw3/python-3.13.16/bin/python3.13" \
demo/impact_client.py --mode wrong
```

Expected:

- Hostname mismatch blocked
- No HTTP request sent

### T06 — Patched Python, Legitimate Server

```bash
"$HOME/acw3/python-3.13.16/bin/python3.13" \
demo/impact_client.py --mode correct
```

Expected:

- Correct hostname verified
- TLS handshake successful
- Legitimate endpoint receives the synthetic session token

### T07 — Untrusted CA Negative Control

```bash
"$HOME/acw3/python-3.13.15/bin/python3.13" \
demo/t07_untrusted_ca.py --mode missing
```

Expected:

- Intended server: `service.lab`
- Client `server_hostname`: `None`
- Server certificate: `other.lab`
- Client trusts an unrelated CA
- Untrusted certificate blocked
- No HTTP request sent

T07 uses the same attacker endpoint on port 8443. No additional server is required.

## 7. Expected Test Results

| Test | Server endpoint | Expected outcome |
|---|---|---|
| T01 | Attacker | Bypass confirmed; mock token received |
| T02 | Attacker | Hostname mismatch blocked |
| T03 | Legitimate | Normal connection successful |
| T04 | None; rejected before connection | Missing hostname rejected by patch |
| T05 | Attacker | Hostname mismatch blocked |
| T06 | Legitimate | Normal connection successful |
| T07 | Attacker | Untrusted certificate rejected |

An expected rejection is a successful security-control test.

Each test should exit with code `0` when the expected outcome occurs.

To inspect the exit code immediately after a test:

```bash
echo $?
```

## 8. Failure Detection

If a test gives an unexpected result, check:

1. The correct Python interpreter was used.
2. Both TLS server ports are listening.
3. The certificate SAN matches the endpoint role.
4. The main CA trusts both server certificates.
5. The independent T07 CA does not trust the attacker certificate.
6. The TLS client still enables `check_hostname=True` and `CERT_REQUIRED`.

A connection failure alone is not evidence that hostname or CA verification worked.

Do not disable TLS security checks to force a test to succeed.

## 9. Presentation Notes

Terminal 1 displays the attacker and legitimate endpoints and the synthetic HTTP requests received.

Terminal 2 displays each test's Python version, intended server, `server_hostname`, configured server certificate identity and outcome.

The displayed server certificate identity is read from the configured local certificate file. For successful TLS handshakes, the client also checks the actual peer certificate.

A successful TLS handshake alone does not prove correct server identity verification.

The main vulnerability evidence is T01 compared with T02 and T04.

The impact demonstration shows synthetic application data reaching an unintended endpoint. It does not simulate real network traffic interception or credential theft.

All generated certificates and private keys remain excluded from GitHub.
