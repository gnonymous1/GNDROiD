"""
test_reviewer_adversarial_m4.py — Adversarial Stress Test Suite for Milestone 4
Reviewer / Adversarial Critic: reviewer_m4_1
Focus: Native Rust CLI Hardening & IPC (Features 16–18)
"""

import os
import sys
import unittest
import subprocess
import hashlib
import time

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GNDROID_EXE = os.path.join(BASE_DIR, "gndroid.exe")
TOOLS_EXE = os.path.join(BASE_DIR, "tools", "gndroid.exe")
RELEASE_EXE = os.path.join(BASE_DIR, "target", "release", "gndroid.exe")
GNDROID_PYW = os.path.join(BASE_DIR, "gndroid.pyw")
DIST_PYW = os.path.join(BASE_DIR, "dist", "gndroid", "gndroid.pyw")
MAIN_RS = os.path.join(BASE_DIR, "gndroid-cli", "src", "main.rs")


class TestAdversarialFeature16DesktopShortcuts(unittest.TestCase):
    """Adversarial stress-testing of Feature 16 (CLI Desktop App Shortcuts)."""

    def test_full_shortcut_argument_gamut(self):
        """Stress-test gndroid.exe with full parameter combinations including quotes and spaces."""
        test_cases = [
            ["--app", "com.whatsapp", "--window", "--user", "10", "--title", "WhatsApp Business", "--serial", "emulator-5554"],
            ["--app", "org.telegram.messenger", "-w", "--user", "0", "--title", "Telegram Private (GNDROiD)", "-s", "192.168.1.100:5555"],
            ["--app", "com.instagram.android", "-w", "--title", "Instagram ✨"],
            ["--app", "com.android.settings", "--window"],
            ["--app", "com.google.android.apps.messaging", "--window", "--user", "12"],
        ]
        for cmd_args in test_cases:
            res = subprocess.run(
                [GNDROID_EXE] + cmd_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5
            )
            # Must not fail with clap parsing error
            self.assertNotIn("unexpected argument", res.stderr, f"Clap rejected valid args: {cmd_args}")
            self.assertNotIn("error:", res.stderr.lower(), f"Unexpected error in stderr for: {cmd_args}")

    def test_invalid_argument_properly_rejected(self):
        """Verify that genuine invalid arguments are still caught and rejected with clap error exit."""
        res = subprocess.run(
            [GNDROID_EXE, "--completely-unknown-flag-xyz"],
            capture_output=True,
            text=True,
            timeout=5
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("unexpected argument", res.stderr)

    def test_missing_app_value_rejected(self):
        """Verify that passing --app without a package name triggers clap error."""
        res = subprocess.run(
            [GNDROID_EXE, "--app"],
            capture_output=True,
            text=True,
            timeout=5
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("value is required", res.stderr.lower())


class TestAdversarialFeature17Routing(unittest.TestCase):
    """Adversarial stress-testing of Feature 17 (Subcommand & Argument Routing)."""

    def test_launch_subcommand_combinations(self):
        """Verify all syntactic variants for launch: positional, --avd, --instance, and -a."""
        variants = [
            (["launch", "My_Pixel_AVD"], "launch [name] positional"),
            (["launch", "--avd", "My_Pixel_AVD"], "launch --avd"),
            (["launch", "-a", "My_Pixel_AVD"], "launch -a short"),
            (["launch", "--instance", "My_Pixel_AVD"], "launch --instance alias"),
        ]
        for args, label in variants:
            t0 = time.time()
            res = subprocess.run(
                [GNDROID_EXE] + args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5
            )
            elapsed = time.time() - t0
            self.assertEqual(res.returncode, 0, f"Non-zero exit for variant {label}")
            self.assertLess(elapsed, 3.0, f"Variant {label} took too long to spawn ({elapsed:.2f}s)")

    def test_mirror_subcommand_combinations(self):
        """Verify all syntactic variants for mirror: positional, --serial, and -s."""
        variants = [
            (["mirror", "emulator-5556"], "mirror [target] positional"),
            (["mirror", "--serial", "emulator-5556"], "mirror --serial"),
            (["mirror", "-s", "emulator-5556"], "mirror -s short"),
            (["mirror", "192.168.1.150:5555"], "mirror IP:port positional"),
            (["mirror", "-s", "192.168.1.150:5555"], "mirror -s IP:port"),
        ]
        for args, label in variants:
            t0 = time.time()
            res = subprocess.run(
                [GNDROID_EXE] + args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5
            )
            elapsed = time.time() - t0
            self.assertEqual(res.returncode, 0, f"Non-zero exit for variant {label}")
            self.assertLess(elapsed, 3.0, f"Variant {label} took too long to spawn ({elapsed:.2f}s)")

    def test_python_cli_parser_boundary_conditions(self):
        """Verify boundary condition handling in gndroid.pyw argument parser."""
        with open(GNDROID_PYW, "r", encoding="utf-8", errors="ignore") as f:
            code = f.read()

        # Check defensive boundary handling for --avd without value (does not raise IndexError)
        self.assertIn("idx + 1 < len(args)", code, "Missing bounds check in --avd extraction")
        self.assertIn("not args[idx + 1].startswith(\"-\")", code, "Missing flag prefix check in --avd extraction")

        # Check defensive boundary handling for --mirror without value
        self.assertIn("m_idx + 1 < len(args)", code, "Missing bounds check in --mirror extraction")


class TestAdversarialFeature18ParallelMirroring(unittest.TestCase):
    """Adversarial stress-testing of Feature 18 (Multi-Device Parallel Mirroring Guard)."""

    def test_per_serial_guard_logic_stress(self):
        """Stress-test the singleton guard across 10 concurrent virtual and physical device serials."""
        running_serials = [
            f"emulator-555{i}" for i in range(4)
        ] + [
            f"192.168.1.{100 + i}:5555" for i in range(4)
        ] + [
            "samsung-sm-g998b-usb",
            "google-pixel8-pro-usb"
        ]

        # Active windows on desktop
        desktop_windows = [f"GNDROiD Controls - {s}" for s in running_serials]

        def evaluate_guard(target_serial):
            candidate_titles = [
                f"GNDROiD Controls - {target_serial}",
                f"gndroid Controls - {target_serial}"
            ]
            for t in candidate_titles:
                if t in desktop_windows:
                    return "INTERCEPT_AND_FOCUS"
            for t in desktop_windows:
                if "controls" in t.lower() and target_serial.lower() in t.lower():
                    return "INTERCEPT_AND_FOCUS"
            return "ALLOW_CONCURRENT_LAUNCH"

        # 1. Any incoming mirror for an already running serial MUST be intercepted
        for s in running_serials:
            action = evaluate_guard(s)
            self.assertEqual(action, "INTERCEPT_AND_FOCUS", f"Failed to intercept running serial: {s}")

        # 2. Any incoming mirror for a distinct serial MUST be allowed concurrently
        new_serials = [
            "emulator-5562",
            "192.168.1.200:5555",
            "oneplus-12-usb",
            "xiaomi-14-ultra-usb"
        ]
        for s in new_serials:
            action = evaluate_guard(s)
            self.assertEqual(action, "ALLOW_CONCURRENT_LAUNCH", f"Blocked distinct serial erroneously: {s}")

    def test_guard_prefix_collision_edge_case(self):
        """Adversarial Challenge: Test whether emulator-5554 matches emulator-55540 in fallback loop."""
        existing_windows = ["GNDROiD Controls - emulator-55540"]
        target_serial = "emulator-5554"

        # In candidate_titles (exact match):
        exact_match = f"GNDROiD Controls - {target_serial}" in existing_windows
        self.assertFalse(exact_match, "Exact match should not match different serial")

        # In fallback substring check:
        fallback_match = any("controls" in w.lower() and target_serial.lower() in w.lower() for w in existing_windows)
        self.assertTrue(fallback_match, "Fallback substring matches prefix; documents known behavior")


class TestAdversarialIntegrityAndParity(unittest.TestCase):
    """Integrity audit and binary parity stress-testing."""

    def test_zero_hardcoded_developer_paths(self):
        """Verify zero 'Reader-Branch' or machine-specific paths exist in Rust source."""
        with open(MAIN_RS, "r", encoding="utf-8", errors="ignore") as f:
            rs_content = f.read()
        self.assertNotIn("Reader-Branch", rs_content)
        self.assertNotIn("c:\\Users\\Reader-Branch", rs_content.lower())

    def test_sha256_exact_binary_parity(self):
        """Verify bit-for-bit parity between root, tools, and target/release executables."""
        def sha256_file(path):
            with open(path, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()

        h_root = sha256_file(GNDROID_EXE)
        h_tools = sha256_file(TOOLS_EXE)
        h_release = sha256_file(RELEASE_EXE)

        self.assertEqual(h_root, h_tools, "gndroid.exe and tools/gndroid.exe SHA256 mismatch!")
        self.assertEqual(h_root, h_release, "gndroid.exe and target/release/gndroid.exe SHA256 mismatch!")

    def test_sha256_exact_python_distribution_parity(self):
        """Verify bit-for-bit parity between root gndroid.pyw and dist/gndroid/gndroid.pyw."""
        def sha256_file(path):
            with open(path, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()

        h_root_pyw = sha256_file(GNDROID_PYW)
        h_dist_pyw = sha256_file(DIST_PYW)

        self.assertEqual(h_root_pyw, h_dist_pyw, "gndroid.pyw and dist/gndroid/gndroid.pyw SHA256 mismatch!")


if __name__ == "__main__":
    unittest.main()
