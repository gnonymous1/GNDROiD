"""
tests/test_gaming_profile.py
============================
Comprehensive unit tests for Feature 19 (Gaming Mode Launch Profile).
"""

import sys
import unittest
from unittest.mock import patch, MagicMock

from nexus.gaming_profile import GamingModeProfile, GamingProfileManager


class TestGamingProfileArgs(unittest.TestCase):
    """Tests QEMU and Scrcpy argument generation and merging."""

    def test_alias_and_class_equality(self):
        self.assertIs(GamingProfileManager, GamingModeProfile)

    def test_get_gaming_qemu_args(self):
        args = GamingModeProfile.get_gaming_qemu_args()
        self.assertIn("-gpu", args)
        idx_gpu = args.index("-gpu")
        self.assertEqual(args[idx_gpu + 1], "host")

        self.assertIn("-cpu", args)
        idx_cpu = args.index("-cpu")
        self.assertEqual(args[idx_cpu + 1], "host")

        self.assertIn("-netfast", args)
        self.assertIn("-netdelay", args)
        self.assertIn("none", args)
        self.assertIn("-netspeed", args)
        self.assertIn("full", args)
        self.assertIn("-no-snapshot-load", args)
        self.assertIn("-no-snapshot-save", args)
        self.assertIn("-crash-report-mode", args)
        self.assertIn("never", args)

    def test_merge_gaming_launch_args_cleanly(self):
        base = [
            "emulator.exe", "-avd", "GNDroid_Pixel_8", "-port", "5554",
            "-gpu", "auto", "-netdelay", "20ms", "-netspeed", "100k"
        ]
        merged = GamingModeProfile.get_gaming_launch_args("GNDroid_Pixel_8", base)

        # Base structure preserved
        self.assertEqual(merged[0], "emulator.exe")
        self.assertIn("-avd", merged)
        self.assertIn("GNDroid_Pixel_8", merged)
        self.assertIn("-port", merged)
        self.assertIn("5554", merged)

        # Conflicting flags replaced
        self.assertIn("-gpu", merged)
        self.assertEqual(merged[merged.index("-gpu") + 1], "host")
        self.assertEqual(merged[merged.index("-netdelay") + 1], "none")
        self.assertEqual(merged[merged.index("-netspeed") + 1], "full")

        # Missing gaming flags appended without duplication
        self.assertIn("-cpu", merged)
        self.assertEqual(merged[merged.index("-cpu") + 1], "host")
        self.assertIn("-netfast", merged)
        self.assertIn("-no-snapshot-load", merged)

        # Assert no duplicate flags
        for f in ["-gpu", "-cpu", "-netfast", "-no-snapshot-load", "-no-snapshot-save"]:
            self.assertEqual(merged.count(f), 1, f"Flag {f} appears multiple times")

    def test_get_gaming_scrcpy_args(self):
        serial = "emulator-5554"
        args = GamingModeProfile.get_gaming_scrcpy_args(serial, target_fps=120)

        self.assertIn("-s", args)
        self.assertEqual(args[args.index("-s") + 1], serial)
        self.assertIn("--max-fps=120", args)
        self.assertIn("--video-buffer=0", args)
        self.assertIn("--audio-buffer=20", args)
        self.assertIn("--video-codec=h264", args)
        self.assertIn("--render-driver=direct3d11", args)
        self.assertIn("--gamepad=uhid", args)
        self.assertIn("--mouse=uhid", args)
        self.assertIn("--keyboard=uhid", args)
        self.assertIn("--stay-awake", args)
        self.assertIn("--print-fps", args)

        # Test custom target_fps (144)
        args_144 = GamingModeProfile.get_gaming_scrcpy_args(serial, target_fps=144)
        self.assertIn("--max-fps=144", args_144)


class TestGamingSystemProperties(unittest.TestCase):
    """Tests Android SurfaceFlinger 120Hz system properties and settings."""

    @patch("subprocess.run")
    def test_apply_gaming_system_properties_execution(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        serial = "emulator-5554"

        applied = GamingModeProfile.apply_gaming_system_properties(serial, adb_path="adb")
        self.assertEqual(len(applied), 9)  # 4 setprop + 5 settings put

        # Inspect subprocess calls
        calls = mock_run.call_args_list
        self.assertEqual(len(calls), 9)

        executed_cmds = [" ".join(c[0][0]) for c in calls]

        # Verify SurfaceFlinger properties
        self.assertTrue(any("shell setprop ro.surface_flinger.has_wide_color_display true" in c for c in executed_cmds))
        self.assertTrue(any("shell setprop ro.surface_flinger.has_HDR_display true" in c for c in executed_cmds))
        self.assertTrue(any("shell setprop ro.surface_flinger.max_frame_buffer_acquired_buffers 3" in c for c in executed_cmds))
        self.assertTrue(any("shell setprop ro.sf.lcd_density 500" in c for c in executed_cmds))

        # Verify refresh rate and animation settings
        self.assertTrue(any("shell settings put system peak_refresh_rate 120.0" in c for c in executed_cmds))
        self.assertTrue(any("shell settings put system min_refresh_rate 120.0" in c for c in executed_cmds))
        self.assertTrue(any("shell settings put global animator_duration_scale 0.5" in c for c in executed_cmds))
        self.assertTrue(any("shell settings put global window_animation_scale 0.5" in c for c in executed_cmds))
        self.assertTrue(any("shell settings put global transition_animation_scale 0.5" in c for c in executed_cmds))


class TestHostSchedulingAndPCores(unittest.TestCase):
    """Tests P-core affinity mask and Win32 process priority scheduling."""

    def test_p_core_affinity_mask_logic(self):
        p_cores = GamingModeProfile.get_p_core_affinity_mask()
        self.assertIsInstance(p_cores, list)
        self.assertTrue(len(p_cores) > 0)
        # Verify even numbered cores or valid range
        for core in p_cores:
            self.assertTrue(isinstance(core, int))
            self.assertTrue(core >= 0)

    @patch("psutil.Process")
    def test_optimize_host_process_scheduling(self, mock_proc_cls):
        mock_qemu = MagicMock()
        mock_scrcpy = MagicMock()

        def proc_side_effect(pid):
            if pid == 1001:
                return mock_qemu
            elif pid == 1002:
                return mock_scrcpy
            return MagicMock()

        mock_proc_cls.side_effect = proc_side_effect

        res = GamingModeProfile.optimize_host_process_scheduling(qemu_pid=1001, scrcpy_pid=1002)

        self.assertTrue(res["qemu_scheduled"])
        self.assertTrue(res["scrcpy_scheduled"])
        self.assertTrue(len(res["p_cores"]) > 0)

        # Verify QEMU received cpu_affinity and nice
        mock_qemu.cpu_affinity.assert_called_once_with(res["p_cores"])
        mock_qemu.nice.assert_called_once()

        # Verify Scrcpy received cpu_affinity and nice
        mock_scrcpy.cpu_affinity.assert_called_once_with(res["p_cores"])
        mock_scrcpy.nice.assert_called_once()

    @patch("nexus.gaming_profile.GamingModeProfile.apply_gaming_system_properties")
    @patch("nexus.gaming_profile.GamingModeProfile.optimize_host_process_scheduling")
    def test_apply_runtime_gaming_optimizations(self, mock_sched, mock_props):
        mock_props.return_value = [("setprop", "done")]
        mock_sched.return_value = {"qemu_scheduled": True}

        result = GamingModeProfile.apply_runtime_gaming_optimizations(
            serial="emulator-5554",
            host_pid=1234,
            scrcpy_pid=5678
        )
        self.assertIn("applied_properties", result)
        self.assertIn("host_scheduling", result)
        mock_props.assert_called_once_with("emulator-5554", "adb")
        mock_sched.assert_called_once_with(1234, 5678)


if __name__ == "__main__":
    unittest.main()
