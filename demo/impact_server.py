
import select
import socket
import ssl
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOST = "127.0.0.1"

RED = "\033[1;31m"
GREEN = "\033[1;32m"
RESET = "\033[0m"

ENDPOINTS = {
    "ATTACKER": {
        "port": 8443,
        "certificate": ROOT / "certs/server.crt",
        "key": ROOT / "certs/server.key",
        "hostname": "other.lab",
        "colour": RED,
    },
    "LEGITIMATE": {
        "port": 8444,
        "certificate": ROOT / "certs/service.crt",
        "key": ROOT / "certs/service.key",
        "hostname": "service.lab",
        "colour": GREEN,
    },
}


def make_context(config):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)

    context.load_cert_chain(
        certfile=str(config["certificate"]),
        keyfile=str(config["key"]),
    )

    return context


def handle_client(connection, role, context):
    colour = ENDPOINTS[role]["colour"]

    try:
        with context.wrap_socket(
            connection, server_side=True
        ) as tls:

            tls.settimeout(5)

            print(
                f"\n[{role}] TLS connection established",
                flush=True,
            )

            request = b""

            while b"\r\n\r\n" not in request and len(request) < 8192:
                chunk = tls.recv(4096)

                if not chunk:
                    break

                request += chunk

            if b"\r\n\r\n" not in request:
                print(
                    f"[{role}] No complete HTTP request received.",
                    flush=True,
                )
                return

            expected_parts = (
                b"GET /api/account/profile HTTP/1.1\r\n",
                b"Host: service.lab\r\n",
                b"Authorization: Bearer MOCK-SESSION-TOKEN-001\r\n",
            )

            if not all(part in request for part in expected_parts):
                print(
                    f"[{role}] Unexpected HTTP request.",
                    flush=True,
                )
                return

            message = request.decode(
                "utf-8", errors="replace"
            )

            print("\n========== RECEIVED HTTP REQUEST ==========")
            print(message.replace("\r", "").strip())
            print("===========================================")

            if role == "ATTACKER":
                print(
                    f"{colour}"
                    "[!] ATTACKER RECEIVED MOCK SESSION TOKEN"
                    f"{RESET}",
                    flush=True,
                )
                print(
                    "Certificate: other.lab | Requested: service.lab",
                    flush=True,
                )
            else:
                print(
                    f"{colour}"
                    "[OK] LEGITIMATE SERVER RECEIVED REQUEST"
                    f"{RESET}",
                    flush=True,
                )
                print(
                    "Certificate: service.lab | Requested: service.lab",
                    flush=True,
                )

            # The client requires this response to confirm receipt.
            body = b"MOCK_REQUEST_RECEIVED"

            response = (
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: text/plain\r\n"
                + f"Content-Length: {len(body)}\r\n".encode()
                + b"Connection: close\r\n\r\n"
                + body
            )

            tls.sendall(response)

    except (ssl.SSLError, OSError) as error:
        print(
            f"[{role}] TLS connection aborted: "
            f"{type(error).__name__}",
            flush=True,
        )

    finally:
        connection.close()


def main():
    listeners = {}
    opened = []

    try:
        for role, config in ENDPOINTS.items():
            context = make_context(config)

            sock = socket.socket(
                socket.AF_INET, socket.SOCK_STREAM
            )
            opened.append(sock)

            sock.setsockopt(
                socket.SOL_SOCKET,
                socket.SO_REUSEADDR,
                1,
            )

            sock.bind((HOST, config["port"]))
            sock.listen(10)

            listeners[sock] = (role, context)

        print("\n========================================")
        print("DUAL-ENDPOINT TLS DEMONSTRATION")
        print("========================================")
        print("[READY] ATTACKER    other.lab   127.0.0.1:8443")
        print("[READY] LEGITIMATE  service.lab 127.0.0.1:8444")
        print("Press Ctrl+C to stop.\n", flush=True)

        while True:
            ready, _, _ = select.select(
                list(listeners.keys()), [], [], 1
            )

            for listener in ready:
                connection, _ = listener.accept()
                connection.settimeout(5)

                role, context = listeners[listener]

                handle_client(connection, role, context)

    except KeyboardInterrupt:
        print("\n[STOPPED] TLS demonstration server.")

    except OSError as error:
        print(
            f"{RED}[SERVER ERROR] {error}{RESET}",
            file=sys.stderr,
        )
        print(
            "Check whether another programme is using port 8443 or 8444.",
            file=sys.stderr,
        )
        return 1

    finally:
        for sock in opened:
            sock.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
