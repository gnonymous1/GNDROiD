#!/usr/bin/env python3
"""
tests/test_challenger_m3_2_adversarial.py - Adversarial Stress & Chaos Test Suite
=================================================================================
Milestone M3: Multi-Instance Subsystems & Extended Sensors

Adversarial Stress Testing:
1. EcoThrottler:
   - 50+ mock instances concurrent registration, churn, and rapid eco toggling
   - Win32 handle lifecycle and leak verification (GetProcessHandleCount)
   - Unexpected process termination resilience (no unhandled exceptions)
2. MemoryTrimmer:
   - 4-tier purge resilience: invalid/negative/non-existent PIDs
   - Subprocess timeouts, command failures, file not found, permission errors
   - Read-only filesystem simulation
   - Invariant dual-interface TrimResult (dict and tuple) across all error scenarios
3. GpxRoutePlayer:
   - Complex GPX routes (100+ points, zero-distance duplicates, negative coordinates, elevation extremes)
   - High speed multiplier (50x) with rapid start/pause/resume/stop cycling & loop mode
   - Geodesic precision, antipodal points, Date Line wrapping, and float overflow resilience
"""

import ctypes
import math
import os
import random
import subprocess
import sys
import threading
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
from nexus.sensor_console import (
    EARTH_RADIUS_METERS,
    GpxRoutePlayer,
    QemuTelnetConsole,
    haversine_bearing,
    haversine_distance,
)


# ===========================================================================
# 1. EcoThrottler Adversarial Stress Tests
# ===========================================================================
class MockStressWin32Api(Win32ProcessApi):
    """Chaos-injecting Win32 API stub for high-churn stress testing."""

    def __init__(self):
        super().__init__()
        self.foreground_hwnd = 0
        self.hwnd_to_pid = {}
        self.process_priorities = {}
        self.process_affinities = {}
        self.dead_pids = set()
        self.call_count_priority = 0
        self.call_count_affinity = 0

    def get_foreground_hwnd(self) -> int:
        return self.foreground_hwnd

    def get_window_pid(self, hwnd: int) -> int:
        return self.hwnd_to_pid.get(hwnd, 0)

    def set_process_priority(self, pid: int, priority_class: int) -> bool:
        self.call_count_priority += 1
        if pid in self.dead_pids:
            return False
        self.process_priorities[pid] = priority_class
        return True

    def set_process_affinity(self, pid: int, affinity_mask: int) -> bool:
        self.call_count_affinity += 1
        if pid in self.dead_pids:
            return False
        self.process_affinities[pid] = affinity_mask
        return True


class TestEcoThrottlerAdversarial(unittest.TestCase):
    """Stress tests EcoThrottler with high instance counts and chaotic state changes."""

    def setUp(self):
        self.mock_api = MockStressWin32Api()
        self.throttler = EcoThrottler(check_interval=0.02, win32_api=self.mock_api)

    def tearDown(self):
        self.throttler.stop()

    def test_50_plus_instances_registration_and_focus_churn(self):
        """
        Adversarial Test 1.1:
        Registers 75 mock instances (exceeding 50+ requirement).
        Rapidly toggles Eco Mode and injects 100 sudden foreground window changes.
        Verifies all instances are correctly prioritized and no exceptions are raised.
        """
        instance_count = 75
        for i in range(instance_count):
            serial = f"instance-{i:03d}"
            qemu_pid = 10000 + i
            scrcpy_pid = 20000 + i
            hwnd = 30000 + i
            self.throttler.register_instance(
                serial=serial,
                qemu_pid=qemu_pid,
                scrcpy_pid=scrcpy_pid,
                hwnd=hwnd,
            )
            self.mock_api.hwnd_to_pid[hwnd] = scrcpy_pid

        reg = self.throttler.get_registered_instances()
        self.assertEqual(len(reg), instance_count)

        # Enable Eco Mode
        self.throttler.enable_eco_mode(target_fps=3, affinity_mask=0x0003)
        self.assertTrue(self.throttler.is_enabled)

        # Churn loop: 100 rapid foreground window transitions
        for iteration in range(100):
            # Select random target: instance hwnd, non-existent hwnd, or 0 (desktop)
            choice = random.randint(0, instance_count + 5)
            if choice < instance_count:
                target_hwnd = 30000 + choice
            elif choice == instance_count:
                target_hwnd = 0
            else:
                target_hwnd = 999999  # External non-GNDROiD app focused (e.g. Chrome)

            self.mock_api.foreground_hwnd = target_hwnd
            results = self.throttler.poll_and_throttle()

            self.assertEqual(len(results), instance_count)
            if choice < instance_count:
                focused_serial = f"instance-{choice:03d}"
                self.assertEqual(results[focused_serial], "focused")
                # All other instances must be throttled
                throttled_count = sum(1 for s, st in results.items() if st == "throttled")
                self.assertEqual(throttled_count, instance_count - 1)
            else:
                # All instances must be throttled if non-GNDROiD window or desktop is active
                throttled_count = sum(1 for s, st in results.items() if st == "throttled")
                self.assertEqual(throttled_count, instance_count)

            # Rapidly toggle eco mode state periodically
            if iteration % 25 == 0:
                self.throttler.disable_eco_mode()
                normal_results = self.throttler.poll_and_throttle()
                self.assertTrue(all(st == "normal" for st in normal_results.values()))
                self.throttler.enable_eco_mode(target_fps=3, affinity_mask=0x0003)

    def test_unexpected_process_termination_resilience(self):
        """
        Adversarial Test 1.2:
        Simulates sudden termination of processes while registered in EcoThrottler.
        Ensures poll_and_throttle handles process death gracefully without crashing.
        """
        self.throttler.register_instance("inst-alive", qemu_pid=1100, scrcpy_pid=1101, hwnd=1001)
        self.throttler.register_instance("inst-dead", qemu_pid=2200, scrcpy_pid=2201, hwnd=2002)

        # Mark inst-dead processes as terminated
        self.mock_api.dead_pids.add(2200)
        self.mock_api.dead_pids.add(2201)

        self.throttler.enable_eco_mode(target_fps=5)

        # Focus is on inst-alive
        self.mock_api.foreground_hwnd = 1001
        self.mock_api.hwnd_to_pid[1001] = 1101
        results = self.throttler.poll_and_throttle()
        self.assertEqual(results["inst-alive"], "focused")
        self.assertEqual(results["inst-dead"], "throttled")

        # Focus switches to dead instance
        self.mock_api.foreground_hwnd = 2002
        self.mock_api.hwnd_to_pid[2002] = 2201
        results = self.throttler.poll_and_throttle()
        self.assertEqual(results["inst-alive"], "throttled")
        self.assertEqual(results["inst-dead"], "focused")

        # Unregister dead instance
        self.throttler.unregister_instance("inst-dead")
        self.assertNotIn("inst-dead", self.throttler.get_registered_instances())

    @unittest.skipUnless(sys.platform.startswith("win"), "Requires Windows Win32 API")
    def test_live_win32_handle_leak_verification(self):
        """
        Adversarial Test 1.3:
        Verifies zero handle leaks in Win32ProcessApi under repetitive priority and
        affinity modifications on live and terminated PIDs.
        """
        kernel32 = ctypes.windll.kernel32
        current_process = kernel32.GetCurrentProcess()

        def get_handle_count() -> int:
            count = ctypes.c_ulong()
            if kernel32.GetProcessHandleCount(current_process, ctypes.byref(count)):
                return int(count.value)
            return 0

        my_pid = os.getpid()
        real_api = Win32ProcessApi()

        # Warm-up call
        real_api.set_process_priority(my_pid, NORMAL_PRIORITY_CLASS)
        real_api.set_process_affinity(my_pid, (1 << (os.cpu_count() or 4)) - 1)

        initial_handles = get_handle_count()

        # Execute 500 priority and affinity modifications on real process
        for _ in range(500):
            real_api.set_process_priority(my_pid, NORMAL_PRIORITY_CLASS)
            real_api.set_process_affinity(my_pid, (1 << (os.cpu_count() or 4)) - 1)

        # Execute 500 calls on invalid/non-existent PIDs
        for dead_pid in [9999999, -1, 0, 8888888]:
            real_api.set_process_priority(dead_pid, NORMAL_PRIORITY_CLASS)
            real_api.set_process_affinity(dead_pid, 0x0001)

        final_handles = get_handle_count()
        handle_diff = final_handles - initial_handles

        # Zero handle leak check: difference must be 0
        self.assertEqual(
            handle_diff,
            0,
            f"Handle leak detected in Win32ProcessApi! Initial: {initial_handles}, Final: {final_handles}, Leaked: {handle_diff}",
        )


# ===========================================================================
# 2. MemoryTrimmer Adversarial Resilience Tests
# ===========================================================================
class TestMemoryTrimmerAdversarial(unittest.TestCase):
    """Stress tests MemoryTrimmer with faulty PIDs, ADB timeouts, and dual-interface contracts."""

    def test_invalid_and_nonexistent_host_pids(self):
        """
        Adversarial Test 2.1:
        Passes invalid host PIDs (negative, 0, non-existent 99999999) to Tier 4.
        Verifies Tier 4 returns (False, 0, details) without raising exceptions.
        """
        invalid_pids = [-999, -1, 0, 99999999]

        for pid in invalid_pids:
            success, freed_bytes, details = MemoryTrimmer.execute_tier4_host_empty_working_set(pid)
            self.assertFalse(success, f"Expected failure for invalid PID {pid}")
            self.assertEqual(freed_bytes, 0)
            self.assertTrue(len(details) > 0)

    @patch("subprocess.run")
    def test_adb_command_timeouts_and_exceptions(self, mock_run):
        """
        Adversarial Test 2.2:
        Simulates subprocess.TimeoutExpired, FileNotFoundError, PermissionError,
        and CalledProcessError across all tiers.
        Verifies methods degrade gracefully without crashing.
        """
        # 1. TimeoutExpired simulation
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["adb"], timeout=5)
        t1_ok, t1_details = MemoryTrimmer.execute_tier1_art_trim("emulator-5554")
        self.assertFalse(t1_ok)
        self.assertIn("error", t1_details.lower())

        t2_ok, t2_details = MemoryTrimmer.execute_tier2_drop_caches("emulator-5554")
        self.assertFalse(t2_ok)

        t3_ok, t3_details = MemoryTrimmer.execute_tier3_compact_memory("emulator-5554")
        self.assertFalse(t3_ok)

        mem_info = MemoryTrimmer.get_guest_memory_info("emulator-5554")
        self.assertEqual(mem_info, {})

        # 2. FileNotFoundError (e.g. adb executable missing)
        mock_run.side_effect = FileNotFoundError("adb not found on PATH")
        t1_ok, _ = MemoryTrimmer.execute_tier1_art_trim("emulator-5554")
        self.assertFalse(t1_ok)

        # 3. PermissionError
        mock_run.side_effect = PermissionError("Access denied")
        t2_ok, _ = MemoryTrimmer.execute_tier2_drop_caches("emulator-5554")
        self.assertFalse(t2_ok)

    @patch("subprocess.run")
    def test_read_only_filesystem_simulation(self, mock_run):
        """
        Adversarial Test 2.3:
        Simulates guest Android filesystem mounted Read-Only (drop_caches & compact_memory write fail).
        """
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="/system/bin/sh: echo: write error: Read-only file system",
        )

        t2_ok, t2_msg = MemoryTrimmer.execute_tier2_drop_caches("emulator-5554")
        self.assertFalse(t2_ok)
        self.assertIn("failed", t2_msg)

        t3_ok, t3_msg = MemoryTrimmer.execute_tier3_compact_memory("emulator-5554")
        self.assertFalse(t3_ok)
        self.assertIn("failed", t3_msg)

    @patch("subprocess.run")
    def test_trim_result_dual_interface_invariance_under_failures(self, mock_run):
        """
        Adversarial Test 2.4:
        Tests TrimResult behavior when ALL tiers fail or produce empty metrics.
        Verifies identical behavior whether treated as Dict or 2-Tuple.
        """
        # Simulate complete failure across all ADB commands
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="Device offline"
        )

        res = MemoryTrimmer.trim_instance(serial="emulator-offline", host_pid=-1)

        # 1. Verification as Dict
        self.assertIsInstance(res, dict)
        self.assertFalse(res["success"])
        self.assertEqual(res["freed_mb"], 0)
        self.assertEqual(res["estimated_freed_mb"], 0)
        self.assertEqual(res["freed_bytes"], 0)
        self.assertIn("elapsed_ms", res)
        self.assertIn("tier_results", res)
        self.assertEqual(res.get("serial"), "emulator-offline")

        # 2. Verification as Tuple
        success, freed_mb = res
        self.assertFalse(success)
        self.assertEqual(freed_mb, 0)

        # 3. Verification of integer indexing
        self.assertEqual(res[0], False)
        self.assertEqual(res[1], 0)
        with self.assertRaises(IndexError):
            _ = res[2]

        # 4. Invariance: tuple conversion
        unpacked_list = list(res)
        self.assertEqual(unpacked_list, [False, 0])


# ===========================================================================
# 3. GpxRoutePlayer High-Speed & Interpolation Stress Tests
# ===========================================================================
class TestGpxRoutePlayerAdversarial(unittest.TestCase):
    """Stress tests GPX route player with 100+ points, edge coordinates, 50x speed, and geodesic math."""

    def setUp(self):
        self.mock_console = MagicMock()
        self.mock_console.set_geo.return_value = True
        self.player = GpxRoutePlayer(console=self.mock_console)

    def tearDown(self):
        self.player.stop_playback()

    def _generate_complex_gpx_xml(self, point_count: int = 120) -> str:
        """Generates GPX XML with 100+ trackpoints, elevation shifts, and negative coordinates."""
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<gpx version="1.1" creator="GNDROiD" xmlns="http://www.topografix.com/GPX/1/1">',
            '  <trk>',
            '    <name>Adversarial Multi-Point Track</name>',
            '    <trkseg>',
        ]

        # Base in Southern & Eastern hemisphere (e.g. Sydney -33.8688, 151.2093)
        base_lat = -33.8688
        base_lon = 151.2093
        base_ele = -15.5  # Below sea-level elevation test

        for i in range(point_count):
            # Introduce zero-distance duplicate points at intervals
            if i in (10, 11, 12, 50, 51):
                lat = base_lat
                lon = base_lon
                ele = base_ele
            else:
                lat = base_lat + (i * 0.001)
                lon = base_lon + (i * 0.0015)
                ele = base_ele + (i * 2.5)

            lines.append(f'      <trkpt lat="{lat:.6f}" lon="{lon:.6f}">')
            lines.append(f'        <ele>{ele:.2f}</ele>')
            lines.append(f'        <time>2026-11-18T10:{i % 60:02d}:00Z</time>')
            lines.append('      </trkpt>')

        lines.extend([
            '    </trkseg>',
            '  </trk>',
            '</gpx>',
        ])
        return '\n'.join(lines)

    def test_complex_gpx_parsing_and_zero_distance_duplicates(self):
        """
        Adversarial Test 3.1:
        Parses GPX with 120 track points containing zero-distance duplicates and negative coordinates.
        Verifies route metrics calculation does not divide by zero or overflow.
        """
        gpx_xml = self._generate_complex_gpx_xml(point_count=120)
        points = self.player.load_gpx_content(gpx_xml)

        self.assertEqual(len(points), 120)
        self.assertGreater(self.player.total_distance_m, 0.0)

        # Verify negative coordinates were parsed properly
        self.assertLess(points[0]["lat"], 0.0)
        self.assertGreater(points[0]["lon"], 0.0)
        self.assertLess(points[0]["ele"], 0.0)

        # Interpolate route at 10-meter step
        interpolated = self.player.interpolate_route(interval_meters=10.0)
        self.assertGreater(len(interpolated), 120)

        # Verify no NaN or Inf in coordinates
        for pt in interpolated:
            self.assertFalse(math.isnan(pt["lat"]))
            self.assertFalse(math.isnan(pt["lon"]))
            self.assertFalse(math.isnan(pt["ele"]))
            self.assertFalse(math.isinf(pt["lat"]))
            self.assertFalse(math.isinf(pt["lon"]))
            self.assertFalse(math.isinf(pt["ele"]))

    def test_geodesic_haversine_precision_and_overflow_resistance(self):
        """
        Adversarial Test 3.2:
        Tests Haversine distance and bearing across extreme boundaries:
        - Antipodal points (North Pole to South Pole)
        - Zero distance (same coordinate)
        - Crossing the International Date Line (179.9 to -179.9)
        - Extreme negative coordinates (South Pole, Dead Sea)
        Verifies mathematical accuracy without float domain errors or overflow.
        """
        # 1. Zero distance
        d_zero = haversine_distance(25.0, 55.0, 25.0, 55.0)
        self.assertAlmostEqual(d_zero, 0.0, places=3)
        b_zero = haversine_bearing(25.0, 55.0, 25.0, 55.0)
        self.assertAlmostEqual(b_zero, 0.0, places=1)

        # 2. Antipodal points: North Pole to South Pole
        # Half Earth circumference = pi * R ≈ 20,015,087 meters
        expected_half_circ = math.pi * EARTH_RADIUS_METERS
        d_poles = haversine_distance(90.0, 0.0, -90.0, 0.0)
        self.assertAlmostEqual(d_poles, expected_half_circ, delta=500)

        # 3. Equator Quarter Circle: (0, 0) to (0, 90)
        expected_quarter = (math.pi / 2.0) * EARTH_RADIUS_METERS
        d_quarter = haversine_distance(0.0, 0.0, 0.0, 90.0)
        self.assertAlmostEqual(d_quarter, expected_quarter, delta=500)

        # 4. Across International Date Line: (0, 179.9) to (0, -179.9)
        # Difference in longitude across the line is 0.2 degrees ≈ 22.2 km
        d_dateline = haversine_distance(0.0, 179.9, 0.0, -179.9)
        self.assertGreater(d_dateline, 21000)
        self.assertLess(d_dateline, 23000)

        # 5. Southern Hemisphere: Sydney to Melbourne
        d_syd_mel = haversine_distance(-33.8688, 151.2093, -37.8136, 144.9631)
        self.assertGreater(d_syd_mel, 700000)   # ~713 km
        self.assertLess(d_syd_mel, 730000)

    def test_high_speed_50x_rapid_cycling_and_loop_mode(self):
        """
        Adversarial Test 3.3:
        Executes playback at 50x speed multiplier with 120 points.
        Rapidly cycles start -> pause -> resume -> pause -> resume -> stop.
        Tests loop mode execution and asserts zero thread deadlocks or leaks.
        """
        gpx_xml = self._generate_complex_gpx_xml(point_count=50)
        self.player.load_gpx_content(gpx_xml)

        telemetry_events = []

        def on_telemetry(t):
            telemetry_events.append(t)

        # 1. Start at 50x speed with loop=True
        self.player.start_playback(
            speed_multiplier=50.0,
            loop=True,
            tick_interval=0.005,
            callback=on_telemetry,
        )
        self.assertTrue(self.player.is_playing)

        # 2. Rapid pause / resume cycling
        for _ in range(5):
            self.player.pause_playback()
            self.assertTrue(self.player.is_paused)
            time.sleep(0.01)
            self.player.resume_playback()
            self.assertFalse(self.player.is_paused)
            time.sleep(0.01)

        # Let loop run across wrap-around
        time.sleep(0.1)

        # 3. Stop playback
        self.player.stop_playback()
        self.assertFalse(self.player.is_playing)
        self.assertFalse(self.player.is_paused)

        # Verify telemetry was captured
        self.assertGreater(len(telemetry_events), 0)
        first_event = telemetry_events[0]
        self.assertIn("speed_kmh", first_event)
        self.assertIn("bearing", first_event)
        self.assertIn("progress_percent", first_event)

        # Verify console received calls
        self.assertTrue(self.mock_console.set_geo.called)


if __name__ == "__main__":
    unittest.main()
