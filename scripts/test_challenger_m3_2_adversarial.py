#!/usr/bin/env python3
"""
scripts/test_challenger_m3_2_adversarial.py
============================================
Adversarial Stress Verification Test Suite for Milestone 3:
Python Core GUI & UX Hardening (Features 11–15)

Auditor: challenger_m3_2 (Empirical Challenger)
Target:
  - AdbInstallOrPushWorker failure modes (INSTALL_FAILED_INVALID_APK, INSTALL_FAILED_INSUFFICIENT_STORAGE, etc.)
  - Verification that NO success notification is displayed upon ADB failure
  - Worker cancellation mechanics (pre-start, mid-flight, batch halt)
  - find_target_window strict exclusion of GNDROiD launcher / management windows
  - Clone signature alignment & Settings dialog argument preservation
"""

import os
import sys
import tempfile
import inspect
import unittest
import subprocess
import ctypes
from typing import List, Tuple
from unittest.mock import MagicMock, patch

# Ensure UTF-8 stdout
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Force headless Qt
os.environ["QT_QPA_PLATFORM"] = "offscreen"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from PyQt6.QtWidgets import QApplication, QMessageBox, QProgressDialog, QWidget
from PyQt6.QtCore import Qt, QUrl, QMimeData

# Ensure single headless QApplication instance
app = QApplication.instance()
if app is None:
    app = QApplication([sys.argv[0], "-platform", "offscreen"])

import gndroid
from gndroid import (
    AdbInstallOrPushWorker,
    find_target_window,
    GNDroidCompanionSidebar,
    GNDroidApp,
    AVDManager,
    GNDroidSettingsDialog,
    tile_running_windows,
)


class TestAdbWorkerFailureModesAndNotifications(unittest.TestCase):
    """
    Stress-tests for AdbInstallOrPushWorker failure emissions and notification suppression.
    Task 1:
      - Simulate an adb install failing with Failure [INSTALL_FAILED_INVALID_APK] or INSTALL_FAILED_INSUFFICIENT_STORAGE.
      - Verify that file_result emits success=False with error message.
      - Verify that under simulated failure, NO success notification is shown to the user.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.apk_invalid = os.path.join(self.temp_dir, "invalid_app.apk")
        with open(self.apk_invalid, "wb") as f:
            f.write(b"corrupt apk data")

        self.apk_storage = os.path.join(self.temp_dir, "storage_fail.apk")
        with open(self.apk_storage, "wb") as f:
            f.write(b"valid apk data but full disk")

        self.data_file = os.path.join(self.temp_dir, "data_payload.bin")
        with open(self.data_file, "wb") as f:
            f.write(b"sample data content")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_adb_install_failure_invalid_apk(self):
        """Simulate adb install failing with Failure [INSTALL_FAILED_INVALID_APK]."""
        worker = AdbInstallOrPushWorker(files=[self.apk_invalid], target_serial="emulator-5554")
        emitted_results: List[Tuple[str, bool, str]] = []
        emitted_finished: List[Tuple[int, int]] = []

        worker.file_result.connect(lambda fname, succ, msg: emitted_results.append((fname, succ, msg)))
        worker.finished_all.connect(lambda s, f: emitted_finished.append((s, f)))

        mock_res = MagicMock()
        mock_res.returncode = 0  # Even if exit code is 0, pm returns Failure
        mock_res.stdout = "Failure [INSTALL_FAILED_INVALID_APK: Failed to extract native libraries]"
        mock_res.stderr = ""

        with patch("subprocess.run", return_value=mock_res):
            worker.run()

        self.assertEqual(len(emitted_results), 1, "Expected exactly 1 file_result signal")
        fname, is_success, msg = emitted_results[0]
        self.assertEqual(fname, "invalid_app.apk")
        self.assertFalse(is_success, "Expected success=False on INSTALL_FAILED_INVALID_APK")
        self.assertIn("INSTALL_FAILED_INVALID_APK", msg, f"Error message missing expected keyword: {msg}")

        self.assertEqual(len(emitted_finished), 1)
        succ_cnt, fail_cnt = emitted_finished[0]
        self.assertEqual(succ_cnt, 0, "Success count must be 0")
        self.assertEqual(fail_cnt, 1, "Fail count must be 1")

    def test_adb_install_failure_insufficient_storage(self):
        """Simulate adb install failing with INSTALL_FAILED_INSUFFICIENT_STORAGE."""
        worker = AdbInstallOrPushWorker(files=[self.apk_storage], target_serial="emulator-5554")
        emitted_results: List[Tuple[str, bool, str]] = []
        emitted_finished: List[Tuple[int, int]] = []

        worker.file_result.connect(lambda fname, succ, msg: emitted_results.append((fname, succ, msg)))
        worker.finished_all.connect(lambda s, f: emitted_finished.append((s, f)))

        mock_res = MagicMock()
        mock_res.returncode = 1
        mock_res.stdout = "Failure [INSTALL_FAILED_INSUFFICIENT_STORAGE]"
        mock_res.stderr = "Error: Not enough disk space on guest device"

        with patch("subprocess.run", return_value=mock_res):
            worker.run()

        self.assertEqual(len(emitted_results), 1)
        fname, is_success, msg = emitted_results[0]
        self.assertEqual(fname, "storage_fail.apk")
        self.assertFalse(is_success, "Expected success=False on INSTALL_FAILED_INSUFFICIENT_STORAGE")
        self.assertIn("INSTALL_FAILED_INSUFFICIENT_STORAGE", msg)

        self.assertEqual(emitted_finished[0], (0, 1))

    def test_sidebar_transfer_suppresses_success_notification_on_failure(self):
        """Verify that under simulated failure in GNDroidCompanionSidebar, NO success notification is shown."""
        sidebar = GNDroidCompanionSidebar(target_serial="emulator-5554")

        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "Failure [INSTALL_FAILED_INVALID_APK]"
        mock_res.stderr = ""

        with patch.object(QMessageBox, "information") as mock_info, \
             patch.object(QMessageBox, "critical") as mock_crit, \
             patch("subprocess.run", return_value=mock_res):

            sidebar._start_async_file_transfer([self.apk_invalid])
            self.assertTrue(len(sidebar._active_workers) > 0, "Worker was not registered in _active_workers")
            worker = sidebar._active_workers[-1]
            worker.wait(5000)
            app.processEvents()

            # Adversarial assertion: NO success notification displayed
            self.assertFalse(
                mock_info.called,
                f"Defect! QMessageBox.information was invoked on failed install: {mock_info.call_args_list}"
            )
            # Must display critical error dialog
            self.assertTrue(
                mock_crit.called,
                "Expected QMessageBox.critical to be called with failure details"
            )
            call_args = mock_crit.call_args[0]
            title, text = call_args[1], call_args[2]
            self.assertEqual(title, "Install Error")
            self.assertIn("INSTALL_FAILED_INVALID_APK", text)

        sidebar.close()
        sidebar.deleteLater()

    def test_app_transfer_suppresses_success_notification_on_failure(self):
        """Verify that under simulated failure in GNDroidApp, NO success notification is shown."""
        main_app = GNDroidApp()

        mock_res = MagicMock()
        mock_res.returncode = 1
        mock_res.stdout = "Failure [INSTALL_FAILED_INSUFFICIENT_STORAGE]"
        mock_res.stderr = ""

        with patch.object(QMessageBox, "information") as mock_info, \
             patch.object(QMessageBox, "critical") as mock_crit, \
             patch("subprocess.run", return_value=mock_res):

            main_app._start_async_file_transfer([self.apk_storage])
            self.assertTrue(len(main_app._active_transfer_workers) > 0)
            worker = main_app._active_transfer_workers[-1]
            worker.wait(5000)
            app.processEvents()

            # Adversarial assertion: NO success notification displayed
            self.assertFalse(
                mock_info.called,
                f"Defect! QMessageBox.information was called on install failure: {mock_info.call_args_list}"
            )
            self.assertTrue(
                mock_crit.called,
                "Expected QMessageBox.critical on failure"
            )
            call_args = mock_crit.call_args[0]
            title, text = call_args[1], call_args[2]
            self.assertEqual(title, "Install Error")
            self.assertIn("INSTALL_FAILED_INSUFFICIENT_STORAGE", text)

        main_app.close()
        main_app.deleteLater()

    def test_file_push_failure_notification_suppression(self):
        """Verify file push failure (permission denied / failed to copy) suppresses success dialog."""
        sidebar = GNDroidCompanionSidebar(target_serial="emulator-5554")

        mock_res = MagicMock()
        mock_res.returncode = 1
        mock_res.stdout = "adb: error: failed to copy 'data_payload.bin': Permission denied"
        mock_res.stderr = ""

        with patch.object(QMessageBox, "information") as mock_info, \
             patch.object(QMessageBox, "critical") as mock_crit, \
             patch("subprocess.run", return_value=mock_res):

            sidebar._start_async_file_transfer([self.data_file])
            worker = sidebar._active_workers[-1]
            worker.wait(5000)
            app.processEvents()

            self.assertFalse(mock_info.called, "QMessageBox.information must NOT be called on push error")
            self.assertTrue(mock_crit.called, "QMessageBox.critical must be called on push error")
            title = mock_crit.call_args[0][1]
            self.assertEqual(title, "Transfer Error")

        sidebar.close()
        sidebar.deleteLater()

    def test_adb_timeout_and_exception_handling(self):
        """Verify worker cleanly catches TimeoutExpired and generic Exception without freezing."""
        worker_timeout = AdbInstallOrPushWorker(files=[self.apk_invalid], target_serial="emulator-5554")
        results = []
        worker_timeout.file_result.connect(lambda f, s, m: results.append((f, s, m)))

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="adb", timeout=120)):
            worker_timeout.run()

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0][1])
        self.assertIn("timed out", results[0][2].lower())

        # Test generic exception
        worker_exc = AdbInstallOrPushWorker(files=[self.apk_invalid], target_serial="emulator-5554")
        results_exc = []
        worker_exc.file_result.connect(lambda f, s, m: results_exc.append((f, s, m)))

        with patch("subprocess.run", side_effect=OSError("ADB execution failed")):
            worker_exc.run()

        self.assertEqual(len(results_exc), 1)
        self.assertFalse(results_exc[0][1])
        self.assertIn("ADB execution failed", results_exc[0][2])


class TestAdbWorkerCancellation(unittest.TestCase):
    """
    Stress-tests for AdbInstallOrPushWorker cancellation mechanics.
    Task 1:
      - Test worker cancellation: verify that calling .cancel() stops further batch processing cleanly.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.batch_files = []
        for i in range(5):
            p = os.path.join(self.temp_dir, f"batch_pkg_{i}.apk")
            with open(p, "wb") as f:
                f.write(b"pkg data")
            self.batch_files.append(p)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_pre_start_cancellation(self):
        """Worker cancelled before run() must halt immediately with 0 subprocess invocations."""
        worker = AdbInstallOrPushWorker(files=self.batch_files, target_serial="emulator-5554")
        emitted_results = []
        emitted_finished = []
        worker.file_result.connect(lambda f, s, m: emitted_results.append((f, s, m)))
        worker.finished_all.connect(lambda s, f: emitted_finished.append((s, f)))

        with patch("subprocess.run") as mock_sub:
            worker.cancel()
            worker.run()

            mock_sub.assert_not_called()
            self.assertEqual(len(emitted_results), 0, "No results should emit when cancelled pre-start")
            self.assertEqual(emitted_finished, [(0, 0)], "finished_all should emit (0, 0)")

    def test_mid_flight_cancellation_stops_subsequent_files(self):
        """Worker cancelled mid-batch must stop executing subsequent files."""
        worker = AdbInstallOrPushWorker(files=self.batch_files, target_serial="emulator-5554")
        emitted_results = []
        emitted_finished = []
        worker.file_result.connect(lambda f, s, m: emitted_results.append((f, s, m)))
        worker.finished_all.connect(lambda s, f: emitted_finished.append((s, f)))

        mock_succ = MagicMock()
        mock_succ.returncode = 0
        mock_succ.stdout = "Success"
        mock_succ.stderr = ""

        run_count = [0]
        def fake_run(*args, **kwargs):
            run_count[0] += 1
            if run_count[0] == 2:
                # Cancel when the 2nd file completes
                worker.cancel()
            return mock_succ

        with patch("subprocess.run", side_effect=fake_run):
            worker.run()

        self.assertEqual(run_count[0], 2, f"Expected exactly 2 files executed before cancellation, got {run_count[0]}")
        self.assertEqual(len(emitted_results), 2, "Expected exactly 2 file_result signals")
        self.assertTrue(worker._is_cancelled, "Worker should flag _is_cancelled=True")
        self.assertEqual(emitted_finished, [(2, 0)], "Expected finished_all to emit (2, 0)")

    def test_progress_dialog_cancel_button_wires_to_worker(self):
        """Verify that canceling QProgressDialog triggers worker.cancel()."""
        sidebar = GNDroidCompanionSidebar(target_serial="emulator-5554")

        mock_succ = MagicMock()
        mock_succ.returncode = 0
        mock_succ.stdout = "Success"
        mock_succ.stderr = ""

        with patch("subprocess.run", return_value=mock_succ):
            sidebar._start_async_file_transfer(self.batch_files)
            worker = sidebar._active_workers[-1]
            self.assertFalse(worker._is_cancelled)

            # Find the active QProgressDialog child
            dialogs = [c for c in sidebar.children() if isinstance(c, QProgressDialog)]
            self.assertTrue(len(dialogs) > 0, "QProgressDialog was not spawned")
            prog = dialogs[0]

            # Trigger cancel signal on the progress dialog
            prog.canceled.emit()
            self.assertTrue(worker._is_cancelled, "Emitting prog.canceled did not set worker._is_cancelled!")

            worker.wait(5000)

        sidebar.close()
        sidebar.deleteLater()


class TestFindTargetWindowRejection(unittest.TestCase):
    """
    Stress-tests for find_target_window exclusion rules.
    Task 2:
      - Pass window titles matching "GNDROiD v2.2.2 — Master Control Suite",
        "GNDROiD Controls", "Multi-Instance Manager".
      - Verify that find_target_window strictly rejects them (does NOT return their HWNDs).
    """

    def _setup_mock_user32(self, window_list: List[Tuple[int, str]]):
        """
        Creates a mock user32 WinDLL where EnumWindows iterates over window_list.
        Each item in window_list is (hwnd, title).
        """
        mock_u32 = MagicMock()
        mock_u32.FindWindowW.return_value = None  # Force EnumWindows search path
        mock_u32.IsIconic.return_value = False

        def fake_enum(cb, lparam):
            for h, title in window_list:
                mock_u32.IsWindowVisible.return_value = 1
                mock_u32.GetWindowTextLengthW.return_value = len(title)

                def fake_get_text(hwnd, buf, maxlen):
                    buf.value = title
                    return len(title)

                mock_u32.GetWindowTextW.side_effect = fake_get_text
                # Call callback
                cont = cb(h, lparam)
                if not cont:
                    break
            return 1

        mock_u32.EnumWindows.side_effect = fake_enum
        return mock_u32

    def test_find_target_window_strictly_rejects_master_control_suite(self):
        """Verify find_target_window strictly rejects 'GNDROiD v2.2.2 — Master Control Suite'."""
        windows = [
            (1001, "GNDROiD v2.2.2 — Master Control Suite")
        ]
        mock_u32 = self._setup_mock_user32(windows)

        with patch.object(gndroid, "user32", mock_u32):
            result = find_target_window(target_serial="")
            self.assertIsNone(result, f"find_target_window falsely matched Master Control Suite! HWND={result}")

            result_serial = find_target_window(target_serial="emulator-5554")
            self.assertIsNone(result_serial, f"find_target_window with serial falsely matched Master Control Suite! HWND={result_serial}")

    def test_find_target_window_strictly_rejects_gndroid_controls(self):
        """Verify find_target_window strictly rejects 'GNDROiD Controls'."""
        windows = [
            (1002, "GNDROiD Controls"),
            (1003, "GNDROiD Controls - emulator-5554"),
            (1004, "gndroid Controls")
        ]
        mock_u32 = self._setup_mock_user32(windows)

        with patch.object(gndroid, "user32", mock_u32):
            result = find_target_window(target_serial="")
            self.assertIsNone(result, f"find_target_window falsely matched Controls window! HWND={result}")

            result_serial = find_target_window(target_serial="emulator-5554")
            self.assertIsNone(result_serial, f"find_target_window with serial falsely matched Controls window! HWND={result_serial}")

    def test_find_target_window_strictly_rejects_multi_instance_manager(self):
        """Verify find_target_window strictly rejects 'Multi-Instance Manager'."""
        windows = [
            (1005, "Multi-Instance Manager"),
            (1006, "GNDROiD Multi-Instance Manager"),
            (1007, "GNDROiD Multi-Instance Manager (emulator-5554)")
        ]
        mock_u32 = self._setup_mock_user32(windows)

        with patch.object(gndroid, "user32", mock_u32):
            result = find_target_window(target_serial="")
            self.assertIsNone(result, f"find_target_window falsely matched Multi-Instance Manager! HWND={result}")

            result_serial = find_target_window(target_serial="emulator-5554")
            self.assertIsNone(result_serial, f"find_target_window with serial falsely matched Multi-Instance Manager! HWND={result_serial}")

    def test_find_target_window_finds_scrcpy_amidst_management_windows(self):
        """
        Verify that when management windows AND a valid Scrcpy window coexist,
        find_target_window skips all management windows and strictly returns the Scrcpy window.
        """
        windows = [
            (1001, "GNDROiD v2.2.2 — Master Control Suite"),
            (1002, "GNDROiD Controls"),
            (1003, "Multi-Instance Manager"),
            (1004, "GNDROiD Settings & Hardware Configuration"),
            (1005, "GNDROiD ADB Doctor"),
            (2001, "GNDROiD - emulator-5554"),  # Valid Scrcpy mirror window
        ]
        mock_u32 = self._setup_mock_user32(windows)

        with patch.object(gndroid, "user32", mock_u32):
            # Test without serial
            result = find_target_window(target_serial="")
            self.assertEqual(result, 2001, f"Expected Scrcpy window HWND 2001, got {result}")

            # Test with serial
            result_serial = find_target_window(target_serial="emulator-5554")
            self.assertEqual(result_serial, 2001, f"Expected Scrcpy window HWND 2001 for serial, got {result_serial}")

    def test_find_target_window_findwindoww_rejection(self):
        """
        Verify that even if user32.FindWindowW returns a management window,
        find_target_window checks the title and rejects it.
        """
        mock_u32 = MagicMock()
        mock_u32.FindWindowW.return_value = 9999
        mock_u32.IsWindowVisible.return_value = 1
        mock_u32.IsIconic.return_value = 0
        mock_u32.GetWindowTextLengthW.return_value = len("GNDROiD Controls")

        def fake_get_text(hwnd, buf, maxlen):
            buf.value = "GNDROiD Controls"
            return len("GNDROiD Controls")
        mock_u32.GetWindowTextW.side_effect = fake_get_text

        # EnumWindows returns None
        mock_u32.EnumWindows.side_effect = lambda cb, lp: 1

        with patch.object(gndroid, "user32", mock_u32):
            result = find_target_window("emulator-5554")
            self.assertIsNone(result, f"FindWindowW match should have been rejected by is_launcher_or_mgmt! Got {result}")


class TestFeatures11And12Integrity(unittest.TestCase):
    """
    Empirical tests for Feature 11 (Clone signature) and Feature 12 (Settings & Auto-Tiling).
    """

    def test_clone_instance_signature_and_invocation(self):
        """Verify AVDManager.clone_instance signature accepts deep_copy_snapshots and caller arguments."""
        sig = inspect.signature(AVDManager.clone_instance)
        self.assertIn("deep_copy_snapshots", sig.parameters)
        self.assertFalse(sig.parameters["deep_copy_snapshots"].default)

        tmp_dir = tempfile.mkdtemp()
        try:
            with patch.object(AVDManager, "get_avd_dir", return_value=tmp_dir):
                src_avd = os.path.join(tmp_dir, "base_inst.avd")
                os.makedirs(os.path.join(src_avd, "snapshots", "snap1"), exist_ok=True)
                with open(os.path.join(tmp_dir, "base_inst.ini"), "w") as f:
                    f.write("target=android-34\n")
                with open(os.path.join(src_avd, "config.ini"), "w") as f:
                    f.write("hw.ramSize=4096\n")
                with open(os.path.join(src_avd, "snapshots", "snap1", "snapshot.pb"), "w") as f:
                    f.write("snapshot-meta")

                # Invoke with deep_copy_snapshots=False (Feature 11 requirement)
                AVDManager.clone_instance(
                    src_name="base_inst",
                    dst_name="cloned_inst_no_snap",
                    dst_display_name="Clone No Snap",
                    deep_copy_snapshots=False
                )
                self.assertTrue(os.path.exists(os.path.join(tmp_dir, "cloned_inst_no_snap.ini")))
                self.assertTrue(os.path.exists(os.path.join(tmp_dir, "cloned_inst_no_snap.avd")))
                # Snapshots must NOT be copied when deep_copy_snapshots=False
                self.assertFalse(os.path.exists(os.path.join(tmp_dir, "cloned_inst_no_snap.avd", "snapshots", "snap1")))

                # Invoke with deep_copy_snapshots=True
                AVDManager.clone_instance(
                    src_name="base_inst",
                    dst_name="cloned_inst_with_snap",
                    dst_display_name="Clone With Snap",
                    deep_copy_snapshots=True
                )
                self.assertTrue(os.path.exists(os.path.join(tmp_dir, "cloned_inst_with_snap.ini")))
                self.assertTrue(os.path.exists(os.path.join(tmp_dir, "cloned_inst_with_snap.avd", "snapshots", "snap1")))
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_settings_dialog_instance_name_defense(self):
        """Verify GNDroidSettingsDialog handles QWidget passed as second argument defensively."""
        parent_widget = QWidget()
        dlg = GNDroidSettingsDialog(target_serial="emulator-5554", instance_name=parent_widget)
        self.assertEqual(dlg.instance_name, "gndroid", "instance_name should default to 'gndroid' if QWidget passed")
        dlg.close()
        dlg.deleteLater()
        parent_widget.close()
        parent_widget.deleteLater()

    def test_tile_running_windows_detection(self):
        """Verify tile_running_windows detects Scrcpy windows and ignores management windows."""
        windows = [
            (501, "GNDROiD - emulator-5554"),
            (502, "gndroid: Floating App"),
            (503, "GNDROiD Controls"),
            (504, "GNDROiD Multi-Instance Manager"),
            (505, "GNDROiD ADB Doctor"),
            (506, "GNDROiD Settings"),
        ]

        mock_u32 = MagicMock()
        def fake_enum(cb, lparam):
            for h, title in windows:
                mock_u32.IsWindowVisible.return_value = 1
                mock_u32.IsIconic.return_value = 0
                mock_u32.GetWindowTextLengthW.return_value = len(title)
                def fake_get_text(hwnd, buf, maxlen):
                    buf.value = title
                    return len(title)
                mock_u32.GetWindowTextW.side_effect = fake_get_text
                cb(h, lparam)
            return 1

        mock_u32.EnumWindows.side_effect = fake_enum
        mock_u32.GetSystemMetrics.return_value = 1920
        mock_u32.MoveWindow.return_value = 1

        with patch.object(gndroid, "user32", mock_u32):
            count = tile_running_windows()
            self.assertEqual(count, 2, f"Expected exactly 2 tiled windows (501, 502), got {count}")


def run_all_tests():
    suite = unittest.TestSuite()
    loader = unittest.TestLoader()
    suite.addTests(loader.loadTestsFromTestCase(TestAdbWorkerFailureModesAndNotifications))
    suite.addTests(loader.loadTestsFromTestCase(TestAdbWorkerCancellation))
    suite.addTests(loader.loadTestsFromTestCase(TestFindTargetWindowRejection))
    suite.addTests(loader.loadTestsFromTestCase(TestFeatures11And12Integrity))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
