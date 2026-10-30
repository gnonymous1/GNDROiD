"""
scripts/test_wireless_mirror.py
===============================
Comprehensive verification suite for nexus/wireless_mirror.py:
  1. Argument construction (--turn-screen-off logic, audio opus vs --no-audio, performance flags).
  2. TCP socket verification (<1.5s timeout, live port vs unbound port).
  3. Fallback behavior (automatic seamless restart with --no-audio upon audio/reset error in <2.0s).
  4. ADB Doctor get_lan_diagnostic_info helper (port 5555, host IP/subnet, mDNS state).
"""

import os
import sys
import time
import socket
import unittest
import threading
import subprocess
from unittest.mock import patch, MagicMock

# Ensure workspace root is in sys.path
WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WORKSPACE_DIR not in sys.path:
    sys.path.insert(0, WORKSPACE_DIR)

from nexus.wireless_mirror import (
    WirelessMirrorManager,
    get_lan_diagnostic_info,
    find_scrcpy_binary,
    find_adb_binary,
)


class TestWirelessMirrorManager(unittest.TestCase):

    def setUp(self):
        self.manager = WirelessMirrorManager()

    # -------------------------------------------------------------------------
    # 1. Argument Construction Tests
    # -------------------------------------------------------------------------
    def test_build_scrcpy_command_physical_usb(self):
        """Physical USB phone: MUST include --turn-screen-off, 60fps, h264, opus, stay-awake."""
        serial = "R58M34ABCD"
        cmd = self.manager.build_scrcpy_command(
            serial=serial,
            is_emulator=False,
            is_wireless=False,
            title="My Phone",
            enable_audio=True
        )

        self.assertIn("-s", cmd)
        self.assertEqual(cmd[cmd.index("-s") + 1], serial)
        self.assertIn("--window-title=My Phone", cmd)
        self.assertIn("--video-codec=h264", cmd)
        self.assertIn("--max-fps=60", cmd)
        self.assertIn("--stay-awake", cmd)
        self.assertIn("--audio-codec=opus", cmd)
        self.assertNotIn("--no-audio", cmd)
        # CRITICAL: Physical USB device MUST have --turn-screen-off
        self.assertIn("--turn-screen-off", cmd)

    def test_build_scrcpy_command_wireless_device(self):
        """Wireless phone: MUST NEVER include --turn-screen-off to prevent black screen lockouts."""
        serial = "192.168.100.25:5555"
        cmd = self.manager.build_scrcpy_command(
            serial=serial,
            is_emulator=False,
            is_wireless=True,
            enable_audio=True
        )

        self.assertIn("-s", cmd)
        self.assertEqual(cmd[cmd.index("-s") + 1], serial)
        self.assertIn(f"--window-title=GNDROiD - {serial}", cmd)
        self.assertIn("--video-codec=h264", cmd)
        self.assertIn("--max-fps=60", cmd)
        self.assertIn("--stay-awake", cmd)
        self.assertIn("--audio-codec=opus", cmd)
        # CRITICAL: Wireless phone MUST NEVER have --turn-screen-off
        self.assertNotIn("--turn-screen-off", cmd)

    def test_build_scrcpy_command_emulator(self):
        """Emulator instance: MUST NEVER include --turn-screen-off to prevent black screen lockouts."""
        serial = "emulator-5554"
        cmd = self.manager.build_scrcpy_command(
            serial=serial,
            is_emulator=True,
            is_wireless=False,
            enable_audio=True
        )

        self.assertIn("-s", cmd)
        self.assertEqual(cmd[cmd.index("-s") + 1], serial)
        self.assertIn("--video-codec=h264", cmd)
        self.assertIn("--max-fps=60", cmd)
        self.assertIn("--stay-awake", cmd)
        self.assertIn("--audio-codec=opus", cmd)
        # CRITICAL: Emulator MUST NEVER have --turn-screen-off
        self.assertNotIn("--turn-screen-off", cmd)

    def test_build_scrcpy_command_audio_safety(self):
        """Audio safety: enable_audio=False MUST include --no-audio and omit --audio-codec=opus."""
        cmd = self.manager.build_scrcpy_command(
            serial="192.168.100.25:5555",
            is_emulator=False,
            is_wireless=True,
            enable_audio=False
        )

        self.assertIn("--no-audio", cmd)
        self.assertNotIn("--audio-codec=opus", cmd)
        self.assertNotIn("--turn-screen-off", cmd)

    def test_build_scrcpy_command_implicit_inference(self):
        """If caller leaves is_wireless/is_emulator at default False, infer safely from serial."""
        # IP:Port pattern inferred as wireless -> no screen off
        cmd_lan = WirelessMirrorManager.build_scrcpy_command(serial="192.168.1.50:5555")
        self.assertNotIn("--turn-screen-off", cmd_lan)

        # emulator- pattern inferred as emulator -> no screen off
        cmd_emu = WirelessMirrorManager.build_scrcpy_command(serial="emulator-5556")
        self.assertNotIn("--turn-screen-off", cmd_emu)

        # Raw USB serial inferred as physical USB -> includes screen off
        cmd_usb = WirelessMirrorManager.build_scrcpy_command(serial="ZY2234ABCD")
        self.assertIn("--turn-screen-off", cmd_usb)

    # -------------------------------------------------------------------------
    # 2. TCP Socket Verification Tests
    # -------------------------------------------------------------------------
    def test_validate_wireless_connection_live_port(self):
        """Validates that an active listening port returns True within 1.5s."""
        # Bind an ephemeral local TCP port
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]

        try:
            start_t = time.time()
            is_connected = WirelessMirrorManager.validate_wireless_connection(f"127.0.0.1:{port}", timeout=1.5)
            elapsed = time.time() - start_t

            self.assertTrue(is_connected, "Expected live port to validate as connected")
            self.assertLess(elapsed, 1.5, "Validation took longer than 1.5s")
        finally:
            srv.close()

    def test_validate_wireless_connection_unbound_port(self):
        """Validates that an unbound/closed port returns False within 1.5s."""
        # Pick an unused port by briefly binding and immediately closing it
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.bind(("127.0.0.1", 0))
        port = srv.getsockname()[1]
        srv.close()

        start_t = time.time()
        is_connected = WirelessMirrorManager.validate_wireless_connection(f"127.0.0.1:{port}", timeout=0.8)
        elapsed = time.time() - start_t

        self.assertFalse(is_connected, "Expected unbound port to return False")
        self.assertLess(elapsed, 1.5, "Validation took longer than 1.5s")

    def test_validate_wireless_connection_invalid_inputs(self):
        """Validates that invalid IP, malformed port, or empty inputs return False gracefully."""
        self.assertFalse(WirelessMirrorManager.validate_wireless_connection(""))
        self.assertFalse(WirelessMirrorManager.validate_wireless_connection(None))
        self.assertFalse(WirelessMirrorManager.validate_wireless_connection("invalid:port:abc"))
        self.assertFalse(WirelessMirrorManager.validate_wireless_connection("192.168.1.1:999999"))

    # -------------------------------------------------------------------------
    # 3. Fallback Behavior Tests
    # -------------------------------------------------------------------------
    def test_launch_resilient_mirror_audio_error_fallback(self):
        """
        When scrcpy terminates in under 2 seconds with an audio error,
        it must automatically relaunch with --no-audio as a seamless fallback.
        """
        mock_proc_fail = MagicMock()
        mock_proc_fail.poll.side_effect = [None, 1]  # Exits quickly
        mock_proc_fail.returncode = 1
        mock_proc_fail.stderr.read.return_value = b"ERROR: Audio initialization failed: opus encoder not supported\n"

        mock_proc_fallback = MagicMock()
        mock_proc_fallback.poll.return_value = None  # Keeps running
        mock_proc_fallback.returncode = None

        launched_cmds = []

        def mock_spawn(cmd, creation_flags):
            launched_cmds.append(cmd)
            if len(launched_cmds) == 1:
                return mock_proc_fail
            return mock_proc_fallback

        manager = WirelessMirrorManager(scrcpy_bin="scrcpy")

        fallback_received = []
        with patch.object(manager, "_spawn_scrcpy", side_effect=mock_spawn):
            final_proc = manager.launch_resilient_mirror(
                serial="192.168.100.25:5555",
                parent=None,
                enable_audio=True,
                sync_probe=True,
                probe_timeout=2.0,
                on_fallback=lambda cmd: fallback_received.append(cmd)
            )

        self.assertEqual(len(launched_cmds), 2, "Expected 2 launches: initial attempt + fallback")
        # Initial attempt had audio opus
        self.assertIn("--audio-codec=opus", launched_cmds[0])
        self.assertNotIn("--no-audio", launched_cmds[0])

        # Second attempt MUST have --no-audio
        self.assertIn("--no-audio", launched_cmds[1])
        self.assertNotIn("--audio-codec=opus", launched_cmds[1])

        # Verify fallback occurred flag
        self.assertTrue(manager.fallback_occurred)
        self.assertEqual(final_proc, mock_proc_fallback)

    def test_launch_resilient_mirror_connection_reset_fallback(self):
        """
        When scrcpy terminates in under 2 seconds with a connection reset error,
        it must automatically restart with --no-audio as fallback.
        """
        mock_proc_fail = MagicMock()
        mock_proc_fail.poll.side_effect = [None, 1]
        mock_proc_fail.returncode = 1
        mock_proc_fail.stderr.read.return_value = b"ERROR: Connection reset by peer: demuxer audio\n"

        mock_proc_fallback = MagicMock()
        mock_proc_fallback.poll.return_value = None

        launched_cmds = []

        def mock_spawn(cmd, creation_flags):
            launched_cmds.append(cmd)
            return mock_proc_fail if len(launched_cmds) == 1 else mock_proc_fallback

        manager = WirelessMirrorManager(scrcpy_bin="scrcpy")

        with patch.object(manager, "_spawn_scrcpy", side_effect=mock_spawn):
            final_proc = manager.launch_resilient_mirror(
                serial="192.168.100.50:5555",
                sync_probe=True,
                probe_timeout=2.0
            )

        self.assertEqual(len(launched_cmds), 2)
        self.assertIn("--no-audio", launched_cmds[1])
        self.assertTrue(manager.fallback_occurred)

    def test_launch_resilient_mirror_stable_session_no_fallback(self):
        """When scrcpy runs stably beyond the probe window, fallback MUST NOT trigger."""
        mock_proc_stable = MagicMock()
        mock_proc_stable.poll.return_value = None  # Stably running

        manager = WirelessMirrorManager(scrcpy_bin="scrcpy")

        with patch.object(manager, "_spawn_scrcpy", return_value=mock_proc_stable):
            final_proc = manager.launch_resilient_mirror(
                serial="192.168.100.25:5555",
                sync_probe=True,
                probe_timeout=0.2  # Fast probe for test
            )

        self.assertEqual(final_proc, mock_proc_stable)
        self.assertFalse(manager.fallback_occurred)
        self.assertIn("--audio-codec=opus", manager.last_command)

    # -------------------------------------------------------------------------
    # 4. ADB Doctor get_lan_diagnostic_info Tests
    # -------------------------------------------------------------------------
    def test_get_lan_diagnostic_info_structure(self):
        """Validates that get_lan_diagnostic_info returns complete expected keys and types."""
        diag = get_lan_diagnostic_info()

        # Check top-level keys
        self.assertIn("port_5555_listening", diag)
        self.assertIn("host_ip", diag)
        self.assertIn("subnet_prefix", diag)
        self.assertIn("mdns_supported", diag)
        self.assertIn("mdns_pairing_active", diag)
        self.assertIn("mdns_services", diag)
        self.assertIn("summary", diag)

        # Check types
        self.assertIsInstance(diag["port_5555_listening"], bool)
        self.assertIsInstance(diag["host_ip"], str)
        self.assertIsInstance(diag["subnet_prefix"], str)
        self.assertIsInstance(diag["mdns_supported"], bool)
        self.assertIsInstance(diag["mdns_pairing_active"], bool)
        self.assertIsInstance(diag["mdns_services"], list)
        self.assertIsInstance(diag["summary"], str)

        # Check nested structures
        self.assertIn("port_5555", diag)
        self.assertIn("wifi_subnet", diag)
        self.assertIn("mdns", diag)

        print(f"\n[Diagnostic Test Output] Summary: {diag['summary']}")
        print(f"[Diagnostic Test Output] Host IP: {diag['host_ip']}, Subnet: {diag['subnet_prefix']}")
        print(f"[Diagnostic Test Output] mDNS Supported: {diag['mdns_supported']}, Services Count: {len(diag['mdns_services'])}")


if __name__ == "__main__":
    print("=" * 70)
    print("RUNNING GNDROiD WIRELESS MIRROR & ADB DOCTOR TEST SUITE")
    print("=" * 70)
    unittest.main(verbosity=2)
