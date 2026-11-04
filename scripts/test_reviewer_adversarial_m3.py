"""
Adversarial Stress Test Suite for Milestone 3 (Python Core GUI & UX Hardening)
Reviewer / Adversarial Critic: reviewer_m3_1
"""

import os
import sys
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock
import subprocess

# Ensure project root is in sys.path
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt

# Initialize headless Qt Application
app = QApplication.instance()
if app is None:
    app = QApplication([sys.argv[0], "-platform", "offscreen"])

import gndroid
from gndroid import (
    AVDManager,
    GNDroidMultiInstanceManager,
    GNDroidCompanionSidebar,
    GNDroidSettingsDialog,
    tile_running_windows,
    tile_windows,
    find_target_window,
    AdbInstallOrPushWorker,
)


class TestAdversarialFeature11Clone(unittest.TestCase):
    """Adversarial stress-testing of AVDManager.clone_instance."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_clone_instance_skips_snapshots_when_deep_copy_snapshots_is_false(self):
        """Verify that when deep_copy_snapshots=False, massive snapshot trees are NOT copied."""
        with patch.object(AVDManager, "get_avd_dir", return_value=self.tmp_dir):
            src_avd = os.path.join(self.tmp_dir, "base.avd")
            os.makedirs(src_avd, exist_ok=True)
            with open(os.path.join(self.tmp_dir, "base.ini"), "w", encoding="utf-8") as f:
                f.write("target=android-34\n")
            with open(os.path.join(src_avd, "config.ini"), "w", encoding="utf-8") as f:
                f.write("hw.ramSize=4096\nhw.cpu.ncore=4\n")

            # Create snapshot hierarchy with dummy large memory dump file
            snap_dir = os.path.join(src_avd, "snapshots", "default_boot")
            os.makedirs(snap_dir, exist_ok=True)
            dummy_ram = os.path.join(snap_dir, "snapshot.ram")
            with open(dummy_ram, "w", encoding="utf-8") as f:
                f.write("DUMMY_RAM_DUMP_DATA")

            # Clone with deep_copy_snapshots=False
            AVDManager.clone_instance(
                src_name="base",
                dst_name="clone_no_snap",
                dst_display_name="Fast Clone",
                deep_copy_snapshots=False
            )

            cloned_snap = os.path.join(self.tmp_dir, "clone_no_snap.avd", "snapshots")
            self.assertFalse(os.path.exists(cloned_snap), "Snapshot directory must NOT exist when deep_copy_snapshots=False")

            # Clone with deep_copy_snapshots=True and full_clone=True
            AVDManager.clone_instance(
                src_name="base",
                dst_name="clone_with_snap",
                dst_display_name="Deep Clone",
                full_clone=True,
                deep_copy_snapshots=True
            )
            cloned_snap_full = os.path.join(self.tmp_dir, "clone_with_snap.avd", "snapshots", "default_boot", "snapshot.ram")
            self.assertTrue(os.path.exists(cloned_snap_full), "Snapshot directory MUST exist when deep_copy_snapshots=True")

    def test_clone_instance_target_exists_raises_file_exists_error(self):
        """Verify FileExistsError when destination instance directory or ini already exists."""
        with patch.object(AVDManager, "get_avd_dir", return_value=self.tmp_dir):
            src_avd = os.path.join(self.tmp_dir, "base.avd")
            os.makedirs(src_avd, exist_ok=True)
            with open(os.path.join(self.tmp_dir, "base.ini"), "w") as f:
                f.write("target=android-34\n")
            with open(os.path.join(src_avd, "config.ini"), "w") as f:
                f.write("hw.ramSize=4096\n")

            # First clone succeeds
            AVDManager.clone_instance("base", "existing_clone", "Clone 1", deep_copy_snapshots=False)

            # Second clone with same name must raise FileExistsError
            with self.assertRaises(FileExistsError):
                AVDManager.clone_instance("base", "existing_clone", "Clone 2", deep_copy_snapshots=False)


class TestAdversarialFeature12SettingsAndTiling(unittest.TestCase):
    """Adversarial stress-testing of Settings Dialog and Real Window Tiling."""

    def test_settings_dialog_positional_parent_recovery(self):
        """Stress-test legacy caller passing parent as second positional argument."""
        parent_widget = QWidget()
        parent_widget.setObjectName("sidebarParent")
        dlg = GNDroidSettingsDialog("emulator-5556", parent_widget)
        self.assertEqual(dlg.instance_name, "gndroid")
        self.assertEqual(dlg.parent(), parent_widget)
        dlg.deleteLater()
        parent_widget.deleteLater()

    def test_action_open_settings_dynamic_avd_resolution(self):
        """Verify action_open_settings resolves real AVD name via ADB emu command."""
        sidebar = GNDroidCompanionSidebar("emulator-5554")
        with patch("subprocess.check_output", return_value="pixel_8_pro\r\nOK\r\n"):
            with patch.object(GNDroidSettingsDialog, "exec") as mock_exec:
                sidebar.action_open_settings()
                mock_exec.assert_called_once()
        sidebar.close()
        sidebar.deleteLater()

    def test_real_tile_running_windows_win32_integration(self):
        """Directly invoke real tile_running_windows against mocked Win32 EnumWindows and MoveWindow."""
        windows = [
            (101, "GNDROiD v2.2.2 — Master Control Suite"),
            (102, "GNDROiD Multi-Instance Manager"),
            (103, "GNDROiD Controls - emulator-5554"),
            (104, "GNDROiD - emulator-5554"),
            (105, "gndroid - 192.168.1.100:5555"),
            (106, "GNDROiD: WhatsApp [Clone #1]"),
            (107, "Android Emulator - Tablet_10:5556"),
        ]

        def mock_enum(cb, lparam):
            for hwnd, title in windows:
                with patch("ctypes.windll.user32.IsWindowVisible", return_value=True):
                    with patch("ctypes.windll.user32.IsIconic", return_value=False):
                        with patch("ctypes.windll.user32.GetWindowTextLengthW", return_value=len(title)):
                            def mock_get(h, buf, maxlen):
                                buf.value = title
                                return len(title)
                            with patch("ctypes.windll.user32.GetWindowTextW", side_effect=mock_get):
                                cb(hwnd, lparam)

        moved_hwnds = []
        def mock_move(hwnd, x, y, w, h, repaint):
            moved_hwnds.append(hwnd)

        with patch("ctypes.windll.user32.EnumWindows", side_effect=mock_enum):
            with patch("ctypes.windll.user32.MoveWindow", side_effect=mock_move):
                count = tile_running_windows()
                self.assertEqual(count, 4, f"Expected 4 emulator/scrcpy windows tiled, got {count}")
                self.assertEqual(moved_hwnds, [104, 105, 106, 107])
                self.assertNotIn(101, moved_hwnds, "Launcher suite must NOT be tiled!")
                self.assertNotIn(102, moved_hwnds, "Multi-Instance Manager must NOT be tiled!")
                self.assertNotIn(103, moved_hwnds, "Companion sidebar must NOT be tiled!")


class TestAdversarialFeature13and14AdbWorker(unittest.TestCase):
    """Adversarial stress-testing of AdbInstallOrPushWorker and error classifications."""

    def test_worker_cancellation_aborts_queue_immediately(self):
        """Verify cancelling worker prevents subsequent files from being processed."""
        worker = AdbInstallOrPushWorker(files=["app1.apk", "app2.apk", "app3.apk"], target_serial="emulator-5554")
        processed = []

        def mock_run(cmd, **kwargs):
            processed.append(cmd[-1])
            worker.cancel()  # Cancel after first execution
            mock_res = MagicMock()
            mock_res.returncode = 0
            mock_res.stdout = "Success\n"
            mock_res.stderr = ""
            return mock_res

        with patch("os.path.exists", return_value=True):
            with patch("subprocess.run", side_effect=mock_run):
                worker.run()

        self.assertEqual(len(processed), 1, "Cancelled worker must immediately abort remaining queue")

    def test_worker_timeout_handling(self):
        """Verify TimeoutExpired exception cleanly emits failure without crashing."""
        worker = AdbInstallOrPushWorker(files=["huge_app.apk"], target_serial="emulator-5554")
        results = []
        worker.file_result.connect(lambda f, s, m: results.append((f, s, m)))

        with patch("os.path.exists", return_value=True):
            with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("adb install", 120)):
                worker.run()

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0][1])
        self.assertIn("timed out", results[0][2].lower())

    def test_worker_push_readonly_filesystem_error(self):
        """Verify ADB push 'Read-only file system' is accurately flagged as failure."""
        worker = AdbInstallOrPushWorker(files=["payload.so"], target_serial="emulator-5554")
        results = []
        worker.file_result.connect(lambda f, s, m: results.append((f, s, m)))

        mock_res = MagicMock()
        mock_res.returncode = 1
        mock_res.stdout = ""
        mock_res.stderr = "adb: error: failed to copy 'payload.so' to '/system/lib64/payload.so': Read-only file system"

        with patch("os.path.exists", return_value=True):
            with patch("subprocess.run", return_value=mock_res):
                worker.run()

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0][1])
        self.assertIn("Read-only file system", results[0][2])


class TestAdversarialFeature15DockingFilter(unittest.TestCase):
    """Adversarial stress-testing of real find_target_window."""

    def test_real_find_target_window_excludes_all_launcher_variants(self):
        """Verify real find_target_window rejects launcher suite and matches Scrcpy window."""
        windows = [
            (301, "GNDROiD v2.2.2 — Master Control Suite"),
            (302, "GNDROiD v3.1.0 — Master Control Suite"),
            (303, "GNDROiD Multi-Instance Manager"),
            (304, "GNDROiD Controls - emulator-5554"),
            (305, "⚙️ GNDROiD Settings & Hardware Configuration"),
            (306, "GNDROiD ADB Doctor"),
            (307, "GNDROiD - emulator-5554"),
        ]

        def mock_enum(cb, lparam):
            for hwnd, title in windows:
                with patch("ctypes.windll.user32.IsWindowVisible", return_value=True):
                    with patch("ctypes.windll.user32.GetWindowTextLengthW", return_value=len(title)):
                        def mock_get(h, buf, maxlen):
                            buf.value = title
                            return len(title)
                        with patch("ctypes.windll.user32.GetWindowTextW", side_effect=mock_get):
                            res = cb(hwnd, lparam)
                            if not res:
                                break

        # With target serial
        with patch("ctypes.windll.user32.FindWindowW", return_value=0):
            with patch("ctypes.windll.user32.EnumWindows", side_effect=mock_enum):
                target = find_target_window("emulator-5554")
                self.assertEqual(target, 307, f"Expected Scrcpy HWND 307, got {target}")

        # Without target serial
        with patch("ctypes.windll.user32.FindWindowW", return_value=0):
            with patch("ctypes.windll.user32.EnumWindows", side_effect=mock_enum):
                target_empty = find_target_window("")
                self.assertEqual(target_empty, 307, f"Expected Scrcpy HWND 307, got {target_empty}")

    def test_real_find_target_window_returns_none_when_only_launcher_exists(self):
        """Verify find_target_window returns None if only launcher exists (no false docking)."""
        windows = [
            (401, "GNDROiD v2.2.2 — Master Control Suite"),
            (402, "GNDROiD Controls"),
        ]

        def mock_enum(cb, lparam):
            for hwnd, title in windows:
                with patch("ctypes.windll.user32.IsWindowVisible", return_value=True):
                    with patch("ctypes.windll.user32.GetWindowTextLengthW", return_value=len(title)):
                        def mock_get(h, buf, maxlen):
                            buf.value = title
                            return len(title)
                        with patch("ctypes.windll.user32.GetWindowTextW", side_effect=mock_get):
                            res = cb(hwnd, lparam)
                            if not res:
                                break

        with patch("ctypes.windll.user32.FindWindowW", return_value=0):
            with patch("ctypes.windll.user32.EnumWindows", side_effect=mock_enum):
                target = find_target_window("emulator-5554")
                self.assertIsNone(target, "Must return None when only launcher suite windows exist")


if __name__ == "__main__":
    unittest.main()
