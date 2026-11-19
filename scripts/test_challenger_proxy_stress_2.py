"""
scripts/test_challenger_proxy_stress_2.py
=========================================
Empirical Adversarial Stress-Test Harness for nexus/proxy_manager.py
Milestone M2 — Enterprise Authenticated Transparent Proxy Engine

Tests:
1. UDP packet tunneling and routing command generation.
2. Fail-closed kill-switch enforcement (socket termination, iptables DROP commands, non-root blackhole fallback, idempotency).
3. MTU 1380 clamping command correctness on eth0 and wlan0 (privilege requirements, interface handling, bounds).
4. DNS leak prevention (Private DNS disable command, SOCKS5 ATYP 0x03 address parsing, remote resolution verification).
5. Concurrency, high-throughput, and adversarial input stress testing.
"""

import os
import sys
import time
import socket
import select
import base64
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


class MockAdbCapture:
    """Captures all ADB commands executed by proxy_manager for deep verification."""

    def __init__(self, root_allowed: bool = True, fail_interfaces: Optional[List[str]] = None):
        self.commands: List[Tuple[List[str], Optional[str]]] = []
        self.root_allowed = root_allowed
        self.fail_interfaces = fail_interfaces or []
        self._lock = threading.Lock()

    def run(self, cmd: List[str], serial: Optional[str] = None) -> subprocess.CompletedProcess:
        with self._lock:
            self.commands.append((list(cmd), serial))

        # Check for su / root failure
        if "su" in cmd and not self.root_allowed:
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=1,
                stdout="",
                stderr="su: inaccessible or not found"
            )

        # Check for interface failure in ip link set
        for iface in self.fail_interfaces:
            if iface in cmd:
                return subprocess.CompletedProcess(
                    args=cmd,
                    returncode=1,
                    stdout="",
                    stderr=f"Cannot find device \"{iface}\""
                )

        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout="OK",
            stderr=""
        )

    def get_executed_strings(self) -> List[str]:
        with self._lock:
            return [" ".join(cmd) for cmd, _ in self.commands]

    def clear(self):
        with self._lock:
            self.commands.clear()


class MockEchoServer:
    """TCP echo server for end-to-end data transfer stress testing."""

    def __init__(self, host: str = "127.0.0.1"):
        self.host = host
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((host, 0))
        self.port = self.sock.getsockname()[1]
        self.sock.listen(64)
        self.running = False
        self.thread: Optional[threading.Thread] = None
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
        try:
            while self.running:
                data = client.recv(65536)
                if not data:
                    break
                client.sendall(data)
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


class MockSocks5Server:
    """SOCKS5 server capturing RFC 1928 handshake and ATYP address details."""

    def __init__(self, username: Optional[str] = None, password: Optional[str] = None):
        self.username = username
        self.password = password
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self.sock.listen(32)
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.connect_requests: List[Dict[str, Any]] = []
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
        try:
            # 1. Method selection
            greet = client.recv(256)
            if not greet or greet[0] != 0x05:
                return
            nmethods = greet[1]
            methods = greet[2:2 + nmethods]

            if self.username and self.password is not None:
                if 0x02 not in methods:
                    client.sendall(b"\x05\xFF")
                    return
                client.sendall(b"\x05\x02")  # Username/Password auth required

                # Subnegotiation
                auth_req = client.recv(512)
                if not auth_req or auth_req[0] != 0x01:
                    return
                ulen = auth_req[1]
                user = auth_req[2:2 + ulen].decode("utf-8", errors="replace")
                plen = auth_req[2 + ulen]
                pwd = auth_req[3 + ulen:3 + ulen + plen].decode("utf-8", errors="replace")

                if user == self.username and pwd == self.password:
                    client.sendall(b"\x01\x00")  # Success
                else:
                    client.sendall(b"\x01\x01")  # Failed
                    return
            else:
                client.sendall(b"\x05\x00")  # No auth required

            # 2. Command request
            cmd_req = client.recv(512)
            if len(cmd_req) < 4 or cmd_req[0] != 0x05 or cmd_req[1] != 0x01:  # CONNECT
                return

            atyp = cmd_req[3]
            addr = ""
            dest_port = 0

            if atyp == 0x01:  # IPv4
                addr = socket.inet_ntoa(cmd_req[4:8])
                dest_port = int.from_bytes(cmd_req[8:10], "big")
            elif atyp == 0x03:  # Domain
                dlen = cmd_req[4]
                addr = cmd_req[5:5 + dlen].decode("utf-8", errors="replace")
                dest_port = int.from_bytes(cmd_req[5 + dlen:7 + dlen], "big")
            elif atyp == 0x04:  # IPv6
                addr = socket.inet_ntop(socket.AF_INET6, cmd_req[4:20])
                dest_port = int.from_bytes(cmd_req[20:22], "big")

            with self._lock:
                self.connect_requests.append({
                    "atyp": atyp,
                    "target_addr": addr,
                    "target_port": dest_port,
                    "raw_req": cmd_req
                })

            # Respond success: VER=5, REP=0, RSV=0, ATYP=1, BND.ADDR=127.0.0.1, BND.PORT=1080
            client.sendall(b"\x05\x00\x00\x01\x7f\x00\x00\x01\x04\x38")

            # Echo data back to client
            while self.running:
                data = client.recv(4096)
                if not data:
                    break
                client.sendall(data)

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


class ChallengerProxyStressTest(unittest.TestCase):
    """Adversarial stress-test suite targeting proxy_manager implementation limits."""

    def setUp(self):
        self.echo_server = MockEchoServer()
        self.echo_server.start()

    def tearDown(self):
        self.echo_server.stop()

    # =========================================================================
    # 1. UDP Packet Tunneling and Routing Command Generation Stress
    # =========================================================================

    def test_udp_routing_command_generation_adversarial(self):
        """
        Adversarially audits routing commands generated by TransparentTun2SocksInterceptor.
        Checks for UDP capture rules, routing tables, and parameter usage.
        """
        adb = MockAdbCapture()
        TransparentTun2SocksInterceptor.apply_tun2socks_routing("emulator-5554", local_port=8990, adb_runner=adb.run)
        cmds = adb.get_executed_strings()

        print(f"\n[STRESS 1.1] apply_tun2socks_routing commands executed ({len(cmds)}):")
        for c in cmds:
            print(f"  -> {c}")

        # Check 1: Does apply_tun2socks_routing generate any UDP interception rule?
        udp_found = any("-p udp" in c or "udp" in c.lower() for c in cmds)
        print(f"  [CHECK] UDP interception rule present: {udp_found}")

        # Check 2: Does apply_tun2socks_routing use local_port in commands?
        port_found = any("8990" in c for c in cmds)
        print(f"  [CHECK] local_port (8990) used in generated commands: {port_found}")

        # Check 3: Check removal commands
        adb.clear()
        TransparentTun2SocksInterceptor.remove_tun2socks_routing("emulator-5554", adb_runner=adb.run)
        rm_cmds = adb.get_executed_strings()
        print(f"[STRESS 1.1] remove_tun2socks_routing commands executed ({len(rm_cmds)}):")
        for c in rm_cmds:
            print(f"  -> {c}")

        # Findings:
        # 1. Commands only clamp TCP MSS (TCPMSS --clamp-mss-to-pmtu) and set ip_forward=1.
        # 2. No iptables REDIRECT / TPROXY / tun device routing rule exists for UDP packets.
        # 3. local_port parameter is unused in apply_tun2socks_routing.
        self.assertTrue(len(cmds) >= 2, "Expected routing commands to be generated")
        self.assertFalse(udp_found, "Confirmed: No UDP interception rule generated in current implementation")
        self.assertFalse(port_found, "Confirmed: local_port is not referenced in generated routing commands")

    def test_udp_datagram_to_proxy_daemon_behavior(self):
        """
        Empirically verifies how LocalProxyDaemon responds to incoming UDP datagrams.
        Since LocalProxyDaemon listens on SOCK_STREAM (TCP), UDP datagrams are refused/ignored.
        """
        cfg = UpstreamConfig(protocol="direct")
        daemon = LocalProxyDaemon(upstream_config=cfg, local_port=0)
        port = daemon.start()
        try:
            # Send UDP packet to proxy daemon port
            udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_sock.settimeout(0.5)
            # Should not raise on sendto, but daemon will not acknowledge or relay UDP
            udp_sock.sendto(b"TEST_UDP_DATAGRAM", ("127.0.0.1", port))
            received = False
            try:
                data, _ = udp_sock.recvfrom(1024)
                received = True
            except (socket.timeout, ConnectionResetError, OSError):
                # On Windows, ICMP Port Unreachable causes WSAECONNRESET (10054) on UDP socket
                received = False
            finally:
                udp_sock.close()

            print(f"\n[STRESS 1.2] UDP packet sent to proxy daemon (127.0.0.1:{port}). Received response: {received}")
            self.assertFalse(received, "Proxy daemon correctly does not respond to raw UDP on TCP port")
        finally:
            daemon.stop()

    def test_socks5_udp_associate_not_implemented(self):
        """
        Verifies that Socks5Client only implements CONNECT (0x01) and not UDP ASSOCIATE (0x03).
        """
        # Socks5Client has handshake and connect_tunnel methods only
        self.assertTrue(hasattr(Socks5Client, "handshake"))
        self.assertTrue(hasattr(Socks5Client, "connect_tunnel"))
        self.assertFalse(hasattr(Socks5Client, "udp_associate"), "Socks5Client lacks UDP ASSOCIATE capability")

    # =========================================================================
    # 2. Fail-Closed Kill-Switch Enforcement Stress
    # =========================================================================

    def test_kill_switch_socket_termination_under_heavy_concurrency(self):
        """
        Stress-tests immediate socket termination when kill-switch activates.
        Opens 50 concurrent bi-directional streaming tunnels, triggers kill-switch,
        and verifies 100% of sockets are terminated immediately with zero leaks.
        """
        cfg = UpstreamConfig(protocol="direct")
        mgr = EnterpriseProxyManager(enable_heartbeat=False)
        port = mgr.start_auth_proxy("direct://", local_port=0)

        connected_socks: List[socket.socket] = []
        threads: List[threading.Thread] = []
        errors: List[Exception] = []
        conns_established = threading.Event()
        barrier = threading.Barrier(51)

        def client_worker():
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5.0)
            try:
                s.connect(("127.0.0.1", port))
                req = f"CONNECT 127.0.0.1:{self.echo_server.port} HTTP/1.1\r\n\r\n"
                s.sendall(req.encode("latin1"))
                resp = s.recv(1024)
                if b"200 Connection Established" in resp:
                    connected_socks.append(s)
                else:
                    errors.append(RuntimeError(f"Unexpected response: {resp}"))
            except Exception as e:
                errors.append(e)
            finally:
                try:
                    barrier.wait(timeout=5.0)
                except Exception:
                    pass

        for _ in range(50):
            t = threading.Thread(target=client_worker, daemon=True)
            threads.append(t)
            t.start()

        barrier.wait(timeout=6.0)
        time.sleep(0.2)

        active_count_before = mgr.get_proxy_status()["active_connections"]
        print(f"\n[STRESS 2.1] Established concurrent tunnel connections: {len(connected_socks)}, active tracked: {active_count_before}")
        self.assertEqual(len(connected_socks), 50, "All 50 concurrent client connections should be established")

        # Now trigger the kill switch
        start_time = time.time()
        mgr.trigger_kill_switch()
        kill_elapsed_ms = (time.time() - start_time) * 1000.0

        # Verify active connection tracking drops to 0
        active_count_after = mgr.get_proxy_status()["active_connections"]
        print(f"  [CHECK] Kill-switch trigger elapsed: {kill_elapsed_ms:.2f} ms")
        print(f"  [CHECK] Active connections tracked after kill-switch: {active_count_after}")
        self.assertEqual(active_count_after, 0, "All tracked active connections must be cleared")

        # Verify every client socket was forcibly terminated by daemon
        terminated_count = 0
        for s in connected_socks:
            try:
                s.settimeout(0.5)
                # Attempting to read or write must fail (EOF or ConnectionResetError)
                d = s.recv(1024)
                if not d:
                    terminated_count += 1
                else:
                    # Echo check: if data returned, socket was not closed
                    pass
            except (socket.error, ConnectionResetError, BrokenPipeError):
                terminated_count += 1
            finally:
                try:
                    s.close()
                except Exception:
                    pass

        print(f"  [CHECK] Verified terminated client sockets: {terminated_count}/50")
        self.assertEqual(terminated_count, 50, "All 50 client sockets must be terminated immediately")
        mgr.stop_auth_proxy()

    def test_kill_switch_command_generation_root_vs_non_root(self):
        """
        Verifies command generation for rooted vs non-root environments in EgressKillSwitch.
        """
        ks = EgressKillSwitch()

        # 1. Rooted environment
        adb_root = MockAdbCapture(root_allowed=True)
        res_root = ks.activate("emulator-5554", adb_runner=adb_root.run, is_rooted=True)
        self.assertTrue(res_root)
        self.assertEqual(ks.state, KillSwitchState.ACTIVE)
        root_cmds = adb_root.get_executed_strings()
        print(f"\n[STRESS 2.2] Rooted kill-switch activation commands:")
        for c in root_cmds:
            print(f"  -> {c}")
        self.assertIn("shell su 0 iptables -I OUTPUT 1 -j DROP", root_cmds)

        # 2. Non-root fallback environment
        adb_non_root = MockAdbCapture(root_allowed=False)
        res_non_root = ks.activate("emulator-5556", adb_runner=adb_non_root.run, is_rooted=False)
        self.assertTrue(res_non_root)
        self.assertEqual(ks.state, KillSwitchState.ACTIVE)
        non_root_cmds = adb_non_root.get_executed_strings()
        print(f"[STRESS 2.2] Non-root fallback activation commands:")
        for c in non_root_cmds:
            print(f"  -> {c}")
        self.assertIn("shell settings put global http_proxy 127.0.0.1:1", non_root_cmds)
        self.assertIn("shell setprop net.dns1 127.0.0.1", non_root_cmds)

    def test_kill_switch_idempotency_and_lingering_rules(self):
        """
        Adversarial test: tests repeated kill-switch activation and checks if recover()
        leaves lingering DROP rules.
        """
        ks = EgressKillSwitch()
        adb = MockAdbCapture(root_allowed=True)

        # Activate 3 times consecutively
        ks.activate("emulator-5554", adb_runner=adb.run, is_rooted=True)
        ks.activate("emulator-5554", adb_runner=adb.run, is_rooted=True)
        ks.activate("emulator-5554", adb_runner=adb.run, is_rooted=True)

        cmds = adb.get_executed_strings()
        insert_count = sum(1 for c in cmds if "iptables -I OUTPUT 1 -j DROP" in c)
        print(f"\n[STRESS 2.3] Consecutive kill-switch activations: 3. 'iptables -I OUTPUT 1' executed: {insert_count} times")

        # Now call recover once
        adb.clear()
        ks.recover("emulator-5554", local_port=8990, adb_runner=adb.run, is_rooted=True)
        recover_cmds = adb.get_executed_strings()
        delete_count = sum(1 for c in recover_cmds if "iptables -D OUTPUT 1" in c)
        print(f"  [CHECK] Recover called once. 'iptables -D OUTPUT 1' executed: {delete_count} times")

        # Note: In lines 994-995, recover() executes su 0 iptables -D and non-su iptables -D.
        # But if activate() was called 3 times, 3 rules were inserted. Calling recover() only deletes at most 2!
        # This surfaces an architectural idempotency challenge: multiple DROP rules can stack up.
        self.assertEqual(ks.state, KillSwitchState.INACTIVE)

    # =========================================================================
    # 3. MTU 1380 Clamping Command Correctness on eth0 and wlan0
    # =========================================================================

    def test_mtu_clamping_commands_and_privilege_audit(self):
        """
        Adversarially audits MTU clamping commands for eth0 and wlan0.
        Verifies:
        1. Exact commands dispatched for eth0 and wlan0 with MTU 1380.
        2. Whether commands require root/su or run as unprivileged adb shell.
        3. Handling of missing network interfaces (e.g. wlan0 on ethernet-only emulator).
        """
        adb = MockAdbCapture()
        success = TransparentTun2SocksInterceptor.clamp_mtu("emulator-5554", mtu=1380, adb_runner=adb.run)
        cmds = adb.get_executed_strings()

        print(f"\n[STRESS 3.1] clamp_mtu commands executed ({len(cmds)}):")
        for c in cmds:
            print(f"  -> {c}")

        self.assertTrue(success)
        self.assertIn("shell ip link set dev eth0 mtu 1380", cmds)
        self.assertIn("shell ip link set dev wlan0 mtu 1380", cmds)

        # Privilege observation:
        has_su = any("su" in c for c in cmds)
        print(f"  [OBSERVATION] clamp_mtu executes with 'su 0': {has_su} (executes as unprivileged shell)")

        # Test restore_mtu
        adb.clear()
        success_restore = TransparentTun2SocksInterceptor.restore_mtu("emulator-5554", mtu=1500, adb_runner=adb.run)
        restore_cmds = adb.get_executed_strings()
        print(f"[STRESS 3.1] restore_mtu commands executed ({len(restore_cmds)}):")
        for c in restore_cmds:
            print(f"  -> {c}")
        self.assertTrue(success_restore)
        self.assertIn("shell ip link set dev eth0 mtu 1500", restore_cmds)
        self.assertIn("shell ip link set dev wlan0 mtu 1500", restore_cmds)

    def test_mtu_clamping_missing_interface_handling(self):
        """
        Tests behavior when wlan0 does not exist on the Android guest.
        """
        # wlan0 fails
        adb_fail_wlan = MockAdbCapture(fail_interfaces=["wlan0"])
        success = TransparentTun2SocksInterceptor.clamp_mtu("emulator-5554", mtu=1380, adb_runner=adb_fail_wlan.run)
        print(f"\n[STRESS 3.2] clamp_mtu with missing wlan0 returns success: {success}")
        # When wlan0 fails, clamp_mtu returns False because one command had returncode != 0
        self.assertFalse(success, "clamp_mtu should return False if an interface fails")

    def test_mtu_extreme_boundary_values(self):
        """
        Tests MTU clamping with boundary values (minimum MTU 576, jumbo frames 9000).
        """
        adb = MockAdbCapture()
        TransparentTun2SocksInterceptor.clamp_mtu("emulator-5554", mtu=576, adb_runner=adb.run)
        TransparentTun2SocksInterceptor.clamp_mtu("emulator-5554", mtu=9000, adb_runner=adb.run)
        cmds = adb.get_executed_strings()
        self.assertIn("shell ip link set dev eth0 mtu 576", cmds)
        self.assertIn("shell ip link set dev eth0 mtu 9000", cmds)

    # =========================================================================
    # 4. DNS Leak Prevention: Private DNS & SOCKS5 ATYP 0x03 Address Parsing
    # =========================================================================

    def test_private_dns_disable_and_restore(self):
        """
        Verifies Private DNS is explicitly disabled on attach and restored on detach.
        """
        adb = MockAdbCapture()
        mgr = EnterpriseProxyManager(adb_runner=adb.run, enable_heartbeat=False)

        # Attach
        mgr.attach_instance_proxy("emulator-5554", mode="local_auth", upstream_config={"protocol": "direct"})
        attach_cmds = adb.get_executed_strings()
        print(f"\n[STRESS 4.1] Private DNS commands during attach_instance_proxy:")
        for c in attach_cmds:
            if "private_dns" in c:
                print(f"  -> {c}")
        self.assertIn("shell settings put global private_dns_mode off", attach_cmds)

        # Detach
        adb.clear()
        mgr.detach_instance_proxy("emulator-5554")
        detach_cmds = adb.get_executed_strings()
        print(f"[STRESS 4.1] Private DNS commands during detach_instance_proxy:")
        for c in detach_cmds:
            if "private_dns" in c:
                print(f"  -> {c}")
        self.assertIn("shell settings put global private_dns_mode opportunistic", detach_cmds)

    def test_socks5_atyp_address_parsing_exhaustive(self):
        """
        Adversarially tests Socks5Client.connect_tunnel packet formation:
        1. Standard domain names -> ATYP 0x03, 1-byte length prefix.
        2. Max 255-byte domain -> ATYP 0x03.
        3. Domain > 255 bytes -> raises ValueError.
        4. IPv4 addresses -> ATYP 0x01, 4 bytes packed IP.
        5. IPv6 addresses -> ATYP 0x04, 16 bytes packed IP.
        """
        # We use a dummy socket that records sent data
        class CapturingSocket:
            def __init__(self):
                self.sent_bytes = b""
            def sendall(self, data):
                self.sent_bytes += data
            def recv(self, size):
                # Return SOCKS5 success: VER=5, REP=0, RSV=0, ATYP=1, BND.ADDR=127.0.0.1, BND.PORT=1080
                return b"\x05\x00\x00\x01\x7f\x00\x00\x01\x04\x38"[:size]

        print(f"\n[STRESS 4.2] Testing SOCKS5 ATYP packet construction:")

        # 1. Standard Domain -> ATYP 0x03
        s = CapturingSocket()
        Socks5Client.connect_tunnel(s, "dns.google", 443)
        pkt = s.sent_bytes
        self.assertEqual(pkt[0:3], b"\x05\x01\x00")
        self.assertEqual(pkt[3], 0x03, "ATYP must be 0x03 for domain names")
        dlen = pkt[4]
        domain = pkt[5:5 + dlen].decode("utf-8")
        port = int.from_bytes(pkt[5 + dlen:7 + dlen], "big")
        self.assertEqual(domain, "dns.google")
        self.assertEqual(port, 443)
        print(f"  [PASS] Domain 'dns.google:443' -> ATYP 0x03, parsed domain: {domain}, port: {port}")

        # 2. IPv4 -> ATYP 0x01
        s = CapturingSocket()
        Socks5Client.connect_tunnel(s, "8.8.8.8", 53)
        pkt = s.sent_bytes
        self.assertEqual(pkt[3], 0x01, "ATYP must be 0x01 for IPv4")
        ip_addr = socket.inet_ntoa(pkt[4:8])
        port = int.from_bytes(pkt[8:10], "big")
        self.assertEqual(ip_addr, "8.8.8.8")
        self.assertEqual(port, 53)
        print(f"  [PASS] IPv4 '8.8.8.8:53' -> ATYP 0x01, parsed IP: {ip_addr}, port: {port}")

        # 3. IPv6 -> ATYP 0x04
        s = CapturingSocket()
        Socks5Client.connect_tunnel(s, "2001:4860:4860::8888", 853)
        pkt = s.sent_bytes
        self.assertEqual(pkt[3], 0x04, "ATYP must be 0x04 for IPv6")
        ip6_addr = socket.inet_ntop(socket.AF_INET6, pkt[4:20])
        port = int.from_bytes(pkt[20:22], "big")
        self.assertEqual(port, 853)
        print(f"  [PASS] IPv6 '2001:4860:4860::8888:853' -> ATYP 0x04, port: {port}")

        # 4. Domain boundary: exactly 255 bytes (allowed)
        long_domain_255 = "a" * 251 + ".com"  # 255 chars
        s = CapturingSocket()
        Socks5Client.connect_tunnel(s, long_domain_255, 80)
        pkt = s.sent_bytes
        self.assertEqual(pkt[3], 0x03)
        self.assertEqual(pkt[4], 255)
        print(f"  [PASS] 255-byte domain boundary accepted (len={pkt[4]})")

        # 5. Domain boundary: 256 bytes (RFC 1928 violation)
        long_domain_256 = "a" * 252 + ".com"  # 256 chars
        s = CapturingSocket()
        with self.assertRaises(ValueError):
            Socks5Client.connect_tunnel(s, long_domain_256, 80)
        print(f"  [PASS] 256-byte domain correctly raises ValueError")

    def test_socks5_remote_dns_resolution_end_to_end(self):
        """
        Empirically verifies that SOCKS5 client delegates DNS resolution to the proxy
        by verifying the upstream mock SOCKS5 server receives ATYP 0x03 with the raw domain name.
        """
        socks_server = MockSocks5Server(username="testuser", password="secretpassword")
        socks_server.start()
        try:
            cfg = UpstreamConfig(
                protocol="socks5",
                host="127.0.0.1",
                port=socks_server.port,
                username="testuser",
                password="secretpassword"
            )
            daemon = LocalProxyDaemon(upstream_config=cfg, local_port=0)
            local_port = daemon.start()
            try:
                # Client sends HTTP CONNECT with an unresolvable internal domain
                client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                client.settimeout(5.0)
                client.connect(("127.0.0.1", local_port))
                req = "CONNECT internal-secure-host.corp:8443 HTTP/1.1\r\n\r\n"
                client.sendall(req.encode("latin1"))

                resp = client.recv(1024)
                self.assertIn(b"200 Connection Established", resp)

                # Send test data and receive echo
                client.sendall(b"PING_SOCKS5_DATA")
                echoed = client.recv(1024)
                self.assertEqual(echoed, b"PING_SOCKS5_DATA")
                client.close()

                # Verify SOCKS5 server received ATYP 0x03 with exact domain
                self.assertEqual(len(socks_server.connect_requests), 1)
                req_info = socks_server.connect_requests[0]
                print(f"\n[STRESS 4.3] SOCKS5 server captured connect request:")
                print(f"  ATYP: {hex(req_info['atyp'])}")
                print(f"  Target: {req_info['target_addr']}:{req_info['target_port']}")
                self.assertEqual(req_info["atyp"], 0x03, "Must use ATYP 0x03 (remote DNS)")
                self.assertEqual(req_info["target_addr"], "internal-secure-host.corp")
                self.assertEqual(req_info["target_port"], 8443)

            finally:
                daemon.stop()
        finally:
            socks_server.stop()

    # =========================================================================
    # 5. Throughput, Buffer Overflow and Malformed Inputs Stress Testing
    # =========================================================================

    def test_high_throughput_large_payload_transfer(self):
        """
        Pumps 4MB of continuous binary data bi-directionally through the local auth proxy
        to stress test socket non-blocking select loops, buffer integrity, and memory safety.
        """
        cfg = UpstreamConfig(protocol="direct")
        daemon = LocalProxyDaemon(upstream_config=cfg, local_port=0)
        port = daemon.start()
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.settimeout(10.0)
            client.connect(("127.0.0.1", port))
            client.sendall(f"CONNECT 127.0.0.1:{self.echo_server.port} HTTP/1.1\r\n\r\n".encode("latin1"))
            resp = client.recv(1024)
            self.assertIn(b"200 Connection Established", resp)

            # Generate 4MB test payload with checksum
            chunk_size = 65536
            total_chunks = 64  # 4MB total
            sample_chunk = os.urandom(chunk_size)

            client.setblocking(True)
            sent_bytes = 0
            recv_bytes = 0

            start_t = time.time()
            for _ in range(total_chunks):
                client.sendall(sample_chunk)
                sent_bytes += len(sample_chunk)
                # Read back echoed data
                chunk_recvd = 0
                while chunk_recvd < len(sample_chunk):
                    part = client.recv(len(sample_chunk) - chunk_recvd)
                    if not part:
                        break
                    chunk_recvd += len(part)
                recv_bytes += chunk_recvd

            elapsed = time.time() - start_t
            throughput_mb_s = (sent_bytes / (1024 * 1024)) / elapsed
            print(f"\n[STRESS 5.1] High Throughput Test:")
            print(f"  Sent: {sent_bytes} bytes, Recv: {recv_bytes} bytes in {elapsed:.2f}s ({throughput_mb_s:.2f} MB/s)")
            self.assertEqual(sent_bytes, recv_bytes)
            client.close()
        finally:
            daemon.stop()

    def test_malformed_http_requests_resilience(self):
        """
        Sends malformed HTTP request strings and oversized headers to LocalProxyDaemon.
        Verifies the daemon handles corrupt inputs gracefully without crashing.
        """
        cfg = UpstreamConfig(protocol="direct")
        daemon = LocalProxyDaemon(upstream_config=cfg, local_port=0)
        port = daemon.start()
        try:
            # 1. Huge header exceeding 64KB
            huge_data = b"GET / HTTP/1.1\r\n" + b"X-Garbage: " + (b"A" * 70000) + b"\r\n\r\n"
            s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s1.settimeout(3.0)
            s1.connect(("127.0.0.1", port))
            s1.sendall(huge_data)
            resp1 = s1.recv(1024)
            s1.close()
            print(f"\n[STRESS 5.2] Oversized header (>64KB) response: {resp1[:40]}")
            self.assertIn(b"431 Request Header Fields Too Large", resp1)

            # 2. Corrupt request line (empty tokens)
            s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s2.settimeout(2.0)
            s2.connect(("127.0.0.1", port))
            s2.sendall(b"INVALID_NO_TOKENS\r\n\r\n")
            try:
                _ = s2.recv(1024)
            except Exception:
                pass
            s2.close()

            # 3. Malformed CONNECT target port (non-integer)
            s3 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s3.settimeout(2.0)
            s3.connect(("127.0.0.1", port))
            s3.sendall(b"CONNECT example.com:notaport HTTP/1.1\r\n\r\n")
            resp3 = s3.recv(1024)
            s3.close()
            print(f"[STRESS 5.2] Malformed CONNECT port response: {resp3!r}")
            # Observation: ValueError in int(port_str) occurs outside try block in _handle_connect,
            # resulting in abrupt connection drop (b'') rather than a structured HTTP 400 Bad Request or 502 Bad Gateway.
            self.assertEqual(resp3, b"", "Port parsing ValueError bubbles to _handle_client dropping connection")

            # Daemon must still be running healthy
            self.assertTrue(daemon.is_running)
        finally:
            daemon.stop()

    def test_detach_while_kill_switch_active_defect(self):
        """
        Adversarial test: checks ordering defect when detaching an instance
        while kill-switch is active.
        Observation: detach_instance_proxy resets proxy to :0, but then calls
        kill_switch.recover() which re-injects 10.0.2.2:8990!
        """
        adb = MockAdbCapture()
        mgr = EnterpriseProxyManager(adb_runner=adb.run, enable_heartbeat=False)
        mgr.attach_instance_proxy("emulator-5554", mode="local_auth", upstream_config={"protocol": "direct"})

        # Trigger kill switch -> state becomes ACTIVE
        mgr.trigger_kill_switch()
        self.assertEqual(mgr.kill_switch.state, KillSwitchState.ACTIVE)

        # Now detach instance
        adb.clear()
        mgr.detach_instance_proxy("emulator-5554")
        cmds = adb.get_executed_strings()

        print(f"\n[STRESS 5.3] Commands during detach while kill-switch ACTIVE:")
        for c in cmds:
            print(f"  -> {c}")

        # Check the command sequence:
        self.assertIn("shell settings put global http_proxy :0", cmds)
        self.assertIn("shell settings put global http_proxy 10.0.2.2:8990", cmds)
        idx_reset = cmds.index("shell settings put global http_proxy :0")
        idx_re_enable = cmds.index("shell settings put global http_proxy 10.0.2.2:8990")
        self.assertTrue(idx_re_enable > idx_reset,
                        "Defect confirmed: recover() re-injects 10.0.2.2:8990 after detach reset it to :0!")



def main():
    suite = unittest.TestLoader().loadTestsFromTestCase(ChallengerProxyStressTest)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
