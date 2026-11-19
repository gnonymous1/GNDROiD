"""
tests/fixtures/mock_proxy.py
=============================
In-memory dual-protocol proxy server:
- HTTP Proxy: handles CONNECT tunneling and GET/POST with upstream Basic/Digest authentication.
- SOCKS5 Proxy: implements RFC 1928 / RFC 1929 authentication and domain-based routing.
- Includes chaos trigger for kill-switch failover testing.
"""

import socket
import base64
import threading
from typing import Dict, List, Optional, Any


class MockDualProxyServer:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 0,
        protocol: str = "http",
        auth_user: Optional[str] = "admin",
        auth_pass: Optional[str] = "p@ss123",
    ):
        self.host = host
        self.requested_port = port
        self.port = 0
        self.protocol = protocol.lower()
        self.auth_user = auth_user
        self.auth_pass = auth_pass
        self.server_socket: Optional[socket.socket] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self.requests_log: List[Dict[str, Any]] = []
        self.auth_successes = 0
        self.auth_failures = 0
        self.active_tunnels = 0

    def start(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.requested_port))
        self.port = self.server_socket.getsockname()[1]
        self.server_socket.listen(10)
        self._running = True
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def trigger_network_drop(self):
        """Forces immediate socket close to simulate upstream server outage."""
        self.stop()

    def _accept_loop(self):
        while self._running:
            try:
                client, _ = self.server_socket.accept()
                if self.protocol in ("socks5", "socks5h"):
                    threading.Thread(target=self._handle_socks5, args=(client,), daemon=True).start()
                else:
                    threading.Thread(target=self._handle_http, args=(client,), daemon=True).start()
            except Exception:
                break

    def _handle_http(self, client: socket.socket):
        with client:
            try:
                raw = client.recv(4096).decode("utf-8", errors="ignore")
            except Exception:
                return
            if not raw:
                return
            lines = raw.split("\r\n")
            req_line = lines[0] if lines else ""
            headers: Dict[str, str] = {}
            for l in lines[1:]:
                if ": " in l:
                    k, v = l.split(": ", 1)
                    headers[k.lower()] = v

            self.requests_log.append({"request": req_line, "headers": headers})

            # Check Authentication
            if self.auth_user and self.auth_pass is not None:
                auth_hdr = headers.get("proxy-authorization", "")
                expected = "Basic " + base64.b64encode(
                    f"{self.auth_user}:{self.auth_pass}".encode("utf-8")
                ).decode("utf-8")
                if auth_hdr != expected:
                    self.auth_failures += 1
                    try:
                        client.sendall(
                            b"HTTP/1.1 407 Proxy Authentication Required\r\n"
                            b"Proxy-Authenticate: Basic realm=\"GNDROiD Mock Proxy\"\r\n"
                            b"Content-Length: 0\r\n\r\n"
                        )
                    except Exception:
                        pass
                    return
                self.auth_successes += 1

            # CONNECT Method
            if req_line.startswith("CONNECT"):
                try:
                    client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                except Exception:
                    return
                self.active_tunnels += 1
                try:
                    client.settimeout(2.0)
                    while self._running:
                        data = client.recv(1024)
                        if not data:
                            break
                        client.sendall(data)
                except Exception:
                    pass
                finally:
                    self.active_tunnels -= 1
            else:
                try:
                    client.sendall(
                        b"HTTP/1.1 200 OK\r\n"
                        b"Content-Type: text/plain\r\n"
                        b"Content-Length: 15\r\n\r\n"
                        b"PROXY_ECHO_PASS"
                    )
                except Exception:
                    pass

    def _handle_socks5(self, client: socket.socket):
        with client:
            try:
                # 1. Negotiation
                header = client.recv(2)
                if not header or header[0] != 5:
                    return
                nmethods = header[1]
                methods = client.recv(nmethods)

                if self.auth_user and self.auth_pass is not None:
                    client.sendall(b"\x05\x02")  # Require USER/PASS
                    # 2. RFC 1929 Auth
                    auth_ver = client.recv(1)
                    if not auth_ver or auth_ver[0] != 1:
                        return
                    u_data = client.recv(1)
                    if not u_data:
                        return
                    ulen = u_data[0]
                    uname = client.recv(ulen).decode("utf-8", errors="ignore")
                    p_data = client.recv(1)
                    if not p_data:
                        return
                    plen = p_data[0]
                    passwd = client.recv(plen).decode("utf-8", errors="ignore")

                    if uname == self.auth_user and passwd == self.auth_pass:
                        self.auth_successes += 1
                        client.sendall(b"\x01\x00")  # Success
                    else:
                        self.auth_failures += 1
                        client.sendall(b"\x01\x01")  # Fail
                        return
                else:
                    client.sendall(b"\x05\x00")  # NO AUTH

                # 3. Request
                req = client.recv(4)
                if not req or req[1] != 1:  # CONNECT = 1
                    return
                atyp = req[3]
                dest_addr = ""
                if atyp == 1:  # IPv4
                    dest_addr = socket.inet_ntoa(client.recv(4))
                elif atyp == 3:  # Domain
                    d_len = client.recv(1)
                    if not d_len:
                        return
                    dlen = d_len[0]
                    dest_addr = client.recv(dlen).decode("utf-8", errors="ignore")
                port_data = client.recv(2)
                if not port_data:
                    return
                port = int.from_bytes(port_data, "big")

                self.requests_log.append({"socks5_dest": dest_addr, "port": port})
                client.sendall(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")

                # Tunnel echo
                self.active_tunnels += 1
                try:
                    client.settimeout(2.0)
                    while self._running:
                        data = client.recv(1024)
                        if not data:
                            break
                        client.sendall(data)
                except Exception:
                    pass
                finally:
                    self.active_tunnels -= 1
            except Exception:
                pass

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


# Alias for compatibility
MockUpstreamProxy = MockDualProxyServer
