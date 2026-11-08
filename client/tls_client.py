
import argparse
import socket
import ssl
from pathlib import Path

# Choose whether to provide an expected hostname.

parser = argparse.ArgumentParser()

parser.add_argument(
    "--mode",
    choices=["missing", "wrong", "correct"],
    required=True
)

args = parser.parse_args()

hostnames = {
    "missing": None,
    "wrong": "service.lab",
    "correct": "other.lab"
}

expected_hostname = hostnames[args.mode]

print("Test mode:", args.mode)


# Certificate authority provided by Person B.
ca_file = Path(__file__).resolve().parent.parent / "certs" / "ca.crt"

context = ssl.create_default_context(
    cafile=str(ca_file)
)

print("Hostname checking:", context.check_hostname)
print("Expected hostname:", expected_hostname)

# These buffers carry TLS data between the
# SSL object and the actual network socket.
incoming = ssl.MemoryBIO()
outgoing = ssl.MemoryBIO()

tls_client = context.wrap_bio(
    incoming,
    outgoing,
    server_side=False,
    server_hostname=expected_hostname
)

# Connect to Person B's local TLS server.
with socket.create_connection(
    ("127.0.0.1", 8443),
    timeout=5
) as sock:

    def send_pending():
        while True:
            data = outgoing.read()
            if not data:
                break
            sock.sendall(data)

    # Perform the TLS handshake.
    while True:
        try:
            tls_client.do_handshake()
            send_pending()
            break

        except ssl.SSLWantReadError:
            send_pending()
            data = sock.recv(16384)

            if not data:
                raise ConnectionError(
                    "Server closed the connection"
                )

            incoming.write(data)

        except ssl.SSLWantWriteError:
            send_pending()

print("TLS HANDSHAKE COMPLETED")
print("TLS version:", tls_client.version())
print("Peer certificate:", tls_client.getpeercert())
