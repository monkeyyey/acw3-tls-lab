
# CVE-2026-19553 — CPython TLS Hostname Verification Bypass

## Project Overview

This project demonstrates CVE-2026-19553, a hostname-verification bypass affecting CPython's `SSLContext.wrap_bio()` API.

The demonstration compares:

- **Python 3.13.15** — Vulnerable version
- **Python 3.13.16** — Patched version

The client uses `ssl.MemoryBIO` and `SSLContext.wrap_bio()` to establish TLS connections.

In the vulnerable version, omitting `server_hostname` can allow a TLS handshake to succeed without checking whether the server certificate matches the hostname expected by the application.

The demonstration shows the security impact using a synthetic HTTP request containing a mock session token.

All activity takes place locally inside an Ubuntu virtual machine. No genuine credentials, external targets or real network interception are involved.

## Demonstration Architecture

The application always intends to communicate with **`service.lab`**.

Two TLS endpoints simulate the legitimate service and an unintended, attacker-controlled server.

| Role | Hostname | Address | Certificate identity |
|---|---|---|---|
| Simulated attacker | `other.lab` | `127.0.0.1:8443` | `other.lab` |
| Legitimate service | `service.lab` | `127.0.0.1:8444` | `service.lab` |

Both endpoints:

- Run inside the same Ubuntu VM.
- Are managed by one Python server programme.
- Use certificates signed by the same local test CA.
- Run on different loopback TCP ports.

The certificate trust chain and hostname verification are separate security checks.

The client verifies the certificate chain using `ssl.CERT_REQUIRED`. When a hostname is supplied, it should also verify that the certificate identifies the expected server.

### Simulated Attack Scenario

1. The application intends to contact `service.lab`.
2. The test client is deliberately directed to the simulated attacker endpoint at `127.0.0.1:8443`.
3. That endpoint presents a CA-trusted certificate for `other.lab`.
4. Vulnerable Python 3.13.15 is tested with `server_hostname=None`.
5. The TLS handshake succeeds without checking the expected hostname.
6. The client sends a synthetic HTTP request containing a mock session token.
7. The attacker endpoint receives the request and returns an acknowledgement.

The lab simulates the consequence of traffic reaching an unintended TLS endpoint. It does not demonstrate how an attacker redirects traffic in a real network.

## Environment

- Ubuntu 24.04 LTS in VMware
- OpenSSL 3.x
- Python 3.13.15, built separately from source
- Python 3.13.16, built separately from source
- Bash and Git

### Python Interpreter Locations

Vulnerable interpreter:

```bash
$HOME/acw3/python-3.13.15/bin/python3.13
```

Patched interpreter:

```bash
$HOME/acw3/python-3.13.16/bin/python3.13
```

Verify both versions:

```bash
"$HOME/acw3/python-3.13.15/bin/python3.13" --version
"$HOME/acw3/python-3.13.16/bin/python3.13" --version
```

Expected:

```text
Python 3.13.15
Python 3.13.16
```

## Relevant Project Files

| File | Purpose |
|---|---|
| `demo/impact_server.py` | Runs both attacker and legitimate TLS endpoints |
| `demo/impact_client.py` | Executes T01–T06 using the selected Python interpreter |
| `demo/t07_untrusted_ca.py` | Executes T07 using an unrelated CA |
| `demo/make_service_cert.sh` | Generates the legitimate `service.lab` certificate |
| `demo/make_t07_ca.sh` | Prepares the independent CA for T07 |
| `demo/preflight.sh` | Runs the existing environment preflight checks |
| `demo/DEMO_RUNBOOK.md` | Full demonstration commands and expected results |
| `certs/ca.crt` | Main trusted test CA certificate |
| `certs/server.crt` | Simulated attacker certificate for `other.lab` |
| `certs/service.crt` | Legitimate server certificate for `service.lab` |
| `certs/t07/ca.crt` | Independent, untrusted CA certificate for T07 |

Generated certificates and private keys are excluded from Git.

## Initial Setup

Run all commands from the repository root:

```bash
cd ~/acw3-github
```

### 1. Check Python Versions

```bash
"$HOME/acw3/python-3.13.15/bin/python3.13" --version
"$HOME/acw3/python-3.13.16/bin/python3.13" --version
```

### 2. Check Existing CA and Attacker Certificate

The main CA and `other.lab` certificate must already be generated.

```bash
ls -l \
  certs/ca.crt \
  certs/ca.key \
  certs/server.crt \
  certs/server.key
```

Do not regenerate the main CA unnecessarily. Replacing it can invalidate previously generated test certificates.

### 3. Generate the Legitimate Server Certificate

```bash
bash demo/make_service_cert.sh
```

This prepares the certificate for `service.lab` using the existing main test CA.

### 4. Prepare the Untrusted CA for T07

```bash
bash demo/make_t07_ca.sh
```

T07 uses a separate CA that does not issue or trust the attacker server certificate.

### 5. Verify Certificates

```bash
openssl verify -CAfile certs/ca.crt certs/server.crt
openssl verify -CAfile certs/ca.crt certs/service.crt
```

Expected:

```text
certs/server.crt: OK
certs/service.crt: OK
```

Check the hostname identities:

```bash
openssl x509 -in certs/server.crt -noout -ext subjectAltName
openssl x509 -in certs/service.crt -noout -ext subjectAltName
```

Expected:

- `server.crt` contains `DNS:other.lab`.
- `service.crt` contains `DNS:service.lab`.

## Running the Demonstration

Only **two Ubuntu terminals** are required.

### Terminal 1 — Start Both TLS Endpoints

```bash
cd ~/acw3-github
python3 -u demo/impact_server.py
```

Expected:

```text
DUAL-ENDPOINT TLS DEMONSTRATION

[READY] ATTACKER    other.lab   127.0.0.1:8443
[READY] LEGITIMATE  service.lab 127.0.0.1:8444
```

Leave Terminal 1 running.

Do not start a second server programme on port 8443.

### Terminal 2 — Verify Server Availability

```bash
cd ~/acw3-github

ss -ltn | grep -E '127\.0\.0\.1:(8443|8444)'
```

Both ports should be listening.

The existing environment preflight can also be run:

```bash
bash demo/preflight.sh
```

## Test Cases

### T01 — Vulnerable Missing Hostname

**Purpose:** Demonstrate the hostname-verification bypass and synthetic data reaching the simulated attacker.

```bash
"$HOME/acw3/python-3.13.15/bin/python3.13" \
demo/impact_client.py --mode missing
```

Expected:

- Intended service: `service.lab`
- Client `server_hostname`: `None`
- Server certificate: `other.lab`
- TLS handshake succeeds
- Attacker endpoint receives the mock session token

### T02 — Vulnerable Explicit Hostname

**Purpose:** Confirm that supplying the expected hostname prevents communication with the wrong server.

```bash
"$HOME/acw3/python-3.13.15/bin/python3.13" \
demo/impact_client.py --mode wrong
```

Expected:

- Client `server_hostname`: `service.lab`
- Server certificate: `other.lab`
- Hostname mismatch rejected
- No application request sent

### T03 — Vulnerable Python, Legitimate Server

**Purpose:** Demonstrate normal communication when the expected hostname matches the legitimate server certificate.

```bash
"$HOME/acw3/python-3.13.15/bin/python3.13" \
demo/impact_client.py --mode correct
```

Expected:

- Client `server_hostname`: `service.lab`
- Server certificate: `service.lab`
- TLS handshake succeeds
- Legitimate server receives the mock request

### T04 — Patched Missing Hostname

**Purpose:** Verify that patched Python rejects a missing hostname.

```bash
"$HOME/acw3/python-3.13.16/bin/python3.13" \
demo/impact_client.py --mode missing
```

Expected:

- Missing hostname rejected
- No TLS connection established
- No application request sent

### T05 — Patched Explicit Hostname

**Purpose:** Confirm that hostname verification still rejects the simulated attacker after patching.

```bash
"$HOME/acw3/python-3.13.16/bin/python3.13" \
demo/impact_client.py --mode wrong
```

Expected:

- Client expects `service.lab`
- Attacker certificate identifies `other.lab`
- Hostname mismatch rejected
- No application request sent

### T06 — Patched Python, Legitimate Server

**Purpose:** Verify normal TLS communication with the legitimate server after patching.

```bash
"$HOME/acw3/python-3.13.16/bin/python3.13" \
demo/impact_client.py --mode correct
```

Expected:

- Correct hostname verified
- TLS handshake succeeds
- Legitimate server receives the mock request

### T07 — Untrusted CA Negative Control

**Purpose:** Demonstrate that the hostname-verification bypass does not disable certificate-chain verification.

```bash
"$HOME/acw3/python-3.13.15/bin/python3.13" \
demo/t07_untrusted_ca.py --mode missing
```

Expected:

- Client `server_hostname`: `None`
- Server certificate: `other.lab`
- Client trusts an unrelated CA
- Certificate-chain verification rejects the connection
- No application request sent

T07 uses the attacker endpoint on port 8443. No additional server is required.

## Expected Test Summary

| Test | Python | Endpoint | Expected result |
|---|---|---|---|
| T01 | 3.13.15 | Attacker | Hostname bypass; mock token received |
| T02 | 3.13.15 | Attacker | Hostname mismatch blocked |
| T03 | 3.13.15 | Legitimate | Normal connection succeeds |
| T04 | 3.13.16 | Attacker configured | Missing hostname rejected before connection |
| T05 | 3.13.16 | Attacker | Hostname mismatch blocked |
| T06 | 3.13.16 | Legitimate | Normal connection succeeds |
| T07 | 3.13.15 | Attacker | Untrusted certificate blocked |

An expected rejection counts as a passed security-control test.

After running each test, check its exit code:

```bash
echo $?
```

Expected exit code for a passed test:

```text
0
```

## Security Controls Being Tested

### Certificate-Chain Verification

The client uses:

```python
context.verify_mode = ssl.CERT_REQUIRED
```

This requires the peer certificate to have a valid trust relationship with the configured CA.

T07 verifies that an unrelated CA cannot authenticate the attacker certificate.

### Hostname Verification

The client uses:

```python
context.check_hostname = True
```

When `server_hostname` is supplied, Python verifies that the peer certificate matches the expected hostname.

T02 and T05 demonstrate rejection of a hostname mismatch.

T01 demonstrates the vulnerable behaviour when the hostname is omitted from `SSLContext.wrap_bio()`.

T04 demonstrates the patched behaviour.

### Application-Level Impact

After a successful TLS handshake, the enhanced client sends a synthetic HTTP request:

```http
GET /api/account/profile HTTP/1.1
Host: service.lab
Authorization: Bearer MOCK-SESSION-TOKEN-001
```

The receiving endpoint returns an acknowledgement.

The mock token is not a genuine credential. The acknowledgement demonstrates that application data reached the endpoint, rather than merely that the TLS handshake completed.

## Validation and Troubleshooting

### Python Version Is Incorrect

Verify the interpreter paths before testing.

Do not use the system Python interpreter as a substitute for the specifically built vulnerable and patched versions.

### Server Is Not Running

Confirm both endpoints are listening:

```bash
ss -ltn | grep -E '127\.0\.0\.1:(8443|8444)'
```

### Port Already in Use

Check for existing listeners:

```bash
ss -ltnp | grep -E ':(8443|8444)'
```

Stop any previously running demonstration server before starting a new one.

### Certificate Verification Fails Unexpectedly

Check that:

- The main CA trusts both server certificates.
- `other.lab` and `service.lab` have the correct certificate SANs.
- The correct endpoint is selected for the test.
- T07 uses the separate, unrelated CA.
- `check_hostname` and `CERT_REQUIRED` remain enabled.

### Test Reports Success Unexpectedly

A security-control test must not pass merely because the connection failed for an unrelated reason.

Unexpected TLS, network or certificate errors should produce a failed test result.

## Demonstration Evidence

Evidence should show:

1. The Python version and test configuration.
2. The intended service and configured server certificate identity.
3. The TLS outcome.
4. Whether the attacker or legitimate endpoint received the synthetic HTTP request.
5. The contrast between vulnerable and patched Python.
6. The independent untrusted-CA rejection in T07.

**Critical comparisons:**

- T01 versus T02: Missing hostname versus explicitly verified hostname.
- T01 versus T04: Vulnerable versus patched Python.
- T03 versus T06: Normal legitimate communication before and after patching.
- T01 versus T07: Trusted wrong-name certificate versus untrusted certificate.

## Full Demonstration Instructions

See:

[DEMO_RUNBOOK.md](demo/DEMO_RUNBOOK.md)

The runbook contains the terminal commands, expected results and presentation sequence for T01–T07.

## Safety and Scope

- All servers bind to `127.0.0.1`.
- Both server identities are simulated.
- Only synthetic HTTP data is exchanged.
- The mock token has no authentication value.
- No real user credentials are collected.
- No external systems are targeted.
- No real network interception is performed.
- Generated certificate private keys must not be committed to Git.
