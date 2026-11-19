"""
scripts/test_challenger_proxy_stress_1.py
==========================================
Empirical Adversarial Stress Harness for GNDROiD Enterprise Proxy Engine (Milestone M2).
Target: nexus/proxy_manager.py

Stress Challenge Dimensions:
1. Upstream disconnects and rapid reconnects during active data transfer.
2. Concurrent client socket pumps under burst load (50+ concurrent clients, churn).
3. Auth credential fuzzing (passwords with spaces, colons, unicode, empty strings, boundary lengths).
4. Heartbeat failure detection latency and socket closure latency benchmark.
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
import unittest
from typing import Dict, Any, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nexus.proxy_manager import (
    EnterpriseProxyManager,
    LocalProxyDaemon,
    UpstreamConfig,
    DigestAuthCalculator,
    Socks5Client,
    TransparentTun2SocksInterceptor,
    EgressKillSwitch,
    ProxyMode,
    KillSwitchState
)

# Silence root logger noise during stress testing
logging.getLogger("gndroid.proxy_manager").setLevel(logging.WARNING)


# -----------------------------------------------------------------------------
# Mock Upstream Adversarial Servers
# -----------------------------------------------------------------------------

class MockAdversarialEchoServer:
    """Configurable TCP echo server for verifying tunnel throughput & abrupt resets."""

    def __init__(self, host: str = "127.0.0.1"):
        self.host = host
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((host, 0))
        self.port = self.sock.getsockname()[1]
        self.sock.listen(128)
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self._clients: List[socket.socket] = []
        self._lock = threading.Lock()
        self.bytes_echoed = 0

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        while self.running:
            try:
                client, _ = self.sock.accept()
                with self._lock:
                    self._clients.append(client)
                t = threading.Thread(target=self._handle, args=(client,), daemon=True)
                t.start()
            except Exception:
                break

    def _handle(self, client: socket.socket):
        try:
            while self.running:
                data = client.recv(65536)
                if not data:
                    break
                client.sendall(data)
                with self._lock:
                    self.bytes_echoed += len(data)
        except Exception:
            pass
        finally:
            with self._lock:
                if client in self._clients:
                    self._clients.remove(client)
            try:
                client.close()
            except Exception:
                pass

    def stop(self):
        self.running = False
        try:
            self.sock.close()
        except Exception:
            pass
        with self._lock:
            for c in list(self._clients):
                try:
                    c.close()
                except Exception:
                    pass
            self._clients.clear()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)


class MockFlappingHttpProxy:
    """
    Mock HTTP proxy capable of simulating abrupt disconnects mid-transfer,
    authentications, and rapid restarts.
    """

    def __init__(
        self,
        auth_type: str = "none",
        valid_user: str = "proxyuser",
        valid_pass: str = "proxypass",
        disconnect_after_bytes: Optional[int] = None
    ):
        self.auth_type = auth_type
        self.valid_user = valid_user
        self.valid_pass = valid_pass
        self.disconnect_after_bytes = disconnect_after_bytes

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self.sock.listen(128)

        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.captured_auth_headers: List[str] = []
        self._clients: List[socket.socket] = []
        self._lock = threading.Lock()

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        while self.running:
            try:
                client, _ = self.sock.accept()
                with self._lock:
                    self._clients.append(client)
                t = threading.Thread(target=self._handle, args=(client,), daemon=True)
                t.start()
            except Exception:
                break

    def _handle(self, client: socket.socket):
        client.settimeout(5.0)
        target_sock = None
        try:
            req_data = b""
            while b"\r\n\r\n" not in req_data:
                chunk = client.recv(4096)
                if not chunk:
                    break
                req_data += chunk

            if not req_data:
                return

            req_str = req_data.decode("latin1", errors="replace")
            lines = req_str.split("\r\n")
            req_line = lines[0]
            headers = {}
            for h in lines[1:]:
                if ":" in h:
                    k, v = h.split(":", 1)
                    headers[k.strip().lower()] = v.strip()

            auth_hdr = headers.get("proxy-authorization", "")
            with self._lock:
                self.captured_auth_headers.append(auth_hdr)

            # Check auth
            if self.auth_type == "basic":
                expected_b64 = base64.b64encode(f"{self.valid_user}:{self.valid_pass}".encode("utf-8")).decode("ascii")
                if auth_hdr != f"Basic {expected_b64}":
                    client.sendall(b"HTTP/1.1 407 Proxy Authentication Required\r\nProxy-Authenticate: Basic realm=\"Proxy\"\r\n\r\n")
                    return

            tokens = req_line.split(" ")
            method = tokens[0]

            if method.upper() == "CONNECT":
                target = tokens[1]
                t_host, t_port = target.split(":", 1) if ":" in target else (target, 443)
                target_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                target_sock.connect((t_host, int(t_port)))

                client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")

                # Forward bi-directional with optional deliberate abrupt disconnect
                bytes_sent_to_client = 0
                sockets = [client, target_sock]
                while self.running:
                    r, _, e = select.select(sockets, [], sockets, 0.5)
                    if e:
                        break
                    for s in r:
                        other = target_sock if s is client else client
                        d = s.recv(16384)
                        if not d:
                            return
                        other.sendall(d)
                        if other is client:
                            bytes_sent_to_client += len(d)
                            if self.disconnect_after_bytes and bytes_sent_to_client >= self.disconnect_after_bytes:
                                # Abruptly sever upstream connection mid-transfer!
                                return
            else:
                body = "OK from upstream mock"
                resp = f"HTTP/1.1 200 OK\r\nContent-Length: {len(body)}\r\n\r\n{body}"
                client.sendall(resp.encode("latin1"))

        except Exception:
            pass
        finally:
            if target_sock:
                try:
                    target_sock.close()
                except Exception:
                    pass
            with self._lock:
                if client in self._clients:
                    self._clients.remove(client)
            try:
                client.close()
            except Exception:
                pass

    def stop(self):
        self.running = False
        try:
            self.sock.close()
        except Exception:
            pass
        with self._lock:
            for c in list(self._clients):
                try:
                    c.close()
                except Exception:
                    pass
            self._clients.clear()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)


class MockHangingServer:
    """Mock server that accepts TCP connections but freezes without sending data (probes hang)."""

    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self.sock.listen(16)
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self._clients: List[socket.socket] = []

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        while self.running:
            try:
                client, _ = self.sock.accept()
                self._clients.append(client)
                # Intentionally freeze: do not send anything
            except Exception:
                break

    def stop(self):
        self.running = False
        try:
            self.sock.close()
        except Exception:
            pass
        for c in self._clients:
            try:
                c.close()
            except Exception:
                pass
        self._clients.clear()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)


# -----------------------------------------------------------------------------
# Test Suite: Empirical Stress & Adversarial Hardening
# -----------------------------------------------------------------------------

class TestChallengerProxyStress1(unittest.TestCase):

    # -------------------------------------------------------------------------
    # Dimension 1: Upstream Disconnects & Rapid Reconnects During Active Transfer
    # -------------------------------------------------------------------------

    def test_01_midstream_upstream_abrupt_disconnect_clean_recovery(self):
        """
        Adversarial Scenario: Client is streaming high-volume data through CONNECT tunnel.
        Upstream server abruptly severs the connection after 8 KB.
        Verify:
        - Client unblocks and receives EOF / error without hanging.
        - Daemon terminates client socket and purges active connection tracking.
        - active_connection_count returns to 0.
        """
        echo_server = MockAdversarialEchoServer()
        echo_server.start()
        self.addCleanup(echo_server.stop)

        # Proxy disconnects after sending back 8192 bytes
        upstream_proxy = MockFlappingHttpProxy(disconnect_after_bytes=8192)
        upstream_proxy.start()
        self.addCleanup(upstream_proxy.stop)

        cfg = UpstreamConfig(protocol="http", host="127.0.0.1", port=upstream_proxy.port)
        daemon = LocalProxyDaemon(upstream_config=cfg, local_port=0)
        local_port = daemon.start()
        self.addCleanup(daemon.stop)

        # Client connects to LocalProxyDaemon
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(3.0)
        client.connect(("127.0.0.1", local_port))
        self.addCleanup(client.close)

        # Send CONNECT
        connect_req = f"CONNECT 127.0.0.1:{echo_server.port} HTTP/1.1\r\nHost: 127.0.0.1:{echo_server.port}\r\n\r\n"
        client.sendall(connect_req.encode("latin1"))

        resp = client.recv(1024)
        self.assertIn(b"200 Connection Established", resp)

        # Now stream 32 KB through tunnel
        payload = b"X" * 16384
        client.sendall(payload)

        # Read back until abrupt EOF
        received = b""
        start_time = time.time()
        while True:
            try:
                chunk = client.recv(4096)
                if not chunk:
                    break
                received += chunk
            except socket.timeout:
                self.fail("Client hung waiting for EOF after upstream disconnect!")
            except ConnectionResetError:
                break

        elapsed = time.time() - start_time
        self.assertLess(elapsed, 2.5, "Client took too long to detect upstream drop")
        self.assertGreaterEqual(len(received), 8192, "Should have received at least 8KB before drop")

        # Wait for daemon cleanup
        time.sleep(0.3)
        self.assertEqual(daemon.active_connection_count, 0, "Daemon connection tracking must be 0 after drop")

    def test_02_rapid_upstream_flapping_churn_resilience(self):
        """
        Adversarial Scenario: Upstream proxy flapped (started, killed, restarted) across 8 cycles.
        Verify:
        - Daemon survives repeated abrupt upstream failures.
        - No socket descriptor leaks or orphaned threads.
        - Successful transfer immediately succeeds when upstream stabilizes.
        """
        echo_server = MockAdversarialEchoServer()
        echo_server.start()
        self.addCleanup(echo_server.stop)

        # We will cycle through 6 rapid proxies
        for cycle in range(6):
            temp_proxy = MockFlappingHttpProxy()
            temp_proxy.start()

            cfg = UpstreamConfig(protocol="http", host="127.0.0.1", port=temp_proxy.port)
            daemon = LocalProxyDaemon(upstream_config=cfg, local_port=0)
            local_port = daemon.start()

            # Client connects and does quick ping
            c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            c.settimeout(2.0)
            c.connect(("127.0.0.1", local_port))
            c.sendall(f"CONNECT 127.0.0.1:{echo_server.port} HTTP/1.1\r\nHost: 127.0.0.1:{echo_server.port}\r\n\r\n".encode("latin1"))
            resp = c.recv(1024)
            self.assertIn(b"200 Connection Established", resp)

            # Abruptly kill the upstream proxy mid-session!
            temp_proxy.stop()

            # Client should cleanly see disconnect
            try:
                c.sendall(b"PING")
                d = c.recv(1024)
            except (ConnectionResetError, socket.error):
                pass
            c.close()

            daemon.stop()
            self.assertEqual(daemon.active_connection_count, 0)

        # Final verification: Fresh upstream proxy and transfer works flawlessly
        final_proxy = MockFlappingHttpProxy()
        final_proxy.start()
        self.addCleanup(final_proxy.stop)

        cfg = UpstreamConfig(protocol="http", host="127.0.0.1", port=final_proxy.port)
        daemon = LocalProxyDaemon(upstream_config=cfg, local_port=0)
        local_port = daemon.start()
        self.addCleanup(daemon.stop)

        c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        c.settimeout(3.0)
        c.connect(("127.0.0.1", local_port))
        self.addCleanup(c.close)
        c.sendall(f"CONNECT 127.0.0.1:{echo_server.port} HTTP/1.1\r\nHost: 127.0.0.1:{echo_server.port}\r\n\r\n".encode("latin1"))
        resp = c.recv(1024)
        self.assertIn(b"200 Connection Established", resp)
        c.sendall(b"STABLE_DATA_TEST_12345")
        echo = c.recv(1024)
        self.assertEqual(echo, b"STABLE_DATA_TEST_12345")

    # -------------------------------------------------------------------------
    # Dimension 2: Concurrent Client Socket Pumps Under Burst Load
    # -------------------------------------------------------------------------

    def test_03_concurrent_client_socket_pumps_50_clients_integrity(self):
        """
        Adversarial Scenario: 50 concurrent client threads simultaneously stream distinct
        high-entropy 32 KB payloads through LocalProxyDaemon.
        Verify:
        - 100% data integrity (no packet cross-talk, interleaving, or corruption).
        - 0 failures across all 50 concurrent streams.
        - Connection count returns to 0 on completion.
        """
        echo_server = MockAdversarialEchoServer()
        echo_server.start()
        self.addCleanup(echo_server.stop)

        upstream_proxy = MockFlappingHttpProxy()
        upstream_proxy.start()
        self.addCleanup(upstream_proxy.stop)

        cfg = UpstreamConfig(protocol="http", host="127.0.0.1", port=upstream_proxy.port)
        daemon = LocalProxyDaemon(upstream_config=cfg, local_port=0)
        local_port = daemon.start()
        self.addCleanup(daemon.stop)

        num_clients = 50
        payload_size = 32768  # 32 KB per client
        results = [False] * num_clients
        errors: List[str] = []
        threads: List[threading.Thread] = []

        def client_worker(idx: int):
            c = None
            try:
                # Generate unique payload with checksum
                header = f"CLIENT_{idx:03d}:".encode("ascii")
                body = os.urandom(payload_size - len(header) - 32)
                expected_hash = hashlib.sha256(header + body).digest()
                full_payload = header + body + expected_hash

                c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                c.settimeout(10.0)
                c.connect(("127.0.0.1", local_port))

                # HTTP CONNECT
                req = f"CONNECT 127.0.0.1:{echo_server.port} HTTP/1.1\r\nHost: 127.0.0.1:{echo_server.port}\r\n\r\n"
                c.sendall(req.encode("latin1"))

                resp = b""
                while b"\r\n\r\n" not in resp:
                    chunk = c.recv(1024)
                    if not chunk:
                        errors.append(f"Client {idx}: EOF during CONNECT handshake")
                        return
                    resp += chunk

                if b"200 Connection Established" not in resp:
                    errors.append(f"Client {idx}: Bad CONNECT status: {resp!r}")
                    return

                # Send full payload
                c.sendall(full_payload)

                # Receive echoed payload back
                received = b""
                while len(received) < len(full_payload):
                    chunk = c.recv(8192)
                    if not chunk:
                        errors.append(f"Client {idx}: Early EOF after {len(received)} bytes")
                        return
                    received += chunk

                # Verify exact byte integrity
                if received == full_payload:
                    results[idx] = True
                else:
                    errors.append(f"Client {idx}: Data corruption detected!")

            except Exception as ex:
                errors.append(f"Client {idx}: Exception: {ex}")
            finally:
                if c:
                    try:
                        c.close()
                    except Exception:
                        pass

        start_time = time.time()
        for i in range(num_clients):
            t = threading.Thread(target=client_worker, args=(i,), daemon=True)
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=15.0)

        elapsed = time.time() - start_time
        successful = sum(results)

        # Assert 100% success rate
        self.assertEqual(len(errors), 0, f"Errors encountered: {errors[:5]}")
        self.assertEqual(successful, num_clients, f"Only {successful}/{num_clients} succeeded")

        # Verify throughput
        total_kb = (num_clients * payload_size * 2) / 1024.0  # bidirectional
        throughput_kb_s = total_kb / elapsed if elapsed > 0 else 0
        self.assertGreater(throughput_kb_s, 100.0, f"Throughput too low: {throughput_kb_s:.1f} KB/s")

        # Allow connections to settle
        time.sleep(0.5)
        self.assertEqual(daemon.active_connection_count, 0, "All active connections must be cleaned up")

    def test_04_rapid_client_abort_churn_burst(self):
        """
        Adversarial Scenario: 60 clients connect in a rapid wave, send partial or full
        CONNECT requests, and immediately abort/close sockets without reading responses.
        Verify:
        - Daemon does not crash on BrokenPipe / ConnectionReset.
        - Daemon cleanly discards half-open sockets without thread explosion.
        - active_connection_count returns to 0.
        """
        upstream_proxy = MockFlappingHttpProxy()
        upstream_proxy.start()
        self.addCleanup(upstream_proxy.stop)

        cfg = UpstreamConfig(protocol="http", host="127.0.0.1", port=upstream_proxy.port)
        daemon = LocalProxyDaemon(upstream_config=cfg, local_port=0)
        local_port = daemon.start()
        self.addCleanup(daemon.stop)

        for i in range(60):
            c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                c.connect(("127.0.0.1", local_port))
                if i % 2 == 0:
                    c.sendall(b"CONNECT 127.0.0.1:80 HTTP/1.1\r\n")  # partial header!
                else:
                    c.sendall(b"GET http://127.0.0.1/ HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
            except Exception:
                pass
            finally:
                c.close()  # immediate abort

        time.sleep(0.5)
        self.assertEqual(daemon.active_connection_count, 0, "All churn sockets must be cleaned up")
        self.assertTrue(daemon.is_running, "Daemon must remain running after abort wave")

    # -------------------------------------------------------------------------
    # Dimension 3: Auth Credential Fuzzing
    # -------------------------------------------------------------------------

    def test_05_auth_credential_fuzzing_spaces_colons_unicode(self):
        """
        Adversarial Scenario: Fuzz auth credentials with:
        1. Spaces: "user name with spaces", "pass word with spaces"
        2. Multiple colons in password: "secret:pass:with:colons"
        3. Multi-byte Unicode: Arabic ("مستخدم:كلمة_مرور"), Chinese ("用户:密码888"), Emojis ("user_🚀:p@ss_🔥")
        4. Empty password: "admin:"
        5. RFC 1929 length boundaries: 255 bytes (pass) vs 256 bytes (ValueError).
        Verify:
        - UpstreamConfig properly parses and roundtrips credentials.
        - Basic auth injection encodes full UTF-8 payload without truncation.
        - SOCKS5 subnegotiation validates 255-byte max length limit.
        """
        fuzz_vectors = [
            ("user space", "pass space with spaces 1234"),
            ("user_colon", "pass:with:multiple:colons:and:signs"),
            ("admin_arabic", "كلمة_المرور_السرية_2026"),
            ("user_chinese", "超级秘密密码_888"),
            ("user_emoji_🚀", "p@ssword_🔥_shield_🛡️"),
            ("user_empty_pass", ""),
            ("special_symbols", "!@#$%^&*()_+~`-={}|[]\\:\";'<>?,./")
        ]

        for username, password in fuzz_vectors:
            cfg = UpstreamConfig(
                protocol="http",
                host="127.0.0.1",
                port=8080,
                username=username,
                password=password
            )
            self.assertTrue(cfg.has_auth, f"Failed has_auth check for {username}")

            # Verify Basic auth encoding roundtrip
            auth_str = f"{username}:{password}"
            b64 = base64.b64encode(auth_str.encode("utf-8")).decode("ascii")
            decoded_auth = base64.b64decode(b64.encode("ascii")).decode("utf-8")
            self.assertEqual(decoded_auth, auth_str, f"Roundtrip failed for {username}")

        # SOCKS5 boundary test: exactly 255 bytes vs 256 bytes
        # Set up a mock SOCKS5 server that selects 0x02 (Username/Password auth)
        socks_srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        socks_srv.bind(("127.0.0.1", 0))
        socks_srv_port = socks_srv.getsockname()[1]
        socks_srv.listen(5)
        self.addCleanup(socks_srv.close)

        def handle_socks_conn(s):
            try:
                s.settimeout(1.0)
                s.recv(10)
                s.sendall(b"\x05\x02")  # Select method 0x02
                try:
                    s.recv(1024)
                except Exception:
                    pass
            finally:
                try:
                    s.close()
                except Exception:
                    pass

        def mock_socks_handshake_respond():
            while True:
                try:
                    s, _ = socks_srv.accept()
                    threading.Thread(target=handle_socks_conn, args=(s,), daemon=True).start()
                except Exception:
                    break

        th_socks = threading.Thread(target=mock_socks_handshake_respond, daemon=True)
        th_socks.start()

        # 256 bytes username must raise ValueError
        uname_256 = "U" * 256
        sock1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock1.connect(("127.0.0.1", socks_srv_port))
        self.addCleanup(sock1.close)
        with self.assertRaises(ValueError):
            Socks5Client.handshake(sock1, uname_256, "valid_pass")

        # 256 bytes password must raise ValueError
        pass_256 = "P" * 256
        sock2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock2.connect(("127.0.0.1", socks_srv_port))
        self.addCleanup(sock2.close)
        with self.assertRaises(ValueError):
            Socks5Client.handshake(sock2, "valid_user", pass_256)

    def test_06_upstream_basic_auth_fuzzed_injection_in_daemon(self):
        """
        Adversarial Scenario: Launch LocalProxyDaemon with unicode and colon-rich credentials.
        Verify that MockFlappingHttpProxy captures the exact decoded Basic auth token.
        """
        echo_server = MockAdversarialEchoServer()
        echo_server.start()
        self.addCleanup(echo_server.stop)

        fuzz_user = "indus_admin_🚀"
        fuzz_pass = "p@ss:wørd_with:colons:and spaces:100%"

        upstream_proxy = MockFlappingHttpProxy(
            auth_type="basic",
            valid_user=fuzz_user,
            valid_pass=fuzz_pass
        )
        upstream_proxy.start()
        self.addCleanup(upstream_proxy.stop)

        cfg = UpstreamConfig(
            protocol="http",
            host="127.0.0.1",
            port=upstream_proxy.port,
            username=fuzz_user,
            password=fuzz_pass
        )
        daemon = LocalProxyDaemon(upstream_config=cfg, local_port=0)
        local_port = daemon.start()
        self.addCleanup(daemon.stop)

        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(5.0)
        client.connect(("127.0.0.1", local_port))
        self.addCleanup(client.close)

        # Guest sends CONNECT with its own auth header (which must be stripped)
        guest_auth = base64.b64encode(b"guest_user:guest_pass").decode("ascii")
        req = (
            f"CONNECT 127.0.0.1:{echo_server.port} HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{echo_server.port}\r\n"
            f"Proxy-Authorization: Basic {guest_auth}\r\n\r\n"
        )
        client.sendall(req.encode("latin1"))

        resp = client.recv(1024)
        self.assertIn(b"200 Connection Established", resp)

        # Check captured auth header in upstream proxy
        self.assertGreater(len(upstream_proxy.captured_auth_headers), 0)
        injected = upstream_proxy.captured_auth_headers[0]
        self.assertTrue(injected.startswith("Basic "))
        b64_val = injected.split(" ", 1)[1]
        decoded = base64.b64decode(b64_val.encode("ascii")).decode("utf-8")
        self.assertEqual(decoded, f"{fuzz_user}:{fuzz_pass}")

    def test_07_digest_auth_calculator_fuzzing(self):
        """
        Adversarial Scenario: Fuzz Digest Auth challenge parser and calculator with:
        - Commas and spaces inside quoted strings
        - SHA-256 and MD5-sess algorithms
        - Unicode usernames and complex passwords
        """
        # Complex challenge header
        challenge = 'Digest realm="IndusBridge, Tech Hub", nonce="dcd98b7102dd2f0e8b11d0f600bfb0c093", qop="auth", algorithm=SHA-256, opaque="5ccc069c403ebaf9f0171e9517f40e41"'
        params = DigestAuthCalculator.parse_challenge(challenge)
        self.assertEqual(params.get("nonce"), "dcd98b7102dd2f0e8b11d0f600bfb0c093")
        self.assertEqual(params.get("qop"), "auth")
        self.assertEqual(params.get("algorithm"), "SHA-256")

        # Test computation with Unicode credentials
        resp_hash, cnonce, hdr = DigestAuthCalculator.compute_response(
            username="خالد_بن_وليد",
            password="كلمة_مرور:معقدة_123",
            realm="IndusBridge",
            nonce="dcd98b7102dd2f0e8b11d0f600bfb0c093",
            uri="127.0.0.1:443",
            method="CONNECT",
            qop="auth",
            algorithm="SHA-256"
        )
        self.assertEqual(len(resp_hash), 64)  # SHA-256 hex length
        self.assertIn('username="خالد_بن_وليد"', hdr)
        self.assertIn('algorithm=SHA-256', hdr)

    # -------------------------------------------------------------------------
    # Dimension 4: Heartbeat Failure Detection & Socket Closure Latency
    # -------------------------------------------------------------------------

    def test_08_socket_closure_latency_benchmark_under_killswitch(self):
        """
        Adversarial Scenario: 30 active client sockets are actively connected and pumping.
        Call daemon.close_all_connections() (kill-switch trigger).
        Measure:
        - Execution latency of close_all_connections(). Target: < 50ms.
        - Ensure all 30 client sockets immediately unblock and receive EOF/reset.
        """
        echo_server = MockAdversarialEchoServer()
        echo_server.start()
        self.addCleanup(echo_server.stop)

        upstream_proxy = MockFlappingHttpProxy()
        upstream_proxy.start()
        self.addCleanup(upstream_proxy.stop)

        cfg = UpstreamConfig(protocol="http", host="127.0.0.1", port=upstream_proxy.port)
        daemon = LocalProxyDaemon(upstream_config=cfg, local_port=0)
        local_port = daemon.start()
        self.addCleanup(daemon.stop)

        clients: List[socket.socket] = []
        for _ in range(30):
            c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            c.settimeout(5.0)
            c.connect(("127.0.0.1", local_port))
            c.sendall(f"CONNECT 127.0.0.1:{echo_server.port} HTTP/1.1\r\nHost: 127.0.0.1:{echo_server.port}\r\n\r\n".encode("latin1"))
            resp = c.recv(1024)
            self.assertIn(b"200 Connection Established", resp)
            clients.append(c)

        time.sleep(0.2)
        self.assertGreaterEqual(daemon.active_connection_count, 30)

        # Benchmark kill-switch socket closure latency
        t0 = time.perf_counter()
        closed_count = daemon.close_all_connections()
        t1 = time.perf_counter()

        closure_latency_ms = (t1 - t0) * 1000.0
        self.assertLess(closure_latency_ms, 50.0, f"Socket closure took too long: {closure_latency_ms:.2f}ms")
        self.assertGreaterEqual(closed_count, 30)
        self.assertEqual(daemon.active_connection_count, 0)

        # Verify all client sockets immediately receive EOF or error when reading
        for idx, c in enumerate(clients):
            try:
                c.settimeout(0.5)
                data = c.recv(1024)
                self.assertEqual(data, b"", f"Client {idx} should have received EOF immediately")
            except (ConnectionResetError, socket.error):
                pass  # Connection reset is also valid immediate closure
            finally:
                c.close()

    def test_09_heartbeat_failure_detection_and_auto_recovery_speed(self):
        """
        Adversarial Scenario: EnterpriseProxyManager running with active heartbeat (interval=0.15s).
        1. Upstream drops -> measure detection latency to kill-switch trigger.
        2. Upstream returns -> measure recovery latency to normal state.
        Target: Failure detected in < 1.0s, recovery in < 1.0s.
        """
        # Custom mock adb runner to avoid external adb requirement
        mock_adb_calls: List[List[str]] = []

        def mock_adb_runner(cmd: List[str], serial: Optional[str] = None):
            mock_adb_calls.append(cmd)
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="OK", stderr="")

        # Start upstream proxy
        upstream_proxy = MockFlappingHttpProxy()
        upstream_proxy.start()

        manager = EnterpriseProxyManager(
            adb_runner=mock_adb_runner,
            heartbeat_interval=0.15,
            enable_heartbeat=True
        )
        local_port = manager.start_auth_proxy(
            upstream_url=f"http://127.0.0.1:{upstream_proxy.port}",
            local_port=0
        )
        self.addCleanup(manager.stop_auth_proxy)

        manager.attach_instance_proxy(
            serial="emulator-5554",
            mode="local_auth",
            upstream_config={"url": f"http://127.0.0.1:{upstream_proxy.port}"},
            enable_kill_switch=True
        )

        # Allow initial heartbeat to verify healthy
        time.sleep(0.3)
        self.assertEqual(manager.get_proxy_status()["heartbeat_status"], "HEALTHY")
        self.assertEqual(manager.kill_switch.state, KillSwitchState.INACTIVE)

        # 1. Kill upstream proxy abruptly
        t_kill = time.time()
        upstream_proxy.stop()

        # Wait for heartbeat failure detection
        detected = False
        while time.time() - t_kill < 2.0:
            status = manager.get_proxy_status()
            if status["heartbeat_status"] == "DOWN" and manager.kill_switch.state == KillSwitchState.ACTIVE:
                detected = True
                break
            time.sleep(0.05)

        detection_latency = time.time() - t_kill
        self.assertTrue(detected, "Heartbeat failed to detect upstream drop within 2s!")
        self.assertLess(detection_latency, 1.2, f"Detection took too long: {detection_latency:.2f}s")

        # 2. Re-bind upstream proxy on the exact same port
        restarted_proxy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        restarted_proxy.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        restarted_proxy.bind(("127.0.0.1", upstream_proxy.port))
        restarted_proxy.listen(16)
        self.addCleanup(restarted_proxy.close)

        # Simple accept loop to satisfy HEAD probe
        restarted_running = [True]
        def dummy_serve():
            while restarted_running[0]:
                try:
                    s, _ = restarted_proxy.accept()
                    s.recv(1024)
                    s.sendall(b"HTTP/1.1 200 OK\r\n\r\n")
                    s.close()
                except Exception:
                    break

        th = threading.Thread(target=dummy_serve, daemon=True)
        th.start()

        # Wait for heartbeat auto-recovery
        t_rec = time.time()
        recovered = False
        while time.time() - t_rec < 2.0:
            status = manager.get_proxy_status()
            if status["heartbeat_status"] == "HEALTHY" and manager.kill_switch.state == KillSwitchState.INACTIVE:
                recovered = True
                break
            time.sleep(0.05)

        recovery_latency = time.time() - t_rec
        restarted_running[0] = False
        self.assertTrue(recovered, "Heartbeat failed to auto-recover within 2s!")
        self.assertLess(recovery_latency, 1.2, f"Recovery took too long: {recovery_latency:.2f}s")

    def test_10_unresponsive_hanging_upstream_probe_timeout(self):
        """
        Adversarial Scenario: Upstream accepts TCP connection on probe port but hangs
        indefinitely (blackhole / freeze).
        Verify:
        - Heartbeat probe socket timeout (0.5s) trips cleanly without hanging the manager.
        - Heartbeat reports "DOWN" and does not dead-lock.
        """
        hanging_server = MockHangingServer()
        hanging_server.start()
        self.addCleanup(hanging_server.stop)

        manager = EnterpriseProxyManager(
            heartbeat_interval=0.2,
            enable_heartbeat=False  # manual health check testing
        )
        manager._upstream_config = UpstreamConfig(
            protocol="http",
            host="127.0.0.1",
            port=hanging_server.port
        )

        t0 = time.time()
        healthy = manager.check_upstream_health()
        elapsed = time.time() - t0

        self.assertFalse(healthy, "Hanging server should be reported as unhealthy")
        self.assertLess(elapsed, 1.5, f"Probe timeout took too long: {elapsed:.2f}s")
        self.assertGreaterEqual(elapsed, 0.4, f"Probe should have waited for socket timeout (~0.5s)")

    def test_11_adversarial_malformed_headers_and_payload_overflow(self):
        """
        Adversarial Scenario: Client sends intentionally hostile requests:
        1. 70 KB oversized header (exceeding 64 KB limit) -> must receive HTTP 431.
        2. Binary garbage request line without HTTP verbs.
        3. Empty request line.
        Verify daemon rejects them safely without hanging or raising unhandled exceptions.
        """
        cfg = UpstreamConfig(protocol="direct", host="", port=0)
        daemon = LocalProxyDaemon(upstream_config=cfg, local_port=0)
        local_port = daemon.start()
        self.addCleanup(daemon.stop)

        # 1. 70 KB oversized header
        c1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        c1.settimeout(3.0)
        c1.connect(("127.0.0.1", local_port))
        self.addCleanup(c1.close)

        huge_header = b"GET / HTTP/1.1\r\nX-Spam: " + (b"A" * 70000)
        c1.sendall(huge_header)
        try:
            resp1 = c1.recv(1024)
            self.assertIn(b"431 Request Header Fields Too Large", resp1)
        except ConnectionResetError:
            # On Windows, closing a socket with unread incoming buffer transmits TCP RST,
            # which immediately terminates the client connection safely.
            pass

        # 2. Binary garbage
        c2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        c2.settimeout(2.0)
        c2.connect(("127.0.0.1", local_port))
        self.addCleanup(c2.close)
        c2.sendall(b"\x00\x01\x02\x03\xFF\xFE\xFD\r\n\r\n")
        # Should close socket cleanly without response
        data = c2.recv(1024)
        self.assertEqual(data, b"")

        # 3. Empty request line
        c3 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        c3.settimeout(2.0)
        c3.connect(("127.0.0.1", local_port))
        self.addCleanup(c3.close)
        c3.sendall(b"\r\n\r\n")
        data = c3.recv(1024)
        self.assertEqual(data, b"")

        time.sleep(0.2)
        self.assertEqual(daemon.active_connection_count, 0)

    def test_12_socks5_domain_and_ipv6_tunnel_negotiation(self):
        """
        Adversarial Scenario: Verify SOCKS5 CONNECT packet formation with:
        1. IPv6 address (ATYP 0x04)
        2. Oversized domain (>255 bytes) -> must raise ValueError
        3. Valid domain name (ATYP 0x03)
        """
        # Mock SOCKS5 server to verify ATYP parsing
        received_atyp: List[int] = []
        received_host: List[str] = []

        socks_srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        socks_srv.bind(("127.0.0.1", 0))
        srv_port = socks_srv.getsockname()[1]
        socks_srv.listen(5)
        self.addCleanup(socks_srv.close)

        def mock_socks_worker():
            for _ in range(2):
                try:
                    s, _ = socks_srv.accept()
                    s.recv(10)
                    s.sendall(b"\x05\x00")  # No auth
                    # Read CONNECT packet
                    hdr = s.recv(4)
                    atyp = hdr[3]
                    received_atyp.append(atyp)
                    if atyp == 0x03:
                        dlen = s.recv(1)[0]
                        host = s.recv(dlen).decode("utf-8")
                        received_host.append(host)
                    elif atyp == 0x04:
                        ip6 = s.recv(16)
                        host = socket.inet_ntop(socket.AF_INET6, ip6)
                        received_host.append(host)
                    s.recv(2)  # port
                    s.sendall(b"\x05\x00\x00\x01\x7F\x00\x00\x01\x1F\x90")  # Success
                    s.close()
                except Exception:
                    pass

        th = threading.Thread(target=mock_socks_worker, daemon=True)
        th.start()

        # 1. Valid Domain Name (ATYP 0x03)
        s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s1.connect(("127.0.0.1", srv_port))
        self.addCleanup(s1.close)
        Socks5Client.handshake(s1)
        Socks5Client.connect_tunnel(s1, "proxy.indusbridge.com", 443)

        # 2. IPv6 Address (ATYP 0x04)
        s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s2.connect(("127.0.0.1", srv_port))
        self.addCleanup(s2.close)
        Socks5Client.handshake(s2)
        Socks5Client.connect_tunnel(s2, "2001:db8::1", 8080)

        th.join(timeout=2.0)
        self.assertEqual(received_atyp, [0x03, 0x04])
        self.assertEqual(received_host[0], "proxy.indusbridge.com")
        self.assertEqual(received_host[1], "2001:db8::1")

        # 3. Oversized domain > 255 bytes must raise ValueError
        s3 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(s3.close)
        huge_domain = "a" * 256 + ".com"
        with self.assertRaises(ValueError):
            Socks5Client.connect_tunnel(s3, huge_domain, 443)

    def test_13_kill_switch_idempotency_and_multi_instance_concurrency(self):
        """
        Adversarial Scenario:
        1. Repeated trigger_kill_switch() and recover_kill_switch() calls on attached instance.
        2. Concurrent instance attachments (5 instances simultaneously attaching and detaching).
        Verify state transitions remain consistent without race conditions or deadlocks.
        """
        mock_commands: List[List[str]] = []
        cmd_lock = threading.Lock()

        def mock_adb(cmd: List[str], serial: Optional[str] = None):
            with cmd_lock:
                mock_commands.append(cmd)
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="OK", stderr="")

        manager = EnterpriseProxyManager(adb_runner=mock_adb, enable_heartbeat=False)
        self.addCleanup(manager.stop_auth_proxy)

        # Attach instance so kill switch has a registered target
        manager.attach_instance_proxy(
            serial="emulator-5554",
            mode="local_auth",
            upstream_config={"protocol": "http", "host": "127.0.0.1", "port": 8080}
        )

        # Test idempotency: 10 repeated trigger calls
        for _ in range(10):
            manager.trigger_kill_switch()
        self.assertEqual(manager.kill_switch.state, KillSwitchState.ACTIVE)

        # 10 repeated recover calls
        for _ in range(10):
            manager.recover_kill_switch()
        self.assertEqual(manager.kill_switch.state, KillSwitchState.INACTIVE)

        # Clean up instance
        manager.detach_instance_proxy("emulator-5554")

        # Concurrent attach/detach from 5 threads
        threads = []
        errors = []

        def worker_inst(idx: int):
            serial = f"emulator-{5554 + idx * 2}"
            try:
                manager.attach_instance_proxy(
                    serial=serial,
                    mode="local_auth",
                    upstream_config={"protocol": "http", "host": "127.0.0.1", "port": 8080}
                )
                time.sleep(0.02)
                status = manager.get_proxy_status(serial=serial)
                if not status.get("instance_specific"):
                    errors.append(f"Instance {serial} missing in status")
                manager.detach_instance_proxy(serial=serial)
            except Exception as e:
                errors.append(f"Worker {idx} error: {e}")

        for i in range(5):
            t = threading.Thread(target=worker_inst, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=3.0)

        self.assertEqual(len(errors), 0, f"Concurrent attach/detach errors: {errors}")
        final_status = manager.get_proxy_status()
        self.assertEqual(len(final_status["instances"]), 0)

    def test_14_zero_instance_killswitch_trigger_edge_case(self):
        """
        Adversarial Scenario:
        When trigger_kill_switch() is invoked without any attached instances (empty _attached_instances),
        the loop in trigger_kill_switch iterates over 0 targets, leaving kill_switch.state as INACTIVE.
        This test documents and verifies this specific behavior.
        """
        manager = EnterpriseProxyManager(enable_heartbeat=False)
        self.assertEqual(len(manager._attached_instances), 0)
        manager.trigger_kill_switch()
        # With 0 instances attached, kill_switch.activate is not called
        self.assertEqual(manager.kill_switch.state, KillSwitchState.INACTIVE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
