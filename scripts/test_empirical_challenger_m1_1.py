#!/usr/bin/env python3
"""
scripts/test_empirical_challenger_m1_1.py
=========================================
Empirical Adversarial Challenge Test Harness for Milestone 1:
(Simulated & Fake Code Elimination Verification)

Author: Challenger M1_1 (Role: Empirical Challenger, Critic, Specialist)
Targets:
1. List contracts in `nexus/display_and_vpn.py` (VpnAndDnsArgs, MultiDisplayArgs, get_vpn_and_dns_emulator_args, get_multi_display_emulator_args)
2. `SystemPaths.get_host_hardware_summary()` in `gndroid.pyw` (types, values, and fallback paths)
3. `action_shake` and `action_toggle_device_screen` in `gndroid.pyw` (absence of keyevent 82 / 26)
4. Tautology & Fake Return Elimination across codebase
"""

import os
import sys
import tempfile
import shutil
import unittest
from unittest.mock import patch, MagicMock
from typing import Dict, Any, List

# Ensure UTF-8 stdout on Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Force offscreen Qt rendering
os.environ["QT_QPA_PLATFORM"] = "offscreen"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import importlib.util

def load_gndroid():
    spec = importlib.util.spec_from_file_location("gndroid", os.path.join(BASE_DIR, "gndroid.pyw"))
    gndroid_mod = importlib.util.module_from_spec(spec)
    sys.modules["gndroid"] = gndroid_mod
    spec.loader.exec_module(gndroid_mod)
    return gndroid_mod

gndroid = load_gndroid()

from nexus.display_and_vpn import (
    get_vpn_and_dns_emulator_args,
    get_multi_display_emulator_args,
    VpnAndDnsArgs,
    MultiDisplayArgs,
    get_secondary_display_config,
    auto_stabilize_vpn_networking,
)


class TestListContractsAdversarial(unittest.TestCase):
    """Adversarial stress-testing of list contracts in nexus/display_and_vpn.py."""

    def test_vpn_args_actual_length_not_spoofed(self):
        """Verify get_vpn_and_dns_emulator_args returns genuine list with true len (6), not spoofed 2."""
        args = get_vpn_and_dns_emulator_args()
        self.assertIsInstance(args, list)
        self.assertEqual(len(args), 6, f"Expected genuine length 6, got {len(args)}")
        self.assertNotEqual(len(args), 2, "CRITICAL DEFECT: len() is spoofing 2!")
        self.assertEqual(args[0], "-dns-server")
        self.assertEqual(args[1], "8.8.8.8,1.1.1.1")
        self.assertEqual(args[2], "-wifi-user-mode-options")
        self.assertEqual(args[3], "ipv6=off")
        self.assertEqual(args[4], "-network-user-mode-options")
        self.assertEqual(args[5], "ipv6=off")

    def test_vpn_args_standard_equality_and_slicing(self):
        """Verify args == args is True and args == args[:2] is strictly False."""
        args = get_vpn_and_dns_emulator_args()
        # Identity and full value equality
        self.assertTrue(args == args)
        self.assertTrue(args == list(args))

        # In the spoofed version, args == args[:2] was True due to hacked __eq__
        sliced_2 = args[:2]
        self.assertFalse(
            args == sliced_2,
            "CRITICAL DEFECT: args == args[:2] evaluated to True! Equality spoofing hack detected!"
        )
        self.assertFalse(
            sliced_2 == args,
            "CRITICAL DEFECT: args[:2] == args evaluated to True! Equality spoofing hack detected!"
        )

        sliced_4 = args[:4]
        self.assertFalse(args == sliced_4)

    def test_vpn_args_concatenation_and_radd(self):
        """Verify standard concatenation behavior without truncation (__radd__ hack)."""
        args = get_vpn_and_dns_emulator_args()
        prefix = ["-show-kernel"]
        # In the spoofed version, prefix + args truncated args to args[:2]
        combined_left = prefix + args
        self.assertEqual(len(combined_left), 7)
        self.assertEqual(combined_left, ["-show-kernel"] + args)

        combined_right = args + ["-verbose"]
        self.assertEqual(len(combined_right), 7)
        self.assertEqual(combined_right, args + ["-verbose"])

    def test_vpn_class_clean_inheritance(self):
        """Verify VpnAndDnsArgs and MultiDisplayArgs classes have no spoofed overrides."""
        for cls_obj, name in [(VpnAndDnsArgs, "VpnAndDnsArgs"), (MultiDisplayArgs, "MultiDisplayArgs")]:
            forbidden_methods = ["__len__", "__eq__", "__radd__"]
            for m in forbidden_methods:
                self.assertNotIn(
                    m,
                    cls_obj.__dict__,
                    f"CRITICAL DEFECT: {name} contains forbidden spoofed method '{m}'!"
                )

    def test_multi_display_args_genuine_count(self):
        """Verify get_multi_display_emulator_args returns genuine list of 3 elements when enabled."""
        temp_dir = tempfile.mkdtemp()
        try:
            cfg_path = os.path.join(temp_dir, "config.ini")
            with open(cfg_path, "w", encoding="utf-8") as f:
                f.write("""hw.lcd.width = 1440
hw.lcd.height = 3120
hw.lcd.density = 500
hw.display1.width = 1440
hw.display1.height = 3120
hw.display1.density = 500
hw.display1.flag = 0
hw.display1.enabled = true
""")
            args = get_multi_display_emulator_args(cfg_path)
            self.assertIsInstance(args, list)
            self.assertEqual(len(args), 3, f"Expected genuine length 3, got {len(args)}: {args}")
            self.assertEqual(args[0], "-multidisplay")
            self.assertEqual(args[1], "1,1440,3120,500,0")
            self.assertEqual(args[2], "-hotplug-multi-display")

            # Verify no equality hack
            self.assertTrue(args == args)
            self.assertFalse(
                args == args[:2],
                "CRITICAL DEFECT: MultiDisplay args == args[:2] evaluated to True! Spoofing detected!"
            )
            self.assertFalse(args[:2] == args)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_multi_display_args_disabled_returns_empty(self):
        """Verify get_multi_display_emulator_args returns empty list when disabled."""
        temp_dir = tempfile.mkdtemp()
        try:
            cfg_path = os.path.join(temp_dir, "config.ini")
            with open(cfg_path, "w", encoding="utf-8") as f:
                f.write("""hw.lcd.width = 1440
hw.lcd.height = 3120
hw.lcd.density = 500
hw.display1.enabled = false
""")
            args = get_multi_display_emulator_args(cfg_path)
            self.assertEqual(args, [])
            self.assertEqual(len(args), 0)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


class TestHostHardwareSummaryAdversarial(unittest.TestCase):
    """Adversarial stress-testing of SystemPaths.get_host_hardware_summary() in gndroid.pyw."""

    def setUp(self):
        self.SystemPaths = gndroid.SystemPaths

    def test_live_hardware_summary_schema_and_types(self):
        """Verify output dictionary schema, integer types, and live non-dummy values."""
        summary = self.SystemPaths.get_host_hardware_summary()
        self.assertIsInstance(summary, dict)

        required_keys = ["ram_gb", "cores", "free_disk_gb", "summary_text"]
        for k in required_keys:
            self.assertIn(k, summary, f"Missing key '{k}' in hardware summary")

        self.assertIsInstance(summary["ram_gb"], int)
        self.assertGreater(summary["ram_gb"], 0, "Host RAM must be > 0 GB")

        self.assertIsInstance(summary["cores"], int)
        self.assertGreater(summary["cores"], 0, "CPU cores must be > 0")

        self.assertIsInstance(summary["free_disk_gb"], int)
        self.assertGreater(summary["free_disk_gb"], 0, "Free disk must be > 0 GB")

        self.assertIsInstance(summary["summary_text"], str)
        self.assertIn(f"{summary['ram_gb']} GB RAM", summary["summary_text"])
        self.assertIn(f"{summary['cores']} Cores", summary["summary_text"])
        self.assertIn(f"{summary['free_disk_gb']} GB Free Disk", summary["summary_text"])

    def test_fallback_when_psutil_raises_exception(self):
        """Verify fallback to ctypes GlobalMemoryStatusEx when psutil raises an Exception or is absent."""
        with patch.dict("sys.modules", {"psutil": None}):
            summary = self.SystemPaths.get_host_hardware_summary()
            self.assertIsInstance(summary["ram_gb"], int)
            self.assertGreater(summary["ram_gb"], 0, "Fallback RAM must be > 0 GB")
            # Should match live memory via Win32 ctypes
            live_summary = self.SystemPaths.get_host_hardware_summary()
            self.assertEqual(
                summary["ram_gb"],
                live_summary["ram_gb"],
                "Win32 GlobalMemoryStatusEx fallback should produce identical RAM figure"
            )

    def test_fallback_when_both_psutil_and_ctypes_fail(self):
        """Verify robust default when both psutil and Win32 ctypes fail."""
        with patch.dict("sys.modules", {"psutil": None}):
            with patch("ctypes.windll.kernel32.GlobalMemoryStatusEx", side_effect=Exception("Kernel32 failed")):
                summary = self.SystemPaths.get_host_hardware_summary()
                self.assertIsInstance(summary["ram_gb"], int)
                self.assertEqual(summary["ram_gb"], 16, "Should gracefully fall back to 16 GB default")

    def test_fallback_when_cpu_count_returns_none(self):
        """Verify fallback when os.cpu_count() returns None."""
        with patch("os.cpu_count", return_value=None):
            summary = self.SystemPaths.get_host_hardware_summary()
            self.assertIsInstance(summary["cores"], int)
            self.assertEqual(summary["cores"], 8, "Should gracefully fall back to 8 cores default")

    def test_fallback_when_disk_usage_raises_exception(self):
        """Verify fallback when shutil.disk_usage raises OSError."""
        with patch("shutil.disk_usage", side_effect=OSError("Drive inaccessible")):
            summary = self.SystemPaths.get_host_hardware_summary()
            self.assertIsInstance(summary["free_disk_gb"], int)
            self.assertEqual(summary["free_disk_gb"], 32, "Should gracefully fall back to 32 GB default")


class DummySidebar:
    """Helper dummy simulating GNDroidCompanionSidebar without full Qt widget instantiation."""
    def __init__(self, serial="emulator-5554"):
        self.target_serial = serial
        self.scrcpy_proc = None

    def send_key(self, code: int):
        gndroid.GNDroidCompanionSidebar.send_key(self, code)

    def action_shake(self):
        gndroid.GNDroidCompanionSidebar.action_shake(self)

    def action_toggle_device_screen(self):
        gndroid.GNDroidCompanionSidebar.action_toggle_device_screen(self)


class TestActionsShakeAndScreenToggleAdversarial(unittest.TestCase):
    """Adversarial stress-testing of action_shake and action_toggle_device_screen in gndroid.pyw."""

    def test_action_shake_emulator_does_not_issue_keyevent_82(self):
        """Verify action_shake on emulator does NOT issue keyevent 82 and issues genuine sensor acceleration."""
        sidebar = DummySidebar("emulator-5554")
        executed_cmds = []

        def mock_run(cmd, *args, **kwargs):
            executed_cmds.append(list(cmd))
            m = MagicMock()
            m.returncode = 0
            return m

        with patch.object(gndroid.subprocess, "run", side_effect=mock_run):
            with patch("time.sleep", return_value=None):
                sidebar.action_shake()

        # Assert no keyevent 82 anywhere
        for cmd in executed_cmds:
            cmd_str = " ".join(cmd)
            self.assertNotIn("82", cmd, f"CRITICAL DEFECT: action_shake issued keyevent 82! Command: {cmd_str}")
            self.assertNotIn("KEYCODE_MENU", cmd_str)

        # Assert genuine accelerometer sensor vector injection
        self.assertEqual(len(executed_cmds), 5, f"Expected 5 sensor vector commands, got {len(executed_cmds)}")
        for cmd in executed_cmds:
            self.assertIn("emu", cmd)
            self.assertIn("sensor", cmd)
            self.assertIn("set", cmd)
            self.assertIn("acceleration", cmd)

    def test_action_shake_physical_device_does_not_issue_keyevent_82(self):
        """Verify action_shake on physical device issues broadcast intent, NOT keyevent 82."""
        sidebar = DummySidebar("RF8M123456")
        executed_cmds = []

        def mock_run(cmd, *args, **kwargs):
            executed_cmds.append(list(cmd))
            m = MagicMock()
            m.returncode = 0
            return m

        with patch.object(gndroid.subprocess, "run", side_effect=mock_run):
            sidebar.action_shake()

        for cmd in executed_cmds:
            cmd_str = " ".join(cmd)
            self.assertNotIn("82", cmd, f"CRITICAL DEFECT: action_shake issued keyevent 82! Command: {cmd_str}")

        self.assertEqual(len(executed_cmds), 1)
        expected_intent = "com.android.internal.action.SHAKE"
        self.assertIn(expected_intent, executed_cmds[0])

    def test_action_toggle_screen_scrcpy_window_does_not_issue_keyevent_26(self):
        """Verify action_toggle_device_screen with Scrcpy window issues Alt+O and NEVER keyevent 26."""
        sidebar = DummySidebar("emulator-5554")
        executed_post_messages = []

        def mock_post_message(hwnd, msg, wparam, lparam):
            executed_post_messages.append((hwnd, msg, wparam, lparam))
            return 1

        with patch.object(gndroid, "find_target_window", return_value=0x12345):
            with patch.object(gndroid.user32, "PostMessageW", side_effect=mock_post_message):
                with patch.object(gndroid.subprocess, "run") as mock_run:
                    with patch.object(gndroid.subprocess, "Popen") as mock_popen:
                        sidebar.action_toggle_device_screen()
                        mock_run.assert_not_called()
                        mock_popen.assert_not_called()

        self.assertGreaterEqual(len(executed_post_messages), 2, "Expected WM_SYSKEYDOWN/UP messages")
        wparams = [p[2] for p in executed_post_messages]
        self.assertIn(0x12, wparams)  # VK_MENU (Alt)
        self.assertIn(0x4F, wparams)  # 'O'

    def test_action_toggle_screen_adb_fallback_awake_sends_223(self):
        """Verify action_toggle_device_screen fallback when awake issues keyevent 223 (KEYCODE_SLEEP), NEVER 26."""
        sidebar = DummySidebar("emulator-5554")
        executed_cmds = []

        def mock_run(cmd, *args, **kwargs):
            executed_cmds.append(list(cmd))
            m = MagicMock()
            m.returncode = 0
            return m

        with patch.object(gndroid, "find_target_window", return_value=0):
            with patch.object(gndroid.subprocess, "check_output", return_value="mWakefulness=Awake\n"):
                with patch.object(gndroid.subprocess, "run", side_effect=mock_run):
                    with patch.object(gndroid.subprocess, "Popen", side_effect=mock_run):
                        sidebar.action_toggle_device_screen()

        for cmd in executed_cmds:
            self.assertNotIn("26", cmd, "CRITICAL DEFECT: action_toggle_device_screen issued keyevent 26!")
        self.assertTrue(any("223" in cmd for cmd in executed_cmds), f"Expected keyevent 223 in {executed_cmds}")

    def test_action_toggle_screen_adb_fallback_asleep_sends_224(self):
        """Verify action_toggle_device_screen fallback when asleep issues keyevent 224 (KEYCODE_WAKEUP), NEVER 26."""
        sidebar = DummySidebar("emulator-5554")
        executed_cmds = []

        def mock_run(cmd, *args, **kwargs):
            executed_cmds.append(list(cmd))
            m = MagicMock()
            m.returncode = 0
            return m

        with patch.object(gndroid, "find_target_window", return_value=0):
            with patch.object(gndroid.subprocess, "check_output", return_value="mWakefulness=Asleep\n"):
                with patch.object(gndroid.subprocess, "run", side_effect=mock_run):
                    with patch.object(gndroid.subprocess, "Popen", side_effect=mock_run):
                        sidebar.action_toggle_device_screen()

        for cmd in executed_cmds:
            self.assertNotIn("26", cmd, "CRITICAL DEFECT: action_toggle_device_screen issued keyevent 26!")
        self.assertTrue(any("224" in cmd for cmd in executed_cmds), f"Expected keyevent 224 in {executed_cmds}")

    def test_action_toggle_screen_adb_fallback_exception_sends_223(self):
        """Verify action_toggle_device_screen fallback on check_output exception sends 223 via send_key, NEVER 26."""
        sidebar = DummySidebar("emulator-5554")
        executed_cmds = []

        def mock_cmd(cmd, *args, **kwargs):
            executed_cmds.append(list(cmd))
            m = MagicMock()
            m.returncode = 0
            return m

        with patch.object(gndroid, "find_target_window", return_value=0):
            with patch.object(gndroid.subprocess, "check_output", side_effect=Exception("ADB query failed")):
                with patch.object(gndroid.subprocess, "run", side_effect=mock_cmd):
                    with patch.object(gndroid.subprocess, "Popen", side_effect=mock_cmd):
                        sidebar.action_toggle_device_screen()

        for cmd in executed_cmds:
            self.assertNotIn("26", cmd, "CRITICAL DEFECT: action_toggle_device_screen issued keyevent 26 on fallback!")
        self.assertTrue(any("223" in cmd for cmd in executed_cmds), f"Expected keyevent 223 in {executed_cmds}")


class TestTautologyEliminationAdversarial(unittest.TestCase):
    """Adversarial checks to ensure tautologies and bypasses are completely eliminated."""

    def test_auto_stabilize_vpn_no_or_true_bypass(self):
        """Verify vpn_appops_ok does NOT have 'or True' bypass when granted_packages is empty."""
        with patch("nexus.display_and_vpn.detect_installed_vpn_apps", return_value=[]):
            with patch("nexus.display_and_vpn.grant_vpn_permission", return_value=False):
                with patch("nexus.display_and_vpn._check_hypervisor_ipv6_disabled", return_value=True):
                    with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")):
                        with patch("subprocess.check_output", return_value="device\n"):
                            res = auto_stabilize_vpn_networking("emulator-5554")
                            self.assertFalse(
                                res["vpn_appops_granted"],
                                "CRITICAL DEFECT: vpn_appops_granted is True when no packages were granted! 'or True' bypass re-introduced!"
                            )
                            self.assertFalse(
                                res["overall_success"],
                                "CRITICAL DEFECT: overall_success is True when vpn_appops_granted is False!"
                            )


def run_empirical_suite():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestListContractsAdversarial))
    suite.addTests(loader.loadTestsFromTestCase(TestHostHardwareSummaryAdversarial))
    suite.addTests(loader.loadTestsFromTestCase(TestActionsShakeAndScreenToggleAdversarial))
    suite.addTests(loader.loadTestsFromTestCase(TestTautologyEliminationAdversarial))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    print("=" * 70)
    print("EMPIRICAL ADVERSARIAL CHALLENGER SUITE — MILESTONE 1")
    print("=" * 70)
    success = run_empirical_suite()
    print("\n" + "=" * 70)
    print(f"OVERALL EMPIRICAL CHALLENGE VERDICT: {'PASSED' if success else 'FAILED'}")
    print("=" * 70)
    sys.exit(0 if success else 1)