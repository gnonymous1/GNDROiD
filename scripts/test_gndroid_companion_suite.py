#!/usr/bin/env python3
"""
scripts/test_gndroid_companion_suite.py
=======================================
Comprehensive Test Suite for GNDROiD Link Companion App, Subnet Radar,
Remote Control Engine, and Unbreakable Watchdog.
"""

import os
import sys
import time
import json
import socket
import unittest
import threading
import http.server
import socketserver
from unittest.mock import MagicMock, patch

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from nexus.gndroid_companion_client import (
    GNDroidCompanionClient,
    GNDroidSubnetRadar,
    GNDroidConnectionWatchdog,
    DEFAULT_PORT,
    BEACON_PORT
)


class MockCompanionServer(http.server.BaseHTTPRequestHandler):
    """Mock HTTP server simulating com.gndroid.companion on device."""

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == "/ping":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"pong": True, "timestamp": time.time()}).encode("utf-8"))
        elif self.path in ("/status", "/api/v1/status"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            status_data = {
                "status": "online",
                "version": "2.3.0",
                "device_name": "Samsung Galaxy S24 Ultra",
                "model": "SM-S928B",
                "battery": 88,
                "charging": True,
                "screen_on": True,
                "accessibility_active": True
            }
            self.wfile.write(json.dumps(status_data).encode("utf-8"))
        elif self.path == "/api/v1/clipboard":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"text": "GNDROiD Mock Clipboard"}).encode("utf-8"))
        elif self.path == "/api/v1/apps":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            apps_data = {
                "apps": [
                    {"name": "Chrome", "package": "com.android.chrome", "system": False},
                    {"name": "YouTube", "package": "com.google.android.youtube", "system": False}
                ],
                "count": 2
            }
            self.wfile.write(json.dumps(apps_data).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
        data = {}
        try:
            data = json.loads(body)
        except Exception:
            pass

        if self.path == "/api/v1/control":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "action": data.get("action")}).encode("utf-8"))
        elif self.path == "/api/v1/clipboard":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True}).encode("utf-8"))
        elif self.path == "/api/v1/launch_app":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "package": data.get("package")}).encode("utf-8"))
        elif self.path == "/api/v1/upload":
            fname = self.headers.get("X-Filename", "mock_upload.dat")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "path": f"/sdcard/Download/{fname}", "size": content_len}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()


class TestGNDroidCompanionSuite(unittest.TestCase):
    """Unit and Integration tests for GNDROiD Companion ecosystem."""

    @classmethod
    def setUpClass(cls):
        # Start a local mock server on an ephemeral port
        cls.mock_port = 54321
        cls.server = socketserver.TCPServer(("127.0.0.1", cls.mock_port), MockCompanionServer)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.client = GNDroidCompanionClient(host="127.0.0.1", port=self.mock_port, timeout=1.0)

    # 1. APK Distribution & Integrity Tests
    def test_companion_apk_distribution(self):
        """Verifies that GNDROiD_Companion.apk is built and present across all target locations."""
        locations = [
            os.path.join(BASE_DIR, "nexus", "GNDROiD_Companion.apk"),
            os.path.join(BASE_DIR, "tools", "GNDROiD_Companion.apk"),
            os.path.join(BASE_DIR, "dist", "gndroid", "nexus", "GNDROiD_Companion.apk"),
            os.path.join(BASE_DIR, "dist", "gndroid", "tools", "GNDROiD_Companion.apk"),
        ]
        for p in locations:
            self.assertTrue(os.path.exists(p), f"APK missing at {p}")
            self.assertGreater(os.path.getsize(p), 10000, f"APK file size too small at {p}")

    def test_legacy_apk_alias_preserved(self):
        """Ensures backward compatibility alias NexusAI_Mobile_Client.apk is maintained."""
        legacy_apk = os.path.join(BASE_DIR, "nexus", "NexusAI_Mobile_Client.apk")
        self.assertTrue(os.path.exists(legacy_apk), "Legacy NexusAI_Mobile_Client.apk missing")
        self.assertGreater(os.path.getsize(legacy_apk), 10000)

    # 2. Companion Client HTTP/REST Endpoint Tests
    def test_client_ping(self):
        """Tests sub-second heartbeat ping."""
        self.assertTrue(self.client.ping())

    def test_client_status(self):
        """Tests live status retrieval."""
        st = self.client.get_status()
        self.assertEqual(st.get("status"), "online")
        self.assertEqual(st.get("version"), "2.3.0")
        self.assertEqual(st.get("model"), "SM-S928B")
        self.assertEqual(st.get("battery"), 88)
        self.assertTrue(st.get("accessibility_active"))

    def test_client_remote_control(self):
        """Tests remote control navigation and hardware commands."""
        self.assertTrue(self.client.nav_back())
        self.assertTrue(self.client.nav_home())
        self.assertTrue(self.client.nav_recents())
        self.assertTrue(self.client.screen_wake())
        self.assertTrue(self.client.screen_lock())
        self.assertTrue(self.client.volume_up())
        self.assertTrue(self.client.volume_down())
        self.assertTrue(self.client.volume_mute())
        self.assertTrue(self.client.tap(500, 800))
        self.assertTrue(self.client.swipe(100, 200, 300, 400, 250))

    def test_client_clipboard_sync(self):
        """Tests bi-directional clipboard sync."""
        text = self.client.get_clipboard()
        self.assertEqual(text, "GNDROiD Mock Clipboard")
        self.assertTrue(self.client.set_clipboard("New Clipboard Content"))

    def test_client_list_and_launch_apps(self):
        """Tests remote app drawer listing and package launch."""
        apps = self.client.list_apps()
        self.assertEqual(len(apps), 2)
        self.assertEqual(apps[0]["package"], "com.android.chrome")
        self.assertTrue(self.client.launch_app("com.android.chrome"))

    def test_client_file_upload(self):
        """Tests line-speed direct LAN file upload."""
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"Test upload payload for GNDROiD Companion")
            temp_path = f.name
        try:
            ok, remote_path = self.client.upload_file(temp_path, "sample.txt")
            self.assertTrue(ok)
            self.assertEqual(remote_path, "/sdcard/Download/sample.txt")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    # 3. Subnet Radar Beacon Discovery Tests
    def test_subnet_radar_discovery(self):
        """Tests that GNDroidSubnetRadar receives UDP beacon and tracks device."""
        radar = GNDroidSubnetRadar(port=58888)
        radar.start()
        try:
            # Emulate incoming UDP beacon
            beacon_data = {
                "magic": "GNDROID_BEACON",
                "version": "2.3.0",
                "device_name": "Google Pixel 8 Pro",
                "model": "Pixel 8 Pro",
                "battery": 95,
                "charging": False,
                "port": 51888
            }
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.sendto(json.dumps(beacon_data).encode("utf-8"), ("127.0.0.1", 58888))
            s.close()

            time.sleep(0.3)
            devs = radar.get_devices()
            self.assertGreaterEqual(len(devs), 1)
            found = False
            for d in devs:
                if d.get("model") == "Pixel 8 Pro":
                    found = True
                    self.assertEqual(d.get("battery"), 95)
                    self.assertEqual(d.get("port"), 51888)
            self.assertTrue(found, "Discovered device not matched in radar registry")
        finally:
            radar.stop()

    # 4. Watchdog Resilience & State Change Tests
    def test_watchdog_state_transitions(self):
        """Tests that connection watchdog tracks connectivity state changes."""
        watchdog = GNDroidConnectionWatchdog(client=self.client, interval_sec=0.2)
        state_events = []

        def on_change(connected, msg):
            state_events.append((connected, msg))

        watchdog.on_state_changed = on_change
        watchdog.start()
        time.sleep(0.5)
        watchdog.stop()

        self.assertTrue(watchdog.is_connected)
        self.assertEqual(watchdog.packet_loss_count, 0)
        self.assertGreaterEqual(len(state_events), 1)
        self.assertTrue(state_events[0][0])

    # 5. GNDroidCompanionManager Integration Tests
    def test_companion_manager_apk_path(self):
        """Verifies that GNDroidCompanionManager resolves the companion APK correctly."""
        import gndroid
        apk_p = gndroid.NexusCompanionManager.get_bundled_apk_path()
        self.assertTrue(os.path.exists(apk_p))
        self.assertTrue(apk_p.endswith(".apk"))
        # Verify alias
        self.assertEqual(gndroid.GNDroidCompanionManager, gndroid.NexusCompanionManager)

    def test_companion_manager_grant_full_phone_permissions(self):
        """Tests scripted ADB permission, Doze whitelist, and accessibility grants."""
        import gndroid
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=b"Success", stderr=b"")
            ok, msg = gndroid.NexusCompanionManager.grant_full_phone_permissions("test_serial")
            self.assertTrue(ok)
            self.assertIn("Port 5555 Wireless ADB Enabled", msg)
            self.assertIn("Background Accessibility & Overlay Permissions Granted", msg)
            self.assertIn("Persistent Background Service & High-Perf Wi-Fi Lock Activated", msg)

    # 6. GUI Tab & Card Initializations
    def test_gui_lan_cards_initialized(self):
        """Verifies that setup_tab_lan creates all remote buttons and stream controls."""
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(sys.argv)
        import gndroid
        with patch.object(gndroid.GNDroidADBFixerDialog, "start_radar_and_qr_services", return_value=None), \
             patch.object(gndroid.GNDroidADBFixerDialog, "refresh_all_diagnostics", return_value=None):
            dlg = gndroid.GNDroidADBFixerDialog()
            try:
                # Check Card 5 Remote Toolbar buttons
                self.assertTrue(hasattr(dlg, "btn_rem_wake"))
                self.assertTrue(hasattr(dlg, "btn_rem_lock"))
                self.assertTrue(hasattr(dlg, "btn_rem_vol_up"))
                self.assertTrue(hasattr(dlg, "btn_rem_vol_down"))
                self.assertTrue(hasattr(dlg, "btn_rem_vol_mute"))
                self.assertTrue(hasattr(dlg, "btn_rem_back"))
                self.assertTrue(hasattr(dlg, "btn_rem_home"))
                self.assertTrue(hasattr(dlg, "btn_rem_recents"))
                self.assertTrue(hasattr(dlg, "btn_rem_notif"))
                self.assertTrue(hasattr(dlg, "btn_rem_qs"))
                self.assertTrue(hasattr(dlg, "btn_rem_clip"))
                self.assertTrue(hasattr(dlg, "btn_rem_push"))
                self.assertTrue(hasattr(dlg, "btn_rem_apps"))

                # Check Card 6 Stream Setting controls
                self.assertTrue(hasattr(dlg, "combo_stream_codec"))
                self.assertTrue(hasattr(dlg, "combo_stream_fps"))
                self.assertTrue(hasattr(dlg, "combo_stream_bitrate"))
                self.assertTrue(hasattr(dlg, "chk_stream_screen_off"))

                self.assertGreaterEqual(dlg.combo_stream_codec.count(), 3)
                self.assertGreaterEqual(dlg.combo_stream_fps.count(), 4)
                self.assertGreaterEqual(dlg.combo_stream_bitrate.count(), 5)
            finally:
                dlg.close()


if __name__ == "__main__":
    unittest.main()
