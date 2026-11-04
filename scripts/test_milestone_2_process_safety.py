"""
scripts/test_milestone_2_process_safety.py
==========================================
Comprehensive Automated Verification Suite for Milestone 2:
Subprocess Lifecycle & Process Safety (Features 7 - 10)

Tests:
1. Feature 7: Scrcpy Stderr Pipe Deadlock Prevention (asynchronous non-blocking drain).
2. Feature 8: Process Tree Lifecycle & Win32 Job Objects (JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE, active registry, clean teardown).
3. Feature 9: Multi-Instance Clean Teardown & File Lock Guard (process exit verification & progressive backoff file lock check).
4. Feature 10: Background Thread Pooling & USB Non-Interference (LanRadarWorker thread limits/mutex, DeviceScannerWorker USB protection).
"""

import os
import sys
import time
import socket
import tempfile
import unittest
import threading
import subprocess
from unittest.mock import patch, MagicMock

# Force offscreen Qt rendering
os.environ["QT_QPA_PLATFORM"] = "offscreen"

# Ensure workspace root is in sys.path
WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WORKSPACE_DIR not in sys.path:
    sys.path.insert(0, WORKSPACE_DIR)

from nexus.wireless_mirror import WirelessMirrorManager
from nexus.app_cloner_and_window import (
    AppWindowManager,
    Win32JobManager,
    assign_to_job_object
)


class TestMilestone2ProcessSafety(unittest.TestCase):

    # =========================================================================
    # FEATURE 7: Scrcpy Stderr Pipe Deadlock Prevention
    # =========================================================================

    def test_feature7_pipe_drain_prevents_buffer_deadlock(self):
        """
        Spawns a python child process that writes 64 KB (> 4 KB Windows pipe buffer)
        to stderr. Without draining, this would block indefinitely.
        Verifies that WirelessMirrorManager.drain_pipe_async consumes all data and allows
        the process to terminate cleanly without hanging.
        """
        python_exe = sys.executable
        # Child process writes 64KB in chunks to stderr
        code = (
            "import sys, time\n"
            "data = b'X' * 1024\n"
            "for _ in range(64):\n"
            "    sys.stderr.buffer.write(data)\n"
            "    sys.stderr.buffer.flush()\n"
            "sys.exit(0)\n"
        )
        proc = subprocess.Popen(
            [python_exe, "-c", code],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE
        )

        drain_thread = WirelessMirrorManager.drain_pipe_async(proc)
        self.assertIsNotNone(drain_thread, "Expected drain thread to be started")

        # Wait for child process to exit. With draining, 64KB completes in < 2 seconds.
        exit_code = proc.wait(timeout=5.0)
        self.assertEqual(exit_code, 0, "Child process should terminate successfully with exit code 0")

    def test_feature7_launch_resilient_mirror_drains_stable_session(self):
        """
        Verifies that when scrcpy runs stably beyond the probe timeout,
        drain_pipe_async is attached to prevent 4KB pipe deadlock during streaming.
        """
        manager = WirelessMirrorManager(scrcpy_bin="scrcpy")
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # Stably running
        mock_proc.stderr = MagicMock()

        with patch.object(manager, "_spawn_scrcpy", return_value=mock_proc), \
             patch.object(manager, "drain_pipe_async") as mock_drain:

            res = manager.launch_resilient_mirror(
                serial="emulator-5554",
                sync_probe=True,
                probe_timeout=0.1
            )
            self.assertEqual(res, mock_proc)
            mock_drain.assert_called_once_with(mock_proc)

    def test_feature7_launch_resilient_mirror_drains_fallback_session(self):
        """
        Verifies that when audio fails early and fallback is spawned,
        drain_pipe_async is attached to the fallback process.
        """
        manager = WirelessMirrorManager(scrcpy_bin="scrcpy")

        mock_fail = MagicMock()
        mock_fail.poll.side_effect = [None, 1]
        mock_fail.returncode = 1
        mock_fail.stderr.read.return_value = b"ERROR: Audio initialization failed: opus\n"

        mock_fallback = MagicMock()
        mock_fallback.poll.return_value = None
        mock_fallback.stderr = MagicMock()

        procs = [mock_fail, mock_fallback]

        with patch.object(manager, "_spawn_scrcpy", side_effect=lambda *args, **kwargs: procs.pop(0)), \
             patch.object(manager, "drain_pipe_async") as mock_drain:

            res = manager.launch_resilient_mirror(
                serial="192.168.100.20:5555",
                sync_probe=True,
                probe_timeout=1.0
            )
            self.assertEqual(res, mock_fallback)
            mock_drain.assert_called_with(mock_fallback)

    # =========================================================================
    # FEATURE 8: Process Tree Lifecycle & Win32 Job Objects
    # =========================================================================

    def test_feature8_win32_job_manager_initialization(self):
        """Verifies Win32JobManager initializes a valid Job Object on Windows."""
        job_mgr = Win32JobManager.get_instance()
        self.assertIsNotNone(job_mgr)
        if sys.platform == "win32":
            self.assertIsNotNone(job_mgr._job_handle, "Expected Win32 Job Object handle on Windows")

    def test_feature8_job_object_assign_and_track_child_process(self):
        """Verifies that child processes are assigned and tracked by the Job Object manager."""
        job_mgr = Win32JobManager.get_instance()
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(10)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        try:
            success = job_mgr.assign_process(proc)
            self.assertTrue(success, "assign_process should return True")
            self.assertIn(proc.pid, job_mgr.get_tracked_pids())
        finally:
            proc.kill()
            proc.wait()

    def test_feature8_app_window_manager_tracks_and_terminates(self):
        """Verifies AppWindowManager tracks active floating windows and terminates them cleanly."""
        mock_proc = MagicMock()
        mock_proc.pid = 99999
        mock_proc.poll.return_value = None

        with patch("subprocess.Popen", return_value=mock_proc):
            proc = AppWindowManager.launch_app_in_dedicated_window(
                serial="emulator-5554",
                package_name="com.android.settings",
                app_title="Settings"
            )
            self.assertEqual(proc, mock_proc)

            active = AppWindowManager.get_active_windows()
            matching = [w for w in active if w.get("package") == "com.android.settings"]
            self.assertGreaterEqual(len(matching), 1)

            # Test terminate_all_windows
            AppWindowManager.terminate_all_windows(timeout=0.5)
            mock_proc.terminate.assert_called()

    def test_feature8_avd_manager_active_instance_tracking(self):
        """Verifies AVDManager active instance registry and stop_instance lifecycle."""
        # Import AVDManager from gndroid
        import importlib.util
        spec = importlib.util.spec_from_file_location("gndroid_mod", os.path.join(WORKSPACE_DIR, "gndroid.pyw"))
        gndroid_mod = importlib.util.module_from_spec(spec)
        # Execute minimal import or use classes directly
        AVDManager = getattr(gndroid_mod, "AVDManager", None)
        if AVDManager is None:
            # Load module
            spec.loader.exec_module(gndroid_mod)
            AVDManager = gndroid_mod.AVDManager

        mock_vm_proc = MagicMock()
        mock_vm_proc.pid = 88888
        mock_vm_proc.poll.return_value = None

        with AVDManager._instances_lock:
            AVDManager._active_instances["test_avd_vm"] = {
                "proc": mock_vm_proc,
                "pid": 88888,
                "port": 5556,
                "serial": "emulator-5556",
                "name": "test_avd_vm",
                "launch_time": time.time(),
                "gpu": "auto",
                "root": False
            }

        tracked = AVDManager.get_active_instance("test_avd_vm")
        self.assertIsNotNone(tracked)
        self.assertEqual(tracked["pid"], 88888)

        # Stop instance
        mock_vm_proc.poll.side_effect = [None, 0]
        stopped = AVDManager.stop_instance("test_avd_vm", timeout=1.0)
        self.assertTrue(stopped)
        self.assertIsNone(AVDManager.get_active_instance("test_avd_vm"))

    # =========================================================================
    # FEATURE 9: Multi-Instance Clean Teardown & File Lock Guard
    # =========================================================================

    def test_feature9_file_lock_detection_and_wait(self):
        """Verifies AVDManager.is_file_locked accurately tests file accessibility."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("gndroid_mod", os.path.join(WORKSPACE_DIR, "gndroid.pyw"))
        gndroid_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gndroid_mod)
        AVDManager = gndroid_mod.AVDManager

        with tempfile.NamedTemporaryFile(delete=False) as tf:
            path = tf.name

        try:
            # Unlocked file
            self.assertFalse(AVDManager.is_file_locked(path))

            # Locked file on Windows
            if sys.platform == "win32":
                import ctypes
                k32 = ctypes.windll.kernel32
                GENERIC_READ = 0x80000000
                GENERIC_WRITE = 0x40000000
                FILE_SHARE_NONE = 0
                OPEN_EXISTING = 3
                FILE_ATTRIBUTE_NORMAL = 0x80
                h = k32.CreateFileW(path, GENERIC_READ | GENERIC_WRITE, FILE_SHARE_NONE, None, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, None)
                self.assertTrue(AVDManager.is_file_locked(path), "File should be detected as locked")
                k32.CloseHandle(h)
                self.assertFalse(AVDManager.is_file_locked(path), "File should be detected as unlocked after handle close")
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_feature9_delete_instance_verified_teardown(self):
        """Verifies AVDManager.delete_instance performs process check and clean deletion."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("gndroid_mod", os.path.join(WORKSPACE_DIR, "gndroid.pyw"))
        gndroid_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gndroid_mod)
        AVDManager = gndroid_mod.AVDManager

        test_dir = tempfile.mkdtemp(prefix="avd_test_")
        avd_name = "test_clean_teardown_avd"
        avd_folder = os.path.join(test_dir, f"{avd_name}.avd")
        ini_file = os.path.join(test_dir, f"{avd_name}.ini")
        os.makedirs(avd_folder, exist_ok=True)
        with open(ini_file, "w") as f:
            f.write("target=android-34\n")
        with open(os.path.join(avd_folder, "userdata.img"), "wb") as f:
            f.write(b"\x00" * 1024)

        with patch.object(AVDManager, "get_avd_dir", return_value=test_dir):
            success = AVDManager.delete_instance(avd_name)
            self.assertTrue(success, "delete_instance should report success")
            self.assertFalse(os.path.exists(ini_file), "ini file should be deleted")
            self.assertFalse(os.path.exists(avd_folder), "avd folder should be deleted")

    # =========================================================================
    # FEATURE 10: Background Thread Pooling & USB Non-Interference
    # =========================================================================

    def test_feature10_device_scanner_usb_non_interference(self):
        """
        Verifies that DeviceScannerWorker defaults self.auto_lan_enabled = False,
        preventing disruptive automatic 'adb tcpip 5555' execution on connected USB phones.
        """
        import importlib.util
        spec = importlib.util.spec_from_file_location("gndroid_mod", os.path.join(WORKSPACE_DIR, "gndroid.pyw"))
        gndroid_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gndroid_mod)
        DeviceScannerWorker = gndroid_mod.DeviceScannerWorker

        worker = DeviceScannerWorker(None)
        # CRITICAL: Must be False by default to protect user USB debug sessions
        self.assertFalse(worker.auto_lan_enabled, "auto_lan_enabled MUST default to False")

    def test_feature10_lan_radar_worker_thread_pool_limit(self):
        """
        Verifies that LanRadarWorker limits concurrent workers to 16 (not 60)
        and uses thread-safe locking for discovered devices.
        """
        import importlib.util
        spec = importlib.util.spec_from_file_location("gndroid_mod", os.path.join(WORKSPACE_DIR, "gndroid.pyw"))
        gndroid_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gndroid_mod)
        LanRadarWorker = gndroid_mod.LanRadarWorker

        worker = LanRadarWorker(None)
        with open(os.path.join(WORKSPACE_DIR, "gndroid.pyw"), "r", encoding="utf-8") as f:
            content = f.read()

        # Check ThreadPoolExecutor max_workers is capped <= 20
        self.assertIn("max_workers=16", content, "ThreadPoolExecutor in LanRadarWorker must use max_workers=16")
        self.assertNotIn("max_workers=60", content, "Uncapped 60-worker thread pool must be removed")
        self.assertIn("found_lock = threading.Lock()", content, "Thread lock must protect shared lists")


if __name__ == "__main__":
    unittest.main(verbosity=2)
