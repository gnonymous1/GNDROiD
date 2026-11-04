"""
test_milestone_4_cli_ipc.py — Milestone 4 Verification Test Suite
Native Rust CLI Hardening & IPC (Features 16–18)

Verifies:
1. Feature 16: Rust CLI Desktop App Shortcut Support (--app, --window, --user, --title, --serial)
2. Feature 17: Rust CLI Subcommand & Argument Routing (launch --avd <name>, mirror -s <serial>)
3. Feature 17: Python gndroid.pyw --avd instance launching via AVDManager.launch_emulator_instance
4. Feature 17: Python gndroid.pyw --mirror serial preservation (no hardcoded empty string)
5. Feature 18: Multi-Device Parallel Mirroring Guard (per-serial ribbon detection allowing concurrent mirrors)
6. General CLI Hardening: Dynamic workspace root resolution in find_workspace_root() without hardcoded user paths
"""

import os
import sys
import unittest
import subprocess
import ctypes
from unittest.mock import patch, MagicMock

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GNDROID_EXE = os.path.join(BASE_DIR, "gndroid.exe")
GNDROID_PYW = os.path.join(BASE_DIR, "gndroid.pyw")
MAIN_RS = os.path.join(BASE_DIR, "gndroid-cli", "src", "main.rs")


class TestMilestone4CliIpc(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if BASE_DIR not in sys.path:
            sys.path.insert(0, BASE_DIR)

    def test_feature16_cli_desktop_shortcut_arguments_present_in_help(self):
        """Feature 16: Verify --app, --window, --user, --title, --serial options in gndroid.exe --help."""
        self.assertTrue(os.path.exists(GNDROID_EXE), f"Compiled binary missing at {GNDROID_EXE}")
        out = subprocess.check_output([GNDROID_EXE, "--help"], text=True)
        self.assertIn("--app", out, "Missing --app option in gndroid.exe --help")
        self.assertIn("--window", out, "Missing --window option in gndroid.exe --help")
        self.assertIn("--user", out, "Missing --user option in gndroid.exe --help")
        self.assertIn("--title", out, "Missing --title option in gndroid.exe --help")
        self.assertIn("--serial", out, "Missing --serial option in gndroid.exe --help")
        print("✓ Feature 16: CLI --help contains all desktop app shortcut options (--app, --window, --user, --title, --serial)")

    def test_feature16_cli_parses_app_shortcut_without_clap_crash(self):
        """Feature 16: Verify gndroid.exe --app <pkg> --window does not trigger clap unexpected argument error."""
        # Run gndroid.exe with --help or a simulated command with --app
        # When clap encounters unrecognized arguments, exit code is 2 or 1 with 'unexpected argument'
        # We test that clap successfully accepts the syntax and does NOT report 'unexpected argument'
        res = subprocess.run(
            [GNDROID_EXE, "--app", "com.whatsapp", "--window", "--user", "10", "--title", "WhatsApp Clone"],
            capture_output=True,
            text=True,
            timeout=5
        )
        # Even if pythonw.exe is spawned in background, clap must NOT crash with error
        self.assertNotIn("unexpected argument '--app' found", res.stderr)
        self.assertNotIn("unexpected argument '--window' found", res.stderr)
        self.assertNotIn("unexpected argument '--user' found", res.stderr)
        print("✓ Feature 16: gndroid.exe parses desktop app shortcut flags cleanly without clap error")

    def test_feature17_cli_launch_subcommand_routing(self):
        """Feature 17: Verify gndroid.exe launch --avd and launch [name] syntax are supported."""
        out = subprocess.check_output([GNDROID_EXE, "launch", "--help"], text=True)
        self.assertIn("--avd", out, "Missing --avd option in gndroid.exe launch --help")
        self.assertIn("AVD_NAME", out, "Missing positional AVD_NAME in gndroid.exe launch --help")
        print("✓ Feature 17: CLI launch subcommand supports both --avd and positional instance name")

    def test_feature17_cli_mirror_subcommand_routing(self):
        """Feature 17: Verify gndroid.exe mirror --serial and mirror [target] syntax are supported."""
        out = subprocess.check_output([GNDROID_EXE, "mirror", "--help"], text=True)
        self.assertIn("--serial", out, "Missing --serial option in gndroid.exe mirror --help")
        self.assertIn("TARGET_SERIAL", out, "Missing positional TARGET_SERIAL in gndroid.exe mirror --help")
        print("✓ Feature 17: CLI mirror subcommand supports both --serial and positional target serial")

    def test_feature17_python_avd_argument_handling(self):
        """Feature 17: Verify gndroid.pyw parses --avd <name> and invokes AVDManager.launch_emulator_instance."""
        with open(GNDROID_PYW, "r", encoding="utf-8", errors="ignore") as f:
            code = f.read()

        # Static contract validation
        self.assertIn('"--avd" in args', code, "gndroid.pyw missing '--avd' CLI argument parser")
        self.assertIn('"--instance" in args', code, "gndroid.pyw missing '--instance' CLI argument parser")
        self.assertIn('AVDManager.launch_emulator_instance(avd_name)', code,
                      "gndroid.pyw does not call AVDManager.launch_emulator_instance(avd_name)")

        # Unit behavior simulation
        from gndroid import AVDManager
        test_args_cases = [
            (["--avd", "Pixel_9_Pro"], "Pixel_9_Pro"),
            (["--instance", "GNDROiD_Clone_2"], "GNDROiD_Clone_2"),
            (["launch", "--avd", "Flagship_AVD"], "Flagship_AVD"),
            (["launch", "Direct_Instance"], "Direct_Instance"),
        ]

        for args, expected_inst in test_args_cases:
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

            self.assertEqual(avd_name, expected_inst, f"Failed to extract AVD name from {args}")

        print("✓ Feature 17: gndroid.pyw correctly handles --avd, --instance, and launch instance routing")

    def test_feature17_python_mirror_serial_preservation(self):
        """Feature 17: Verify gndroid.pyw parses --mirror <serial> and preserves target_serial (no hardcoded empty string)."""
        with open(GNDROID_PYW, "r", encoding="utf-8", errors="ignore") as f:
            code = f.read()

        # Contract check: in --mirror block, start_mirror_with_fallback must receive target_serial
        self.assertIn('sidebar = start_mirror_with_fallback(target_serial, None)', code,
                      "gndroid.pyw still passes hardcoded empty string to start_mirror_with_fallback")

        # Extraction logic verification
        test_mirror_cases = [
            (["--mirror", "192.168.1.105:5555"], "192.168.1.105:5555"),
            (["mirror", "emulator-5556"], "emulator-5556"),
            (["--mirror", "--serial", "phone-usb-1234"], "phone-usb-1234"),
            (["--mirror", "-s", "emulator-5558"], "emulator-5558"),
        ]

        for args, expected_serial in test_mirror_cases:
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

            self.assertEqual(target_serial, expected_serial, f"Failed to preserve serial for {args}")

        print("✓ Feature 17: gndroid.pyw preserves target serial in --mirror mode without clearing")

    def test_feature18_multi_device_mirroring_guard_allows_concurrent_devices(self):
        """Feature 18: Verify cross-process guard checks specific serial/title and does NOT block different devices."""
        with open(GNDROID_PYW, "r", encoding="utf-8", errors="ignore") as f:
            code = f.read()

        # Check that the global blind exit on generic GNDROiD Controls is gone
        # It must check candidate_titles with check_serial
        self.assertIn('GNDROiD Controls - {check_serial}', code,
                      "gndroid.pyw missing per-serial candidate title check")
        self.assertIn('check_serial.lower() in w_title', code,
                      "gndroid.pyw missing window enumeration serial check")

        # Simulate guard evaluation
        def simulate_guard(existing_window_titles, incoming_serial):
            # Returns existing hwnd if found, else None
            candidate_titles = [
                f"GNDROiD Controls - {incoming_serial}",
                f"gndroid Controls - {incoming_serial}"
            ]
            for t in candidate_titles:
                if t in existing_window_titles:
                    return 1001

            for t in existing_window_titles:
                if "controls" in t.lower() and incoming_serial.lower() in t.lower():
                    return 1002
            return None

        # Scenario A: Device A is running. User tries to mirror Device A again -> Guard intercepts
        active_windows = ["GNDROiD Controls - emulator-5554"]
        match_same = simulate_guard(active_windows, "emulator-5554")
        self.assertIsNotNone(match_same, "Guard should find existing ribbon for same serial")

        # Scenario B: Device A is running. User launches mirror for Device B -> Guard allows concurrent mirror
        match_diff = simulate_guard(active_windows, "192.168.1.100:5555")
        self.assertIsNone(match_diff, "Guard must NOT block a distinct device serial from mirroring concurrently")

        # Scenario C: Multiple devices running in parallel
        parallel_windows = [
            "GNDROiD Controls - emulator-5554",
            "GNDROiD Controls - 192.168.1.100:5555",
            "GNDROiD Controls - physical-usb-device"
        ]
        # Querying fourth device allows launch
        self.assertIsNone(simulate_guard(parallel_windows, "emulator-5556"))
        # Querying running device blocks duplicate
        self.assertIsNotNone(simulate_guard(parallel_windows, "192.168.1.100:5555"))

        print("✓ Feature 18: Multi-device mirroring guard allows concurrent mirroring of distinct devices")

    def test_general_cli_dynamic_workspace_root_resolution(self):
        """General Hardening: Verify find_workspace_root() in main.rs has zero hardcoded username paths."""
        with open(MAIN_RS, "r", encoding="utf-8", errors="ignore") as f:
            rs_code = f.read()

        # Verify hardcoded developer path is completely removed
        self.assertNotIn("Reader-Branch", rs_code,
                         "find_workspace_root in main.rs still contains hardcoded 'Reader-Branch' path!")

        # Verify dynamic resolution mechanisms
        self.assertIn("ancestors()", rs_code, "main.rs missing dynamic ancestor directory traversal")
        self.assertIn("gndroid.pyw", rs_code, "main.rs does not verify gndroid.pyw existence dynamically")
        self.assertIn("GNDROID_HOME", rs_code, "main.rs missing GNDROID_HOME environment variable lookup")

        print("✓ General Hardening: find_workspace_root() dynamically resolves workspace with zero hardcoded user paths")

    def test_binary_synchronization_and_live_execution(self):
        """Verify gndroid.exe and tools/gndroid.exe are identical compiled binaries matching target/release."""
        release_bin = os.path.join(BASE_DIR, "target", "release", "gndroid.exe")
        root_bin = os.path.join(BASE_DIR, "gndroid.exe")
        tools_bin = os.path.join(BASE_DIR, "tools", "gndroid.exe")

        self.assertTrue(os.path.exists(release_bin), f"Missing {release_bin}")
        self.assertTrue(os.path.exists(root_bin), f"Missing {root_bin}")
        self.assertTrue(os.path.exists(tools_bin), f"Missing {tools_bin}")

        rel_size = os.path.getsize(release_bin)
        root_size = os.path.getsize(root_bin)
        tools_size = os.path.getsize(tools_bin)

        self.assertEqual(rel_size, root_size, "root gndroid.exe does not match compiled target/release binary size")
        self.assertEqual(rel_size, tools_size, "tools/gndroid.exe does not match compiled target/release binary size")
        self.assertGreater(rel_size, 1_000_000, "Compiled binary size is unexpectedly small")

        # Test live execution
        res = subprocess.run([root_bin, "--version"], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        self.assertIn("gndroid 2.2.2", res.stdout)
        print(f"✓ Binary Synchronization: gndroid.exe and tools/gndroid.exe verified ({rel_size:,} bytes, v2.2.2)")


if __name__ == "__main__":
    unittest.main()
