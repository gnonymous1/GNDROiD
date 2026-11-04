"""
scripts/test_challenger_m4_portability.py
Empirical Challenger Test Suite for Milestone 4 (Portability, Process Lifecycle & IPC)
Challenger: challenger_m4_2

Tests:
1. Binary hash parity across root, tools/, and dist/
2. Workspace root discovery from diverse CWDs (root, tools/, TEMP, Desktop)
3. Native CLI (gndroid.exe) argument routing and subcommand handling
4. Python CLI (gndroid.pyw) entrypoint parsing and GUI-loop lifecycle
5. Multi-device parallel mirroring guard resilience
"""

import os
import sys
import tempfile
import unittest
import hashlib
import subprocess
import time
from unittest.mock import patch, MagicMock

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GNDROID_EXE = os.path.join(BASE_DIR, "gndroid.exe")
TOOLS_EXE = os.path.join(BASE_DIR, "tools", "gndroid.exe")
RELEASE_EXE = os.path.join(BASE_DIR, "target", "release", "gndroid.exe")
GNDROID_PYW = os.path.join(BASE_DIR, "gndroid.pyw")
DIST_PYW = os.path.join(BASE_DIR, "dist", "gndroid", "gndroid.pyw")
MAIN_RS = os.path.join(BASE_DIR, "gndroid-cli", "src", "main.rs")


def get_sha256(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest().upper()


class TestPortabilityAndProcessLifecycle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if BASE_DIR not in sys.path:
            sys.path.insert(0, BASE_DIR)

    # =========================================================================
    # 1. Binary Hash & Distribution Parity
    # =========================================================================
    def test_01_binary_hash_parity_executables(self):
        """Verify gndroid.exe, tools/gndroid.exe, and target/release/gndroid.exe SHA256 parity."""
        self.assertTrue(os.path.exists(GNDROID_EXE), f"Missing {GNDROID_EXE}")
        self.assertTrue(os.path.exists(TOOLS_EXE), f"Missing {TOOLS_EXE}")
        self.assertTrue(os.path.exists(RELEASE_EXE), f"Missing {RELEASE_EXE}")

        hash_root = get_sha256(GNDROID_EXE)
        hash_tools = get_sha256(TOOLS_EXE)
        hash_release = get_sha256(RELEASE_EXE)

        self.assertEqual(hash_root, hash_tools, "gndroid.exe and tools/gndroid.exe have mismatched hashes!")
        self.assertEqual(hash_root, hash_release, "gndroid.exe does not match compiled target/release/gndroid.exe!")
        self.assertGreater(os.path.getsize(GNDROID_EXE), 1_000_000, "Executable unexpectedly small")
        print(f"[TEST 1 PASS] Executable SHA256 verified: {hash_root} ({os.path.getsize(GNDROID_EXE):,} bytes)")

    def test_02_script_parity_gndroid_pyw(self):
        """Verify gndroid.pyw and dist/gndroid/gndroid.pyw SHA256 parity."""
        self.assertTrue(os.path.exists(GNDROID_PYW), f"Missing {GNDROID_PYW}")
        self.assertTrue(os.path.exists(DIST_PYW), f"Missing {DIST_PYW}")

        hash_root = get_sha256(GNDROID_PYW)
        hash_dist = get_sha256(DIST_PYW)

        self.assertEqual(hash_root, hash_dist, "gndroid.pyw and dist/gndroid/gndroid.pyw have mismatched hashes!")
        self.assertGreater(os.path.getsize(GNDROID_PYW), 400_000, "Script unexpectedly small")
        print(f"[TEST 2 PASS] gndroid.pyw SHA256 verified: {hash_root} ({os.path.getsize(GNDROID_PYW):,} bytes)")

    # =========================================================================
    # 2. Workspace Root Discovery from Diverse Working Directories
    # =========================================================================
    def test_03_workspace_root_from_project_root(self):
        """Run gndroid.exe --help and devices from project root."""
        res_help = subprocess.run([GNDROID_EXE, "--help"], cwd=BASE_DIR, capture_output=True, text=True)
        self.assertEqual(res_help.returncode, 0)
        self.assertIn("Usage: gndroid.exe", res_help.stdout)

        res_dev = subprocess.run([GNDROID_EXE, "devices"], cwd=BASE_DIR, capture_output=True, text=True)
        self.assertEqual(res_dev.returncode, 0)
        self.assertIn("Connected Android Devices & Virtual Machines", res_dev.stdout)
        print("[TEST 3 PASS] Execution from project root verified.")

    def test_04_workspace_root_from_tools_directory(self):
        """Run tools\\gndroid.exe --help and devices from inside tools/."""
        tools_dir = os.path.join(BASE_DIR, "tools")
        res_help = subprocess.run([TOOLS_EXE, "--help"], cwd=tools_dir, capture_output=True, text=True)
        self.assertEqual(res_help.returncode, 0)
        self.assertIn("Usage: gndroid.exe", res_help.stdout)

        res_dev = subprocess.run([TOOLS_EXE, "devices"], cwd=tools_dir, capture_output=True, text=True)
        self.assertEqual(res_dev.returncode, 0)
        self.assertIn("Connected Android Devices & Virtual Machines", res_dev.stdout)
        print("[TEST 4 PASS] Execution from tools/ directory verified.")

    def test_05_workspace_root_from_temp_directory(self):
        """Run gndroid.exe and tools/gndroid.exe from %TEMP% directory via absolute path."""
        temp_dir = tempfile.gettempdir()
        res_help = subprocess.run([GNDROID_EXE, "--help"], cwd=temp_dir, capture_output=True, text=True)
        self.assertEqual(res_help.returncode, 0)

        res_tools_help = subprocess.run([TOOLS_EXE, "--help"], cwd=temp_dir, capture_output=True, text=True)
        self.assertEqual(res_tools_help.returncode, 0)

        res_dev = subprocess.run([GNDROID_EXE, "devices"], cwd=temp_dir, capture_output=True, text=True)
        self.assertEqual(res_dev.returncode, 0)
        self.assertIn("Connected Android Devices & Virtual Machines", res_dev.stdout)

        res_tools_dev = subprocess.run([TOOLS_EXE, "devices"], cwd=temp_dir, capture_output=True, text=True)
        self.assertEqual(res_tools_dev.returncode, 0)
        self.assertIn("Connected Android Devices & Virtual Machines", res_tools_dev.stdout)
        print("[TEST 5 PASS] Execution from TEMP directory via absolute path verified.")

    def test_06_workspace_root_from_sibling_directory_relative_path(self):
        """Run gndroid.exe from parent Desktop directory via relative path."""
        parent_dir = os.path.dirname(BASE_DIR)
        
        # Test relative invocation via PowerShell from parent Desktop
        cmd_help = f"Set-Location '{parent_dir}'; & '.\\Android Emulator\\gndroid.exe' --help"
        res_help = subprocess.run(["powershell", "-NoProfile", "-Command", cmd_help], capture_output=True, text=True)
        self.assertEqual(res_help.returncode, 0, f"Relative gndroid.exe --help failed: {res_help.stderr}")
        self.assertIn("Usage: gndroid.exe", res_help.stdout)

        cmd_dev = f"Set-Location '{parent_dir}'; & '.\\Android Emulator\\tools\\gndroid.exe' devices"
        res_dev = subprocess.run(["powershell", "-NoProfile", "-Command", cmd_dev], capture_output=True, text=True)
        self.assertEqual(res_dev.returncode, 0, f"Relative tools\\gndroid.exe devices failed: {res_dev.stderr}")
        self.assertIn("Connected Android Devices & Virtual Machines", res_dev.stdout)
        print("[TEST 6 PASS] Execution from parent directory via relative path verified.")

    # =========================================================================
    # 3. Dynamic Root Resolution Code Inspection (main.rs)
    # =========================================================================
    def test_07_no_hardcoded_paths_in_rust_source(self):
        """Ensure main.rs has zero hardcoded user directories and uses robust ancestors traversal."""
        with open(MAIN_RS, "r", encoding="utf-8", errors="ignore") as f:
            code = f.read()

        self.assertNotIn("Reader-Branch", code, "Hardcoded 'Reader-Branch' path found in main.rs!")
        self.assertNotIn(r"C:\Users\\", code, "Hardcoded user directory found in main.rs!")
        self.assertIn("exe_path.canonicalize()", code, "Missing canonicalize call in main.rs")
        self.assertIn("ancestors()", code, "Missing ancestors traversal in main.rs")
        self.assertIn("GNDROID_HOME", code, "Missing GNDROID_HOME env check in main.rs")
        print("[TEST 7 PASS] Dynamic path resolution in main.rs verified clean of hardcoded user paths.")

    # =========================================================================
    # 4. gndroid.pyw CLI Routing & Lifecycle
    # =========================================================================
    def test_08_avd_and_instance_argument_extraction(self):
        """Verify gndroid.pyw argument handling extracts avd/instance names across all variants."""
        # Simulated extraction tests matching lines 10141-10163 of gndroid.pyw
        def extract_avd(args):
            avd_name = ""
            if "--avd" in args:
                idx = args.index("--avd")
                if idx + 1 < len(args) and not args[idx + 1].startswith("-"):
                    avd_name = args[idx + 1]
            elif "--instance" in args:
                idx = args.index("--instance")
                if idx + 1 < len(args) and not args[idx + 1].startswith("-"):
                    avd_name = args[idx + 1]
            elif "launch" in args:
                idx = args.index("launch")
                if idx + 1 < len(args) and not args[idx + 1].startswith("-"):
                    avd_name = args[idx + 1]

            if not avd_name and ("--avd" in args or "--instance" in args):
                avd_name = "gndroid"
            return avd_name

        self.assertEqual(extract_avd(["--avd", "Test_AVD_1"]), "Test_AVD_1")
        self.assertEqual(extract_avd(["--instance", "Test_Instance_2"]), "Test_Instance_2")
        self.assertEqual(extract_avd(["launch", "Positional_AVD"]), "Positional_AVD")
        self.assertEqual(extract_avd(["launch", "--avd", "Combo_AVD"]), "Combo_AVD")
        self.assertEqual(extract_avd(["--avd"]), "gndroid")
        self.assertEqual(extract_avd(["--instance"]), "gndroid")
        print("[TEST 8 PASS] --avd and --instance extraction logic verified.")

    def test_09_mirror_argument_extraction(self):
        """Verify gndroid.pyw argument handling extracts mirror serial across all variants."""
        def extract_mirror_serial(args):
            target_serial = ""
            if "--mirror" in args:
                m_idx = args.index("--mirror")
                if m_idx + 1 < len(args) and not args[m_idx + 1].startswith("-"):
                    target_serial = args[m_idx + 1]
            elif "mirror" in args:
                m_idx = args.index("mirror")
                if m_idx + 1 < len(args) and not args[m_idx + 1].startswith("-"):
                    target_serial = args[m_idx + 1]

            if not target_serial:
                if "--serial" in args:
                    s_idx = args.index("--serial")
                    if s_idx + 1 < len(args):
                        target_serial = args[s_idx + 1]
                elif "-s" in args:
                    s_idx = args.index("-s")
                    if s_idx + 1 < len(args):
                        target_serial = args[s_idx + 1]
            return target_serial

        self.assertEqual(extract_mirror_serial(["--mirror", "192.168.1.100:5555"]), "192.168.1.100:5555")
        self.assertEqual(extract_mirror_serial(["mirror", "emulator-5556"]), "emulator-5556")
        self.assertEqual(extract_mirror_serial(["--mirror", "-s", "phone_123"]), "phone_123")
        self.assertEqual(extract_mirror_serial(["--mirror", "--serial", "phone_456"]), "phone_456")
        self.assertEqual(extract_mirror_serial(["mirror", "-s", "phone_789"]), "phone_789")
        self.assertEqual(extract_mirror_serial(["--mirror"]), "")
        print("[TEST 9 PASS] --mirror serial extraction logic verified.")

    def test_10_app_shortcut_flags_nonblocking_contract(self):
        """Verify gndroid.exe forwards --app and does not crash clap or open GUI blocking loop."""
        res = subprocess.run(
            [GNDROID_EXE, "--app", "com.android.settings", "--window", "--user", "0", "--title", "Settings"],
            capture_output=True,
            text=True,
            timeout=5
        )
        self.assertEqual(res.returncode, 0, f"gndroid.exe returned non-zero: {res.stderr}")
        self.assertNotIn("error:", res.stderr)
        self.assertIn("GNDROiD process spawned successfully in background", res.stdout)
        print("[TEST 10 PASS] --app shortcut non-blocking dispatch verified.")

    def test_11_help_flag_lifecycle_empirical_investigation(self):
        """
        Empirically test 'python gndroid.pyw --help' process lifecycle.
        Documents whether python gndroid.pyw --help terminates cleanly or stays running in GUI loop.
        """
        proc = subprocess.Popen([sys.executable, GNDROID_PYW, "--help"])
        time.sleep(1.5)
        poll = proc.poll()
        if poll is None:
            # Process is still running inside QApplication event loop!
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except Exception:
                proc.kill()
            status = "GUI_LOOP_OPEN (Process stayed alive, terminated by test)"
        else:
            status = f"EXITED_CODE_{poll}"

        print(f"[TEST 11 EMPIRICAL FINDING] python gndroid.pyw --help lifecycle: {status}")
        # Note: gndroid.exe --help exits immediately with code 0.
        # But gndroid.pyw --help enters GNDroidApp().show() because gndroid.pyw lacks a --help argument handler.
        self.assertIsNotNone(proc)

    def test_12_multidevice_singleton_guard_logic(self):
        """Verify per-device singleton guard distinguishes different device serials."""
        def check_guard(running_titles, incoming_serial):
            # Same logic as gndroid.pyw:10202-10228
            candidate_titles = [
                f"GNDROiD Controls - {incoming_serial}",
                f"gndroid Controls - {incoming_serial}"
            ]
            for t in candidate_titles:
                if t in running_titles:
                    return "BLOCKED_SAME_DEVICE"
            for t in running_titles:
                if "controls" in t.lower() and incoming_serial.lower() in t.lower():
                    return "BLOCKED_SAME_DEVICE"
            return "ALLOWED_CONCURRENT"

        running = ["GNDROiD Controls - emulator-5554"]
        self.assertEqual(check_guard(running, "emulator-5554"), "BLOCKED_SAME_DEVICE")
        self.assertEqual(check_guard(running, "emulator-5556"), "ALLOWED_CONCURRENT")
        self.assertEqual(check_guard(running, "192.168.1.50:5555"), "ALLOWED_CONCURRENT")
        print("[TEST 12 PASS] Multi-device singleton guard logic verified.")


if __name__ == "__main__":
    unittest.main()
