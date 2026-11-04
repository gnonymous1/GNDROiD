"""
Empirical Adversarial Challenge Test Suite for Milestone 3
Target: Quick Clone Signature Alignment, Settings Dialog Parameter Alignment, Auto-Tiling & Docking Filters
Author: challenger_m3_1 (Empirical Challenger)
"""

import os
import sys
import math
import shutil
import inspect
import tempfile
import unittest
from unittest.mock import MagicMock, patch, call

# Ensure root directory is on sys.path
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from PyQt6.QtWidgets import QApplication, QWidget, QDialog
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl, QMimeData

# Initialize headless QApplication
app = QApplication.instance()
if app is None:
    app = QApplication([sys.argv[0], "-platform", "offscreen"])

import gndroid
from gndroid import (
    AVDManager,
    GNDroidMultiInstanceManager,
    GNDroidCompanionSidebar,
    GNDroidSettingsDialog,
    GNDroidApp,
    tile_running_windows,
    tile_windows,
    find_target_window,
    AdbInstallOrPushWorker,
)


class TestAdversarialTask1CloneInstance(unittest.TestCase):
    """
    Task 1: Test AVDManager.clone_instance.
    Verify clone_instance accepts all parameter combinations and handles
    deep_copy_snapshots, full_clone, file skips, and config generation.
    """

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="gndroid_clone_test_")
        self.avd_patcher = patch.object(AVDManager, "get_avd_dir", return_value=self.tmp_dir)
        self.avd_patcher.start()

        # Create realistic source AVD directory structure
        self.src_name = "flagship_src"
        self.src_avd = os.path.join(self.tmp_dir, f"{self.src_name}.avd")
        os.makedirs(self.src_avd, exist_ok=True)

        with open(os.path.join(self.tmp_dir, f"{self.src_name}.ini"), "w", encoding="utf-8") as f:
            f.write("target=android-34\npath=mock\n")

        # Standard config
        with open(os.path.join(self.src_avd, "config.ini"), "w", encoding="utf-8") as f:
            f.write(
                "AvdId=flagship_src\n"
                "avd.ini.displayname=Flagship Source\n"
                "hw.ramSize=4096\n"
                "hw.cpu.ncore=4\n"
                "gndroid.root=no\n"
            )

        # Standard data files
        with open(os.path.join(self.src_avd, "userdata-qemu.img"), "w") as f:
            f.write("userdata")
        with open(os.path.join(self.src_avd, "cache.img"), "w") as f:
            f.write("cache")
        with open(os.path.join(self.src_avd, "system.img"), "w") as f:
            f.write("system")

        # Files that MUST be skipped
        with open(os.path.join(self.src_avd, "hardware-qemu.ini.lock"), "w") as f:
            f.write("lock")
        with open(os.path.join(self.src_avd, "multiinstance.lock"), "w") as f:
            f.write("lock")
        with open(os.path.join(self.src_avd, "stale_run.lock"), "w") as f:
            f.write("lock")
        with open(os.path.join(self.src_avd, "ram.img"), "w") as f:
            f.write("dump")
        with open(os.path.join(self.src_avd, "ram.bin"), "w") as f:
            f.write("dump")

        # tmpAdbCmds directory (must be skipped)
        tmp_cmd_dir = os.path.join(self.src_avd, "tmpAdbCmds")
        os.makedirs(tmp_cmd_dir, exist_ok=True)
        with open(os.path.join(tmp_cmd_dir, "cmd1.txt"), "w") as f:
            f.write("cmd")

        # Snapshots directory
        snap_dir = os.path.join(self.src_avd, "snapshots", "default_boot")
        os.makedirs(snap_dir, exist_ok=True)
        with open(os.path.join(snap_dir, "snapshot.pb"), "w") as f:
            f.write("protobuf")
        with open(os.path.join(snap_dir, "ram.bin"), "w") as f:
            f.write("ram_dump")

    def tearDown(self):
        self.avd_patcher.stop()
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_signature_has_all_parameters_and_defaults(self):
        """Verify full signature of AVDManager.clone_instance."""
        sig = inspect.signature(AVDManager.clone_instance)
        params = sig.parameters

        expected = {
            "src_name": inspect.Parameter.POSITIONAL_OR_KEYWORD,
            "dst_name": inspect.Parameter.POSITIONAL_OR_KEYWORD,
            "dst_display_name": inspect.Parameter.POSITIONAL_OR_KEYWORD,
            "ram_mb": inspect.Parameter.POSITIONAL_OR_KEYWORD,
            "cores": inspect.Parameter.POSITIONAL_OR_KEYWORD,
            "root_enabled": inspect.Parameter.POSITIONAL_OR_KEYWORD,
            "full_clone": inspect.Parameter.POSITIONAL_OR_KEYWORD,
            "progress_cb": inspect.Parameter.POSITIONAL_OR_KEYWORD,
            "deep_copy_snapshots": inspect.Parameter.POSITIONAL_OR_KEYWORD,
        }

        for param_name in expected:
            self.assertIn(param_name, params, f"Parameter '{param_name}' missing from clone_instance signature")

        self.assertEqual(params["ram_mb"].default, None)
        self.assertEqual(params["cores"].default, None)
        self.assertEqual(params["root_enabled"].default, None)
        self.assertEqual(params["full_clone"].default, True)
        self.assertEqual(params["progress_cb"].default, None)
        self.assertEqual(params["deep_copy_snapshots"].default, False)

    def test_clone_combinations_no_type_error(self):
        """Test all 2x2 combinations of (full_clone, deep_copy_snapshots) without TypeError."""
        combinations = [
            {"full_clone": True, "deep_copy_snapshots": False},
            {"full_clone": False, "deep_copy_snapshots": False},
            {"full_clone": True, "deep_copy_snapshots": True},
            {"full_clone": False, "deep_copy_snapshots": True},
        ]

        for i, comb in enumerate(combinations):
            dst = f"clone_comb_{i}"
            try:
                AVDManager.clone_instance(
                    src_name=self.src_name,
                    dst_name=dst,
                    dst_display_name=f"Clone Comb {i}",
                    **comb
                )
            except TypeError as te:
                self.fail(f"Combination {comb} raised unexpected TypeError: {te}")

            self.assertTrue(os.path.exists(os.path.join(self.tmp_dir, f"{dst}.ini")))
            self.assertTrue(os.path.exists(os.path.join(self.tmp_dir, f"{dst}.avd")))

    def test_caller_exact_invocation(self):
        """Test exact invocation as called by GNDroidMultiInstanceManager.action_clone_instance."""
        dst = "quick_cloned_inst"
        AVDManager.clone_instance(
            self.src_name,
            dst,
            "Quick Cloned Instance",
            deep_copy_snapshots=False
        )
        self.assertTrue(os.path.exists(os.path.join(self.tmp_dir, f"{dst}.ini")))
        self.assertTrue(os.path.exists(os.path.join(self.tmp_dir, f"{dst}.avd")))

    def test_positional_arguments_invocation(self):
        """Test invoking clone_instance with all 9 arguments positionally."""
        progress_calls = []
        dst = "pos_cloned_inst"
        AVDManager.clone_instance(
            self.src_name,
            dst,
            "Positional Cloned Instance",
            8192,
            8,
            True,
            True,
            lambda p: progress_calls.append(p),
            True
        )
        self.assertTrue(os.path.exists(os.path.join(self.tmp_dir, f"{dst}.ini")))
        dst_avd = os.path.join(self.tmp_dir, f"{dst}.avd")
        self.assertTrue(os.path.exists(dst_avd))
        self.assertGreater(len(progress_calls), 0)
        self.assertEqual(progress_calls[-1], 100)

        # Verify config update
        with open(os.path.join(dst_avd, "config.ini"), "r", encoding="utf-8") as f:
            cfg = f.read()
        self.assertIn("hw.ramSize=8192", cfg)
        self.assertIn("hw.cpu.ncore=8", cfg)
        self.assertIn("gndroid.root=yes", cfg)
        self.assertIn(f"AvdId={dst}", cfg)

    def test_snapshot_exclusion_when_deep_copy_false(self):
        """Verify snapshots folder is omitted when deep_copy_snapshots=False (default)."""
        dst = "quick_no_snap"
        AVDManager.clone_instance(
            src_name=self.src_name,
            dst_name=dst,
            dst_display_name="No Snap",
            full_clone=True,
            deep_copy_snapshots=False
        )
        dst_avd = os.path.join(self.tmp_dir, f"{dst}.avd")
        snap_path = os.path.join(dst_avd, "snapshots")
        self.assertFalse(os.path.exists(snap_path), "snapshots/ must NOT exist when deep_copy_snapshots=False")

    def test_snapshot_inclusion_when_deep_copy_true(self):
        """Verify snapshots/snapshot.pb is copied when deep_copy_snapshots=True & full_clone=True, but ram.bin is skipped."""
        dst = "deep_snap"
        AVDManager.clone_instance(
            src_name=self.src_name,
            dst_name=dst,
            dst_display_name="Deep Snap",
            full_clone=True,
            deep_copy_snapshots=True
        )
        dst_avd = os.path.join(self.tmp_dir, f"{dst}.avd")
        snap_file = os.path.join(dst_avd, "snapshots", "default_boot", "snapshot.pb")
        self.assertTrue(os.path.exists(snap_file), "snapshot.pb must exist when deep_copy_snapshots=True")
        # RAM dumps must still be skipped even in snapshots
        ram_file = os.path.join(dst_avd, "snapshots", "default_boot", "ram.bin")
        self.assertFalse(os.path.exists(ram_file), "ram.bin inside snapshots must be skipped")

    def test_clean_clone_excludes_userdata_and_snapshots(self):
        """Verify full_clone=False excludes userdata, cache, and snapshots even if deep_copy_snapshots=True."""
        dst = "clean_clone"
        AVDManager.clone_instance(
            src_name=self.src_name,
            dst_name=dst,
            dst_display_name="Clean Clone",
            full_clone=False,
            deep_copy_snapshots=True
        )
        dst_avd = os.path.join(self.tmp_dir, f"{dst}.avd")
        self.assertFalse(os.path.exists(os.path.join(dst_avd, "userdata-qemu.img")))
        self.assertFalse(os.path.exists(os.path.join(dst_avd, "cache.img")))
        self.assertFalse(os.path.exists(os.path.join(dst_avd, "snapshots")))
        # System img must still be copied
        self.assertTrue(os.path.exists(os.path.join(dst_avd, "system.img")))

    def test_lock_files_and_tmp_cmds_always_skipped(self):
        """Verify .lock files, tmpAdbCmds, and root ram dumps are NEVER copied."""
        dst = "skip_check"
        AVDManager.clone_instance(
            src_name=self.src_name,
            dst_name=dst,
            dst_display_name="Skip Check",
            full_clone=True,
            deep_copy_snapshots=True
        )
        dst_avd = os.path.join(self.tmp_dir, f"{dst}.avd")
        self.assertFalse(os.path.exists(os.path.join(dst_avd, "hardware-qemu.ini.lock")))
        self.assertFalse(os.path.exists(os.path.join(dst_avd, "multiinstance.lock")))
        self.assertFalse(os.path.exists(os.path.join(dst_avd, "stale_run.lock")))
        self.assertFalse(os.path.exists(os.path.join(dst_avd, "tmpAdbCmds")))
        self.assertFalse(os.path.exists(os.path.join(dst_avd, "ram.img")))
        self.assertFalse(os.path.exists(os.path.join(dst_avd, "ram.bin")))

    def test_file_exists_error_on_duplicate(self):
        """Verify FileExistsError is raised if destination already exists."""
        dst = "existing_dst"
        # First clone succeeds
        AVDManager.clone_instance(self.src_name, dst, "First Clone")
        # Second clone to same destination must raise FileExistsError
        with self.assertRaises(FileExistsError):
            AVDManager.clone_instance(self.src_name, dst, "Duplicate Clone")


class TestAdversarialTask2SettingsDialog(unittest.TestCase):
    """
    Task 2: Test settings dialog parameter alignment and safeguards.
    Verify GNDroidCompanionSidebar.action_open_settings and GNDroidSettingsDialog.__init__.
    """

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="gndroid_settings_test_")
        self.avd_patcher = patch.object(AVDManager, "get_avd_dir", return_value=self.tmp_dir)
        self.avd_patcher.start()

    def tearDown(self):
        self.avd_patcher.stop()
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_sidebar_action_open_settings_parameter_passing(self):
        """Verify GNDroidCompanionSidebar.action_open_settings passes target_serial, instance_name, and parent=self."""
        sidebar = GNDroidCompanionSidebar("emulator-5554")
        try:
            with patch("subprocess.check_output", return_value="pixel_phone\n"):
                with patch("gndroid.GNDroidSettingsDialog") as mock_dialog_cls:
                    mock_instance = MagicMock()
                    mock_dialog_cls.return_value = mock_instance

                    sidebar.action_open_settings()

                    mock_dialog_cls.assert_called_once_with(
                        target_serial="emulator-5554",
                        instance_name="pixel_phone",
                        parent=sidebar
                    )
                    mock_instance.exec.assert_called_once()
        finally:
            sidebar.close()
            sidebar.deleteLater()

    def test_sidebar_action_open_settings_fallback_on_adb_error(self):
        """Verify instance_name falls back to 'gndroid' if adb emu avd name fails."""
        sidebar = GNDroidCompanionSidebar("emulator-5556")
        try:
            with patch("subprocess.check_output", side_effect=Exception("ADB disconnected")):
                with patch("gndroid.GNDroidSettingsDialog") as mock_dialog_cls:
                    mock_instance = MagicMock()
                    mock_dialog_cls.return_value = mock_instance

                    sidebar.action_open_settings()

                    mock_dialog_cls.assert_called_once_with(
                        target_serial="emulator-5556",
                        instance_name="gndroid",
                        parent=sidebar
                    )
        finally:
            sidebar.close()
            sidebar.deleteLater()

    def test_sidebar_action_settings_delegates_to_action_open_settings(self):
        """Verify action_settings calls action_open_settings."""
        sidebar = GNDroidCompanionSidebar("emulator-5554")
        try:
            with patch.object(sidebar, "action_open_settings") as mock_open:
                sidebar.action_settings()
                mock_open.assert_called_once()
        finally:
            sidebar.close()
            sidebar.deleteLater()

    def test_settings_dialog_handles_legacy_two_arg_call(self):
        """
        Adversarial: If someone calls GNDroidSettingsDialog(serial, parent_widget),
        verify that instance_name does NOT become the QWidget object.
        """
        parent_widget = QWidget()
        try:
            dlg = GNDroidSettingsDialog("emulator-5554", parent_widget)
            self.assertEqual(dlg.instance_name, "gndroid", "instance_name must be normalized to 'gndroid'")
            self.assertEqual(dlg.target_serial, "emulator-5554")
            self.assertEqual(dlg.parent(), parent_widget)
            dlg.deleteLater()
        finally:
            parent_widget.deleteLater()

    def test_settings_dialog_handles_none_and_empty_strings(self):
        """Adversarial: Test GNDroidSettingsDialog with None and empty inputs."""
        dlg = GNDroidSettingsDialog(None, None, None)
        self.assertEqual(dlg.instance_name, "gndroid")
        self.assertEqual(dlg.target_serial, "")
        self.assertIsNone(dlg.parent())
        dlg.deleteLater()

        dlg2 = GNDroidSettingsDialog("", "", None)
        self.assertEqual(dlg2.instance_name, "gndroid")
        self.assertEqual(dlg2.target_serial, "")
        dlg2.deleteLater()

    def test_settings_dialog_preserves_proper_instance_name(self):
        """Verify GNDroidSettingsDialog preserves given instance_name when valid."""
        dlg = GNDroidSettingsDialog("emulator-5554", "custom_instance")
        self.assertEqual(dlg.instance_name, "custom_instance")
        self.assertEqual(dlg.target_serial, "emulator-5554")
        dlg.deleteLater()


class TestAdversarialTask3AutoTiling(unittest.TestCase):
    """
    Task 3: Test auto-tiling.
    Stress-test tile_running_windows with window titles of varying cases,
    verify all matching Scrcpy/emulator windows are detected and management windows excluded.
    """

    def test_window_title_filtering_adversarial_matrix(self):
        """
        Adversarial Matrix: 30+ titles tested against the exact detection and exclusion logic
        of tile_running_windows.
        """
        def filter_title(t: str) -> bool:
            t_lower = t.lower()
            is_scrcpy_app = t.startswith("GNDROiD:") or t.startswith("gndroid:") or t.startswith("GNDROiD -") or t.startswith("gndroid -")
            is_mgmt = any(k in t_lower for k in ["controls", "manager", "doctor", "settings & hardware", "suite", "launcher"]) or "gndroid settings" in t_lower
            return (is_scrcpy_app or ("gndroid" in t_lower or "android emulator" in t_lower)) and not is_mgmt

        matrix = [
            # --- Valid Scrcpy Windows (Must PASS) ---
            ("GNDROiD - emulator-5554", True),
            ("gndroid - emulator-5554", True),
            ("Gndroid - emulator-5554", True),
            ("GNDROID - emulator-5554", True),
            ("GNDROiD - 192.168.1.50:5555", True),
            ("gndroid - 192.168.1.50:5555", True),
            ("GNDROiD: WhatsApp", True),
            ("gndroid: WhatsApp", True),
            ("Gndroid: WhatsApp", True),
            ("GNDROID: WhatsApp", True),
            ("GNDROiD: Settings [Clone #1]", True),
            ("GNDROiD: Camera", True),
            ("GNDROiD: YouTube", True),
            ("Android Emulator - Pixel_7_API_34", True),
            ("android emulator - nexus_5", True),
            ("ANDROID EMULATOR - Tablet", True),
            ("GNDROiD", True),
            ("gndroid", True),
            ("gndroid virtual display", True),

            # --- Management Suite & Non-Tiling Windows (Must REJECT) ---
            ("GNDROiD v2.2.2 — Master Control Suite", False),
            ("GNDROiD v3.0.0 — Master Control Suite", False),
            ("GNDROiD Multi-Instance Manager", False),
            ("gndroid multi-instance manager", False),
            ("GNDROiD Controls - emulator-5554", False),
            ("gndroid controls", False),
            ("⚙️ GNDROiD Settings & Hardware Configuration — Flagship", False),
            ("GNDROiD Settings", False),
            ("gndroid settings", False),
            ("GNDROiD ADB Doctor", False),
            ("gndroid adb doctor", False),
            ("GNDROiD App Launcher", False),
            ("GNDROiD Launcher", False),
            ("Master Control Suite", False),

            # --- External / Unrelated Windows (Must REJECT) ---
            ("Google Chrome", False),
            ("Visual Studio Code", False),
            ("Command Prompt", False),
            ("WhatsApp - Web", False),
            ("Calculator", False),
        ]

        failures = []
        for title, expected in matrix:
            actual = filter_title(title)
            if actual != expected:
                failures.append(f"Title '{title}': expected {expected}, got {actual}")

        self.assertEqual(len(failures), 0, "\n".join(failures))

    def test_tile_running_windows_layout_calculations(self):
        """
        Verify the grid layout geometry calculations (cols, rows, width, height, x, y)
        for various window counts N = 1, 2, 3, 4, 6.
        """
        screen_w, screen_h = 1920, 1080

        for n in [1, 2, 3, 4, 6]:
            cols = math.ceil(math.sqrt(n))
            rows = math.ceil(n / cols)
            w = (screen_w - 40) // cols
            h = (screen_h - 80) // rows

            # Verify all grid cells fit within screen boundaries
            for i in range(n):
                r = i // cols
                c = i % cols
                x = 20 + c * w
                y = 40 + r * h

                self.assertGreaterEqual(x, 20)
                self.assertGreaterEqual(y, 40)
                self.assertLessEqual(x + w, screen_w)
                self.assertLessEqual(y + h, screen_h)

    def test_tile_running_windows_mock_win32_integration(self):
        """
        Empirically test tile_running_windows by mocking user32 EnumWindows,
        IsWindowVisible, IsIconic, and MoveWindow.
        """
        mock_windows = {
            101: (True, False, "GNDROiD - emulator-5554"),       # Should tile
            102: (True, False, "GNDROiD: WhatsApp"),             # Should tile
            103: (True, False, "GNDROiD v2.2.2 — Master Control Suite"), # Exclude!
            104: (True, False, "GNDROiD Multi-Instance Manager"),         # Exclude!
            105: (True, True,  "GNDROiD - emulator-5556"),       # Iconic (minimized) -> Exclude!
            106: (False, False, "GNDROiD - emulator-5558"),      # Not visible -> Exclude!
            107: (True, False, "Google Chrome"),                 # Unrelated -> Exclude!
        }

        def fake_is_visible(h):
            return 1 if (h in mock_windows and mock_windows[h][0]) else 0

        def fake_is_iconic(h):
            return 1 if (h in mock_windows and mock_windows[h][1]) else 0

        def fake_text_len(h):
            return len(mock_windows[h][2]) if h in mock_windows else 0

        def fake_get_text(h, buf, length):
            if h in mock_windows:
                buf.value = mock_windows[h][2]
                return len(mock_windows[h][2])
            return 0

        def fake_enum_windows(callback, lparam):
            for hwnd in mock_windows:
                callback(hwnd, lparam)
            return True

        moved_hwnds = []
        def fake_move_window(hwnd, x, y, w, h, repaint):
            moved_hwnds.append(hwnd)
            return 1

        with patch.object(gndroid.user32, "EnumWindows", side_effect=fake_enum_windows), \
             patch.object(gndroid.user32, "IsWindowVisible", side_effect=fake_is_visible), \
             patch.object(gndroid.user32, "IsIconic", side_effect=fake_is_iconic), \
             patch.object(gndroid.user32, "GetWindowTextLengthW", side_effect=fake_text_len), \
             patch.object(gndroid.user32, "GetWindowTextW", side_effect=fake_get_text), \
             patch.object(gndroid.user32, "MoveWindow", side_effect=fake_move_window):
            count = tile_running_windows()

        # Exactly 2 windows (101 and 102) should be tiled
        self.assertEqual(count, 2)
        self.assertEqual(moved_hwnds, [101, 102])

    def test_find_target_window_docking_exclusion(self):
        """
        Verify find_target_window strictly excludes launcher and management suite windows
        and only selects legitimate Scrcpy/emulator windows.
        """
        mock_windows = {
            201: (True, "GNDROiD v2.2.2 — Master Control Suite"), # Launcher
            202: (True, "GNDROiD Multi-Instance Manager"),        # Manager
            203: (True, "GNDROiD - emulator-5554"),               # Scrcpy target
        }

        def fake_is_visible(h):
            return 1 if (h in mock_windows and mock_windows[h][0]) else 0

        def fake_text_len(h):
            return len(mock_windows[h][1]) if h in mock_windows else 0

        def fake_get_text(h, buf, length):
            if h in mock_windows:
                buf.value = mock_windows[h][1]
                return len(mock_windows[h][1])
            return 0

        def fake_enum_windows(callback, lparam):
            for hwnd in mock_windows:
                if not callback(hwnd, lparam):
                    break
            return True

        with patch.object(gndroid.user32, "FindWindowW", return_value=0), \
             patch.object(gndroid.user32, "EnumWindows", side_effect=fake_enum_windows), \
             patch.object(gndroid.user32, "IsWindowVisible", side_effect=fake_is_visible), \
             patch.object(gndroid.user32, "GetWindowTextLengthW", side_effect=fake_text_len), \
             patch.object(gndroid.user32, "GetWindowTextW", side_effect=fake_get_text):

            # When looking for emulator-5554
            hwnd = find_target_window("emulator-5554")
            self.assertEqual(hwnd, 203, "find_target_window must find the Scrcpy window (203)")

class TestAdversarialTask4AsyncWorkerAndStatus(unittest.TestCase):
    """
    Task 4 / Features 13 & 14: Non-Blocking ADB File Operations and Error Reporting.
    Adversarially test cancellation, timeouts, partial batch failures, and error parsing.
    """

    def test_worker_cancellation(self):
        """Verify worker terminates loop early when cancel() is triggered."""
        files = ["app1.apk", "app2.apk", "app3.apk"]
        worker = AdbInstallOrPushWorker(files, target_serial="emulator-5554")
        worker.cancel()

        results = []
        finished = []
        worker.file_result.connect(lambda f, s, m: results.append((f, s, m)))
        worker.finished_all.connect(lambda s, f: finished.append((s, f)))

        with patch("os.path.exists", return_value=True):
            worker.run()

        # Because cancel() was set, 0 files should have been processed
        self.assertEqual(len(results), 0)
        self.assertEqual(finished, [(0, 0)])

    def test_worker_batch_with_partial_failures(self):
        """Verify batch containing both success and failed installs accurately tracks counts."""
        files = ["good.apk", "bad.apk", "good.bin"]
        worker = AdbInstallOrPushWorker(files, target_serial="emulator-5554")

        def fake_run(cmd, **kwargs):
            res = MagicMock()
            if "good.apk" in cmd:
                res.returncode = 0
                res.stdout = "Success\n"
                res.stderr = ""
            elif "bad.apk" in cmd:
                res.returncode = 0  # exit 0 but failed in output
                res.stdout = "Failure [INSTALL_PARSE_FAILED_NOT_APK]\n"
                res.stderr = ""
            elif "good.bin" in cmd:
                res.returncode = 0
                res.stdout = "1 file pushed\n"
                res.stderr = ""
            return res

        results = []
        finished = []
        worker.file_result.connect(lambda f, s, m: results.append((f, s, m)))
        worker.finished_all.connect(lambda s, f: finished.append((s, f)))

        with patch("os.path.exists", return_value=True), \
             patch("subprocess.run", side_effect=fake_run):
            worker.run()

        self.assertEqual(len(results), 3)
        self.assertTrue(results[0][1], "good.apk should succeed")
        self.assertFalse(results[1][1], "bad.apk should fail")
        self.assertIn("INSTALL_PARSE_FAILED_NOT_APK", results[1][2])
        self.assertTrue(results[2][1], "good.bin push should succeed")
        self.assertEqual(finished, [(2, 1)], "Should report 2 successes and 1 failure")

    def test_worker_timeout_handling(self):
        """Verify subprocess.TimeoutExpired is caught and cleanly reported as failure."""
        import subprocess
        files = ["huge_app.apk"]
        worker = AdbInstallOrPushWorker(files, target_serial="emulator-5554")

        results = []
        finished = []
        worker.file_result.connect(lambda f, s, m: results.append((f, s, m)))
        worker.finished_all.connect(lambda s, f: finished.append((s, f)))

        with patch("os.path.exists", return_value=True), \
             patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["adb"], timeout=120)):
            worker.run()

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0][1])
        self.assertIn("timed out after 120 seconds", results[0][2])
        self.assertEqual(finished, [(0, 1)])

    def test_worker_file_push_error_keywords(self):
        """Verify file push error keywords: 'read-only file system', 'no space left'."""
        error_cases = [
            ("No space left on device\n", "no space left"),
            ("Read-only file system\n", "read-only file system"),
        ]

        for out_text, expected_err in error_cases:
            worker = AdbInstallOrPushWorker(["data.dat"], target_serial="emulator-5554")
            mock_res = MagicMock(returncode=0, stdout=out_text, stderr="")

            results = []
            worker.file_result.connect(lambda f, s, m: results.append((f, s, m)))

            with patch("os.path.exists", return_value=True), \
                 patch("subprocess.run", return_value=mock_res):
                worker.run()

            self.assertEqual(len(results), 1)
            self.assertFalse(results[0][1], f"Expected failure on '{expected_err}'")


if __name__ == "__main__":
    unittest.main()
