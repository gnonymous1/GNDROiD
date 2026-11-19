#!/usr/bin/env python3
"""
tests/test_sensor_console.py - Unit Tests for QEMU Console Client & GPX Route Player
===================================================================================

Validates:
1. QemuTelnetConsole Client:
   - Socket connection and Telnet protocol handshake
   - Authentication flow via token string and token file resolution
   - Protocol command generation:
     - geo fix <lon> <lat> <alt> <satellites>
     - sensor set <type> <values>
     - network delay / speed
     - power capacity / ac / status
     - gsm signal / voice
     - finger touch
2. Geodesic Mathematics:
   - Haversine distance calculation against known distances
   - Haversine bearing calculation across cardinal and diagonal headings
3. GPX Route Player:
   - XML parsing of <trkpt>, <rtept>, <wpt> with elevation and timestamps
   - Spatial route interpolation at configurable distance steps
   - Multi-threaded playback loop, speed acceleration, progress telemetry callbacks
   - Pause, resume, and stop controls
"""

import math
import os
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from nexus.sensor_console import (
    GpxRoutePlayer,
    QemuTelnetConsole,
    haversine_bearing,
    haversine_distance,
)


class MockTelnetServer:
    """Lightweight in-memory loopback server simulating QEMU Telnet console."""

    def __init__(self, expected_token: str = "test_token_123"):
        self.expected_token = expected_token
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.bind(("127.0.0.1", 0))
        self.server_sock.listen(1)
        self.port = self.server_sock.getsockname()[1]
        self.received_commands = []
        self.is_authenticated = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        try:
            client, _ = self.server_sock.accept()
            # Send greeting banner
            greeting = (
                "Android Console: Authentication required\r\n"
                "Android Console: type 'auth <auth_token>' to authenticate\r\n"
                "OK\r\n"
            )
            client.sendall(greeting.encode("utf-8"))

            buf = ""
            while True:
                data = client.recv(1024)
                if not data:
                    break
                buf += data.decode("utf-8", errors="replace")
                while "\r\n" in buf or "\n" in buf:
                    if "\r\n" in buf:
                        line, buf = buf.split("\r\n", 1)
                    else:
                        line, buf = buf.split("\n", 1)

                    line = line.strip()
                    if not line:
                        continue
                    self.received_commands.append(line)

                    if line.startswith("auth "):
                        token = line.split(" ", 1)[1]
                        if token == self.expected_token:
                            self.is_authenticated = True
                            client.sendall(b"OK\r\n")
                        else:
                            client.sendall(b"KO: invalid token\r\n")
                    elif line == "quit":
                        client.sendall(b"OK: bye\r\n")
                        client.close()
                        return
                    else:
                        if self.is_authenticated:
                            client.sendall(b"OK\r\n")
                        else:
                            client.sendall(b"KO: authentication required\r\n")
        except Exception:
            pass

    def close(self):
        try:
            self.server_sock.close()
        except Exception:
            pass


class TestQemuTelnetConsole(unittest.TestCase):
    """Tests the QEMU Telnet console client against a mock console server."""

    def setUp(self):
        self.server = MockTelnetServer(expected_token="secret_auth_token_2026")
        self.client = QemuTelnetConsole(
            host="127.0.0.1", port=self.server.port, timeout=2.0
        )

    def tearDown(self):
        self.client.close()
        self.server.close()

    def test_connect_and_authenticate(self):
        """Verifies initial connect, token reading, and authentication handshake."""
        # Connect client with explicit token
        self.client.connect()
        auth_ok = self.client.authenticate("secret_auth_token_2026")
        self.assertTrue(auth_ok)
        self.assertTrue(self.client.is_authenticated)

    def test_auth_token_file_resolution(self):
        """Verifies reading token from a specified auth_token_path."""
        with tempfile.NamedTemporaryFile("w", delete=False) as tf:
            tf.write("secret_auth_token_2026\n")
            token_path = tf.name

        try:
            client2 = QemuTelnetConsole(
                host="127.0.0.1",
                port=self.server.port,
                auth_token_path=token_path,
                timeout=2.0,
            )
            # connect() automatically resolves token and authenticates
            connected = client2.connect()
            self.assertTrue(connected)
            self.assertTrue(client2.is_authenticated)
            client2.close()
        finally:
            if os.path.exists(token_path):
                os.remove(token_path)

    def test_sensor_and_hardware_commands(self):
        """Verifies sending geo fix, sensor, network, and power commands."""
        self.client.connect()
        self.client.authenticate("secret_auth_token_2026")

        # Geo fix
        geo_ok = self.client.set_geo(longitude=55.2708, latitude=25.2048, altitude=12.5, satellites=12)
        self.assertTrue(geo_ok)
        self.assertIn("geo fix 55.270800 25.204800 12.5 12", self.server.received_commands)

        # Acceleration sensor
        acc_ok = self.client.set_sensor("acceleration", (0.0, 9.8066, 0.0))
        self.assertTrue(acc_ok)
        self.assertIn("sensor set acceleration 0.0000:9.8066:0.0000", self.server.received_commands)

        # Network delay and speed
        self.assertTrue(self.client.set_network_delay("lte"))
        self.assertIn("network delay lte", self.server.received_commands)
        self.assertTrue(self.client.set_network_speed("full"))
        self.assertIn("network speed full", self.server.received_commands)

        # Power commands
        self.assertTrue(self.client.set_power_capacity(85))
        self.assertIn("power capacity 85", self.server.received_commands)
        self.assertTrue(self.client.set_power_ac(True))
        self.assertIn("power ac on", self.server.received_commands)
        self.assertTrue(self.client.set_power_status("charging"))
        self.assertIn("power status charging", self.server.received_commands)

        # Telephony and fingerprint
        self.assertTrue(self.client.set_gsm_signal(4))
        self.assertIn("gsm signal 4", self.server.received_commands)
        self.assertTrue(self.client.finger_touch(1))
        self.assertIn("finger touch 1", self.server.received_commands)


class TestGeodesicMath(unittest.TestCase):
    """Tests Haversine distance and bearing algorithms."""

    def test_haversine_distance_known_coordinates(self):
        """
        Tests distance between Burj Khalifa (25.1972, 55.2744) and
        Dubai Frame (25.2345, 55.3003). Distance is approximately 4.8 km to 5.0 km.
        """
        dist = haversine_distance(25.1972, 55.2744, 25.2345, 55.3003)
        self.assertGreater(dist, 4700)
        self.assertLess(dist, 5100)

    def test_haversine_distance_zero(self):
        """Distance between the same coordinates is 0.0."""
        dist = haversine_distance(25.2048, 55.2708, 25.2048, 55.2708)
        self.assertAlmostEqual(dist, 0.0, places=2)

    def test_haversine_bearing_cardinal(self):
        """Tests bearings for North, South, East, and West."""
        # Due North
        b_north = haversine_bearing(0.0, 0.0, 1.0, 0.0)
        self.assertAlmostEqual(b_north, 0.0, delta=1.0)

        # Due East
        b_east = haversine_bearing(0.0, 0.0, 0.0, 1.0)
        self.assertAlmostEqual(b_east, 90.0, delta=1.0)

        # Due South
        b_south = haversine_bearing(1.0, 0.0, 0.0, 0.0)
        self.assertAlmostEqual(b_south, 180.0, delta=1.0)

        # Due West
        b_west = haversine_bearing(0.0, 1.0, 0.0, 0.0)
        self.assertAlmostEqual(b_west, 270.0, delta=1.0)


class TestGpxRoutePlayer(unittest.TestCase):
    """Tests GPX parsing, route interpolation, and simulated playback."""

    SAMPLE_GPX = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="GNDROiD" xmlns="http://www.topografix.com/GPX/1/1">
  <trk>
    <name>Dubai Marina Promenade</name>
    <trkseg>
      <trkpt lat="25.0800" lon="55.1400">
        <ele>5.0</ele>
        <time>2026-11-18T08:00:00Z</time>
      </trkpt>
      <trkpt lat="25.0810" lon="55.1410">
        <ele>5.5</ele>
        <time>2026-11-18T08:00:30Z</time>
      </trkpt>
      <trkpt lat="25.0820" lon="55.1420">
        <ele>6.0</ele>
        <time>2026-11-18T08:01:00Z</time>
      </trkpt>
    </trkseg>
  </trk>
</gpx>
"""

    def setUp(self):
        self.mock_console = MagicMock()
        self.mock_console.set_geo.return_value = True
        self.player = GpxRoutePlayer(console=self.mock_console)

    def tearDown(self):
        self.player.stop_playback()

    def test_gpx_parsing(self):
        """Verifies parsing coordinates, elevation, and segment distances."""
        points = self.player.load_gpx_content(self.SAMPLE_GPX)
        self.assertEqual(len(points), 3)
        self.assertAlmostEqual(points[0]["lat"], 25.0800)
        self.assertAlmostEqual(points[0]["lon"], 55.1400)
        self.assertAlmostEqual(points[0]["ele"], 5.0)

        self.assertTrue(self.player.total_distance_m > 0)

    def test_route_interpolation(self):
        """Verifies spatial interpolation adds waypoints at specified intervals."""
        self.player.load_gpx_content(self.SAMPLE_GPX)
        orig_count = len(self.player._raw_points)

        # Interpolate at 25-meter steps
        interpolated = self.player.interpolate_route(interval_meters=25.0)
        self.assertGreater(len(interpolated), orig_count)

    def test_playback_and_telemetry_callbacks(self):
        """Runs accelerated playback and collects progress telemetry callbacks."""
        self.player.load_gpx_content(self.SAMPLE_GPX)

        telemetry_records = []

        def on_telemetry(data):
            telemetry_records.append(data)

        # Start playback at high speed (50x)
        self.player.start_playback(
            speed_multiplier=50.0,
            loop=False,
            tick_interval=0.01,
            callback=on_telemetry,
        )

        # Wait for completion (3 points at 0.01s takes ~0.05s)
        time.sleep(0.15)
        self.player.stop_playback()

        self.assertFalse(self.player.is_playing)
        self.assertGreater(len(telemetry_records), 0)

        # Verify telemetry structure
        t0 = telemetry_records[0]
        self.assertIn("lat", t0)
        self.assertIn("lon", t0)
        self.assertIn("bearing", t0)
        self.assertIn("speed_kmh", t0)
        self.assertIn("progress_percent", t0)

        # Verify console received geo fixes
        self.assertTrue(self.mock_console.set_geo.called)

    def test_playback_pause_and_resume(self):
        """Verifies pause and resume controls."""
        self.player.load_gpx_content(self.SAMPLE_GPX)
        self.player.start_playback(speed_multiplier=1.0, tick_interval=0.05)

        self.assertTrue(self.player.is_playing)
        self.player.pause_playback()
        self.assertTrue(self.player.is_paused)

        self.player.resume_playback()
        self.assertFalse(self.player.is_paused)

        self.player.stop_playback()
        self.assertFalse(self.player.is_playing)


if __name__ == "__main__":
    unittest.main()
