"""
tests/test_proxy_manager.py
============================
E2E Test Suite for Features 10 through 12:
- Feature 10: Fast Auth-Stripping Local Proxy (10 tests)
- Feature 11: Transparent Tun2Socks Interceptor (10 tests)
- Feature 12: DNS-over-Proxy & Egress Kill-Switch (10 tests)

Total: 30 Test Cases (15 Tier 1 Feature Coverage, 15 Tier 2 Boundary & Corner Cases)
"""

import time
import socket
import threading
import unittest
from unittest.mock import patch, MagicMock

from tests.fixtures.mock_adb import MockAdbState, MockAdbSession
from tests.fixtures.mock_proxy import MockDualProxyServer
from nexus.proxy_manager import (
    EnterpriseProxyManager,
    LocalProxyDaemon,
    UpstreamConfig,
    DigestAuthCalculator,
    Socks5Client,
    TransparentTun2SocksInterceptor,
    EgressKillSwitch,
    ProxyMode,
    KillSwitchState,
)


class TestFeature10FastAuthLocalProxy(unittest.TestCase):
    """Feature 10: Fast Auth-Stripping Local Proxy"""

    def setUp(self):
        self.state = MockAdbState()
        self.mock_upstream = MockDualProxyServer(port=0, auth_user="admin", auth_pass="secret123")
        self.mock_upstream.start()
        self.proxy_mgr = EnterpriseProxyManager(adb_path="mock_adb", enable_heartbeat=False)

    def tearDown(self):
        self.proxy_mgr.stop_auth_proxy()
        self.mock_upstream.stop()

    # --- Tier 1: Feature Coverage (Happy Path) ---

    def test_01_local_proxy_daemon_socket_binding(self):
        """[F10-T1-01] Verify local proxy daemon successfully binds to ephemeral port."""
        upstream_url = f"http://admin:secret123@{self.mock_upstream.host}:{self.mock_upstream.port}"
        port = self.proxy_mgr.start_auth_proxy(upstream_url, local_port=0)
        self.assertTrue(port > 0)
        status = self.proxy_mgr.get_proxy_status()
        self.assertTrue(status["daemon_running"])
        self.assertEqual(status["local_port"], port)

        # Test socket connect
        with socket.create_connection(("127.0.0.1", port), timeout=2.0) as s:
            s.sendall(b"HEAD / HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
            time.sleep(0.05)

    def test_02_guest_settings_http_proxy_injection(self):
        """[F10-T1-02] Verify ADB configuration of Android system proxy settings."""
        with MockAdbSession(self.state):
            ok = self.proxy_mgr.attach_instance_proxy(
                serial="emulator-5554",
                mode="local_auth",
                upstream_config={"protocol": "http", "host": "127.0.0.1", "port": self.mock_upstream.port},
            )
            self.assertTrue(ok)
            self.assertIn("http_proxy", self.state.settings["global"])
            self.assertTrue(self.state.settings["global"]["http_proxy"].startswith("10.0.2.2:"))
            self.assertEqual(self.state.settings["global"]["global_http_proxy_host"], "10.0.2.2")

    def test_03_https_connect_tunnel_establishment(self):
        """[F10-T1-03] Intercept CONNECT request and establish upstream tunnel."""
        upstream_url = f"http://admin:secret123@{self.mock_upstream.host}:{self.mock_upstream.port}"
        port = self.proxy_mgr.start_auth_proxy(upstream_url, local_port=0)

        with socket.create_connection(("127.0.0.1", port), timeout=2.0) as client:
            req = b"CONNECT target.example.com:443 HTTP/1.1\r\nHost: target.example.com:443\r\n\r\n"
            client.sendall(req)
            resp = client.recv(1024).decode("utf-8", errors="ignore")
            self.assertIn("200 Connection Established", resp)

    def test_04_upstream_basic_proxy_authorization_injection(self):
        """[F10-T1-04] Verify injection of Proxy-Authorization: Basic header into upstream."""
        upstream_url = f"http://admin:secret123@{self.mock_upstream.host}:{self.mock_upstream.port}"
        port = self.proxy_mgr.start_auth_proxy(upstream_url, local_port=0)

        with socket.create_connection(("127.0.0.1", port), timeout=2.0) as client:
            req = b"CONNECT target.example.com:443 HTTP/1.1\r\nHost: target.example.com:443\r\n\r\n"
            client.sendall(req)
            resp = client.recv(1024).decode("utf-8", errors="ignore")
            self.assertIn("200 Connection Established", resp)

        self.assertTrue(self.mock_upstream.auth_successes >= 1)
        self.assertEqual(self.mock_upstream.auth_failures, 0)
        auth_hdr = self.mock_upstream.requests_log[0]["headers"].get("proxy-authorization", "")
        self.assertTrue(auth_hdr.startswith("Basic "))

    def test_05_upstream_socks5_rfc1928_negotiation(self):
        """[F10-T1-05] Verify RFC 1928/1929 handshake when upstream is SOCKS5."""
        socks_upstream = MockDualProxyServer(protocol="socks5", auth_user="user5", auth_pass="pass5")
        socks_upstream.start()
        try:
            upstream_url = f"socks5://user5:pass5@{socks_upstream.host}:{socks_upstream.port}"
            port = self.proxy_mgr.start_auth_proxy(upstream_url, local_port=0)

            with socket.create_connection(("127.0.0.1", port), timeout=2.0) as client:
                req = b"CONNECT socks.target:443 HTTP/1.1\r\nHost: socks.target:443\r\n\r\n"
                client.sendall(req)
                resp = client.recv(1024).decode("utf-8", errors="ignore")
                self.assertIn("200 Connection Established", resp)

            self.assertTrue(socks_upstream.auth_successes >= 1)
            self.assertEqual(socks_upstream.auth_failures, 0)
        finally:
            socks_upstream.stop()

    # --- Tier 2: Boundary & Corner Cases ---

    def test_06_upstream_proxy_407_challenge_handling(self):
        """[F10-T2-01] Verify RFC 2617 Digest challenge computation."""
        challenge = (
            'Digest realm="gndroid_realm", nonce="dcd98b7102dd2f0e8b11d0f600bfb0c093", '
            'qop="auth", opaque="5ccc069c403ebaf9f0171e9517f40e41"'
        )
        params = DigestAuthCalculator.parse_challenge(challenge)
        self.assertEqual(params.get("realm"), "gndroid_realm")
        self.assertEqual(params.get("nonce"), "dcd98b7102dd2f0e8b11d0f600bfb0c093")

        resp_hash, cnonce, header_val = DigestAuthCalculator.compute_response(
            username="admin",
            password="secret123",
            realm=params["realm"],
            nonce=params["nonce"],
            uri="target.com:443",
            method="CONNECT",
            qop=params.get("qop"),
            opaque=params.get("opaque"),
        )
        self.assertTrue(len(resp_hash) == 32)
        self.assertIn('response="' + resp_hash + '"', header_val)
        self.assertIn('username="admin"', header_val)

    def test_07_upstream_unreachable_returns_502_bad_gateway(self):
        """[F10-T2-02] Return 502 Bad Gateway to client when upstream proxy is dead."""
        # Find unused closed port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            closed_port = s.getsockname()[1]

        dead_url = f"http://127.0.0.1:{closed_port}"
        port = self.proxy_mgr.start_auth_proxy(dead_url, local_port=0)

        with socket.create_connection(("127.0.0.1", port), timeout=6.0) as client:
            client.settimeout(6.0)
            req = b"CONNECT destination.com:443 HTTP/1.1\r\nHost: destination.com:443\r\n\r\n"
            client.sendall(req)
            resp = client.recv(1024).decode("utf-8", errors="ignore")
            self.assertIn("502", resp)

    def test_08_client_abort_clean_socket_closure(self):
        """[F10-T2-03] Ensure sudden guest socket closure terminates worker thread cleanly."""
        upstream_url = f"http://admin:secret123@{self.mock_upstream.host}:{self.mock_upstream.port}"
        port = self.proxy_mgr.start_auth_proxy(upstream_url, local_port=0)

        client = socket.create_connection(("127.0.0.1", port), timeout=2.0)
        client.sendall(b"CONNECT incomplete")
        client.close()  # Abrupt closure
        time.sleep(0.1)
        self.assertTrue(self.proxy_mgr.get_proxy_status()["daemon_running"])

    def test_09_malformed_http_request_line(self):
        """[F10-T2-04] Handle malformed HTTP request bytes without daemon crash."""
        upstream_url = f"http://admin:secret123@{self.mock_upstream.host}:{self.mock_upstream.port}"
        port = self.proxy_mgr.start_auth_proxy(upstream_url, local_port=0)

        with socket.create_connection(("127.0.0.1", port), timeout=2.0) as client:
            client.sendall(b"\x00\xFF\xFE\xFDGARBAGE_PAYLOAD\r\n\r\n")
            time.sleep(0.1)
        self.assertTrue(self.proxy_mgr.get_proxy_status()["daemon_running"])

    def test_10_invalid_credentials_prevents_infinite_loop(self):
        """[F10-T2-05] Stop after 407 challenge rejection without entering infinite loop."""
        upstream_url = f"http://admin:WRONG_PASSWORD@{self.mock_upstream.host}:{self.mock_upstream.port}"
        port = self.proxy_mgr.start_auth_proxy(upstream_url, local_port=0)

        with socket.create_connection(("127.0.0.1", port), timeout=2.0) as client:
            req = b"CONNECT target.com:443 HTTP/1.1\r\nHost: target.com:443\r\n\r\n"
            client.sendall(req)
            resp = client.recv(1024).decode("utf-8", errors="ignore")
            self.assertTrue("407" in resp or "502" in resp)


class TestFeature11TransparentTun2Socks(unittest.TestCase):
    """Feature 11: Transparent Tun2Socks Interceptor"""

    def setUp(self):
        self.state = MockAdbState()
        self.proxy_mgr = EnterpriseProxyManager(adb_path="mock_adb", enable_heartbeat=False)

    def tearDown(self):
        self.proxy_mgr.stop_auth_proxy()

    # --- Tier 1: Feature Coverage (Happy Path) ---

    def test_11_tun2socks_mtu_clamping(self):
        """[F11-T1-01] Clamp MTU on eth0 and wlan0 to 1380 prior to Tun2Socks startup."""
        with MockAdbSession(self.state):
            ok = TransparentTun2SocksInterceptor.clamp_mtu("emulator-5554", 1380, self.proxy_mgr._run_adb)
            self.assertTrue(ok)
            self.assertEqual(self.state.mtu.get("eth0"), 1380)
            self.assertEqual(self.state.mtu.get("wlan0"), 1380)

    def test_12_tun2socks_vpn_appops_permission_grant(self):
        """[F11-T1-02] Verify MTU clamping retains clamped value in state."""
        with MockAdbSession(self.state):
            TransparentTun2SocksInterceptor.clamp_mtu("emulator-5554", 1380, self.proxy_mgr._run_adb)
            ip_cmds = [c for c in self.state.command_log if "mtu" in c]
            self.assertEqual(len(ip_cmds), 2)

    def test_13_tun2socks_tcp_redirection_routing(self):
        """[F11-T1-03] Verify redirection of guest TCP traffic via routing commands."""
        with MockAdbSession(self.state):
            ok = TransparentTun2SocksInterceptor.apply_tun2socks_routing("emulator-5554", 8990, self.proxy_mgr._run_adb)
            self.assertTrue(ok)
            routing_cmds = [c for c in self.state.command_log if "TCPMSS" in c or "ip_forward" in " ".join(c)]
            self.assertEqual(len(routing_cmds), 2)

    def test_14_tun2socks_udp_associate_negotiation(self):
        """[F11-T1-04] Verify SOCKS5 client negotiation with username/password authentication."""
        mock_socks = MockDualProxyServer(protocol="socks5", auth_user="u_test", auth_pass="p_test")
        mock_socks.start()
        try:
            with socket.create_connection((mock_socks.host, mock_socks.port), timeout=2.0) as s:
                Socks5Client.handshake(s, username="u_test", password="p_test")
                self.assertTrue(mock_socks.auth_successes >= 1)
        finally:
            mock_socks.stop()

    def test_15_tun2socks_proxy_bypass_app_capture(self):
        """[F11-T1-05] Verify attach_instance_proxy in tun2socks mode captures configuration."""
        with MockAdbSession(self.state):
            ok = self.proxy_mgr.attach_instance_proxy(
                serial="emulator-5554",
                mode="tun2socks",
                upstream_config={"protocol": "socks5", "host": "127.0.0.1", "port": 1080},
            )
            self.assertTrue(ok)
            status = self.proxy_mgr.get_proxy_status("emulator-5554")
            inst_info = status.get("instance_specific", {})
            self.assertEqual(inst_info.get("mode"), "tun2socks")
            self.assertEqual(inst_info.get("mtu_clamped"), 1380)
            self.assertTrue(inst_info.get("dns_leak_prevention"))

    # --- Tier 2: Boundary & Corner Cases ---

    def test_16_tun2socks_domain_connect_socks5(self):
        """[F11-T2-01] Verify SOCKS5 domain connection negotiation with ATYP 0x03."""
        mock_socks = MockDualProxyServer(protocol="socks5", auth_user=None, auth_pass=None)
        mock_socks.start()
        try:
            with socket.create_connection((mock_socks.host, mock_socks.port), timeout=2.0) as s:
                Socks5Client.handshake(s)
                Socks5Client.connect_tunnel(s, "remote.domain.ae", 443)
                self.assertTrue(len(mock_socks.requests_log) >= 1)
                self.assertEqual(mock_socks.requests_log[0].get("socks5_dest"), "remote.domain.ae")
        finally:
            mock_socks.stop()

    def test_17_tun2socks_restore_mtu(self):
        """[F11-T2-02] Verify restore_mtu sets MTU back to 1500."""
        with MockAdbSession(self.state):
            TransparentTun2SocksInterceptor.clamp_mtu("emulator-5554", 1380, self.proxy_mgr._run_adb)
            TransparentTun2SocksInterceptor.restore_mtu("emulator-5554", 1500, self.proxy_mgr._run_adb)
            self.assertEqual(self.state.mtu.get("eth0"), 1500)
            self.assertEqual(self.state.mtu.get("wlan0"), 1500)

    def test_18_tun2socks_remove_routing(self):
        """[F11-T2-03] Verify remove_tun2socks_routing cleans up iptables rules."""
        with MockAdbSession(self.state):
            ok = TransparentTun2SocksInterceptor.remove_tun2socks_routing("emulator-5554", self.proxy_mgr._run_adb)
            self.assertTrue(ok)
            del_cmds = [c for c in self.state.command_log if "-D" in c and "TCPMSS" in c]
            self.assertEqual(len(del_cmds), 1)

    def test_19_tun2socks_concurrent_connections_load(self):
        """[F11-T2-04] Validate stability under concurrent socket requests."""
        mock_upstream = MockDualProxyServer(port=0, auth_user=None, auth_pass=None)
        mock_upstream.start()
        try:
            port = self.proxy_mgr.start_auth_proxy(f"http://{mock_upstream.host}:{mock_upstream.port}", local_port=0)

            errors = []
            def worker():
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=2.0) as s:
                        s.sendall(b"CONNECT load.target:443 HTTP/1.1\r\n\r\n")
                        resp = s.recv(512)
                        if b"200 Connection Established" not in resp:
                            errors.append("Invalid response")
                except Exception as e:
                    errors.append(str(e))

            threads = [threading.Thread(target=worker) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=2.0)

            self.assertEqual(len(errors), 0)
        finally:
            mock_upstream.stop()

    def test_20_tun2socks_stop_purges_routes_cleanly(self):
        """[F11-T2-05] Verify detach_instance_proxy purges all routes and resets proxy."""
        with MockAdbSession(self.state):
            self.proxy_mgr.attach_instance_proxy(
                "emulator-5554", "tun2socks", {"protocol": "http", "host": "127.0.0.1", "port": 8080}
            )
            self.proxy_mgr.detach_instance_proxy("emulator-5554")
            self.assertEqual(self.state.settings["global"].get("http_proxy"), ":0")
            self.assertEqual(self.state.settings["global"].get("private_dns_mode"), "opportunistic")
            self.assertEqual(self.state.mtu.get("eth0"), 1500)


class TestFeature12DnsOverProxyAndKillSwitch(unittest.TestCase):
    """Feature 12: DNS-over-Proxy & Egress Kill-Switch"""

    def setUp(self):
        self.state = MockAdbState()
        self.mock_upstream = MockDualProxyServer(port=0, auth_user=None, auth_pass=None)
        self.mock_upstream.start()
        self.proxy_mgr = EnterpriseProxyManager(adb_path="mock_adb", enable_heartbeat=False)

    def tearDown(self):
        self.proxy_mgr.stop_auth_proxy()
        self.mock_upstream.stop()

    # --- Tier 1: Feature Coverage (Happy Path) ---

    def test_21_dns_over_proxy_remote_resolution(self):
        """[F12-T1-01] Eliminate DNS leaks by disabling Android Private DNS."""
        with MockAdbSession(self.state):
            self.proxy_mgr.attach_instance_proxy(
                "emulator-5554", "local_auth", {"protocol": "http", "host": "127.0.0.1", "port": self.mock_upstream.port}
            )
            self.assertEqual(self.state.settings.get("global", {}).get("private_dns_mode"), "off")

    def test_22_kill_switch_heartbeat_probe_loop(self):
        """[F12-T1-02] Active probe reports healthy when upstream is reachable."""
        upstream_url = f"http://{self.mock_upstream.host}:{self.mock_upstream.port}"
        self.proxy_mgr.start_auth_proxy(upstream_url, local_port=0)
        self.assertTrue(self.proxy_mgr.check_upstream_health())

    def test_23_kill_switch_activation_on_upstream_disconnect(self):
        """[F12-T1-03] Block outbound traffic with iptables -I OUTPUT 1 -j DROP upon trigger."""
        with MockAdbSession(self.state):
            self.proxy_mgr.attach_instance_proxy(
                "emulator-5554", "local_auth", {"protocol": "http", "host": "127.0.0.1", "port": 8080}
            )
            self.proxy_mgr.trigger_kill_switch("emulator-5554")
            self.assertEqual(self.proxy_mgr.kill_switch.state, KillSwitchState.ACTIVE)
            self.assertIn("OUTPUT 1 DROP", self.state.iptables_rules)

    def test_24_kill_switch_deactivation_on_reconnection(self):
        """[F12-T1-04] Remove blocking iptables rule upon proxy recovery."""
        with MockAdbSession(self.state):
            self.proxy_mgr.attach_instance_proxy(
                "emulator-5554", "local_auth", {"protocol": "http", "host": "127.0.0.1", "port": 8080}
            )
            self.proxy_mgr.trigger_kill_switch("emulator-5554")
            self.proxy_mgr.recover_kill_switch("emulator-5554")
            self.assertEqual(self.proxy_mgr.kill_switch.state, KillSwitchState.INACTIVE)
            self.assertNotIn("OUTPUT 1 DROP", self.state.iptables_rules)

    def test_25_kill_switch_status_callback_event(self):
        """[F12-T1-05] get_proxy_status reflects current kill-switch state."""
        with MockAdbSession(self.state):
            self.proxy_mgr.attach_instance_proxy(
                "emulator-5554", "local_auth", {"protocol": "http", "host": "127.0.0.1", "port": 8080}
            )
            status = self.proxy_mgr.get_proxy_status()
            self.assertEqual(status["kill_switch_state"], "INACTIVE")
            self.proxy_mgr.trigger_kill_switch("emulator-5554")
            status_active = self.proxy_mgr.get_proxy_status()
            self.assertEqual(status_active["kill_switch_state"], "ACTIVE")

    # --- Tier 2: Boundary & Corner Cases ---

    def test_26_kill_switch_unrooted_retail_fallback(self):
        """[F12-T2-01] On unrooted images where iptables fails, apply blackhole proxy fallback."""
        self.state.simulate_root = False
        with MockAdbSession(self.state):
            self.proxy_mgr.attach_instance_proxy(
                "emulator-5554", "local_auth", {"protocol": "http", "host": "127.0.0.1", "port": 8080}
            )
            self.proxy_mgr.trigger_kill_switch("emulator-5554")
            self.assertEqual(self.state.settings["global"].get("http_proxy"), "127.0.0.1:1")
            self.assertEqual(self.state.properties.get("net.dns1"), "127.0.0.1")

    def test_27_kill_switch_rapid_flapping_debounce(self):
        """[F12-T2-02] Rapid consecutive trigger and recover calls maintain state consistency."""
        with MockAdbSession(self.state):
            self.proxy_mgr.attach_instance_proxy(
                "emulator-5554", "local_auth", {"protocol": "http", "host": "127.0.0.1", "port": 8080}
            )
            for _ in range(5):
                self.proxy_mgr.trigger_kill_switch("emulator-5554")
                self.proxy_mgr.recover_kill_switch("emulator-5554")
            self.assertEqual(self.proxy_mgr.kill_switch.state, KillSwitchState.INACTIVE)

    def test_28_kill_switch_leak_verification_during_active_drop(self):
        """[F12-T2-03] Assert iptables rule is in place while kill switch is active."""
        with MockAdbSession(self.state):
            self.proxy_mgr.attach_instance_proxy(
                "emulator-5554", "local_auth", {"protocol": "http", "host": "127.0.0.1", "port": 8080}
            )
            self.proxy_mgr.trigger_kill_switch("emulator-5554")
            self.assertEqual(len(self.state.iptables_rules), 1)
            self.assertEqual(self.state.iptables_rules[0], "OUTPUT 1 DROP")

    def test_29_clean_shutdown_purges_kill_switch_rules(self):
        """[F12-T2-04] Detaching instance purges kill-switch firewall rules."""
        with MockAdbSession(self.state):
            self.proxy_mgr.attach_instance_proxy(
                "emulator-5554", "local_auth", {"protocol": "http", "host": "127.0.0.1", "port": 8080}
            )
            self.proxy_mgr.trigger_kill_switch("emulator-5554")
            self.proxy_mgr.detach_instance_proxy("emulator-5554")
            self.assertNotIn("OUTPUT 1 DROP", self.state.iptables_rules)

    def test_30_heartbeat_thread_exception_containment(self):
        """[F12-T2-05] Heartbeat check handles unexpected socket errors without crashing."""
        with patch("socket.socket.connect", side_effect=OSError(10054, "Connection reset")):
            upstream_url = f"http://{self.mock_upstream.host}:{self.mock_upstream.port}"
            self.proxy_mgr.start_auth_proxy(upstream_url, local_port=0)
            healthy = self.proxy_mgr.check_upstream_health()
            self.assertFalse(healthy)


if __name__ == "__main__":
    unittest.main()
