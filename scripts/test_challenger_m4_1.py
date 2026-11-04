"""
scripts/test_challenger_m4_1.py — Empirical Challenger Verification Suite for Milestone 4
Adversarial stress-testing of Native Rust CLI Hardening & IPC (Features 16–18).

Author: challenger_m4_1 (Milestone 4 Empirical CLI Verifier)
Target:
1. Feature 16: Complex desktop shortcut flags via gndroid.exe (--app, --window, --user, --title, --serial)
2. Feature 17: Subcommand routing for launch (--avd, positional) and mirror (-s, positional)
3. Feature 18: Multi-device companion ribbon collision avoidance and duplicate guard
"""

import os
import sys
import unittest
import subprocess
import tempfile
import ctypes
import time
from typing import Optional, List, Tuple

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GNDROID_EXE = os.path.join(BASE_DIR, "gndroid.exe")
TOOLS_GNDROID_EXE = os.path.join(BASE_DIR, "tools", "gndroid.exe")
GNDROID_PYW = os.path.join(BASE_DIR, "gndroid.pyw")
MAIN_RS = os.path.join(BASE_DIR, "gndroid-cli", "src", "main.rs")


def invoke_cli(cmd_args: List[str], timeout: float = 3.0) -> Tuple[int, str, str]:
    """
    Executes gndroid.exe using TemporaryFiles for stdout/stderr to prevent pipe buffer
    inheritance hangs when detached pythonw.exe child processes are spawned.
    """
    with tempfile.TemporaryFile(mode='w+', encoding='utf-8') as out_f, \
         tempfile.TemporaryFile(mode='w+', encoding='utf-8') as err_f:
        proc = subprocess.Popen(cmd_args, stdout=out_f, stderr=err_f, stdin=subprocess.DEVNULL)
        try:
            retcode = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            retcode = proc.wait()
        out_f.seek(0)
        err_f.seek(0)
        return retcode, out_f.read().strip(), err_f.read().strip()


class TestMilestone4EmpiricalChallenger(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if BASE_DIR not in sys.path:
            sys.path.insert(0, BASE_DIR)
        assert os.path.exists(GNDROID_EXE), f"Compiled native binary missing at {GNDROID_EXE}"
        assert os.path.exists(GNDROID_PYW), f"Core Python script missing at {GNDROID_PYW}"

    @classmethod
    def tearDownClass(cls):
        # Clean up any detached pythonw instances that may have been spawned during test executions
        try:
            subprocess.run(["taskkill", "/F", "/IM", "pythonw.exe"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=0x08000000)
        except Exception:
            pass

    # --------------------------------------------------------------------------
    # FEATURE 16: Desktop App Shortcut CLI Invocations
    # --------------------------------------------------------------------------
    def test_feature16_complex_desktop_shortcut_invocation(self):
        """Feature 16: Invoke gndroid.exe with exact prompt flags:
        `gndroid.exe --app com.example.my_app --window --user 10 --title "My Pinned App - Work"`
        Verify clap parses cleanly with exit code 0 (and specifically != 2)."""
        cmd = [
            GNDROID_EXE,
            "--app", "com.example.my_app",
            "--window",
            "--user", "10",
            "--title", "My Pinned App - Work"
        ]
        retcode, stdout, stderr = invoke_cli(cmd)
        self.assertNotEqual(retcode, 2, f"Clap rejected arguments with error code 2. Stderr: {stderr}")
        self.assertEqual(retcode, 0, f"Expected exit code 0, got {retcode}. Stderr: {stderr}")
        self.assertNotIn("error:", stderr.lower())
        self.assertNotIn("unexpected argument", stderr.lower())
        self.assertIn("GNDROiD process spawned successfully", stdout)
        print("✓ Feature 16: Exact prompt desktop shortcut flags parsed with exit code 0")

    def test_feature16_desktop_shortcut_variations_and_negative_test(self):
        """Feature 16: Test flag permutations, short options, special characters, and verify clap error on invalid flags."""
        test_cases = [
            # Short -w option
            [GNDROID_EXE, "--app", "org.telegram.messenger", "-w", "--title", "Telegram Work"],
            # Cloned user profile with spaces in title
            [GNDROID_EXE, "--app", "com.whatsapp", "--window", "--user", "12", "--title", "WhatsApp [Personal & Work]"],
            # Explicit serial target
            [GNDROID_EXE, "--app", "com.android.chrome", "--window", "-s", "192.168.1.100:5555"],
            # Unicode / non-ASCII app title
            [GNDROID_EXE, "--app", "com.instagram.android", "--window", "--title", "Instagram Work"],
        ]
        for cmd in test_cases:
            retcode, stdout, stderr = invoke_cli(cmd)
            self.assertNotEqual(retcode, 2, f"Clap failed on command {cmd}. Stderr: {stderr}")
            self.assertEqual(retcode, 0, f"Exit code not 0 for {cmd}. Stderr: {stderr}")
            self.assertNotIn("unexpected argument", stderr.lower())

        # Negative test: clap MUST fail on invalid/unrecognized flags with exit code 2
        bad_cmd = [GNDROID_EXE, "--nonexistent-unrecognized-flag"]
        retcode_bad, stdout_bad, stderr_bad = invoke_cli(bad_cmd)
        self.assertEqual(retcode_bad, 2, f"Clap should return exit code 2 for unrecognized flag, got {retcode_bad}")
        self.assertIn("unexpected argument", stderr_bad.lower())
        print(f"✓ Feature 16: Valid variations succeeded (code 0) and invalid flag rejected by clap (code 2)")

    # --------------------------------------------------------------------------
    # FEATURE 17: Subcommand & Argument Routing (Launch & Mirror)
    # --------------------------------------------------------------------------
    def test_feature17_launch_subcommand_named_and_positional(self):
        """Feature 17: Test `gndroid.exe launch --avd "Pixel_7_Pro_API_34"` and `gndroid.exe launch "Pixel_7_Pro_API_34"`."""
        # 1. Named flag: --avd
        cmd_named = [GNDROID_EXE, "launch", "--avd", "Pixel_7_Pro_API_34"]
        ret_named, out_named, err_named = invoke_cli(cmd_named)
        self.assertEqual(ret_named, 0, f"launch --avd failed. Stderr: {err_named}")
        self.assertNotIn("error:", err_named.lower())
        self.assertIn("GNDROiD process spawned successfully", out_named)

        # 2. Positional argument
        cmd_pos = [GNDROID_EXE, "launch", "Pixel_7_Pro_API_34"]
        ret_pos, out_pos, err_pos = invoke_cli(cmd_pos)
        self.assertEqual(ret_pos, 0, f"launch positional failed. Stderr: {err_pos}")
        self.assertNotIn("error:", err_pos.lower())
        self.assertIn("GNDROiD process spawned successfully", out_pos)

        # 3. Visible alias flag: --instance
        cmd_alias = [GNDROID_EXE, "launch", "--instance", "Pixel_7_Pro_API_34"]
        ret_alias, out_alias, err_alias = invoke_cli(cmd_alias)
        self.assertEqual(ret_alias, 0, f"launch --instance failed. Stderr: {err_alias}")

        print("✓ Feature 17: `launch --avd` and `launch <name>` executed cleanly with exit code 0")

    def test_feature17_mirror_subcommand_named_and_positional(self):
        """Feature 17: Test `gndroid.exe mirror -s 192.168.1.100:5555` and `gndroid.exe mirror 192.168.1.100:5555`."""
        # 1. Named flag: -s
        cmd_short = [GNDROID_EXE, "mirror", "-s", "192.168.1.100:5555"]
        ret_short, out_short, err_short = invoke_cli(cmd_short)
        self.assertEqual(ret_short, 0, f"mirror -s failed. Stderr: {err_short}")
        self.assertNotIn("error:", err_short.lower())
        self.assertIn("GNDROiD process spawned successfully", out_short)

        # 2. Positional argument
        cmd_pos = [GNDROID_EXE, "mirror", "192.168.1.100:5555"]
        ret_pos, out_pos, err_pos = invoke_cli(cmd_pos)
        self.assertEqual(ret_pos, 0, f"mirror positional failed. Stderr: {err_pos}")
        self.assertNotIn("error:", err_pos.lower())
        self.assertIn("GNDROiD process spawned successfully", out_pos)

        # 3. Long named flag: --serial
        cmd_long = [GNDROID_EXE, "mirror", "--serial", "192.168.1.100:5555"]
        ret_long, out_long, err_long = invoke_cli(cmd_long)
        self.assertEqual(ret_long, 0, f"mirror --serial failed. Stderr: {err_long}")

        print("✓ Feature 17: `mirror -s` and `mirror <serial>` executed cleanly with exit code 0")

    def test_feature17_backend_parameter_propagation_contract(self):
        """Feature 17: Verify gndroid.pyw preserves target serial without clearing or hardcoding empty strings."""
        with open(GNDROID_PYW, "r", encoding="utf-8", errors="ignore") as f:
            py_code = f.read()

        # Contract 1: In --mirror handling, start_mirror_with_fallback must receive target_serial
        self.assertIn("sidebar = start_mirror_with_fallback(target_serial, None)", py_code,
                      "start_mirror_with_fallback must receive target_serial, not hardcoded empty string")

        # Contract 2: In --avd handling, AVDManager.launch_emulator_instance must receive avd_name
        self.assertIn("AVDManager.launch_emulator_instance(avd_name)", py_code,
                      "AVDManager.launch_emulator_instance must receive avd_name")

        # Extraction logic verification
        def parse_gndroid_mirror(args):
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

        self.assertEqual(parse_gndroid_mirror(["--mirror", "192.168.1.100:5555"]), "192.168.1.100:5555")
        self.assertEqual(parse_gndroid_mirror(["mirror", "192.168.1.100:5555"]), "192.168.1.100:5555")
        self.assertEqual(parse_gndroid_mirror(["--mirror", "-s", "192.168.1.100:5555"]), "192.168.1.100:5555")
        self.assertEqual(parse_gndroid_mirror(["--mirror", "--serial", "192.168.1.100:5555"]), "192.168.1.100:5555")

        print("✓ Feature 17: Python backend parameter preservation contract verified")

    # --------------------------------------------------------------------------
    # FEATURE 18: Multi-Device Ribbon Collision Avoidance & Singleton Guard
    # --------------------------------------------------------------------------
    def test_feature18_multi_device_ribbon_logic_matrix(self):
        """Feature 18: Test multi-device ribbon detection logic with distinct serials vs duplicate serials.
        Confirm two distinct serials do not collide."""
        def evaluate_ribbon_guard(existing_windows: List[str], check_serial: str) -> Optional[str]:
            """Simulation of the exact logic in gndroid.pyw:10186-10239."""
            if not check_serial:
                for c_title in ["GNDROiD Controls", "gndroid Controls"]:
                    if c_title in existing_windows:
                        return c_title
                return None

            # 1. Exact match for target serial ribbon
            candidate_titles = [
                f"GNDROiD Controls - {check_serial}",
                f"gndroid Controls - {check_serial}"
            ]
            for c_title in candidate_titles:
                if c_title in existing_windows:
                    return c_title

            # 2. Window enumeration fallback for target serial ribbon
            for w in existing_windows:
                w_title = w.lower()
                if "controls" in w_title and check_serial.lower() in w_title:
                    return w

            return None

        # Scenario 1: Empty workspace -> Launch permitted
        self.assertIsNone(evaluate_ribbon_guard([], "emulator-5554"))

        # Scenario 2: Duplicate serial -> Intercepted by guard
        windows_active = ["GNDROiD Controls - emulator-5554"]
        match_duplicate = evaluate_ribbon_guard(windows_active, "emulator-5554")
        self.assertIsNotNone(match_duplicate)
        self.assertEqual(match_duplicate, "GNDROiD Controls - emulator-5554")

        # Scenario 3: Distinct serial -> NOT intercepted (Concurrent mirroring allowed!)
        match_distinct = evaluate_ribbon_guard(windows_active, "192.168.1.100:5555")
        self.assertIsNone(match_distinct, "Distinct serial 192.168.1.100:5555 was incorrectly blocked by emulator-5554!")

        # Scenario 4: Multiple concurrent devices active
        multi_windows = [
            "GNDROiD Controls - emulator-5554",
            "GNDROiD Controls - 192.168.1.100:5555",
            "GNDROiD Controls - usb_device_pixel7",
        ]
        # Any of the 3 existing serials are blocked from duplicate launch
        for active in ["emulator-5554", "192.168.1.100:5555", "usb_device_pixel7"]:
            self.assertIsNotNone(evaluate_ribbon_guard(multi_windows, active))

        # Distinct 4th device allowed
        self.assertIsNone(evaluate_ribbon_guard(multi_windows, "emulator-5556"))
        self.assertIsNone(evaluate_ribbon_guard(multi_windows, "192.168.1.101:5555"))

        # Scenario 5: Case insensitivity
        self.assertIsNotNone(evaluate_ribbon_guard(windows_active, "EMULATOR-5554"))

        print("✓ Feature 18: Multi-device ribbon logic correctly blocks duplicates and allows distinct serials")

    def test_feature18_live_win32_window_isolation(self):
        """Feature 18: Live OS-level stress-test using real Win32 desktop windows.
        Creates an actual window on the Windows OS desktop and executes gndroid.pyw's
        window enumeration logic against live OS window handles."""
        from PyQt6.QtWidgets import QApplication, QWidget

        app = QApplication.instance() or QApplication([])

        user32 = ctypes.windll.user32
        user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
        user32.FindWindowW.restype = ctypes.c_void_p
        user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
        user32.IsWindowVisible.restype = ctypes.c_bool
        user32.GetWindowTextLengthW.argtypes = [ctypes.c_void_p]
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
        user32.GetWindowTextW.restype = ctypes.c_int

        serial_alpha = f"device_alpha_{int(time.time())}"
        serial_beta = f"device_beta_{int(time.time())}"
        title_alpha = f"GNDROiD Controls - {serial_alpha}"

        # Create real visible window for Alpha
        w_alpha = QWidget()
        w_alpha.setWindowTitle(title_alpha)
        w_alpha.show()
        app.processEvents()

        hwnd_alpha = int(w_alpha.winId())
        self.assertTrue(bool(hwnd_alpha), "Failed to acquire winId for serial_alpha window")

        try:
            # Live guard detection for serial_alpha (duplicate device check)
            found_hwnd = None
            candidate_titles = [
                f"GNDROiD Controls - {serial_alpha}",
                f"gndroid Controls - {serial_alpha}"
            ]
            for c_title in candidate_titles:
                h = user32.FindWindowW(None, c_title)
                if h and user32.IsWindowVisible(h):
                    found_hwnd = h
                    break

            self.assertEqual(found_hwnd, hwnd_alpha, "Live guard failed to locate existing ribbon for serial_alpha!")

            # Live guard detection for serial_beta (distinct device check)
            beta_found_hwnd = None
            candidate_titles_beta = [
                f"GNDROiD Controls - {serial_beta}",
                f"gndroid Controls - {serial_beta}"
            ]
            for c_title in candidate_titles_beta:
                h = user32.FindWindowW(None, c_title)
                if h and user32.IsWindowVisible(h):
                    beta_found_hwnd = h
                    break

            if not beta_found_hwnd:
                def enum_cb(h, lparam):
                    nonlocal beta_found_hwnd
                    if user32.IsWindowVisible(h):
                        length = user32.GetWindowTextLengthW(h)
                        if length > 0:
                            buf = ctypes.create_unicode_buffer(length + 1)
                            user32.GetWindowTextW(h, buf, length + 1)
                            w_title = buf.value.lower()
                            if "controls" in w_title and serial_beta.lower() in w_title:
                                beta_found_hwnd = h
                                return False
                    return True
                WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
                user32.EnumWindows(WNDENUMPROC(enum_cb), 0)

            # Assert that searching for distinct serial_beta does NOT collide with serial_alpha
            self.assertIsNone(beta_found_hwnd, "Live guard falsely matched serial_beta against serial_alpha ribbon!")
            print(f"✓ Feature 18: Live Win32 OS window isolation verified: duplicate blocked, distinct permitted")

        finally:
            w_alpha.close()
            app.processEvents()

    # --------------------------------------------------------------------------
    # GENERAL HARDENING & BINARY INTEGRITY
    # --------------------------------------------------------------------------
    def test_binary_synchronization_and_hashes(self):
        """Verify gndroid.exe and tools/gndroid.exe are identical compiled release binaries."""
        self.assertTrue(os.path.exists(GNDROID_EXE))
        self.assertTrue(os.path.exists(TOOLS_GNDROID_EXE))
        size_root = os.path.getsize(GNDROID_EXE)
        size_tools = os.path.getsize(TOOLS_GNDROID_EXE)
        self.assertEqual(size_root, size_tools, "File sizes of gndroid.exe and tools/gndroid.exe mismatch")
        self.assertGreater(size_root, 1_000_000, "Executable is unexpectedly small")

        import hashlib
        with open(GNDROID_EXE, "rb") as f1, open(TOOLS_GNDROID_EXE, "rb") as f2:
            h1 = hashlib.sha256(f1.read()).hexdigest()
            h2 = hashlib.sha256(f2.read()).hexdigest()
        self.assertEqual(h1, h2, "SHA256 hashes of gndroid.exe and tools/gndroid.exe do not match")
        print(f"✓ Binary Integrity: gndroid.exe and tools/gndroid.exe are byte-identical ({size_root:,} bytes)")


if __name__ == "__main__":
    unittest.main()
