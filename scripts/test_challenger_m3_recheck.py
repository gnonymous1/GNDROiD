"""
Empirical verification script for challenger_m3_recheck.
Verifies:
1. _run_guest_cmd behavior against Permission denied, non-zero exit codes, and live unrooted execution.
2. QEMU hypervisor IPv6 disablement flags in get_vpn_and_dns_emulator_args and AVDManager.launch_emulator_instance.
3. Schema completeness and truthful calculation of overall_success.
"""
import sys
import os
import unittest
from unittest.mock import MagicMock, patch
import subprocess

# Ensure repo root is on sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from nexus.display_and_vpn import (
    get_vpn_and_dns_emulator_args,
    auto_stabilize_vpn_networking,
    OFFLINE_STABILIZATION_RESULT,
    grant_vpn_permission,
    detect_installed_vpn_apps,
    _find_adb
)


class TestChallengerM3Recheck(unittest.TestCase):

    def test_01_launch_args_flags_present(self):
        """Verify -wifi-user-mode-options ipv6=off and -network-user-mode-options ipv6=off."""
        args = get_vpn_and_dns_emulator_args()
        args_list = list(args)
        print("\n[CHECK 1] get_vpn_and_dns_emulator_args():", args_list)
        
        self.assertIn("-wifi-user-mode-options", args_list)
        idx_wifi = args_list.index("-wifi-user-mode-options")
        self.assertEqual(args_list[idx_wifi + 1], "ipv6=off")

        self.assertIn("-network-user-mode-options", args_list)
        idx_net = args_list.index("-network-user-mode-options")
        self.assertEqual(args_list[idx_net + 1], "ipv6=off")

        # Check AVDManager.launch_emulator_instance in gndroid.pyw
        gndroid_path = os.path.join(REPO_ROOT, "gndroid.pyw")
        with open(gndroid_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn('"-wifi-user-mode-options", "ipv6=off"', content)
        self.assertIn('"-network-user-mode-options", "ipv6=off"', content)
        print("[CHECK 1] PASSED: QEMU launch flags present in both get_vpn_and_dns_emulator_args and gndroid.pyw")

    def test_02_run_guest_cmd_permission_denied_and_nonzero_oracle(self):
        """
        Verify that _run_guest_cmd inside auto_stabilize_vpn_networking
        does NOT return True on Permission denied or non-zero exit codes.
        """
        print("\n[CHECK 2] Testing _run_guest_cmd oracle rejection on failures...")

        # Case A: returncode=1, out="Permission denied" -> Must NOT succeed
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Permission denied")
            res = auto_stabilize_vpn_networking("emulator-5554")
            self.assertFalse(res["mtu_clamped"], "mtu_clamped should be False when command fails with Permission denied")
            self.assertFalse(res["ipv6_disabled"], "ipv6_disabled should be False when command fails with Permission denied")

        # Case B: returncode=0, but out="RTNETLINK answers: Permission denied" -> Must NOT succeed
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="RTNETLINK answers: Permission denied", stderr="")
            res = auto_stabilize_vpn_networking("emulator-5554")
            self.assertFalse(res["mtu_clamped"], "mtu_clamped should be False when stdout has Permission denied")
            self.assertFalse(res["ipv6_disabled"], "ipv6_disabled should be False when stdout has Permission denied")

        # Case C: returncode=127, out="/system/bin/sh: foo: not found" -> Must NOT succeed
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=127, stdout="", stderr="/system/bin/sh: ip: not found")
            res = auto_stabilize_vpn_networking("emulator-5554")
            self.assertFalse(res["mtu_clamped"], "mtu_clamped should be False on returncode 127")

        print("[CHECK 2] PASSED: Oracle rejects Permission denied and non-zero returncodes.")

    def test_03_live_emulator_truthfulness(self):
        """
        On the active live emulator (emulator-5554), verify truthful reporting of
        kernel operations that fail under unprivileged adbd.
        """
        adb = _find_adb()
        try:
            state = subprocess.check_output([adb, "-s", "emulator-5554", "get-state"], text=True, timeout=3).strip()
        except Exception:
            self.skipTest("Live emulator-5554 not available")

        if state != "device":
            self.skipTest("emulator-5554 not in 'device' state")

        # Check build type
        build_type = subprocess.check_output(
            [adb, "-s", "emulator-5554", "shell", "getprop", "ro.build.type"],
            text=True, timeout=3
        ).strip()
        print(f"\n[CHECK 3] Live emulator build type: {build_type}")

        res = auto_stabilize_vpn_networking("emulator-5554")
        print("[CHECK 3] Live stabilization result:", res)

        if build_type == "user":
            # On user build, MTU clamp and sysctl MUST be False (no fake success!)
            self.assertFalse(res["mtu_clamped"], "mtu_clamped must be False on unrooted user build")
            self.assertFalse(res["ipv6_disabled"], "ipv6_disabled must be False on unrooted user build")
            self.assertFalse(res["eth0_mtu"])
            self.assertFalse(res["wlan0_mtu"])
            self.assertFalse(res["ipv6_all"])
            print("[CHECK 3] Verified: mtu_clamped and ipv6_disabled are truthfully reported as False on user build.")
        
        # User settings MUST succeed
        self.assertTrue(res["captive_portal_disabled"], "captive portal must be disabled")
        self.assertTrue(res["private_dns_set"], "private DNS must be configured")
        self.assertTrue(res["overall_success"], "overall_success must be True via hypervisor IPv6 flag + settings")

    def test_04_schema_contract_complete(self):
        """Verify all 17 keys are present in OFFLINE_STABILIZATION_RESULT and live output."""
        print("\n[CHECK 4] Verifying schema completeness...")
        expected_keys = {
            "mtu_clamped", "ipv6_disabled", "captive_portal_disabled",
            "vpn_appops_granted", "private_dns_set", "eth0_mtu", "wlan0_mtu",
            "ipv6_all", "ipv6_default", "ipv6_eth0", "ipv6_wlan0",
            "captive_portal_mode", "captive_portal_detection_enabled",
            "private_dns_mode", "private_dns_specifier", "appops_packages",
            "overall_success"
        }
        self.assertEqual(set(OFFLINE_STABILIZATION_RESULT.keys()), expected_keys)
        offline_res = auto_stabilize_vpn_networking("emulator-nonexistent-9999")
        self.assertEqual(set(offline_res.keys()), expected_keys)
        print("[CHECK 4] PASSED: All 17 schema keys present.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
