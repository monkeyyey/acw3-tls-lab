
#!/usr/bin/env python3

import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
PYTHON_ROOT = Path.home() / "acw3"
CLIENT = PROJECT / "client" / "tls_client.py"

TESTS = [
    ("T01", "3.13.15", "missing", "success"),
    ("T02", "3.13.15", "wrong", "hostname_error"),
    ("T03", "3.13.15", "correct", "success"),
    ("T04", "3.13.16", "missing", "missing_error"),
]

if len(sys.argv) > 1:
    if sys.argv[1:] != ["--all"]:
        sys.exit("Usage: python3 demo/run_demo.py [--all]")

    TESTS += [
        ("T05", "3.13.16", "wrong", "hostname_error"),
        ("T06", "3.13.16", "correct", "success"),
    ]

HOSTNAMES = {
    "missing": "None",
    "wrong": "service.lab",
    "correct": "other.lab",
}

DESCRIPTIONS = {
    "success": "TLS handshake completes",
    "hostname_error": "Hostname mismatch rejected",
    "missing_error": "Missing hostname rejected with ValueError",
}

failures = 0

for test_id, version, mode, expected in TESTS:
    interpreter = (
        PYTHON_ROOT / f"python-{version}" / "bin" / "python3.13"
    )

    print(f"\n{'=' * 55}")
    print(f"{test_id} | Python {version} | Mode: {mode}")
    print(f"{'=' * 55}")
    print(f"Expected: {DESCRIPTIONS[expected]}")

    try:
        result = subprocess.run(
            [str(interpreter), str(CLIENT), "--mode", mode],
            cwd=PROJECT,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        print(f"Actual: Execution failed: {error}")
        print("RESULT: FAIL")
        failures += 1
        continue

    stdout = result.stdout
    stderr = result.stderr

    configuration_ok = all([
        f"Test mode: {mode}" in stdout,
        "Hostname checking: True" in stdout,
        f"Expected hostname: {HOSTNAMES[mode]}" in stdout,
    ])

    if expected == "success":
        passed = (
            configuration_ok
            and result.returncode == 0
            and "TLS HANDSHAKE COMPLETED" in stdout
            and "Peer certificate:" in stdout
        )
        actual = (
            "TLS HANDSHAKE COMPLETED"
            if passed else "Expected handshake not confirmed"
        )

    elif expected == "hostname_error":
        passed = (
            configuration_ok
            and result.returncode != 0
            and "ssl.SSLCertVerificationError:" in stderr
            and "Hostname mismatch" in stderr
            and "TLS HANDSHAKE COMPLETED" not in stdout
        )
        actual = (
            "Certificate rejected: Hostname mismatch"
            if passed else "Expected hostname error not confirmed"
        )

    else:
        passed = (
            configuration_ok
            and result.returncode != 0
            and "ValueError: check_hostname requires server_hostname"
            in stderr
            and "TLS HANDSHAKE COMPLETED" not in stdout
        )
        actual = (
            "ValueError: check_hostname requires server_hostname"
            if passed else "Expected ValueError not confirmed"
        )

    print(f"Actual:   {actual}")
    print(f"RESULT:   {'PASS' if passed else 'FAIL'}")

    if not passed:
        failures += 1
        print(f"Exit code: {result.returncode}")
        print("--- Full diagnostic output ---")
        print(stdout)
        print(stderr)

print(f"\n{'=' * 55}")
print(f"SUMMARY: {len(TESTS) - failures}/{len(TESTS)} tests passed")
print(f"{'=' * 55}")

sys.exit(1 if failures else 0)
