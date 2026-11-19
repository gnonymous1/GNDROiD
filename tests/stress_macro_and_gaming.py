"""
tests/stress_macro_and_gaming.py
================================
Adversarial empirical stress suite for Feature 18 (Macro Engine)
and Feature 19 (Gaming Mode Launch Profile).

Executed by: Challenger 2 (Milestone M4)
Tests:
1. Macro Engine:
   - Variable and extreme playback speed scaling (0.1x, 1.0x, 5.0x, 10.0x, 100.0x)
   - Rapid cancellation & stop race conditions (1ms, 5ms, 10ms across 100 iterations each)
   - Large script volume (10,000 steps recording and playback, memory & latency check)
   - Edge case scripts (empty script, 0ms identical timestamps, negative/out-of-bounds coordinates)
   - JSON roundtrip stress (corrupt JSON, missing fields, malformed types)
2. Gaming Profile:
   - Base args permutation stress (empty, duplicates [-gpu swiftshader, -gpu auto, -gpu host], unrecognized)
   - Incomplete parameter flag stress (trailing -gpu without value)
   - Process scheduling edge cases (PID -1, 0, 4, 999999)
   - Scrcpy args stress (FPS 60, 120, 144, 240, 0, -1)
"""

import os
import sys
import json
import time
import psutil
import tempfile
import threading
import unittest
from typing import List, Dict, Any

from nexus.macro_engine import MacroEngine, MacroStep, MacroScript
from nexus.gaming_profile import GamingModeProfile, GamingProfileManager


class TestMacroEngineStress(unittest.TestCase):
    """Adversarial stress testing for MacroEngine."""

    def test_speed_scaling_precision(self):
        """Test playback timing across 0.1x, 1.0x, 5.0x, 10.0x, 100.0x speeds."""
        steps = [
            MacroStep(timestamp_ms=0, action=0, x_norm=0.5, y_norm=0.5),
            MacroStep(timestamp_ms=100, action=1, x_norm=0.5, y_norm=0.5),
        ]
        test_speeds = [0.1, 1.0, 5.0, 10.0, 100.0]
        results = {}

        for spd in test_speeds:
            engine = MacroEngine()
            t0 = time.perf_counter()
            engine.play(steps, repeat_count=1, speed=spd)
            while engine.is_playing:
                time.sleep(0.001)
            actual_elapsed = time.perf_counter() - t0
            clamped_spd = max(0.1, min(10.0, spd))
            expected_clamped = 0.100 / clamped_spd
            expected_unclamped = 0.100 / spd
            results[spd] = {
                "actual_ms": actual_elapsed * 1000,
                "expected_clamped_ms": expected_clamped * 1000,
                "expected_unclamped_ms": expected_unclamped * 1000,
                "ratio": actual_elapsed / expected_clamped
            }
            # Verify reasonable proximity to clamped speed
            self.assertFalse(engine.is_playing)
            self.assertEqual(len(engine.dispatched_events), 2)
            # Timing should be within 50ms jitter tolerance on Windows
            self.assertLess(abs(actual_elapsed - expected_clamped), 0.05)

        print("\n[MacroEngine] Playback Speed Timing Results:")
        for spd, data in results.items():
            print(f"  Speed {spd:>5}x: actual={data['actual_ms']:.2f}ms, "
                  f"expected_clamped={data['expected_clamped_ms']:.2f}ms "
                  f"(unclamped={data['expected_unclamped_ms']:.2f}ms), ratio={data['ratio']:.2f}")

    def test_cancellation_race_conditions(self):
        """Test immediate cancellation after 1ms, 5ms, 10ms across 100 iterations."""
        steps = [
            MacroStep(timestamp_ms=0, action=0, x_norm=0.5, y_norm=0.5),
            MacroStep(timestamp_ms=200, action=2, x_norm=0.6, y_norm=0.6),
            MacroStep(timestamp_ms=500, action=1, x_norm=0.6, y_norm=0.6),
        ]
        delays = [0.001, 0.005, 0.010]
        total_iterations = 0
        failed_is_playing = 0
        orphan_threads = 0

        engine = MacroEngine()
        for delay in delays:
            for _ in range(100):
                total_iterations += 1
                engine.play(steps, repeat_count=0, speed=1.0)
                time.sleep(delay)
                engine.stop()
                if engine.is_playing:
                    failed_is_playing += 1
                if engine._play_thread is not None and engine._play_thread.is_alive():
                    orphan_threads += 1

        print(f"\n[MacroEngine] Cancellation Race Results: {total_iterations} iterations, "
              f"failed_is_playing={failed_is_playing}, orphan_threads={orphan_threads}")
        self.assertEqual(failed_is_playing, 0, f"is_playing was True after stop in {failed_is_playing} runs")
        self.assertEqual(orphan_threads, 0, f"Orphan thread remained in {orphan_threads} runs")

    def test_large_script_volume_10k_steps(self):
        """Test recording and playback of 10,000 steps with rapid touch and key events."""
        proc = psutil.Process(os.getpid())
        mem_before = proc.memory_info().rss / (1024 * 1024)

        engine = MacroEngine()
        engine.start_recording()

        t0_rec = time.perf_counter()
        for i in range(10000):
            if i % 2 == 0:
                engine.record_touch(action=2, x_norm=(i % 1000) / 1000.0, y_norm=(i % 1000) / 1000.0)
            else:
                engine.record_key(is_down=(i % 4 == 1), keycode=19 + (i % 5))
        rec_time = time.perf_counter() - t0_rec
        script = engine.stop_recording()

        mem_after_rec = proc.memory_info().rss / (1024 * 1024)
        mem_growth_mb = mem_after_rec - mem_before

        self.assertEqual(len(script.steps), 10000)
        self.assertLess(mem_growth_mb, 20.0, f"Excessive memory growth: {mem_growth_mb:.2f}MB")

        # Playback test with callback
        dispatched = []
        engine.event_dispatch_callback = lambda s: dispatched.append(s)

        t0_play = time.perf_counter()
        engine.play(script.steps, repeat_count=1, speed=10.0)
        while engine.is_playing:
            time.sleep(0.005)
        play_time = time.perf_counter() - t0_play

        self.assertEqual(len(dispatched), 10000)
        print(f"\n[MacroEngine] 10k Steps: recorded in {rec_time:.4f}s, replayed in {play_time:.4f}s, "
              f"memory delta={mem_growth_mb:.2f}MB")

    def test_edge_cases_empty_and_zero_timestamps(self):
        """Test empty script, identical 0ms timestamps, and negative/out-of-bound coords."""
        engine = MacroEngine()

        # 1. Empty script
        engine.play([], repeat_count=1)
        time.sleep(0.02)
        self.assertFalse(engine.is_playing)
        self.assertEqual(len(engine.dispatched_events), 0)

        # 2. Identical 0ms timestamps
        zero_steps = [
            MacroStep(timestamp_ms=0, action=0, x_norm=0.1, y_norm=0.1),
            MacroStep(timestamp_ms=0, action=2, x_norm=0.2, y_norm=0.2),
            MacroStep(timestamp_ms=0, action=1, x_norm=0.2, y_norm=0.2),
        ]
        engine.play(zero_steps, repeat_count=1, speed=1.0)
        while engine.is_playing:
            time.sleep(0.001)
        self.assertEqual(len(engine.dispatched_events), 3)

        # 3. Coordinate clamping in record_touch
        engine.start_recording()
        engine.record_touch(action=0, x_norm=-0.5, y_norm=1.5)
        engine.record_touch(action=1, x_norm=2.0, y_norm=-1.0)
        clamped_script = engine.stop_recording()
        self.assertEqual(clamped_script.steps[0].x_norm, 0.0)
        self.assertEqual(clamped_script.steps[0].y_norm, 1.0)
        self.assertEqual(clamped_script.steps[1].x_norm, 1.0)
        self.assertEqual(clamped_script.steps[1].y_norm, 0.0)

    def test_json_roundtrip_stress_and_corruption(self):
        """Test corrupt JSON, missing fields, and malformed types."""
        # 1. Corrupt JSON syntax
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write("{invalid json syntax, missing braces")
            p1 = f.name
        try:
            with self.assertRaises(json.JSONDecodeError):
                MacroScript.load_from_file(p1)
        finally:
            if os.path.exists(p1):
                os.remove(p1)

        # 2. Empty JSON dict ({})
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write("{}")
            p2 = f.name
        try:
            s2 = MacroScript.load_from_file(p2)
            self.assertEqual(s2.name, "Macro Script")
            self.assertEqual(len(s2.steps), 0)
            self.assertEqual(s2.duration_ms, 0)
        finally:
            if os.path.exists(p2):
                os.remove(p2)

        # 3. Missing fields inside step dict ({'steps': [{}]})
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            json.dump({"steps": [{}]}, f)
            p3 = f.name
        try:
            s3 = MacroScript.load_from_file(p3)
            self.assertEqual(len(s3.steps), 1)
            self.assertEqual(s3.steps[0].timestamp_ms, 0)
            self.assertEqual(s3.steps[0].action, 0)
            self.assertEqual(s3.steps[0].x_norm, 0.0)
        finally:
            if os.path.exists(p3):
                os.remove(p3)

        # 4. Malformed type in field (string for timestamp_ms)
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            json.dump({"steps": [{"timestamp_ms": "not_an_int"}]}, f)
            p4 = f.name
        try:
            with self.assertRaises(ValueError):
                MacroScript.load_from_file(p4)
        finally:
            if os.path.exists(p4):
                os.remove(p4)


class TestGamingProfileStress(unittest.TestCase):
    """Adversarial stress testing for GamingModeProfile."""

    def test_base_args_empty_and_unrecognized(self):
        """Test empty base args and unrecognized custom flags."""
        # Empty base args
        res_empty = GamingModeProfile.get_gaming_launch_args("test", [])
        self.assertIn("-gpu", res_empty)
        self.assertEqual(res_empty[res_empty.index("-gpu") + 1], "host")
        self.assertIn("-cpu", res_empty)
        self.assertEqual(res_empty[res_empty.index("-cpu") + 1], "host")

        # Unrecognized custom flags preserved
        base_custom = ["emulator.exe", "-unrecognized_flag", "foo", "-custom_param"]
        res_custom = GamingModeProfile.get_gaming_launch_args("test", base_custom)
        self.assertEqual(res_custom[0], "emulator.exe")
        self.assertIn("-unrecognized_flag", res_custom)
        self.assertIn("foo", res_custom)
        self.assertIn("-custom_param", res_custom)
        self.assertIn("-gpu", res_custom)

    def test_base_args_duplicate_flags_stress(self):
        """
        Adversarial test: pass base args with duplicate flags
        ['-gpu swiftshader', '-gpu auto', '-gpu host'].
        Verify whether get_gaming_launch_args produces a clean list without duplicate flags.
        """
        base_duplicates = [
            "emulator.exe",
            "-gpu", "swiftshader",
            "-gpu", "auto",
            "-gpu", "host"
        ]
        res = GamingModeProfile.get_gaming_launch_args("test", base_duplicates)
        gpu_count = res.count("-gpu")
        print(f"\n[GamingProfile] Duplicate -gpu flags count in result: {gpu_count} (result={res})")

        # Objective check: flag list must NOT have duplicate flags
        self.assertEqual(
            gpu_count, 1,
            f"Adversarial failure: get_gaming_launch_args produced {gpu_count} duplicate '-gpu' flags: {res}"
        )

    def test_incomplete_trailing_parameter_flag_stress(self):
        """
        Adversarial test: pass incomplete parameter flag at the end of base_args
        without a parameter value (e.g. ['emulator.exe', '-gpu']).
        Verify whether get_gaming_launch_args handles it gracefully or crashes with IndexError.
        """
        base_incomplete = ["emulator.exe", "-gpu"]
        try:
            res = GamingModeProfile.get_gaming_launch_args("test", base_incomplete)
            self.assertIn("-gpu", res)
            self.assertEqual(res[res.index("-gpu") + 1], "host")
            print(f"\n[GamingProfile] Incomplete trailing flag handled: {res}")
        except IndexError as e:
            self.fail(f"Adversarial failure: get_gaming_launch_args crashed with IndexError on incomplete flag: {e}")

    def test_process_scheduling_edge_cases(self):
        """Test negative PIDs, non-existent PIDs, PID 0, PID 4 (System)."""
        test_pids = [-1, 0, 4, 999999]
        for pid in test_pids:
            try:
                res = GamingModeProfile.optimize_host_process_scheduling(qemu_pid=pid)
                self.assertIsInstance(res, dict)
                self.assertIn("timer_elevated", res)
                self.assertIn("p_cores", res)
                self.assertIn("qemu_scheduled", res)
                self.assertFalse(res["qemu_scheduled"])
            except Exception as e:
                self.fail(f"Uncaught exception for PID {pid}: {type(e).__name__}: {e}")

        print("\n[GamingProfile] Process scheduling edge case PIDs passed without uncaught crashes.")

    def test_scrcpy_custom_fps_formatting(self):
        """Test custom FPS values (60, 120, 144, 240, 0, -1)."""
        fps_values = [60, 120, 144, 240, 0, -1]
        for fps in fps_values:
            args = GamingModeProfile.get_gaming_scrcpy_args("emulator-5554", target_fps=fps)
            self.assertIn("-s", args)
            self.assertEqual(args[1], "emulator-5554")
            self.assertIn(f"--max-fps={fps}", args)

        print("\n[GamingProfile] Scrcpy FPS formatting verified for all target FPS inputs.")


if __name__ == "__main__":
    unittest.main()
