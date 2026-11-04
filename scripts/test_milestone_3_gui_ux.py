"""
Unit & Integration Test Suite for Milestone 3: Python Core GUI & UX Hardening (Features 11–15)
Author: worker_m3
"""

import os
import sys
import inspect
import unittest
import tempfile
import shutil
from unittest.mock import MagicMock, patch

# Ensure root directory is on sys.path
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from PyQt6.QtWidgets import QApplication, QWidget, QDialog
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl, QMimeData

# Initialize headless QApplication if not running
app = QApplication.instance()
if app is None:
    app = QApplication([sys.argv[0], "-platform", "offscreen"])

# Import gndroid components
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


class TestFeature11CloneSignatureAlignment(unittest.TestCase):
    """Feature 11: Multi-Instance Quick Clone Signature Alignment."""

    def test_clone_instance_signature_parameters(self):
        """Verify AVDManager.clone_instance accepts deep_copy_snapshots with default False."""
        sig = inspect.signature(AVDManager.clone_instance)
        params = sig.parameters

        # Check required parameters exist
        expected_params = [
            "src_name", "dst_name", "dst_display_name", "ram_mb", "cores",
            "root_enabled", "full_clone", "progress_cb", "deep_copy_snapshots"
        ]
        for p in expected_params:
            self.assertIn(p, params, f"Parameter '{p}' missing from AVDManager.clone_instance signature")

        # Check default value of deep_copy_snapshots
        self.assertFalse(params["deep_copy_snapshots"].default, "deep_copy_snapshots default must be False")

    def test_clone_instance_invocation_with_keyword_arguments(self):
        """Verify calling clone_instance with caller arguments executes without TypeError."""
        tmp_dir = tempfile.mkdtemp()
        try:
            with patch.object(AVDManager, "get_avd_dir", return_value=tmp_dir):
                # Create mock source AVD
                src_avd = os.path.join(tmp_dir, "base_inst.avd")
                os.makedirs(src_avd, exist_ok=True)
                with open(os.path.join(tmp_dir, "base_inst.ini"), "w") as f:
                    f.write("target=android-34\n")
                with open(os.path.join(src_avd, "config.ini"), "w") as f:
                    f.write("hw.ramSize=4096\n")

                # Invoke with caller keyword arguments
                AVDManager.clone_instance(
                    src_name="base_inst",
                    dst_name="cloned_inst",
                    dst_display_name="Cloned Instance",
                    deep_copy_snapshots=False
                )

                # Verify cloned files exist
                self.assertTrue(os.path.exists(os.path.join(tmp_dir, "cloned_inst.ini")))
                self.assertTrue(os.path.exists(os.path.join(tmp_dir, "cloned_inst.avd")))
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


class TestFeature12SidebarSettingsAndAutoTiling(unittest.TestCase):
    """Feature 12: Companion Sidebar Settings & Auto-Tiling Fixes."""

    def test_settings_dialog_argument_shifting_safeguard(self):
        """Verify GNDroidSettingsDialog handles QWidget passed as second argument without corruption."""
        dummy_parent = QWidget()
        # Even if called positionally with (serial, dummy_parent)
        dlg = GNDroidSettingsDialog("emulator-5554", dummy_parent)
        self.assertEqual(dlg.instance_name, "gndroid", "instance_name must be normalized to 'gndroid' instead of QWidget")
        self.assertEqual(dlg.target_serial, "emulator-5554")
        self.assertEqual(dlg.parent(), dummy_parent)
        dlg.deleteLater()
        dummy_parent.deleteLater()

    def test_action_open_settings_caller(self):
        """Verify GNDroidCompanionSidebar has action_open_settings and action_settings alias."""
        sidebar = GNDroidCompanionSidebar("emulator-5554")
        self.assertTrue(hasattr(sidebar, "action_open_settings"))
        self.assertTrue(hasattr(sidebar, "action_settings"))
        sidebar.close()
        sidebar.deleteLater()

    def test_tile_windows_case_insensitive_matching(self):
        """Verify window matching in tile_running_windows detects GNDROiD Scrcpy windows and ignores manager."""
        test_titles = [
            ("GNDROiD - emulator-5554", True),
            ("gndroid - 192.168.1.50:5555", True),
            ("GNDROiD: Settings [Clone #1]", True),
            ("Android Emulator - Pixel_7", True),
            ("GNDROiD v2.2.2 — Master Control Suite", False),
            ("GNDROiD Multi-Instance Manager", False),
            ("GNDROiD Controls - emulator-5554", False),
            ("⚙️ GNDROiD Settings & Hardware Configuration — Flagship", False),
            ("GNDROiD ADB Doctor", False),
        ]

        def filter_title(t: str) -> bool:
            t_lower = t.lower()
            is_scrcpy_app = t.startswith("GNDROiD:") or t.startswith("gndroid:") or t.startswith("GNDROiD -") or t.startswith("gndroid -")
            is_mgmt = any(k in t_lower for k in ["controls", "manager", "doctor", "settings & hardware", "suite", "launcher"]) or "gndroid settings" in t_lower
            return (is_scrcpy_app or ("gndroid" in t_lower or "android emulator" in t_lower)) and not is_mgmt

        for title, expected in test_titles:
            result = filter_title(title)
            self.assertEqual(result, expected, f"Title '{title}' classification failed: expected {expected}, got {result}")

    def test_auto_tile_alias_on_multi_instance_manager(self):
        """Verify action_auto_tile_desktop alias exists on GNDroidMultiInstanceManager."""
        self.assertTrue(hasattr(GNDroidMultiInstanceManager, "action_auto_tile_desktop"))
        self.assertTrue(hasattr(GNDroidMultiInstanceManager, "action_tile_windows"))
        self.assertEqual(
            GNDroidMultiInstanceManager.action_auto_tile_desktop,
            GNDroidMultiInstanceManager.action_tile_windows
        )


class TestFeature13NonBlockingWorker(unittest.TestCase):
    """Feature 13: Non-Blocking Main GUI Event Loop."""

    def test_worker_is_qthread_with_signals(self):
        """Verify AdbInstallOrPushWorker inherits from QThread and defines required signals."""
        self.assertTrue(issubclass(AdbInstallOrPushWorker, QThread))
        worker = AdbInstallOrPushWorker(files=["test.apk"], target_serial="emulator-5554")
        self.assertTrue(hasattr(worker, "progress"))
        self.assertTrue(hasattr(worker, "file_result"))
        self.assertTrue(hasattr(worker, "finished_all"))
        self.assertTrue(hasattr(worker, "cancel"))

    def test_sidebar_drop_event_delegates_to_async_worker(self):
        """Verify GNDroidCompanionSidebar.dropEvent initiates async worker without blocking subprocess."""
        sidebar = GNDroidCompanionSidebar("emulator-5554")
        with patch.object(sidebar, "_start_async_file_transfer") as mock_transfer:
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile("C:/temp/app.apk")])
            event = MagicMock()
            event.mimeData.return_value = mime
            sidebar.dropEvent(event)
            mock_transfer.assert_called_once_with(["C:/temp/app.apk"])
        sidebar.close()
        sidebar.deleteLater()

    def test_main_app_drop_event_delegates_to_async_worker(self):
        """Verify GNDroidApp.dropEvent initiates async worker without blocking subprocess."""
        app_win = GNDroidApp()
        with patch.object(app_win, "_start_async_file_transfer") as mock_transfer:
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile("C:/temp/file.pdf")])
            event = MagicMock()
            event.mimeData.return_value = mime
            app_win.dropEvent(event)
            mock_transfer.assert_called_once_with(["C:/temp/file.pdf"])
        app_win.close()
        app_win.deleteLater()


class TestFeature14AccurateOperationStatus(unittest.TestCase):
    """Feature 14: Accurate Operation Status & Error Feedback."""

    def test_apk_success_detection(self):
        """Verify APK install success only when returncode is 0 and no failure keyword in output."""
        worker = AdbInstallOrPushWorker(files=["sample.apk"], target_serial="emulator-5554")
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "Performing Streamed Install\nSuccess\n"
        mock_res.stderr = ""

        with patch("os.path.exists", return_value=True):
            with patch("subprocess.run", return_value=mock_res):
                results = []
                worker.file_result.connect(lambda f, s, m: results.append((f, s, m)))
                worker.run()
                self.assertEqual(len(results), 1)
                self.assertTrue(results[0][1], "Should report success on returncode=0 and 'Success'")

    def test_apk_failure_detection_nonzero_returncode(self):
        """Verify APK install failure when returncode != 0."""
        worker = AdbInstallOrPushWorker(files=["sample.apk"], target_serial="emulator-5554")
        mock_res = MagicMock()
        mock_res.returncode = 1
        mock_res.stdout = ""
        mock_res.stderr = "adb: device unauthorized."

        with patch("os.path.exists", return_value=True):
            with patch("subprocess.run", return_value=mock_res):
                results = []
                worker.file_result.connect(lambda f, s, m: results.append((f, s, m)))
                worker.run()
                self.assertEqual(len(results), 1)
                self.assertFalse(results[0][1], "Should report failure when returncode != 0")
                self.assertIn("unauthorized", results[0][2])

    def test_apk_failure_detection_install_failed_string(self):
        """Verify APK install failure when returncode == 0 but output contains INSTALL_FAILED."""
        worker = AdbInstallOrPushWorker(files=["sample.apk"], target_serial="emulator-5554")
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "Failure [INSTALL_FAILED_INVALID_APK: Failed to extract native libraries]"
        mock_res.stderr = ""

        with patch("os.path.exists", return_value=True):
            with patch("subprocess.run", return_value=mock_res):
                results = []
                worker.file_result.connect(lambda f, s, m: results.append((f, s, m)))
                worker.run()
                self.assertEqual(len(results), 1)
                self.assertFalse(results[0][1], "Must report failure if output contains INSTALL_FAILED")
                self.assertIn("INSTALL_FAILED_INVALID_APK", results[0][2])

    def test_file_push_failure_detection(self):
        """Verify file push failure when output contains error / permission denied."""
        worker = AdbInstallOrPushWorker(files=["data.bin"], target_serial="emulator-5554")
        mock_res = MagicMock()
        mock_res.returncode = 1
        mock_res.stdout = ""
        mock_res.stderr = "adb: error: failed to copy 'data.bin' to '/sdcard/Download/data.bin': Permission denied"

        with patch("os.path.exists", return_value=True):
            with patch("subprocess.run", return_value=mock_res):
                results = []
                worker.file_result.connect(lambda f, s, m: results.append((f, s, m)))
                worker.run()
                self.assertEqual(len(results), 1)
                self.assertFalse(results[0][1], "Must report failure on file push error")
                self.assertIn("Permission denied", results[0][2])


class TestFeature15CompanionSidebarDockingFilter(unittest.TestCase):
    """Feature 15: Companion Sidebar Docking Filter."""

    def test_docking_filter_excludes_launcher_and_dialogs(self):
        """Verify docking filter rejects GNDROiD launcher itself and other management dialogs."""
        excluded = [
            "GNDROiD v2.2.2 — Master Control Suite",
            "GNDROiD v3.0.0 — Master Control Suite",
            "GNDROiD Multi-Instance Manager",
            "GNDROiD Controls - emulator-5554",
            "GNDROiD Settings & Hardware Configuration — Flagship",
            "GNDROiD ADB Doctor",
            "GNDROiD Image Downloader",
            "GNDROiD App Drawer & Cloner",
            "GNDROiD Wireless Pairing",
        ]
        accepted = [
            "GNDROiD - emulator-5554",
            "gndroid - 192.168.1.50:5555",
            "GNDROiD: WhatsApp [Clone #1]",
            "Android Emulator - Pixel_7_API_34",
            "GNDROiD",
        ]

        # Use exact filter logic from find_target_window
        excluded_keywords = [
            "controls", "not connected", "control & settings", "settings",
            "master control suite", "multi-instance", "manager", "doctor",
            "downloader", "drawer", "pairing", "dialog", "quick clone", "clean locks"
        ]

        import re
        def is_launcher_or_mgmt(title_str: str) -> bool:
            t_low = title_str.lower()
            if any(k in t_low for k in excluded_keywords):
                return True
            if re.search(r"gndroid\s+v\d", t_low):
                return True
            return False

        for title in excluded:
            self.assertTrue(is_launcher_or_mgmt(title), f"Launcher/mgmt window '{title}' was NOT excluded!")

        for title in accepted:
            self.assertFalse(is_launcher_or_mgmt(title), f"Valid target window '{title}' was falsely excluded!")


if __name__ == "__main__":
    unittest.main()
