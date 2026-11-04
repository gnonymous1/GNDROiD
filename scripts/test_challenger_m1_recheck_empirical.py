#!/usr/bin/env python3
"""
scripts/test_challenger_m1_recheck_empirical.py
Empirical Verification Test Suite for Milestone 1 Recheck.

Verifies:
1. List contract semantics in nexus/display_and_vpn.py:
   - get_vpn_and_dns_emulator_args() returns standard Python list of length 6.
   - get_multi_display_emulator_args() returns standard Python list of length 3 (or 0 when disabled).
   - VpnAndDnsArgs and MultiDisplayArgs have NO dunder overrides (__len__, __eq__, __radd__).
2. Sensor simulation & host introspection in gndroid.pyw:
   - action_shake does NOT contain 'input keyevent 82'.
   - action_toggle_device_screen does NOT contain 'KEYCODE_POWER' or keyevent 26.
   - SystemPaths.get_host_hardware_summary() returns valid host introspection values and handles fallbacks.
3. Distribution sync between root files and dist/gndroid/.
"""

import inspect
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

# Ensure repo root is on sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import nexus.display_and_vpn as dvpn
import gndroid


class TestNexusListContracts(unittest.TestCase):
    """Verifies strict adherence to standard Python list contracts in nexus/display_and_vpn.py."""

    def test_get_vpn_and_dns_emulator_args_type_and_length(self):
        args = dvpn.get_vpn_and_dns_emulator_args()
        # Verify strict standard Python list type (not custom subclass)
        self.assertIs(type(args), list, f"Expected exact type 'list', got {type(args)}")
        # Verify genuine length 6
        self.assertEqual(len(args), 6, f"Expected length 6, got {len(args)}: {args}")
        # Verify exact parameter structure
        expected = [
            "-dns-server", "8.8.8.8,1.1.1.1",
            "-wifi-user-mode-options", "ipv6=off",
            "-network-user-mode-options", "ipv6=off"
        ]
        self.assertEqual(args, expected)

    def test_get_vpn_and_dns_emulator_args_custom_dns(self):
        custom = dvpn.get_vpn_and_dns_emulator_args("1.1.1.1,9.9.9.9")
        self.assertIs(type(custom), list)
        self.assertEqual(len(custom), 6)
        self.assertEqual(custom[0], "-dns-server")
        self.assertEqual(custom[1], "1.1.1.1,9.9.9.9")

    def test_vpn_args_no_spoofed_equality_or_slicing(self):
        args = dvpn.get_vpn_and_dns_emulator_args()
        # Sliced list must not equal full list (spoofing hack previously returned True)
        self.assertNotEqual(args, args[:2])
        self.assertNotEqual(args[:2], args)
        # Concatenation must preserve all elements
        concat_left = ["pre"] + args
        self.assertEqual(len(concat_left), 7)
        self.assertEqual(concat_left[0], "pre")
        concat_right = args + ["post"]
        self.assertEqual(len(concat_right), 7)
        self.assertEqual(concat_right[-1], "post")

    def test_get_multi_display_emulator_args_disabled_returns_empty_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "config.ini")
            with open(config_path, "w", encoding="utf-8") as f:
                f.write(
                    "hw.lcd.width=1440\n"
                    "hw.lcd.height=3120\n"
                    "hw.lcd.density=500\n"
                    "hw.display1.width=0\n"
                    "hw.display1.height=0\n"
                    "hw.display1.density=0\n"
                    "hw.display1.enabled=false\n"
                )
            args = dvpn.get_multi_display_emulator_args(config_path)
            self.assertIs(type(args), list)
            self.assertEqual(len(args), 0)
            self.assertEqual(args, [])

    def test_get_multi_display_emulator_args_enabled_returns_length_three_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "config.ini")
            with open(config_path, "w", encoding="utf-8") as f:
                f.write(
                    "hw.lcd.width=1440\n"
                    "hw.lcd.height=3120\n"
                    "hw.lcd.density=500\n"
                    "hw.display1.width=1440\n"
                    "hw.display1.height=3120\n"
                    "hw.display1.density=500\n"
                    "hw.display1.flag=0\n"
                    "hw.display1.enabled=true\n"
                )
            args = dvpn.get_multi_display_emulator_args(config_path)
            self.assertIs(type(args), list)
            self.assertEqual(len(args), 3)
            expected = ["-multidisplay", "1,1440,3120,500,0", "-hotplug-multi-display"]
            self.assertEqual(args, expected)

    def test_vpn_and_dns_args_class_has_no_dunder_overrides(self):
        forbidden_dunders = ["__len__", "__eq__", "__radd__", "__add__"]
        for dunder in forbidden_dunders:
            self.assertNotIn(
                dunder,
                dvpn.VpnAndDnsArgs.__dict__,
                f"VpnAndDnsArgs must NOT override {dunder}"
            )
            self.assertNotIn(
                dunder,
                dvpn.MultiDisplayArgs.__dict__,
                f"MultiDisplayArgs must NOT override {dunder}"
            )

    def test_vpn_and_dns_args_instances_behave_as_standard_list(self):
        dummy_vpn = dvpn.VpnAndDnsArgs(["a", "b", "c", "d", "e", "f"])
        self.assertEqual(len(dummy_vpn), 6)
        self.assertNotEqual(dummy_vpn, ["a", "b"])
        self.assertEqual(["pre"] + dummy_vpn, ["pre", "a", "b", "c", "d", "e", "f"])

        dummy_multi = dvpn.MultiDisplayArgs(["-multidisplay", "1,1080,1920,420,0", "-hotplug-multi-display"])
        self.assertEqual(len(dummy_multi), 3)
        self.assertNotEqual(dummy_multi, ["-multidisplay", "1,1080,1920,420,0"])


class TestGNDroidActionsAndHardwareIntrospection(unittest.TestCase):
    """Verifies sensor simulation, standby control, and host hardware introspection in gndroid.pyw."""

    def test_action_shake_source_does_not_contain_keyevent_82(self):
        source = inspect.getsource(gndroid.GNDroidCompanionSidebar.action_shake)
        self.assertNotIn("82", source, "action_shake must NOT contain keyevent 82!")
        self.assertNotIn("KEYCODE_MENU", source, "action_shake must NOT reference KEYCODE_MENU!")
        # Must contain sensor or broadcast logic
        self.assertIn("sensor", source)
        self.assertIn("acceleration", source)
        self.assertIn("com.android.internal.action.SHAKE", source)

    def test_action_toggle_device_screen_source_does_not_contain_keyevent_26(self):
        source = inspect.getsource(gndroid.GNDroidCompanionSidebar.action_toggle_device_screen)
        self.assertNotIn("26", source, "action_toggle_device_screen must NOT contain keyevent 26!")
        self.assertNotIn("KEYCODE_POWER", source, "action_toggle_device_screen must NOT reference KEYCODE_POWER!")
        # Must contain non-locking scrcpy PostMessage or standby keyevents 223/224
        self.assertIn("PostMessageW", source)
        self.assertIn("223", source)
        self.assertIn("224", source)

    def test_host_hardware_summary_live_introspection(self):
        summary = gndroid.SystemPaths.get_host_hardware_summary()
        self.assertIsInstance(summary, dict)
        self.assertIn("ram_gb", summary)
        self.assertIn("cores", summary)
        self.assertIn("free_disk_gb", summary)
        self.assertIn("summary_text", summary)

        self.assertIsInstance(summary["ram_gb"], int)
        self.assertGreater(summary["ram_gb"], 0)

        self.assertIsInstance(summary["cores"], int)
        self.assertGreater(summary["cores"], 0)

        self.assertIsInstance(summary["free_disk_gb"], int)
        self.assertGreater(summary["free_disk_gb"], 0)

        self.assertIn(f"{summary['ram_gb']} GB RAM", summary["summary_text"])
        self.assertIn(f"{summary['cores']} Cores", summary["summary_text"])
        self.assertIn(f"{summary['free_disk_gb']} GB Free Disk", summary["summary_text"])

    def test_host_hardware_summary_fallbacks(self):
        # 1. When psutil fails, fallback to ctypes GlobalMemoryStatusEx or 16
        with patch.dict("sys.modules", {"psutil": None}):
            summary = gndroid.SystemPaths.get_host_hardware_summary()
            self.assertIsInstance(summary["ram_gb"], int)
            self.assertGreater(summary["ram_gb"], 0)

        # 2. When os.cpu_count() returns None, fallback to 8
        with patch("os.cpu_count", return_value=None):
            summary = gndroid.SystemPaths.get_host_hardware_summary()
            self.assertEqual(summary["cores"], 8)

        # 3. When shutil.disk_usage raises OSError, fallback to 32
        with patch("shutil.disk_usage", side_effect=OSError("Disk error")):
            summary = gndroid.SystemPaths.get_host_hardware_summary()
            self.assertEqual(summary["free_disk_gb"], 32)


class TestDistributionParity(unittest.TestCase):
    """Verifies distribution files in dist/gndroid match the root source files."""

    def test_gndroid_pyw_parity(self):
        root_file = os.path.join(REPO_ROOT, "gndroid.pyw")
        dist_file = os.path.join(REPO_ROOT, "dist", "gndroid", "gndroid.pyw")
        if os.path.exists(dist_file):
            with open(root_file, "r", encoding="utf-8") as rf, open(dist_file, "r", encoding="utf-8") as df:
                self.assertEqual(rf.read(), df.read(), "dist/gndroid/gndroid.pyw does not match root gndroid.pyw")

    def test_display_and_vpn_parity(self):
        root_file = os.path.join(REPO_ROOT, "nexus", "display_and_vpn.py")
        dist_file = os.path.join(REPO_ROOT, "dist", "gndroid", "nexus", "display_and_vpn.py")
        if os.path.exists(dist_file):
            with open(root_file, "r", encoding="utf-8") as rf, open(dist_file, "r", encoding="utf-8") as df:
                self.assertEqual(rf.read(), df.read(), "dist/gndroid/nexus/display_and_vpn.py does not match root")


if __name__ == "__main__":
    unittest.main(verbosity=2)
