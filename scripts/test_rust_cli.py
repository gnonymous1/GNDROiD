import os
import sys
import glob
import unittest
import subprocess

sys.stdout.reconfigure(encoding='utf-8')

class TestGNDROiDRustCLI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.exe_path = os.path.join(cls.base_dir, "gndroid.exe")

    def test_gndroid_exe_exists_and_sized(self):
        """Verify gndroid.exe exists and is a compiled native binary."""
        self.assertTrue(os.path.exists(self.exe_path), f"Missing {self.exe_path}")
        size = os.path.getsize(self.exe_path)
        self.assertGreater(size, 500_000, f"gndroid.exe size {size} is too small")
        print(f"✓ Verified native gndroid.exe exists ({size:,} bytes)")

    def test_version_subcommand(self):
        """Verify gndroid.exe --version outputs correct version string."""
        out = subprocess.check_output([self.exe_path, "--version"], text=True)
        self.assertIn("gndroid 2.2.2", out)
        print("✓ Verified gndroid.exe --version outputs 'gndroid 2.2.2'")

    def test_help_subcommands(self):
        """Verify gndroid.exe --help lists all expected subcommands."""
        out = subprocess.check_output([self.exe_path, "--help"], text=True)
        expected_commands = ["gui", "launch", "mirror", "multi", "fix", "lan", "download", "devices", "clean", "shortcuts"]
        for cmd in expected_commands:
            self.assertIn(cmd, out, f"Missing subcommand '{cmd}' in help output")
        print(f"✓ Verified all subcommands present in CLI: {', '.join(expected_commands)}")

    def test_devices_subcommand(self):
        """Verify gndroid.exe devices executes and prints radar banner."""
        res = subprocess.run([self.exe_path, "devices"], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        self.assertIn("Connected Android Devices", res.stdout)
        print("✓ Verified gndroid.exe devices runs cleanly")

    def test_clean_subcommand(self):
        """Verify gndroid.exe clean executes and restarts ADB."""
        res = subprocess.run([self.exe_path, "clean"], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        self.assertIn("ADB server", res.stdout)
        print("✓ Verified gndroid.exe clean restarts ADB and clears conflicts")

    def test_no_legacy_bat_files_exist(self):
        """Verify zero .bat files remain in the repository."""
        bats = []
        for root, dirs, files in os.walk(self.base_dir):
            dirs[:] = [d for d in dirs if d not in ("target", ".git", ".venv", "node_modules")]
            for f in files:
                if f.lower().endswith(".bat"):
                    bats.append(os.path.join(root, f))
        self.assertEqual(len(bats), 0, f"Found unexpected .bat files: {bats}")
        print("✓ Verified 0 legacy .bat files exist in the repository")

    def test_desktop_shortcuts_installed(self):
        """Verify all 5 official shortcuts exist on user's Desktop."""
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        expected_lnks = [
            "GNDROiD.lnk",
            "GNDROiD Multi-Instance.lnk",
            "GNDROiD Mirror.lnk",
            "GNDROiD Wireless LAN.lnk",
            "GNDROiD ADB Doctor.lnk",
        ]
        for lnk in expected_lnks:
            p = os.path.join(desktop, lnk)
            self.assertTrue(os.path.exists(p), f"Missing desktop shortcut: {p}")
        print("✓ Verified all 5 desktop shortcuts (GNDROiD, Multi, Mirror, LAN, Doctor) exist on Desktop")

if __name__ == "__main__":
    unittest.main()
