import socket
import ssl

ADDRESS = ("127.0.0.1", 8443)
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain("certs/server.crt", "certs/server.key")

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(ADDRESS)
    listener.listen(5)
    print(f"[*] Local TLS test server listening on https://{ADDRESS[0]}:{ADDRESS[1]}", flush=True)

    while True:
        conn, addr = listener.accept()
        try:
            with context.wrap_socket(conn, server_side=True) as tls_sock:
                print(f"[+] TLS handshake established from {addr}", flush=True)
                data = tls_sock.recv(1024)
                if data:
                    print(f"    Received: {data.decode('utf-8', errors='replace')}", flush=True)
        except (ssl.SSLError, ConnectionError, OSError) as error:
            print(f"[-] Handshake rejected / closed: {error}", flush=True)
