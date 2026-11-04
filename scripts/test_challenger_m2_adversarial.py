"""
scripts/test_challenger_m2_adversarial.py
=========================================
Empirical Adversarial Stress Verification Suite for Milestone 2:
Subprocess Lifecycle & Process Safety (Features 7 - 10)

Author: challenger_m2_2 (Teamwork Challenger)
Mission: Stress-test Win32 Job Object containment, kernel enrollment,
         exclusive file locking, teardown backoff polling, and instance deletion.
"""

import os
import sys
import time
import tempfile
import unittest
import threading
import subprocess
from unittest.mock import patch, MagicMock

# Force offscreen Qt rendering
os.environ["QT_QPA_PLATFORM"] = "offscreen"

WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WORKSPACE_DIR not in sys.path:
    sys.path.insert(0, WORKSPACE_DIR)

import ctypes
from ctypes import wintypes
import psutil

from nexus.wireless_mirror import WirelessMirrorManager
from nexus.app_cloner_and_window import (
    AppWindowManager,
    Win32JobManager,
    assign_to_job_object
)

# Dynamic import of AVDManager, DeviceScannerWorker, LanRadarWorker from gndroid.pyw
import importlib.util
spec = importlib.util.spec_from_file_location("gndroid_mod", os.path.join(WORKSPACE_DIR, "gndroid.pyw"))
gndroid_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gndroid_mod)
AVDManager = gndroid_mod.AVDManager
DeviceScannerWorker = gndroid_mod.DeviceScannerWorker
LanRadarWorker = gndroid_mod.LanRadarWorker


class TestMilestone2Adversarial(unittest.TestCase):

    # =========================================================================
    # TASK 1: Win32 Job Object Kernel Verification & Process Assignment
    # =========================================================================

    def test_job_object_singleton_and_kernel_flags(self):
        """
        Adversarial Test 1:
        Query Windows kernel directly via QueryInformationJobObject to verify
        that JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE (0x00002000) is set on the OS Job Object.
        """
        job_mgr1 = Win32JobManager.get_instance()
        job_mgr2 = Win32JobManager.get_instance()
        self.assertIs(job_mgr1, job_mgr2, "Win32JobManager must be a strict singleton")

        if sys.platform != "win32":
            self.skipTest("Win32 Job Object verification requires Windows platform")

        self.assertIsNotNone(job_mgr1._job_handle, "Job Object handle must not be None")
        self.assertNotEqual(job_mgr1._job_handle, 0, "Job Object handle must be valid")

        k32 = ctypes.windll.kernel32

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ('ReadOperationCount', ctypes.c_uint64),
                ('WriteOperationCount', ctypes.c_uint64),
                ('OtherOperationCount', ctypes.c_uint64),
                ('ReadTransferCount', ctypes.c_uint64),
                ('WriteTransferCount', ctypes.c_uint64),
                ('OtherTransferCount', ctypes.c_uint64),
            ]

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ('PerProcessUserTimeLimit', ctypes.c_int64),
                ('PerJobUserTimeLimit', ctypes.c_int64),
                ('LimitFlags', wintypes.DWORD),
                ('MinimumWorkingSetSize', ctypes.c_size_t),
                ('MaximumWorkingSetSize', ctypes.c_size_t),
                ('ActiveProcessLimit', wintypes.DWORD),
                ('Affinity', ctypes.c_size_t),
                ('PriorityClass', wintypes.DWORD),
                ('SchedulingClass', wintypes.DWORD),
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ('BasicLimitInformation', JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ('IoInfo', IO_COUNTERS),
                ('ProcessMemoryLimit', ctypes.c_size_t),
                ('JobMemoryLimit', ctypes.c_size_t),
                ('PeakProcessMemoryLimit', ctypes.c_size_t),
                ('PeakJobMemoryLimit', ctypes.c_size_t),
            ]

        JobObjectExtendedLimitInformation = 9
        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        return_length = wintypes.DWORD()

        res = k32.QueryInformationJobObject(
            job_mgr1._job_handle,
            JobObjectExtendedLimitInformation,
            ctypes.byref(info),
            ctypes.sizeof(info),
            ctypes.byref(return_length)
        )
        self.assertNotEqual(res, 0, "QueryInformationJobObject must succeed on the Win32 Job Object")
        
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
        flags = info.BasicLimitInformation.LimitFlags
        self.assertTrue(
            bool(flags & JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE),
            f"Expected JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE (0x2000) to be set. Got LimitFlags: {hex(flags)}"
        )

    def test_kernel_is_process_in_job_empirical(self):
        """
        Adversarial Test 2:
        Spawn a live child process, assign it to Win32JobManager, and query the
        Windows kernel directly with IsProcessInJob to guarantee empirical enrollment.
        """
        if sys.platform != "win32":
            self.skipTest("Requires Windows platform")

        job_mgr = Win32JobManager.get_instance()
        k32 = ctypes.windll.kernel32

        # Spawn a genuine long-running process
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        try:
            # Assign to Job Object
            assigned = job_mgr.assign_process(proc)
            self.assertTrue(assigned, "assign_process must return True for live Popen")

            # Query Windows kernel directly via IsProcessInJob
            is_in_job = wintypes.BOOL()
            # proc._handle is opened with PROCESS_ALL_ACCESS on Windows
            h_proc = proc._handle
            res = k32.IsProcessInJob(h_proc, job_mgr._job_handle, ctypes.byref(is_in_job))
            self.assertNotEqual(res, 0, "IsProcessInJob API call must succeed")
            self.assertEqual(is_in_job.value, 1, "Windows kernel must confirm the process is enrolled in the Job Object")

            # Also check tracked PIDs
            self.assertIn(proc.pid, job_mgr.get_tracked_pids())
        finally:
            proc.kill()
            proc.wait()

    def test_job_assignment_by_pid_and_kernel_verification(self):
        """
        Adversarial Test 3:
        Spawn a child process and assign it using only its integer PID (fallback path).
        Verify kernel confirms enrollment.
        """
        if sys.platform != "win32":
            self.skipTest("Requires Windows platform")

        job_mgr = Win32JobManager.get_instance()
        k32 = ctypes.windll.kernel32

        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        try:
            assigned = job_mgr.assign_process(proc.pid)
            self.assertTrue(assigned, "assign_process must succeed when given an integer PID")

            is_in_job = wintypes.BOOL()
            res = k32.IsProcessInJob(proc._handle, job_mgr._job_handle, ctypes.byref(is_in_job))
            self.assertNotEqual(res, 0, "IsProcessInJob API call must succeed")
            self.assertEqual(is_in_job.value, 1, "Kernel must confirm process enrolled via PID assignment")
        finally:
            proc.kill()
            proc.wait()

    def test_job_object_kill_on_close_parent_exit(self):
        """
        Adversarial Test 4:
        Empirically verify Windows kernel KILL_ON_JOB_CLOSE behavior:
        Spawn a helper parent process that initializes Win32JobManager,
        spawns a child process, enrolls it, and exits abruptly.
        Verify Windows kernel automatically terminates the child process.
        """
        if sys.platform != "win32":
            self.skipTest("Requires Windows platform")

        helper_code = (
            "import sys, time, subprocess\n"
            "from nexus.app_cloner_and_window import Win32JobManager\n"
            "job_mgr = Win32JobManager.get_instance()\n"
            "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
            "job_mgr.assign_process(child)\n"
            "print(child.pid, flush=True)\n"
            "sys.exit(0)\n"
        )

        proc = subprocess.Popen(
            [sys.executable, "-c", helper_code],
            stdout=subprocess.PIPE,
            text=True
        )
        child_pid_str = proc.stdout.readline().strip()
        proc.stdout.close()
        child_pid = int(child_pid_str)
        proc.wait(timeout=5.0)

        # Allow kernel a brief moment to close job handle and terminate processes
        time.sleep(1.0)
        is_alive = psutil.pid_exists(child_pid)
        self.assertFalse(
            is_alive,
            f"Child process {child_pid} MUST be reaped by Windows kernel when parent exits with KILL_ON_JOB_CLOSE"
        )

    def test_job_assignment_edge_cases(self):
        """
        Adversarial Test 4:
        Stress test assign_process with adversarial / invalid inputs:
        None, negative PID, non-existent high PID, terminated process.
        """
        job_mgr = Win32JobManager.get_instance()

        # 1. None
        self.assertFalse(job_mgr.assign_process(None))

        # 2. Non-existent PID
        res = job_mgr.assign_process(99999999)
        self.assertFalse(res, "assign_process should return False for non-existent PID")

        # 3. Terminated process
        dead_proc = subprocess.Popen([sys.executable, "-c", "import sys; sys.exit(0)"])
        dead_proc.wait(timeout=2.0)
        # Assigning a terminated process should not throw an unhandled exception
        try:
            job_mgr.assign_process(dead_proc)
        except Exception as e:
            self.fail(f"assign_process on dead process raised exception: {e}")

    def test_job_manager_terminate_all_tracked_processes(self):
        """
        Adversarial Test 5:
        Spawn multiple live processes, assign them to JobManager,
        and verify terminate_all_tracked_processes cleanly kills them all.
        """
        job_mgr = Win32JobManager.get_instance()
        procs = [
            subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
            for _ in range(3)
        ]

        try:
            for p in procs:
                job_mgr.assign_process(p)

            # Terminate all
            job_mgr.terminate_all_tracked_processes(timeout=2.0)

            for p in procs:
                self.assertIsNotNone(p.poll(), f"Process {p.pid} should have terminated")
                self.assertFalse(psutil.pid_exists(p.pid), f"PID {p.pid} should no longer exist in OS")
        finally:
            for p in procs:
                try:
                    p.kill()
                except Exception:
                    pass

    # =========================================================================
    # TASK 2: File Lock Detection & Teardown Guards
    # =========================================================================

    def test_is_file_locked_accurate_detection_and_release(self):
        """
        Adversarial Test 6:
        Simulate an active locked file handle with FILE_SHARE_NONE.
        Verify is_file_locked accurately detects True while open,
        and False immediately after CloseHandle.
        """
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            path = tf.name

        try:
            # Baseline: Unlocked
            self.assertFalse(AVDManager.is_file_locked(path), "Fresh file should be unlocked")

            if sys.platform == "win32":
                k32 = ctypes.windll.kernel32
                GENERIC_READ = 0x80000000
                GENERIC_WRITE = 0x40000000
                FILE_SHARE_NONE = 0
                OPEN_EXISTING = 3
                FILE_ATTRIBUTE_NORMAL = 0x80

                # Open exclusive handle
                h = k32.CreateFileW(
                    path,
                    GENERIC_READ | GENERIC_WRITE,
                    FILE_SHARE_NONE,
                    None,
                    OPEN_EXISTING,
                    FILE_ATTRIBUTE_NORMAL,
                    None
                )
                self.assertNotEqual(h, -1, "Failed to create exclusive file handle")
                try:
                    # While handle is held, is_file_locked MUST be True
                    self.assertTrue(
                        AVDManager.is_file_locked(path),
                        "is_file_locked must return True when an exclusive handle is held"
                    )
                finally:
                    k32.CloseHandle(h)

                # After close, must return False immediately
                self.assertFalse(
                    AVDManager.is_file_locked(path),
                    "is_file_locked must return False immediately after handle is closed"
                )
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_is_file_locked_edge_cases(self):
        """
        Adversarial Test 7:
        Test is_file_locked with non-existent path, directory path, and empty string.
        """
        self.assertFalse(AVDManager.is_file_locked("C:\\non_existent_file_xyz_12345.img"))
        self.assertFalse(AVDManager.is_file_locked(""))

        # Directory path
        temp_dir = tempfile.mkdtemp()
        try:
            # Calling is_file_locked on directory should not crash
            result = AVDManager.is_file_locked(temp_dir)
            self.assertIsInstance(result, bool)
        finally:
            os.rmdir(temp_dir)

    def test_wait_for_file_locks_released_with_dynamic_delayed_release(self):
        """
        Adversarial Test 8:
        Create an AVD folder with userdata.img. Hold an exclusive lock in a background thread
        and release it after 0.5s. Verify wait_for_file_locks_released polls using progressive
        backoff and succeeds as soon as the lock is freed.
        """
        if sys.platform != "win32":
            self.skipTest("Requires Windows platform")

        temp_dir = tempfile.mkdtemp(prefix="avd_lock_test_")
        img_path = os.path.join(temp_dir, "userdata.img")
        with open(img_path, "wb") as f:
            f.write(b"\x00" * 4096)

        k32 = ctypes.windll.kernel32
        GENERIC_READ = 0x80000000
        GENERIC_WRITE = 0x40000000
        FILE_SHARE_NONE = 0
        OPEN_EXISTING = 3
        FILE_ATTRIBUTE_NORMAL = 0x80

        h = k32.CreateFileW(
            img_path,
            GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_NONE,
            None,
            OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL,
            None
        )
        self.assertNotEqual(h, -1)

        def delayed_release():
            time.sleep(0.5)
            k32.CloseHandle(h)

        release_thread = threading.Thread(target=delayed_release)
        release_thread.start()

        start_time = time.time()
        # wait_for_file_locks_released has timeout=5.0
        success = AVDManager.wait_for_file_locks_released(temp_dir, timeout=5.0)
        elapsed = time.time() - start_time

        release_thread.join()

        try:
            self.assertTrue(success, "wait_for_file_locks_released should succeed after dynamic lock release")
            self.assertGreaterEqual(elapsed, 0.4, "Must have waited for the lock release")
            self.assertLess(elapsed, 3.0, "Must return promptly after lock release without hanging")
        finally:
            shutil_dir = temp_dir
            import shutil
            shutil.rmtree(shutil_dir, ignore_errors=True)

    def test_wait_for_file_locks_released_timeout(self):
        """
        Adversarial Test 9:
        Hold an exclusive lock continuously. Verify wait_for_file_locks_released
        times out and returns False without hanging or crashing.
        """
        if sys.platform != "win32":
            self.skipTest("Requires Windows platform")

        temp_dir = tempfile.mkdtemp(prefix="avd_lock_timeout_")
        img_path = os.path.join(temp_dir, "system.img.qcow2")
        with open(img_path, "wb") as f:
            f.write(b"\x00" * 4096)

        k32 = ctypes.windll.kernel32
        h = k32.CreateFileW(
            img_path,
            0x80000000 | 0x40000000,
            0,
            None,
            3,
            0x80,
            None
        )
        self.assertNotEqual(h, -1)

        try:
            start_time = time.time()
            success = AVDManager.wait_for_file_locks_released(temp_dir, timeout=0.6)
            elapsed = time.time() - start_time

            self.assertFalse(success, "Must return False when lock is held beyond timeout")
            self.assertGreaterEqual(elapsed, 0.5, "Must wait up to the timeout")
            self.assertLess(elapsed, 2.0, "Must not exceed timeout significantly")
        finally:
            k32.CloseHandle(h)
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_delete_instance_checks_and_terminates_running_process(self):
        """
        Adversarial Test 10:
        Verify AVDManager.delete_instance checks active running instance status,
        stops the running process, and then safely deletes folder.
        """
        test_dir = tempfile.mkdtemp(prefix="avd_del_active_")
        avd_name = "active_running_instance_test"
        avd_folder = os.path.join(test_dir, f"{avd_name}.avd")
        ini_file = os.path.join(test_dir, f"{avd_name}.ini")
        os.makedirs(avd_folder, exist_ok=True)
        with open(ini_file, "w") as f:
            f.write("target=android-34\n")
        with open(os.path.join(avd_folder, "userdata.img"), "wb") as f:
            f.write(b"\x00" * 1024)

        # Mock active running instance
        mock_proc = MagicMock()
        mock_proc.pid = 77777
        mock_proc.poll.side_effect = [None, None, 0]  # running, then terminates

        with AVDManager._instances_lock:
            AVDManager._active_instances[avd_name] = {
                "proc": mock_proc,
                "pid": 77777,
                "port": 5558,
                "serial": "emulator-5558",
                "name": avd_name,
                "launch_time": time.time(),
                "gpu": "auto",
                "root": False
            }

        try:
            with patch.object(AVDManager, "get_avd_dir", return_value=test_dir):
                deleted = AVDManager.delete_instance(avd_name)
                self.assertTrue(deleted, "delete_instance should succeed")
                self.assertFalse(os.path.exists(ini_file), "ini file should be deleted")
                self.assertFalse(os.path.exists(avd_folder), "avd folder should be deleted")
                self.assertNotIn(avd_name, AVDManager._active_instances, "Instance must be removed from active registry")
        finally:
            import shutil
            shutil.rmtree(test_dir, ignore_errors=True)

    # =========================================================================
    # TASK 3: High-Pressure Scrcpy Stderr Drain Verification
    # =========================================================================

    def test_drain_pipe_async_high_throughput_flood(self):
        """
        Adversarial Test 11:
        Flood 256 KB of binary logs to stderr (64x larger than the 4 KB Windows pipe buffer).
        Without asynchronous draining, process hangs at 4 KB.
        Verify process completes cleanly in under 3.0 seconds.
        """
        code = (
            "import sys, time\n"
            "chunk = b'D' * 4096\n"
            "for _ in range(64):\n"  # 64 * 4096 = 256 KB
            "    sys.stderr.buffer.write(chunk)\n"
            "    sys.stderr.buffer.flush()\n"
            "sys.exit(0)\n"
        )
        proc = subprocess.Popen(
            [sys.executable, "-c", code],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE
        )

        drain_thread = WirelessMirrorManager.drain_pipe_async(proc)
        self.assertIsNotNone(drain_thread)

        start = time.time()
        exit_code = proc.wait(timeout=5.0)
        elapsed = time.time() - start

        self.assertEqual(exit_code, 0)
        self.assertLess(elapsed, 3.0, "High throughput drain should complete rapidly without stalling")

    # =========================================================================
    # TASK 4: Thread Pool Concurrency & Mutex Verification
    # =========================================================================

    def test_device_scanner_usb_non_interference(self):
        """
        Adversarial Test 12:
        Ensure auto_lan_enabled is explicitly False by default.
        """
        scanner = DeviceScannerWorker(None)
        self.assertFalse(
            scanner.auto_lan_enabled,
            "auto_lan_enabled MUST be False to prevent aggressive USB debugging hijacking"
        )

    def test_lan_radar_concurrency_and_mutex(self):
        """
        Adversarial Test 13:
        Verify source code contains max_workers=16 and found_lock mutex protection.
        """
        with open(os.path.join(WORKSPACE_DIR, "gndroid.pyw"), "r", encoding="utf-8") as f:
            src = f.read()

        self.assertIn("max_workers=16", src)
        self.assertNotIn("max_workers=60", src)
        self.assertIn("found_lock = threading.Lock()", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
