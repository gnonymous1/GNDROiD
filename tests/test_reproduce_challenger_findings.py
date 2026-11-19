"""
tests/test_reproduce_challenger_findings.py
===========================================
Empirical reproduction script for vulnerabilities and edge-case failures
identified by Challenger M1-2 in nexus/region_controller.py.
"""

import subprocess
import unittest
from unittest.mock import patch, MagicMock

from nexus.region_controller import UniversalRegionController, REGIONS


class TestReproduceFindings(unittest.TestCase):

    def setUp(self):
        self.controller = UniversalRegionController(adb_path="adb")

    def test_reproduce_finding_1_verify_egress_attribute_error_on_stderr_none(self):
        """
        FINDING 1: In nexus/region_controller.py line 549:
        cmd_res.stderr.strip() is called without null-checking cmd_res.stderr.
        When stderr is None and host fallback also fails, an unhandled AttributeError is raised.
        """
        mock_proc = MagicMock(returncode=1, stdout="", stderr=None)
        with patch.object(self.controller, "_run_shell", return_value=mock_proc), \
             patch("urllib.request.urlopen", side_effect=Exception("Host offline")):
            with self.assertRaises(AttributeError) as ctx:
                self.controller.verify_egress("emu-1", "US")
            self.assertIn("'NoneType' object has no attribute 'strip'", str(ctx.exception))
            print("\n[EMPIRICALLY CONFIRMED] Finding 1: AttributeError raised on cmd_res.stderr.strip():", ctx.exception)

    def test_reproduce_finding_2_verify_egress_unhandled_timeout_expired(self):
        """
        FINDING 2: In nexus/region_controller.py line 514:
        cmd_res = self._run_shell(...) is outside any try-except block in verify_egress.
        If ADB hangs or times out on guest curl, verify_egress crashes with unhandled
        subprocess.TimeoutExpired and bypasses host fallback completely.
        """
        with patch.object(self.controller, "_run_shell", side_effect=subprocess.TimeoutExpired(cmd="curl", timeout=8)):
            with self.assertRaises(subprocess.TimeoutExpired) as ctx:
                self.controller.verify_egress("emu-1", "US")
            print("[EMPIRICALLY CONFIRMED] Finding 2: TimeoutExpired uncaught in verify_egress:", ctx.exception)

    def test_reproduce_finding_3_silent_false_positive_on_offline_or_missing_device(self):
        """
        FINDING 3: In nexus/region_controller.py lines 289-313, 357-384:
        _run_shell runs subprocess.run without check=True and returncode is never checked.
        When ADB returns error code 1 ('error: device offline' or 'error: device not found'),
        apply_tier1_telephony and apply_tier2_system_os report True, and switch_region
        reports overall_success=True.
        """
        offline_proc = MagicMock(returncode=1, stdout="", stderr="error: device offline")
        with patch.object(self.controller, "_run_shell", return_value=offline_proc), \
             patch.object(self.controller, "apply_tier3_hardware_gps", return_value=False), \
             patch.object(self.controller, "verify_egress", return_value=(False, {"status": "offline"})):
            res = self.controller.switch_region("dead-device-serial", "AE", strict_network=False)
            self.assertTrue(res.tier1_telephony, "Tier 1 claimed success despite device offline!")
            self.assertTrue(res.tier2_system, "Tier 2 claimed success despite device offline!")
            self.assertTrue(res.success, "switch_region claimed overall success on offline device!")
            print(f"[EMPIRICALLY CONFIRMED] Finding 3: False positive success on offline device (res.success={res.success})")


if __name__ == "__main__":
    unittest.main()
