
import argparse
import re
import socket
import ssl
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

HOST = "127.0.0.1"
PORT = 8443
CA_FILE = ROOT / "certs" / "t07" / "ca.crt"
SERVER_CERT = ROOT / "certs" / "server.crt"

RED = "\033[1;31m"
GREEN = "\033[1;32m"
RESET = "\033[0m"


def get_server_certificate_name():
    """Read the configured server certificate's DNS SAN."""
    try:
        result = subprocess.run(
            [
                "openssl", "x509",
                "-in", str(SERVER_CERT),
                "-noout", "-ext", "subjectAltName",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError(
            f"Cannot inspect server certificate: {error}"
        ) from error

    names = re.findall(
        r"DNS\s*:\s*([^,\s]+)", result.stdout
    )

    if not names:
        raise RuntimeError("No DNS SAN in server certificate")

    return ", ".join(names)


def send_pending(outgoing, sock):
    while True:
        data = outgoing.read()
        if not data:
            break
        sock.sendall(data)


def run_test():
    if sys.version_info[:3] != (3, 13, 15):
        print(f"{RED}[FAIL] Expected Python 3.13.15{RESET}")
        return 1

    if not CA_FILE.is_file():
        print(f"{RED}[FAIL] Independent T07 CA missing{RESET}")
        print("Run: bash demo/make_t07_ca.sh")
        return 1

    try:
        certificate_name = get_server_certificate_name()

        context = ssl.create_default_context(
            cafile=str(CA_FILE)
        )

        # Keep all actual security checks enabled.
        if (
            context.check_hostname is not True
            or context.verify_mode != ssl.CERT_REQUIRED
        ):
            raise RuntimeError("TLS verification is disabled")

        print()
        print("=" * 45)
        print(f"T07 | Python {sys.version.split()[0]}")
        print("Intended service: service.lab")
        print("Client server_hostname: None")
        print(f"Server certificate: {certificate_name}")
        print("Client trusts: Unrelated test CA")
        print("=" * 45)

        incoming = ssl.MemoryBIO()
        outgoing = ssl.MemoryBIO()

        tls_client = context.wrap_bio(
            incoming,
            outgoing,
            server_side=False,
            server_hostname=None,
        )

        with socket.create_connection(
            (HOST, PORT), timeout=5
        ) as sock:
            sock.settimeout(5)

            while True:
                try:
                    tls_client.do_handshake()
                    send_pending(outgoing, sock)

                    print(
                        f"{RED}[FAIL] UNTRUSTED "
                        f"CERTIFICATE ACCEPTED{RESET}"
                    )
                    return 1

                except ssl.SSLCertVerificationError as error:
                    reason = getattr(
                        error, "verify_message", str(error)
                    )
                    code = getattr(error, "verify_code", None)

                    expected_error = (
                        code == 20
                        and "unable to get local issuer certificate"
                        in reason.lower()
                    )

                    if expected_error:
                        print(
                            f"{GREEN}[BLOCKED] "
                            f"UNTRUSTED CERTIFICATE{RESET}"
                        )
                        print(
                            "Certificate-chain verification "
                            "still works."
                        )
                        print("No mock request sent.")
                        return 0

                    print(
                        f"{RED}[FAIL] UNEXPECTED "
                        f"CERTIFICATE ERROR{RESET}"
                    )
                    print("Reason:", reason)
                    return 1

                except ssl.SSLWantReadError:
                    send_pending(outgoing, sock)

                    data = sock.recv(16384)
                    if not data:
                        raise ConnectionError(
                            "Server closed during handshake"
                        )

                    incoming.write(data)

                except ssl.SSLWantWriteError:
                    send_pending(outgoing, sock)

    except (OSError, ssl.SSLError, ValueError, RuntimeError) as error:
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
        choices=["missing"],
    )
    parser.parse_args()

    sys.exit(run_test())
