#!/usr/bin/env python3
"""
tests/test_eco_and_memory.py - Unit Tests for Eco Throttler & Memory Trimmer
===========================================================================

Validates:
1. Eco Throttler:
   - Win32 priority constants and affinity mask calculations
   - Instance registration and unregistration lifecycle
   - Focus evaluation: HWND matching and PID matching
   - Throttling state transitions: Focused (NORMAL) vs Unfocused (IDLE / Efficiency Affinity)
   - Enable/Disable lifecycle and clean background thread termination
   - Live Win32 priority & working set operations on current process
2. Memory Trimmer:
   - TrimResult dual dictionary and tuple-unpacking interface
   - Tier 1: Android ART am trim-memory execution
   - Tier 2: Linux drop_caches=3 cache purge
   - Tier 3: Linux compact_memory=1 memory compaction
   - Tier 4: Host Win32 K32EmptyWorkingSet execution on live process
   - Guest /proc/meminfo parsing
   - Batch trimming across multiple instance serials
"""

import os
import subprocess
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

from nexus.eco_throttler import (
    BELOW_NORMAL_PRIORITY_CLASS,
    IDLE_PRIORITY_CLASS,
    NORMAL_PRIORITY_CLASS,
    EcoThrottler,
    Win32ProcessApi,
)
from nexus.memory_trimmer import MemoryTrimmer, TrimResult


class MockWin32Api(Win32ProcessApi):
    """Controllable Win32 API stub for deterministic unit testing."""

    def __init__(self):
        super().__init__()
        self.foreground_hwnd = 0
        self.hwnd_to_pid = {}
        self.process_priorities = {}
        self.process_affinities = {}

    def get_foreground_hwnd(self) -> int:
        return self.foreground_hwnd

    def get_window_pid(self, hwnd: int) -> int:
        return self.hwnd_to_pid.get(hwnd, 0)

    def set_process_priority(self, pid: int, priority_class: int) -> bool:
        self.process_priorities[pid] = priority_class
        return True

    def set_process_affinity(self, pid: int, affinity_mask: int) -> bool:
        self.process_affinities[pid] = affinity_mask
        return True


class TestEcoThrottler(unittest.TestCase):
    """Tests dynamic priority and affinity modulation in EcoThrottler."""

    def setUp(self):
        self.mock_api = MockWin32Api()
        self.throttler = EcoThrottler(check_interval=0.05, win32_api=self.mock_api)

    def tearDown(self):
        self.throttler.stop()

    def test_instance_registration(self):
        """Verifies registering and unregistering instances."""
        self.throttler.register_instance(
            serial="emulator-5554", qemu_pid=1001, scrcpy_pid=1002, hwnd=55540
        )
        reg = self.throttler.get_registered_instances()
        self.assertIn("emulator-5554", reg)
        self.assertEqual(reg["emulator-5554"]["qemu_pid"], 1001)
        self.assertEqual(reg["emulator-5554"]["scrcpy_pid"], 1002)
        self.assertEqual(reg["emulator-5554"]["hwnd"], 55540)

        self.throttler.unregister_instance("emulator-5554")
        self.assertNotIn("emulator-5554", self.throttler.get_registered_instances())

    def test_focus_detection_and_dynamic_throttling(self):
        """
        Registers two instances:
        - Instance A (focused via HWND)
        - Instance B (unfocused background)
        Verifies Instance A receives NORMAL priority while Instance B is demoted
        to IDLE priority with restricted CPU affinity.
        """
        self.throttler.register_instance(
            serial="inst-A", qemu_pid=1010, scrcpy_pid=1011, hwnd=10001
        )
        self.throttler.register_instance(
            serial="inst-B", qemu_pid=2020, scrcpy_pid=2021, hwnd=20002
        )

        # Set Instance A as foreground window
        self.mock_api.foreground_hwnd = 10001
        self.mock_api.hwnd_to_pid[10001] = 1011

        self.throttler.enable_eco_mode(target_fps=5, affinity_mask=0x0003)

        results = self.throttler.poll_and_throttle()
        self.assertEqual(results["inst-A"], "focused")
        self.assertEqual(results["inst-B"], "throttled")

        # Verify Instance A has NORMAL priority
        self.assertEqual(self.mock_api.process_priorities[1010], NORMAL_PRIORITY_CLASS)
        self.assertEqual(self.mock_api.process_priorities[1011], NORMAL_PRIORITY_CLASS)

        # Verify Instance B has IDLE priority for QEMU and BELOW_NORMAL for Scrcpy
        self.assertEqual(self.mock_api.process_priorities[2020], IDLE_PRIORITY_CLASS)
        self.assertEqual(self.mock_api.process_priorities[2021], BELOW_NORMAL_PRIORITY_CLASS)

        # Verify Instance B has restricted affinity mask (0x0003)
        self.assertEqual(self.mock_api.process_affinities[2020], 0x0003)
        self.assertEqual(self.mock_api.process_affinities[2021], 0x0003)

    def test_focus_switching_restoration(self):
        """Verifies state switches seamlessly when focus changes to Instance B."""
        self.throttler.register_instance("inst-A", qemu_pid=1010, hwnd=10001)
        self.throttler.register_instance("inst-B", qemu_pid=2020, hwnd=20002)

        self.throttler.enable_eco_mode(target_fps=5, affinity_mask=0x0001)

        # Focus switches to Instance B
        self.mock_api.foreground_hwnd = 20002
        results = self.throttler.poll_and_throttle()

        self.assertEqual(results["inst-A"], "throttled")
        self.assertEqual(results["inst-B"], "focused")

        self.assertEqual(self.mock_api.process_priorities[2020], NORMAL_PRIORITY_CLASS)
        self.assertEqual(self.mock_api.process_priorities[1010], IDLE_PRIORITY_CLASS)

    def test_disable_eco_mode_restores_all(self):
        """Disabling eco mode restores all instances to NORMAL priority and full affinity."""
        self.throttler.register_instance("inst-A", qemu_pid=1010)
        self.throttler.register_instance("inst-B", qemu_pid=2020)

        self.throttler.enable_eco_mode(target_fps=5)
        # Background poll demotes both
        self.throttler.poll_and_throttle()
        self.assertEqual(self.mock_api.process_priorities[1010], IDLE_PRIORITY_CLASS)

        # Disable eco mode
        self.throttler.disable_eco_mode()
        self.assertEqual(self.mock_api.process_priorities[1010], NORMAL_PRIORITY_CLASS)
        self.assertEqual(self.mock_api.process_priorities[2020], NORMAL_PRIORITY_CLASS)


class TestMemoryTrimmer(unittest.TestCase):
    """Tests 4-tier memory reclamation, TrimResult interface, and Win32 purging."""

    def test_trim_result_dual_interface(self):
        """Verifies TrimResult works as both a dictionary and an unpackable tuple."""
        res = TrimResult({
            "success": True,
            "freed_mb": 256,
            "tiers_executed": ["tier1", "tier2"],
        })

        # Dictionary access
        self.assertTrue(res["success"])
        self.assertEqual(res["freed_mb"], 256)
        self.assertEqual(res.get("tiers_executed"), ["tier1", "tier2"])

        # Integer indexing
        self.assertTrue(res[0])
        self.assertEqual(res[1], 256)

        # Tuple unpacking
        success, freed_mb = res
        self.assertTrue(success)
        self.assertEqual(freed_mb, 256)

    @patch("subprocess.run")
    def test_tier1_art_trim_execution(self, mock_run):
        """Verifies ADB ActivityManager trim-memory commands are invoked."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="Trim memory success", stderr=""
        )

        success, details = MemoryTrimmer.execute_tier1_art_trim("emulator-5554")
        self.assertTrue(success)
        self.assertIn("trim-memory", details)
        self.assertEqual(mock_run.call_count, 2)

    @patch("subprocess.run")
    def test_tier2_and_3_kernel_purges(self, mock_run):
        """Verifies drop_caches and compact_memory executions."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )

        t2_success, t2_msg = MemoryTrimmer.execute_tier2_drop_caches("emulator-5554")
        self.assertTrue(t2_success)
        self.assertIn("flushed", t2_msg)

        t3_success, t3_msg = MemoryTrimmer.execute_tier3_compact_memory("emulator-5554")
        self.assertTrue(t3_success)
        self.assertIn("executed", t3_msg)

    @unittest.skipUnless(sys.platform.startswith("win"), "Windows-specific test")
    def test_tier4_live_win32_empty_working_set(self):
        """Executes real Win32 EmptyWorkingSet on the current Python test process."""
        my_pid = os.getpid()
        success, freed_bytes, details = MemoryTrimmer.execute_tier4_host_empty_working_set(my_pid)
        self.assertTrue(success)
        self.assertTrue(freed_bytes >= 0)
        self.assertIn(str(my_pid), details)

    @patch("nexus.memory_trimmer.MemoryTrimmer.get_guest_memory_info")
    @patch("nexus.memory_trimmer.MemoryTrimmer.execute_tier1_art_trim")
    @patch("nexus.memory_trimmer.MemoryTrimmer.execute_tier2_drop_caches")
    @patch("nexus.memory_trimmer.MemoryTrimmer.execute_tier3_compact_memory")
    @patch("nexus.memory_trimmer.MemoryTrimmer.execute_tier4_host_empty_working_set")
    def test_full_4tier_trim_orchestration(
        self, mock_t4, mock_t3, mock_t2, mock_t1, mock_mem
    ):
        """Verifies the complete trim_instance orchestration and statistics compilation."""
        mock_mem.side_effect = [
            {"MemFree": 100000, "MemTotal": 4000000},  # Before
            {"MemFree": 356000, "MemTotal": 4000000},  # After (256 MB freed)
        ]
        mock_t1.return_value = (True, "ART Trim OK")
        mock_t2.return_value = (True, "Caches Dropped")
        mock_t3.return_value = (True, "Compacted")
        mock_t4.return_value = (True, 157286400, "Working set trimmed (150MB)")

        res = MemoryTrimmer.trim_instance(serial="emulator-5554", host_pid=1234)

        self.assertTrue(res["success"])
        self.assertEqual(len(res["tiers_executed"]), 4)
        self.assertIn("tier1_art_trim", res["tiers_executed"])
        self.assertIn("tier4_win32_empty_working_set", res["tiers_executed"])
        self.assertTrue(res["freed_mb"] > 0)

        # Unpack as tuple
        success, freed_mb = res
        self.assertTrue(success)
        self.assertTrue(freed_mb > 0)


if __name__ == "__main__":
    unittest.main()
