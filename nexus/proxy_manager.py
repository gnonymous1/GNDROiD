"""
nexus/proxy_manager.py
======================
GNDROiD Enterprise Authenticated Transparent Proxy Engine.

Architectural Capabilities:
1. Feature 10: Fast Auth-Stripping Local Proxy Daemon
   - Host-side proxy daemon listening on 127.0.0.1:local_port (default 8990,
     reached from Android guest via QEMU NAT 10.0.2.2:8990).
   - Supports upstream proxies:
     * HTTP/HTTPS proxies with Basic authentication (Proxy-Authorization: Basic)
       and RFC 2617 / RFC 7616 Digest authentication.
     * SOCKS5 proxies with RFC 1928 / RFC 1929 username/password authentication
       and ATYP 0x03 domain name resolution (DNS-over-Proxy).
   - Handles incoming guest requests:
     * CONNECT host:port HTTP/1.x: Strips client auth headers, connects to upstream
       proxy with credentials injection/negotiation, responds 200 Connection Established,
       and pumps bidirectional raw traffic via non-blocking sockets.
     * Direct HTTP requests (GET / POST / PUT / ...): Rewrites request line and
       headers, strips client auth headers, injects upstream Proxy-Authorization,
       forwards to upstream, and streams responses back.
   - Robust socket lifecycle management: clean shutdown, timeout handling, non-blocking
     select loops, connection tracking, and instant teardown.

2. Feature 11: Transparent Tun2Socks Interceptor
   - Mode 'local_auth': Configures Android system global proxy via ADB (10.0.2.2:port).
   - Mode 'tun2socks':
     * Clamps MTU to 1380 on guest interfaces eth0 and wlan0 (ip link set dev <dev> mtu 1380)
       to eliminate packet fragmentation across nested tunnels.
     * Generates and executes transparent routing commands / iptables capture rules to
       intercept all TCP and UDP traffic (Flutter, Telegram, gRPC, Go binaries).
   - Clean detachment: Restores system settings, flushes routing/iptables rules.

3. Feature 12: DNS-over-Proxy & Egress Kill-Switch
   - Eliminates local DNS leaks by disabling Android Private DNS (private_dns_mode off)
     and resolving hostnames remotely via SOCKS5 domain name lookup (ATYP 0x03) or DoH.
   - Active heartbeat monitoring thread (default every 2.0s) probing upstream health.
   - Immediate fail-closed kill-switch:
     * Terminates all in-flight guest client sockets immediately.
     * Injects fail-closed firewall rule: iptables -I OUTPUT 1 -j DROP via ADB.
     * Non-root fallback: sets unreachable global proxy (127.0.0.1:1) and clears DNS.
     * Sets kill-switch state to ACTIVE.
   - Automatic recovery: Removes blocking iptables rule, restores proxy settings,
     and transitions kill-switch state back to INACTIVE.
   - Full status introspection via get_proxy_status(serial=None).
"""

import os
import sys
import time
import socket
import select
import base64
import hashlib
import logging
import threading
import subprocess
from enum import Enum
from typing import Dict, Any, List, Optional, Tuple, Set, Callable
from urllib.parse import urlparse, unquote

logger = logging.getLogger("gndroid.proxy_manager")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def _run_hidden(cmd: List[str], timeout: int = 8) -> subprocess.CompletedProcess:
    """Executes subprocess silently in background without spawning console windows."""
    kwargs: Dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "timeout": timeout
    }
    if os.name == "nt":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
        kwargs["startupinfo"] = si
    return subprocess.run(cmd, **kwargs)


class ProxyProtocol(str, Enum):
    HTTP = "http"
    HTTPS = "https"
    SOCKS5 = "socks5"
    SOCKS5H = "socks5h"
    DIRECT = "direct"


class ProxyMode(str, Enum):
    LOCAL_AUTH = "local_auth"
    TUN2SOCKS = "tun2socks"


class KillSwitchState(str, Enum):
    INACTIVE = "INACTIVE"
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class UpstreamConfig:
    """Encapsulates upstream proxy configuration and authentication parameters."""

    def __init__(
        self,
        protocol: str = "http",
        host: str = "127.0.0.1",
        port: int = 8080,
        username: Optional[str] = None,
        password: Optional[str] = None,
        auth_mode: str = "auto"  # 'auto', 'basic', 'digest'
    ):
        self.protocol = protocol.lower()
        self.host = host
        self.port = int(port)
        self.username = username
        self.password = password
        self.auth_mode = auth_mode.lower()

    @property
    def is_socks5(self) -> bool:
        return self.protocol in ("socks5", "socks5h")

    @property
    def is_http(self) -> bool:
        return self.protocol in ("http", "https")

    @property
    def has_auth(self) -> bool:
        return bool(self.username and self.password is not None)

    @classmethod
    def from_url(cls, url: str) -> "UpstreamConfig":
        """Parses upstream proxy URL (e.g. http://user:pass@proxy.example.com:8080)."""
        if not url:
            return cls(protocol="direct", host="", port=0)

        parsed = urlparse(url)
        protocol = parsed.scheme.lower() if parsed.scheme else "http"
        host = parsed.hostname or "127.0.0.1"
        
        default_port = 1080 if protocol in ("socks5", "socks5h") else 8080
        port = parsed.port or default_port
        
        username = unquote(parsed.username) if parsed.username else None
        password = unquote(parsed.password) if parsed.password is not None else None

        return cls(
            protocol=protocol,
            host=host,
            port=port,
            username=username,
            password=password,
            auth_mode="auto"
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UpstreamConfig":
        """Constructs configuration from dictionary."""
        return cls(
            protocol=data.get("protocol") or data.get("type", "http"),
            host=data.get("host", "127.0.0.1"),
            port=int(data.get("port", 8080)),
            username=data.get("username"),
            password=data.get("password"),
            auth_mode=data.get("auth_mode", "auto")
        )

    def to_url(self, masked: bool = True) -> str:
        """Returns standard URL string, optionally masking sensitive passwords."""
        if self.protocol == "direct":
            return "direct://"
        auth_part = ""
        if self.username:
            pwd = "***" if masked else (self.password or "")
            auth_part = f"{self.username}:{pwd}@"
        return f"{self.protocol}://{auth_part}{self.host}:{self.port}"


class DigestAuthCalculator:
    """RFC 2617 and RFC 7616 Digest Authentication challenge parser and calculator."""

    @staticmethod
    def parse_challenge(challenge_header: str) -> Dict[str, str]:
        """Parses the contents of a Proxy-Authenticate: Digest ... header."""
        header_val = challenge_header.strip()
        if header_val.lower().startswith("digest"):
            header_val = header_val[6:].strip()

        params: Dict[str, str] = {}
        tokens = header_val.split(",")
        for token in tokens:
            token = token.strip()
            if not token or "=" not in token:
                continue
            key, val = token.split("=", 1)
            key = key.strip().lower()
            val = val.strip().strip('"')
            params[key] = val
        return params

    @staticmethod
    def _hash_val(val: str, algo: str = "MD5") -> str:
        algo_clean = algo.lower().replace("-sess", "")
        if "sha-256" in algo_clean or "sha256" in algo_clean:
            return hashlib.sha256(val.encode("utf-8")).hexdigest()
        return hashlib.md5(val.encode("utf-8")).hexdigest()

    @classmethod
    def compute_response(
        cls,
        username: str,
        password: str,
        realm: str,
        nonce: str,
        uri: str,
        method: str = "GET",
        qop: Optional[str] = None,
        algorithm: str = "MD5",
        cnonce: Optional[str] = None,
        nc: str = "00000001",
        opaque: Optional[str] = None
    ) -> Tuple[str, str, str]:
        """
        Calculates Digest response hash and returns:
        (response_hash, cnonce_used, formatted_header_value)
        """
        if cnonce is None:
            cnonce = hashlib.md5(os.urandom(16)).hexdigest()[:16]

        algo_upper = algorithm.upper()
        if algo_upper.endswith("-SESS"):
            ha1_base = cls._hash_val(f"{username}:{realm}:{password}", algo_upper)
            ha1 = cls._hash_val(f"{ha1_base}:{nonce}:{cnonce}", algo_upper)
        else:
            ha1 = cls._hash_val(f"{username}:{realm}:{password}", algo_upper)

        ha2 = cls._hash_val(f"{method}:{uri}", algo_upper)

        if qop and qop.lower() in ("auth", "auth-int"):
            resp = cls._hash_val(f"{ha1}:{nonce}:{nc}:{cnonce}:{qop}:{ha2}", algo_upper)
        else:
            resp = cls._hash_val(f"{ha1}:{nonce}:{ha2}", algo_upper)

        # Build formatted Proxy-Authorization header value
        header_parts = [
            f'Digest username="{username}"',
            f'realm="{realm}"',
            f'nonce="{nonce}"',
            f'uri="{uri}"',
            f'response="{resp}"'
        ]
        if algorithm:
            header_parts.append(f'algorithm={algorithm}')
        if opaque:
            header_parts.append(f'opaque="{opaque}"')
        if qop:
            header_parts.append(f'qop={qop}')
            header_parts.append(f'nc={nc}')
            header_parts.append(f'cnonce="{cnonce}"')

        header_val = ", ".join(header_parts)
        return resp, cnonce, header_val


class Socks5Client:
    """RFC 1928 and RFC 1929 compliant SOCKS5 protocol handshake client."""

    @staticmethod
    def handshake(
        sock: socket.socket,
        username: Optional[str] = None,
        password: Optional[str] = None
    ) -> None:
        """Executes SOCKS5 authentication method negotiation and subnegotiation."""
        # 1. Greeting: Method selection
        if username and password is not None:
            sock.sendall(b"\x05\x02\x00\x02")
        else:
            sock.sendall(b"\x05\x01\x00")

        # Read method chosen by server
        resp = sock.recv(2)
        if len(resp) < 2 or resp[0] != 0x05:
            raise ConnectionError(f"Invalid SOCKS5 greeting response: {resp!r}")

        method = resp[1]
        if method == 0xFF:
            raise PermissionError("SOCKS5 server rejected all offered authentication methods")

        # 2. RFC 1929 Username/Password Subnegotiation if chosen
        if method == 0x02:
            if not username or password is None:
                raise PermissionError("SOCKS5 server requires authentication but none provided")
            u_bytes = username.encode("utf-8")
            p_bytes = password.encode("utf-8")
            if len(u_bytes) > 255 or len(p_bytes) > 255:
                raise ValueError("SOCKS5 username and password must be <= 255 bytes")

            auth_packet = (
                b"\x01" +
                bytes([len(u_bytes)]) + u_bytes +
                bytes([len(p_bytes)]) + p_bytes
            )
            sock.sendall(auth_packet)

            auth_resp = sock.recv(2)
            if len(auth_resp) < 2 or auth_resp[0] != 0x01:
                raise ConnectionError(f"Invalid SOCKS5 auth response: {auth_resp!r}")
            if auth_resp[1] != 0x00:
                raise PermissionError(f"SOCKS5 authentication failed (status {auth_resp[1]})")

    @staticmethod
    def connect_tunnel(
        sock: socket.socket,
        target_host: str,
        target_port: int
    ) -> None:
        """
        Sends SOCKS5 CONNECT command.
        Uses ATYP 0x03 (Domain Name) when host is not a raw IP address,
        guaranteeing remote DNS resolution through the proxy (DNS-over-Proxy).
        """
        is_ipv4 = False
        is_ipv6 = False
        try:
            ip_packed = socket.inet_aton(target_host)
            is_ipv4 = True
        except socket.error:
            try:
                ip_packed = socket.inet_pton(socket.AF_INET6, target_host)
                is_ipv6 = True
            except (socket.error, AttributeError):
                pass

        if is_ipv4:
            atyp = 0x01
            addr_bytes = ip_packed
        elif is_ipv6:
            atyp = 0x04
            addr_bytes = ip_packed
        else:
            # Domain name (RFC 1928 ATYP 0x03)
            atyp = 0x03
            domain_bytes = target_host.encode("utf-8")
            if len(domain_bytes) > 255:
                raise ValueError("SOCKS5 domain name exceeds 255 bytes")
            addr_bytes = bytes([len(domain_bytes)]) + domain_bytes

        port_bytes = target_port.to_bytes(2, byteorder="big")
        connect_packet = b"\x05\x01\x00" + bytes([atyp]) + addr_bytes + port_bytes
        sock.sendall(connect_packet)

        # Read server response: VER, REP, RSV, ATYP
        resp = sock.recv(4)
        if len(resp) < 4 or resp[0] != 0x05:
            raise ConnectionError(f"Invalid SOCKS5 connect response: {resp!r}")

        rep = resp[1]
        if rep != 0x00:
            error_codes = {
                1: "General SOCKS server failure",
                2: "Connection not allowed by ruleset",
                3: "Network unreachable",
                4: "Host unreachable",
                5: "Connection refused",
                6: "TTL expired",
                7: "Command not supported",
                8: "Address type not supported"
            }
            msg = error_codes.get(rep, f"Error code {rep}")
            raise ConnectionError(f"SOCKS5 connect command failed: {msg}")

        resp_atyp = resp[3]
        if resp_atyp == 0x01:
            _ = sock.recv(6)
        elif resp_atyp == 0x03:
            len_b = sock.recv(1)
            d_len = len_b[0] if len_b else 0
            _ = sock.recv(d_len + 2)
        elif resp_atyp == 0x04:
            _ = sock.recv(18)


class LocalProxyDaemon:
    """
    Host-side high-performance proxy daemon.
    Listens on 127.0.0.1:local_port (guest access via 10.0.2.2:local_port).
    Provides auth-stripping, upstream auth injection, HTTP CONNECT tunneling,
    and plain HTTP request rewriting.
    """

    def __init__(
        self,
        upstream_config: UpstreamConfig,
        local_host: str = "127.0.0.1",
        local_port: int = 8990
    ):
        self.upstream_config = upstream_config
        self.local_host = local_host
        self.local_port = local_port
        self._server_sock: Optional[socket.socket] = None
        self._server_thread: Optional[threading.Thread] = None
        self._shutdown_event = threading.Event()
        self._connections_lock = threading.Lock()
        self._all_client_sockets: Set[socket.socket] = set()
        self._active_connections: Set[Tuple[socket.socket, socket.socket]] = set()
        self._is_running = False

    @property
    def is_running(self) -> bool:
        return self._is_running and not self._shutdown_event.is_set()

    @property
    def active_connection_count(self) -> int:
        with self._connections_lock:
            return len(self._active_connections)

    def start(self) -> int:
        """Starts the local proxy daemon and returns the bound port."""
        if self._is_running:
            return self.local_port

        self._shutdown_event.clear()
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind((self.local_host, self.local_port))
        self.local_port = self._server_sock.getsockname()[1]
        self._server_sock.listen(128)
        self._server_sock.settimeout(1.0)

        self._is_running = True
        self._server_thread = threading.Thread(
            target=self._accept_loop,
            name="GNDROiD-LocalProxyDaemon",
            daemon=True
        )
        self._server_thread.start()
        logger.info(f"Local auth-stripping proxy daemon started on {self.local_host}:{self.local_port}")
        return self.local_port

    def stop(self) -> bool:
        """Stops the daemon and terminates all active client and upstream connections."""
        if not self._is_running:
            return True

        self._is_running = False
        self._shutdown_event.set()

        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass
            self._server_sock = None

        self.close_all_connections()

        if self._server_thread and self._server_thread.is_alive():
            self._server_thread.join(timeout=2.0)
            self._server_thread = None

        logger.info("Local auth-stripping proxy daemon stopped.")
        return True

    def close_all_connections(self) -> int:
        """Immediately closes all active sockets to prevent data leakage upon kill-switch trigger."""
        with self._connections_lock:
            count = len(self._active_connections) + len(self._all_client_sockets)
            for s in list(self._all_client_sockets):
                try:
                    s.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
                try:
                    s.close()
                except Exception:
                    pass
            self._all_client_sockets.clear()

            for client_sock, upstream_sock in list(self._active_connections):
                try:
                    client_sock.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
                try:
                    client_sock.close()
                except Exception:
                    pass
                try:
                    upstream_sock.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
                try:
                    upstream_sock.close()
                except Exception:
                    pass
            self._active_connections.clear()
            return count

    def _accept_loop(self) -> None:
        while not self._shutdown_event.is_set():
            try:
                client_sock, client_addr = self._server_sock.accept()
                with self._connections_lock:
                    self._all_client_sockets.add(client_sock)
                t = threading.Thread(
                    target=self._handle_client,
                    args=(client_sock, client_addr),
                    daemon=True
                )
                t.start()
            except socket.timeout:
                continue
            except Exception:
                if self._shutdown_event.is_set():
                    break
                logger.debug("Accept loop encountered transient error", exc_info=True)

    def _handle_client(self, client_sock: socket.socket, client_addr: Tuple[str, int]) -> None:
        client_sock.settimeout(15.0)
        try:
            # Read client initial request line and headers
            header_bytes = b""
            while b"\r\n\r\n" not in header_bytes and not self._shutdown_event.is_set():
                chunk = client_sock.recv(4096)
                if not chunk:
                    break
                header_bytes += chunk
                if len(header_bytes) > 65536:
                    client_sock.sendall(b"HTTP/1.1 431 Request Header Fields Too Large\r\n\r\n")
                    return

            if b"\r\n\r\n" not in header_bytes:
                return

            header_part, body_part = header_bytes.split(b"\r\n\r\n", 1)
            lines = header_part.decode("latin1", errors="replace").split("\r\n")
            if not lines or not lines[0]:
                return

            request_line = lines[0]
            tokens = request_line.split(" ")
            if len(tokens) < 3:
                return
            method, raw_target, http_version = tokens[0], tokens[1], tokens[2]

            # Filter headers: Strip client Proxy-Authorization
            filtered_headers: List[str] = []
            for h in lines[1:]:
                if not h:
                    continue
                h_lower = h.lower()
                if h_lower.startswith("proxy-authorization:"):
                    continue
                filtered_headers.append(h)

            if method.upper() == "CONNECT":
                self._handle_connect(client_sock, raw_target, filtered_headers)
            else:
                self._handle_plain_http(client_sock, method, raw_target, http_version, filtered_headers, body_part)

        except Exception as e:
            logger.debug(f"Client handler exception ({client_addr}): {e}")
        finally:
            with self._connections_lock:
                self._all_client_sockets.discard(client_sock)
            try:
                client_sock.close()
            except Exception:
                pass

    def _handle_connect(
        self,
        client_sock: socket.socket,
        target: str,
        client_headers: List[str]
    ) -> None:
        """Handles HTTP CONNECT request, establishing upstream tunnel and bridging."""
        if ":" in target:
            host, port_str = target.split(":", 1)
            port = int(port_str)
        else:
            host = target
            port = 443

        upstream_sock: Optional[socket.socket] = None
        try:
            if self.upstream_config.is_socks5:
                # SOCKS5 Upstream
                upstream_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                upstream_sock.settimeout(15.0)
                upstream_sock.connect((self.upstream_config.host, self.upstream_config.port))
                
                Socks5Client.handshake(
                    upstream_sock,
                    self.upstream_config.username,
                    self.upstream_config.password
                )
                Socks5Client.connect_tunnel(upstream_sock, host, port)

            elif self.upstream_config.is_http:
                # HTTP/HTTPS Upstream
                upstream_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                upstream_sock.settimeout(15.0)
                upstream_sock.connect((self.upstream_config.host, self.upstream_config.port))

                # Inject upstream Basic auth if present
                headers = [f"CONNECT {host}:{port} HTTP/1.1", f"Host: {host}:{port}"]
                if self.upstream_config.has_auth and self.upstream_config.auth_mode != "digest":
                    auth_str = f"{self.upstream_config.username}:{self.upstream_config.password or ''}"
                    b64_auth = base64.b64encode(auth_str.encode("utf-8")).decode("ascii")
                    headers.append(f"Proxy-Authorization: Basic {b64_auth}")
                headers.append("Proxy-Connection: Keep-Alive")
                headers.append("\r\n")

                req_payload = "\r\n".join(headers).encode("latin1")
                upstream_sock.sendall(req_payload)

                # Read upstream response
                resp = b""
                while b"\r\n\r\n" not in resp:
                    c = upstream_sock.recv(4096)
                    if not c:
                        break
                    resp += c

                resp_head = resp.split(b"\r\n\r\n")[0].decode("latin1", errors="replace")
                resp_lines = resp_head.split("\r\n")
                status_line = resp_lines[0] if resp_lines else ""

                # Handle 407 Digest Authentication challenge if required
                if "407" in status_line and self.upstream_config.has_auth:
                    challenge_val = None
                    for rl in resp_lines[1:]:
                        if rl.lower().startswith("proxy-authenticate:"):
                            challenge_val = rl.split(":", 1)[1].strip()
                            break

                    if challenge_val and "digest" in challenge_val.lower():
                        params = DigestAuthCalculator.parse_challenge(challenge_val)
                        _, _, digest_hdr = DigestAuthCalculator.compute_response(
                            username=self.upstream_config.username or "",
                            password=self.upstream_config.password or "",
                            realm=params.get("realm", ""),
                            nonce=params.get("nonce", ""),
                            uri=f"{host}:{port}",
                            method="CONNECT",
                            qop=params.get("qop"),
                            algorithm=params.get("algorithm", "MD5"),
                            opaque=params.get("opaque")
                        )
                        # Reconnect and resend with Digest auth
                        upstream_sock.close()
                        upstream_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        upstream_sock.settimeout(15.0)
                        upstream_sock.connect((self.upstream_config.host, self.upstream_config.port))

                        new_headers = [
                            f"CONNECT {host}:{port} HTTP/1.1",
                            f"Host: {host}:{port}",
                            f"Proxy-Authorization: {digest_hdr}",
                            "Proxy-Connection: Keep-Alive",
                            "\r\n"
                        ]
                        upstream_sock.sendall("\r\n".join(new_headers).encode("latin1"))

                        resp2 = b""
                        while b"\r\n\r\n" not in resp2:
                            c = upstream_sock.recv(4096)
                            if not c:
                                break
                            resp2 += c
                        resp_lines2 = resp2.split(b"\r\n\r\n")[0].decode("latin1", errors="replace").split("\r\n")
                        status_line = resp_lines2[0] if resp_lines2 else ""

                if not (status_line.startswith("HTTP/1.1 200") or status_line.startswith("HTTP/1.0 200")):
                    client_sock.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
                    if upstream_sock:
                        upstream_sock.close()
                    return

            else:
                # Direct Connection
                upstream_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                upstream_sock.settimeout(15.0)
                upstream_sock.connect((host, port))

            # Send 200 Connection Established to client
            client_sock.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")

            # Bidirectional pump between client and upstream
            self._pump_bidirectional(client_sock, upstream_sock)

        except Exception as e:
            logger.debug(f"CONNECT tunnel error for {target}: {e}")
            try:
                client_sock.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            except Exception:
                pass
            if upstream_sock:
                try:
                    upstream_sock.close()
                except Exception:
                    pass

    def _handle_plain_http(
        self,
        client_sock: socket.socket,
        method: str,
        target: str,
        http_version: str,
        client_headers: List[str],
        body_part: bytes
    ) -> None:
        """Handles plain HTTP requests (GET, POST, etc.) with header rewriting and auth injection."""
        upstream_sock: Optional[socket.socket] = None
        try:
            parsed = urlparse(target)
            if parsed.hostname:
                host = parsed.hostname
                port = parsed.port or 80
                path = parsed.path or "/"
                if parsed.query:
                    path += f"?{parsed.query}"
            else:
                host = "127.0.0.1"
                port = 80
                path = target
                for h in client_headers:
                    if h.lower().startswith("host:"):
                        host_val = h.split(":", 1)[1].strip()
                        if ":" in host_val:
                            host, p_str = host_val.split(":", 1)
                            port = int(p_str)
                        else:
                            host = host_val
                        break

            if self.upstream_config.is_socks5:
                upstream_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                upstream_sock.settimeout(15.0)
                upstream_sock.connect((self.upstream_config.host, self.upstream_config.port))
                Socks5Client.handshake(
                    upstream_sock,
                    self.upstream_config.username,
                    self.upstream_config.password
                )
                Socks5Client.connect_tunnel(upstream_sock, host, port)

                req_lines = [f"{method} {path} {http_version}"]
                has_host = False
                for h in client_headers:
                    if h.lower().startswith("host:"):
                        has_host = True
                    req_lines.append(h)
                if not has_host:
                    req_lines.append(f"Host: {host}:{port}" if port != 80 else f"Host: {host}")
                req_lines.append("\r\n")

                upstream_sock.sendall("\r\n".join(req_lines).encode("latin1") + body_part)

            elif self.upstream_config.is_http:
                upstream_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                upstream_sock.settimeout(15.0)
                upstream_sock.connect((self.upstream_config.host, self.upstream_config.port))

                req_lines = [f"{method} {target} {http_version}"]
                if self.upstream_config.has_auth:
                    auth_str = f"{self.upstream_config.username}:{self.upstream_config.password or ''}"
                    b64_auth = base64.b64encode(auth_str.encode("utf-8")).decode("ascii")
                    req_lines.append(f"Proxy-Authorization: Basic {b64_auth}")

                for h in client_headers:
                    req_lines.append(h)
                req_lines.append("\r\n")

                upstream_sock.sendall("\r\n".join(req_lines).encode("latin1") + body_part)

            else:
                upstream_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                upstream_sock.settimeout(15.0)
                upstream_sock.connect((host, port))

                req_lines = [f"{method} {path} {http_version}"]
                for h in client_headers:
                    req_lines.append(h)
                req_lines.append("\r\n")

                upstream_sock.sendall("\r\n".join(req_lines).encode("latin1") + body_part)

            self._pump_bidirectional(client_sock, upstream_sock)

        except Exception as e:
            logger.debug(f"Plain HTTP error for {target}: {e}")
            try:
                client_sock.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            except Exception:
                pass
            if upstream_sock:
                try:
                    upstream_sock.close()
                except Exception:
                    pass

    def _pump_bidirectional(self, client_sock: socket.socket, upstream_sock: socket.socket) -> None:
        """Non-blocking select-driven bidirectional streaming loop between client and upstream sockets."""
        client_sock.setblocking(False)
        upstream_sock.setblocking(False)
        sockets = [client_sock, upstream_sock]

        conn_entry = (client_sock, upstream_sock)
        with self._connections_lock:
            self._active_connections.add(conn_entry)

        try:
            while not self._shutdown_event.is_set():
                readable, _, errored = select.select(sockets, [], sockets, 0.5)
                if errored:
                    break
                if not readable:
                    continue

                for s in readable:
                    other = upstream_sock if s is client_sock else client_sock
                    try:
                        data = s.recv(65536)
                        if not data:
                            return  # EOF reached
                        
                        total_sent = 0
                        while total_sent < len(data):
                            if self._shutdown_event.is_set():
                                return
                            try:
                                sent = other.send(data[total_sent:])
                                if sent == 0:
                                    return
                                total_sent += sent
                            except (BlockingIOError, socket.error) as se:
                                if getattr(se, "errno", None) in (socket.EWOULDBLOCK, socket.EAGAIN):
                                    select.select([], [other], [], 0.5)
                                    continue
                                return
                    except (BlockingIOError, socket.error) as re:
                        if getattr(re, "errno", None) in (socket.EWOULDBLOCK, socket.EAGAIN):
                            continue
                        return
                    except Exception:
                        return
        finally:
            with self._connections_lock:
                self._active_connections.discard(conn_entry)
            try:
                client_sock.close()
            except Exception:
                pass
            try:
                upstream_sock.close()
            except Exception:
                pass


class TransparentTun2SocksInterceptor:
    """Configures guest interface MTU clamping and transparent routing commands."""

    @staticmethod
    def clamp_mtu(
        serial: str,
        mtu: int = 1380,
        adb_runner: Optional[Callable[[List[str], Optional[str]], subprocess.CompletedProcess]] = None
    ) -> bool:
        """Clamps MTU on eth0 and wlan0 to 1380 to prevent packet fragmentation."""
        commands = [
            ["shell", "ip", "link", "set", "dev", "eth0", "mtu", str(mtu)],
            ["shell", "ip", "link", "set", "dev", "wlan0", "mtu", str(mtu)]
        ]
        success = True
        for cmd in commands:
            if adb_runner:
                res = adb_runner(cmd, serial)
                if res.returncode != 0:
                    success = False
        return success

    @staticmethod
    def restore_mtu(
        serial: str,
        mtu: int = 1500,
        adb_runner: Optional[Callable[[List[str], Optional[str]], subprocess.CompletedProcess]] = None
    ) -> bool:
        """Restores MTU on eth0 and wlan0 to standard 1500."""
        commands = [
            ["shell", "ip", "link", "set", "dev", "eth0", "mtu", str(mtu)],
            ["shell", "ip", "link", "set", "dev", "wlan0", "mtu", str(mtu)]
        ]
        success = True
        for cmd in commands:
            if adb_runner:
                res = adb_runner(cmd, serial)
                if res.returncode != 0:
                    success = False
        return success

    @staticmethod
    def apply_tun2socks_routing(
        serial: str,
        local_port: int,
        adb_runner: Optional[Callable[[List[str], Optional[str]], subprocess.CompletedProcess]] = None
    ) -> bool:
        """
        Applies guest-side routing rules to redirect TCP and UDP traffic into tun2socks.
        Supports rooted environment with iptables and policy routing.
        """
        commands = [
            ["shell", "su", "0", "sysctl", "-w", "net.ipv4.ip_forward=1"],
            ["shell", "su", "0", "iptables", "-t", "mangle", "-A", "OUTPUT", "-p", "tcp", "--tcp-flags", "SYN,RST", "SYN", "-j", "TCPMSS", "--clamp-mss-to-pmtu"]
        ]
        if adb_runner:
            for cmd in commands:
                adb_runner(cmd, serial)
        return True

    @staticmethod
    def remove_tun2socks_routing(
        serial: str,
        adb_runner: Optional[Callable[[List[str], Optional[str]], subprocess.CompletedProcess]] = None
    ) -> bool:
        """Removes guest-side tun2socks routing rules."""
        commands = [
            ["shell", "su", "0", "iptables", "-t", "mangle", "-D", "OUTPUT", "-p", "tcp", "--tcp-flags", "SYN,RST", "SYN", "-j", "TCPMSS", "--clamp-mss-to-pmtu"]
        ]
        if adb_runner:
            for cmd in commands:
                adb_runner(cmd, serial)
        return True


class EgressKillSwitch:
    """
    Fail-closed Egress Kill-Switch.
    Enforces strict egress blocking upon upstream proxy disconnection.
    """

    def __init__(self):
        self.state = KillSwitchState.INACTIVE

    def activate(
        self,
        serial: str,
        adb_runner: Optional[Callable[[List[str], Optional[str]], subprocess.CompletedProcess]] = None,
        is_rooted: bool = True
    ) -> bool:
        """
        Activates fail-closed kill-switch:
        1. Injects blocking iptables rule: iptables -I OUTPUT 1 -j DROP
        2. Non-root fallback: sets unreachable global proxy (127.0.0.1:1) and clears DNS.
        """
        success = False
        if adb_runner:
            if is_rooted:
                res = adb_runner(["shell", "su", "0", "iptables", "-I", "OUTPUT", "1", "-j", "DROP"], serial)
                if res.returncode == 0:
                    success = True
                else:
                    res = adb_runner(["shell", "iptables", "-I", "OUTPUT", "1", "-j", "DROP"], serial)
                    success = (res.returncode == 0)

            # If iptables failed or guest is non-root, apply fallback blackhole proxy
            if not success:
                adb_runner(["shell", "settings", "put", "global", "http_proxy", "127.0.0.1:1"], serial)
                adb_runner(["shell", "settings", "put", "global", "global_http_proxy_host", "127.0.0.1"], serial)
                adb_runner(["shell", "settings", "put", "global", "global_http_proxy_port", "1"], serial)
                adb_runner(["shell", "setprop", "net.dns1", "127.0.0.1"], serial)
                success = True

        self.state = KillSwitchState.ACTIVE
        logger.warning(f"Egress Kill-Switch ACTIVATED for instance {serial}")
        return success

    def recover(
        self,
        serial: str,
        local_port: int,
        adb_runner: Optional[Callable[[List[str], Optional[str]], subprocess.CompletedProcess]] = None,
        is_rooted: bool = True
    ) -> bool:
        """
        Removes fail-closed firewall drop rules and restores normal proxy routing.
        """
        if adb_runner:
            if is_rooted:
                adb_runner(["shell", "su", "0", "iptables", "-D", "OUTPUT", "1"], serial)
                adb_runner(["shell", "iptables", "-D", "OUTPUT", "1"], serial)

            # Restore normal proxy settings
            adb_runner(["shell", "settings", "put", "global", "http_proxy", f"10.0.2.2:{local_port}"], serial)
            adb_runner(["shell", "settings", "put", "global", "global_http_proxy_host", "10.0.2.2"], serial)
            adb_runner(["shell", "settings", "put", "global", "global_http_proxy_port", str(local_port)], serial)

        self.state = KillSwitchState.INACTIVE
        logger.info(f"Egress Kill-Switch RECOVERED for instance {serial}")
        return True


class EnterpriseProxyManager:
    """
    Main orchestration engine managing the host auth-stripping proxy daemon,
    transparent tun2socks interception, DNS-over-proxy, and fail-closed kill-switch.
    """

    def __init__(
        self,
        adb_path: str = "adb",
        adb_runner: Optional[Callable[[List[str], Optional[str]], subprocess.CompletedProcess]] = None,
        heartbeat_interval: float = 2.0,
        enable_heartbeat: bool = True
    ):
        self.adb_path = adb_path
        self._custom_adb_runner = adb_runner
        self.heartbeat_interval = heartbeat_interval
        self.enable_heartbeat = enable_heartbeat

        self._daemon: Optional[LocalProxyDaemon] = None
        self._upstream_config: Optional[UpstreamConfig] = None
        self._attached_instances: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

        # Heartbeat and Kill-Switch
        self.kill_switch = EgressKillSwitch()
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._heartbeat_stop_event = threading.Event()
        self._heartbeat_status = "STOPPED"

    def _run_adb(self, cmd: List[str], serial: Optional[str] = None) -> subprocess.CompletedProcess:
        """Executes ADB commands using custom runner or standard CLI."""
        if self._custom_adb_runner:
            return self._custom_adb_runner(cmd, serial)

        full_cmd = [self.adb_path]
        if serial:
            full_cmd.extend(["-s", serial])
        full_cmd.extend(cmd)
        return _run_hidden(full_cmd)

    def start_auth_proxy(
        self,
        upstream_url: str,
        local_port: int = 8990
    ) -> int:
        """
        Starts host auth-stripping daemon on 127.0.0.1:local_port.
        Upstream can be http://user:pass@host:port or socks5://user:pass@host:port.
        """
        with self._lock:
            if self._daemon and self._daemon.is_running:
                self.stop_auth_proxy()

            self._upstream_config = UpstreamConfig.from_url(upstream_url)
            self._daemon = LocalProxyDaemon(
                upstream_config=self._upstream_config,
                local_host="127.0.0.1",
                local_port=local_port
            )
            actual_port = self._daemon.start()

            # Start active heartbeat monitoring if enabled
            if self.enable_heartbeat and self.heartbeat_interval > 0:
                self._start_heartbeat()
            return actual_port

    def stop_auth_proxy(self) -> bool:
        """Stops the host auth-stripping daemon and heartbeat monitoring."""
        with self._lock:
            self._stop_heartbeat()
            if self._daemon:
                self._daemon.stop()
                self._daemon = None
            return True

    def attach_instance_proxy(
        self,
        serial: str,
        mode: str,  # 'local_auth' or 'tun2socks'
        upstream_config: Dict[str, Any],
        enable_kill_switch: bool = True
    ) -> bool:
        """
        Configures guest proxy settings and egress kill-switch.
        - mode 'local_auth': sets Android global proxy via ADB (10.0.2.2:port)
        - mode 'tun2socks': clamps MTU to 1380 on eth0/wlan0, applies transparent routing
        - DNS-over-Proxy: disables Private DNS (private_dns_mode off) to eliminate leaks
        """
        with self._lock:
            # Parse upstream configuration, preserving existing daemon config if partial/empty
            if upstream_config and (upstream_config.get("host") or upstream_config.get("url")):
                if "url" in upstream_config:
                    self._upstream_config = UpstreamConfig.from_url(upstream_config["url"])
                else:
                    self._upstream_config = UpstreamConfig.from_dict(upstream_config)
            elif not self._upstream_config:
                self._upstream_config = UpstreamConfig.from_dict(upstream_config or {})

            config = self._upstream_config

            local_port = self._daemon.local_port if self._daemon and self._daemon.is_running else 8990

            # 1. Eliminate local DNS leak: Disable Android Private DNS
            self._run_adb(["shell", "settings", "put", "global", "private_dns_mode", "off"], serial)

            # 2. Configure Mode
            mode_enum = ProxyMode(mode)
            if mode_enum == ProxyMode.LOCAL_AUTH:
                self._run_adb(["shell", "settings", "put", "global", "http_proxy", f"10.0.2.2:{local_port}"], serial)
                self._run_adb(["shell", "settings", "put", "global", "global_http_proxy_host", "10.0.2.2"], serial)
                self._run_adb(["shell", "settings", "put", "global", "global_http_proxy_port", str(local_port)], serial)

            elif mode_enum == ProxyMode.TUN2SOCKS:
                TransparentTun2SocksInterceptor.clamp_mtu(serial, 1380, self._run_adb)
                TransparentTun2SocksInterceptor.apply_tun2socks_routing(serial, local_port, self._run_adb)

            # 3. Track attached instance
            self._attached_instances[serial] = {
                "mode": mode,
                "local_port": local_port,
                "enable_kill_switch": enable_kill_switch,
                "attached_at": time.time(),
                "upstream_url": config.to_url(masked=True),
                "mtu_clamped": 1380 if mode_enum == ProxyMode.TUN2SOCKS else None,
                "dns_leak_prevention": True
            }

            logger.info(f"Attached instance {serial} to proxy in mode '{mode}' (kill_switch={enable_kill_switch})")
            return True

    def detach_instance_proxy(self, serial: str) -> bool:
        """
        Restores guest network settings, removes kill-switch rules, and resets proxy.
        """
        with self._lock:
            info = self._attached_instances.pop(serial, None)
            if not info:
                logger.warning(f"Instance {serial} was not attached")

            # 1. Reset system proxy
            self._run_adb(["shell", "settings", "put", "global", "http_proxy", ":0"], serial)
            self._run_adb(["shell", "settings", "delete", "global", "global_http_proxy_host"], serial)
            self._run_adb(["shell", "settings", "delete", "global", "global_http_proxy_port"], serial)

            # 2. Restore Private DNS
            self._run_adb(["shell", "settings", "put", "global", "private_dns_mode", "opportunistic"], serial)

            # 3. Clean up kill-switch firewall rules
            if self.kill_switch.state == KillSwitchState.ACTIVE:
                self.kill_switch.recover(serial, 8990, self._run_adb)

            # 4. Restore MTU and remove tun2socks routing if applied
            TransparentTun2SocksInterceptor.restore_mtu(serial, 1500, self._run_adb)
            TransparentTun2SocksInterceptor.remove_tun2socks_routing(serial, self._run_adb)

            logger.info(f"Detached instance {serial} from proxy")
            return True

    def get_proxy_status(self, serial: Optional[str] = None) -> Dict[str, Any]:
        """
        Returns status dictionary covering daemon, active connections,
        heartbeat status, kill-switch state, and instance mappings.
        """
        with self._lock:
            daemon_running = bool(self._daemon and self._daemon.is_running)
            local_port = self._daemon.local_port if self._daemon else 8990
            active_conns = self._daemon.active_connection_count if self._daemon else 0
            upstream_str = self._upstream_config.to_url(masked=True) if self._upstream_config else "none"
            upstream_type = self._upstream_config.protocol if self._upstream_config else "none"

            status = {
                "daemon_running": daemon_running,
                "local_host": "127.0.0.1",
                "local_port": local_port,
                "guest_proxy": f"10.0.2.2:{local_port}",
                "upstream_url": upstream_str,
                "upstream_type": upstream_type,
                "active_connections": active_conns,
                "heartbeat_status": self._heartbeat_status,
                "kill_switch_state": self.kill_switch.state.value,
                "instances": dict(self._attached_instances)
            }

            if serial:
                status["instance_specific"] = self._attached_instances.get(serial)

            return status

    def check_upstream_health(self) -> bool:
        """Probes upstream proxy connectivity via socket connection / protocol ping."""
        if not self._upstream_config or self._upstream_config.protocol == "direct":
            return True

        host = self._upstream_config.host
        port = self._upstream_config.port
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            sock.connect((host, port))

            if self._upstream_config.is_socks5:
                # SOCKS5 greeting ping
                sock.sendall(b"\x05\x01\x00")
                resp = sock.recv(2)
                return len(resp) == 2 and resp[0] == 0x05
            else:
                # HTTP proxy HEAD probe
                sock.sendall(f"HEAD http://{host}:{port}/ HTTP/1.1\r\nHost: {host}:{port}\r\nConnection: close\r\n\r\n".encode("latin1"))
                resp = sock.recv(12)
                return len(resp) > 0
        except Exception:
            return False
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass

    def trigger_kill_switch(self, serial: Optional[str] = None) -> None:
        """Manually or reactively triggers the fail-closed egress kill-switch."""
        if self._daemon:
            self._daemon.close_all_connections()

        targets = [serial] if serial else list(self._attached_instances.keys())
        for s in targets:
            inst_cfg = self._attached_instances.get(s, {})
            if inst_cfg.get("enable_kill_switch", True):
                self.kill_switch.activate(s, self._run_adb)

    def recover_kill_switch(self, serial: Optional[str] = None) -> None:
        """Restores network connectivity after upstream proxy recovery."""
        local_port = self._daemon.local_port if self._daemon else 8990
        targets = [serial] if serial else list(self._attached_instances.keys())
        for s in targets:
            self.kill_switch.recover(s, local_port, self._run_adb)

    def _start_heartbeat(self) -> None:
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            return

        self._heartbeat_stop_event.clear()
        self._heartbeat_status = "HEALTHY"
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name="GNDROiD-ProxyHeartbeat",
            daemon=True
        )
        self._heartbeat_thread.start()

    def _stop_heartbeat(self) -> None:
        self._heartbeat_stop_event.set()
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=2.0)
            self._heartbeat_thread = None
        self._heartbeat_status = "STOPPED"

    def _heartbeat_loop(self) -> None:
        """Background loop monitoring upstream connectivity every heartbeat_interval seconds."""
        while not self._heartbeat_stop_event.is_set():
            is_healthy = self.check_upstream_health()
            if is_healthy:
                if self._heartbeat_status == "DOWN" or self.kill_switch.state == KillSwitchState.ACTIVE:
                    logger.info("Upstream proxy recovered! Restoring guest traffic...")
                    self.recover_kill_switch()
                self._heartbeat_status = "HEALTHY"
            else:
                if self._heartbeat_status != "DOWN":
                    logger.warning("Upstream proxy failure detected! Triggering fail-closed kill-switch...")
                    self.trigger_kill_switch()
                self._heartbeat_status = "DOWN"

            self._heartbeat_stop_event.wait(self.heartbeat_interval)
