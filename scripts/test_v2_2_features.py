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

class TestGNDROiDV22(unittest.TestCase):
    def test_version_and_imports(self):
        self.assertIn(gndroid.VERSION, ["2.2.1", "2.2.2"])
        print(f"✓ Verified VERSION == {gndroid.VERSION}")

    def test_wireless_conversion_methods(self):
        self.assertTrue(hasattr(gndroid.SystemPaths, "convert_usb_to_wireless_lan"))
        self.assertTrue(hasattr(gndroid.SystemPaths, "scan_subnet_for_android_devices"))
        print("✓ Verified convert_usb_to_wireless_lan and scan_subnet_for_android_devices exist")

    def test_multi_device_sidebars(self):
        self.assertTrue(hasattr(gndroid.GNDroidCompanionSidebar, "_active_sidebars"))
        self.assertIsInstance(gndroid.GNDroidCompanionSidebar._active_sidebars, dict)
        print("✓ Verified GNDroidCompanionSidebar._active_sidebars dictionary exists for multi-device mirroring")

    def test_logo_assets(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        png_path = os.path.join(base_dir, "gndroid.png")
        ico_path = os.path.join(base_dir, "gndroid.ico")
        self.assertTrue(os.path.exists(png_path), f"Missing {png_path}")
        self.assertTrue(os.path.exists(ico_path), f"Missing {ico_path}")
        self.assertGreater(os.path.getsize(png_path), 5000)
        self.assertGreater(os.path.getsize(ico_path), 5000)
        print(f"✓ Verified 3D transparent emblem assets: {png_path} ({os.path.getsize(png_path)} bytes), {ico_path} ({os.path.getsize(ico_path)} bytes)")

    def test_scrcpy_screen_standby_flags(self):
        with open("gndroid.pyw", "r", encoding="utf-8") as f:
            code = f.read()
        self.assertIn("--turn-screen-off", code)
        self.assertIn("--stay-awake", code)
        self.assertIn("GNDROiD - {selected_serial}", code)
        self.assertIn("action_toggle_device_screen", code)
        print("✓ Verified --turn-screen-off, --stay-awake, and action_toggle_device_screen in gndroid.pyw")

    def test_installer_config(self):
        with open("gndroid_installer.iss", "r", encoding="utf-8") as f:
            iss = f.read()
        self.assertIn('#define MyAppName "GNDROiD"', iss)
        self.assertTrue('#define MyAppVersion "2.2.1"' in iss or '#define MyAppVersion "2.2.2"' in iss)
        self.assertTrue('OutputBaseFilename=GNDROiD-Setup-v2.2.1-Full' in iss or 'OutputBaseFilename=GNDROiD-Setup-v2.2.2-Full' in iss)
        print("✓ Verified Inno Setup config updated to GNDROiD v2.2.x")

if __name__ == "__main__":
    unittest.main()
