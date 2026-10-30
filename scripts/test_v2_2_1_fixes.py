import os
import sys
import unittest
import importlib.util

sys.stdout.reconfigure(encoding='utf-8')

def load_gndroid():
    spec = importlib.util.spec_from_file_location("gndroid", "gndroid.pyw")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

gndroid = load_gndroid()

class TestGNDROiDV221Fixes(unittest.TestCase):
    def test_adb_fixer_dialog_no_attribute_error(self):
        """Verify GNDroidADBFixerDialog initializes without AttributeError and action_kill_port_conflicts exists."""
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(sys.argv)
        dialog = gndroid.GNDroidADBFixerDialog("", None)
        self.assertTrue(hasattr(dialog, "action_kill_port_conflicts"))
        self.assertTrue(hasattr(dialog, "tabs"))
        self.assertGreaterEqual(dialog.tabs.count(), 2)
        self.assertIn("Wireless", dialog.tabs.tabText(1))
        dialog.close()
        print("✓ Verified GNDroidADBFixerDialog initializes smoothly with tab 1 Wireless Mode")

    def test_system_paths_get_phone_lan_ip(self):
        """Verify SystemPaths has get_phone_lan_ip method."""
        self.assertTrue(hasattr(gndroid.SystemPaths, "get_phone_lan_ip"))
        self.assertTrue(callable(gndroid.SystemPaths.get_phone_lan_ip))
        print("✓ Verified SystemPaths.get_phone_lan_ip exists and is callable")

    def test_emulator_launch_command_no_unsupported_flags(self):
        """Verify that emulator launch commands do not contain -no-boot-check."""
        with open("gndroid.pyw", "r", encoding="utf-8") as f:
            code = f.read()
        self.assertNotIn("-no-boot-check", code, "gndroid.pyw should not contain obsolete '-no-boot-check' flag")
        print("✓ Verified no obsolete '-no-boot-check' flag in gndroid.pyw")

    def test_table_column1_width_and_clean_labels(self):
        """Verify Multi-Instance Manager Column 1 is 305px and display name stripping logic."""
        with open("gndroid.pyw", "r", encoding="utf-8") as f:
            code = f.read()
        self.assertIn("self.table.setColumnWidth(1, 305)", code)
        self.assertIn("re.sub(r'\\s*\\(\\d+GB RAM\\s*/\\s*\\d+\\s*Cores\\)', '', inst['display_name']", code)
        print("✓ Verified Column 1 set to 305px and clean identity label formatting")

    def test_dropdown_modes_included(self):
        """Verify that mode_usb and mode_lan are defined in dev_combo population."""
        with open("gndroid.pyw", "r", encoding="utf-8") as f:
            code = f.read()
        self.assertIn('"type": "mode_usb"', code)
        self.assertIn('"type": "mode_lan"', code)
        print("✓ Verified physical USB mode and wireless LAN mode registered in dropdown")

if __name__ == "__main__":
    unittest.main()
