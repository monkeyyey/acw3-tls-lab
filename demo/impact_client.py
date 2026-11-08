
import argparse
import re
import socket
import ssl
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOST = "127.0.0.1"

RED = "\033[1;31m"
GREEN = "\033[1;32m"
RESET = "\033[0m"

# Every scenario represents an application intending
# to communicate with service.lab.
SCENARIOS = {
    "missing": {
        "hostname": None,
        "port": 8443,
        "certificate": "server.crt",
        "expected_identity": "other.lab",
        "role": "ATTACKER",
    },
    "wrong": {
        "hostname": "service.lab",
        "port": 8443,
        "certificate": "server.crt",
        "expected_identity": "other.lab",
        "role": "ATTACKER",
    },
    "correct": {
        "hostname": "service.lab",
        "port": 8444,
        "certificate": "service.crt",
        "expected_identity": "service.lab",
        "role": "LEGITIMATE",
    },
}


def get_certificate_names(filename):
    path = ROOT / "certs" / filename

    try:
        result = subprocess.run(
            [
                "openssl",
                "x509",
                "-in",
                str(path),
                "-noout",
                "-ext",
                "subjectAltName",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError(
            f"Cannot inspect certificate: {error}"
        ) from error

    names = re.findall(
        r"DNS\s*:\s*([^,\s]+)",
        result.stdout,
    )

    if not names:
        raise RuntimeError("No DNS SAN found")

    return names


def send_pending(outgoing, sock):
    while outgoing.pending:
        sock.sendall(outgoing.read())


def receive_network(incoming, sock):
    data = sock.recv(16384)

    if not data:
        raise ConnectionError("TLS connection closed")

    incoming.write(data)


def run(mode):
    version = sys.version_info[:3]

    if version not in ((3, 13, 15), (3, 13, 16)):
        print(f"{RED}[FAIL] Wrong Python version{RESET}")
        return 1

    patched = version == (3, 13, 16)

    test_ids = {
        "missing": "T04" if patched else "T01",
        "wrong": "T05" if patched else "T02",
        "correct": "T06" if patched else "T03",
    }

    config = SCENARIOS[mode]
    expected_hostname = config["hostname"]

    try:
        configured_names = get_certificate_names(
            config["certificate"]
        )

        if configured_names != [config["expected_identity"]]:
            raise RuntimeError(
                "Incorrect configured server certificate"
            )

        print()
        print("=" * 45)
        print(f"{test_ids[mode]} | Python {sys.version.split()[0]}")
        print("Intended service: service.lab")
        print(f"Endpoint: {config['role'].lower()}")
        print(f"Client server_hostname: {expected_hostname!r}")
        print(f"Server certificate: {', '.join(configured_names)}")
        print("=" * 45)

        context = ssl.create_default_context(
            cafile=str(ROOT / "certs" / "ca.crt")
        )

        # Preserve actual security checks.
        if (
            context.check_hostname is not True
            or context.verify_mode != ssl.CERT_REQUIRED
        ):
            raise RuntimeError("TLS verification is disabled")

        incoming = ssl.MemoryBIO()
        outgoing = ssl.MemoryBIO()

        tls = context.wrap_bio(
            incoming,
            outgoing,
            server_side=False,
            server_hostname=expected_hostname,
        )

        with socket.create_connection(
            (HOST, config["port"]), timeout=5
        ) as sock:

            sock.settimeout(5)

            while True:
                try:
                    tls.do_handshake()
                    send_pending(outgoing, sock)
                    break

                except ssl.SSLWantReadError:
                    send_pending(outgoing, sock)
                    receive_network(incoming, sock)

                except ssl.SSLWantWriteError:
                    send_pending(outgoing, sock)

            # Verify actual peer certificate after handshake.
            certificate = tls.getpeercert()

            actual_names = [
                value
                for kind, value in certificate.get(
                    "subjectAltName", ()
                )
                if kind == "DNS"
            ]

            if actual_names != configured_names:
                raise RuntimeError(
                    "TLS peer identity differs from configured certificate"
                )

            if mode == "wrong" or (
                mode == "missing" and patched
            ):
                raise RuntimeError(
                    "Unsafe TLS configuration unexpectedly accepted"
                )

            print(f"{GREEN}TLS HANDSHAKE SUCCESSFUL{RESET}")
            print("Sending synthetic session token...")

            # Same mock request in attacker and legitimate tests.
            request = (
                "GET /api/account/profile HTTP/1.1\r\n"
                "Host: service.lab\r\n"
                "Authorization: Bearer MOCK-SESSION-TOKEN-001\r\n"
                "Accept: application/json\r\n"
                "Connection: close\r\n"
                "\r\n"
            ).encode("ascii")

            sent = 0

            while sent < len(request):
                try:
                    sent += tls.write(request[sent:])
                    send_pending(outgoing, sock)

                except ssl.SSLWantReadError:
                    send_pending(outgoing, sock)
                    receive_network(incoming, sock)

                except ssl.SSLWantWriteError:
                    send_pending(outgoing, sock)

            # Confirm that the endpoint received the mock request.
            response = b""
            acknowledgement = b"MOCK_REQUEST_RECEIVED"

            while acknowledgement not in response:
                try:
                    chunk = tls.read(4096)

                    if not chunk:
                        raise ConnectionError(
                            "Server closed without acknowledgement"
                        )

                    response += chunk

                except ssl.SSLWantReadError:
                    send_pending(outgoing, sock)
                    receive_network(incoming, sock)

            if mode == "missing":
                print(
                    f"\n{RED}"
                    "[!] HOSTNAME VERIFICATION BYPASS CONFIRMED"
                    f"{RESET}"
                )
                print(
                    f"{RED}"
                    "[!] ATTACKER RECEIVED MOCK SESSION TOKEN"
                    f"{RESET}"
                )

            else:
                print(
                    f"{GREEN}"
                    "[OK] CORRECT HOSTNAME VERIFIED"
                    f"{RESET}"
                )
                print(
                    f"{GREEN}"
                    "[OK] LEGITIMATE SERVER RECEIVED REQUEST"
                    f"{RESET}"
                )

            return 0

    except ssl.SSLCertVerificationError as error:
        if (
            mode == "wrong"
            and "hostname mismatch" in str(error).lower()
        ):
            print(
                f"{GREEN}"
                "[BLOCKED] HOSTNAME MISMATCH"
                f"{RESET}"
            )
            print("No application request sent.")
            return 0

        print(
            f"{RED}[FAIL] Unexpected certificate error: "
            f"{error}{RESET}"
        )
        return 1

    except ValueError as error:
        if (
            mode == "missing"
            and patched
            and "check_hostname requires server_hostname"
            in str(error)
        ):
            print(
                f"{GREEN}"
                "[PATCHED] MISSING HOSTNAME REJECTED"
                f"{RESET}"
            )
            print("No application request sent.")
            return 0

        print(f"{RED}[FAIL] {error}{RESET}")
        return 1

    except (OSError, ssl.SSLError, RuntimeError) as error:
        print(
            f"{RED}[FAIL] "
            f"{type(error).__name__}: {error}{RESET}"
        )
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--mode",
        required=True,
        choices=SCENARIOS.keys(),
    )

    args = parser.parse_args()
    sys.exit(run(args.mode))
