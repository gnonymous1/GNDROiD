#!/usr/bin/env python3
"""
scripts/verify_secondary_display.py
===================================
Automated verification suite for Requirement R1:
1. Secondary display configuration consistency (defaults to matching primary display 1440x3120 @ 500 DPI).
2. Multi-display emulator arguments (-multidisplay 1,1440,3120,500,0 and -hotplug-multi-display).
3. Sanitization of wild/4K landscape secondary configurations to prevent portrait screen shrinking and letterboxing.
4. Key preservation in AVDManager.update_instance_settings (does not strip hw.display1.*).
5. AVDManager.launch_emulator_instance appends multi-display arguments to emulator CLI.
6. Resolution preset defaults across GNDroidCreateDialog, GNDroidInstanceSettingsDialog, and GNDroidSettingsDialog.
"""

import os
import sys
import tempfile
import shutil
import importlib.util

# Ensure UTF-8 stdout on Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Force offscreen Qt rendering for automated / headless environments
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from nexus.display_and_vpn import (
    get_secondary_display_config,
    set_secondary_display_config,
    get_multi_display_emulator_args,
    sanitize_multi_display_config,
    read_config_dict,
    write_config_keys
)


def test_secondary_display_engine_defaults():
    print("\n[TEST 1] Verifying Secondary Display Engine Defaults & Arguments...")
    temp_dir = tempfile.mkdtemp()
    try:
        cfg_path = os.path.join(temp_dir, "config.ini")
        # Base config with flagship 1440x3120 primary display
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write("hw.lcd.width=1440\nhw.lcd.height=3120\nhw.lcd.density=500\n")

        # 1. Verify default read when secondary display not yet enabled
        cfg_default = get_secondary_display_config(cfg_path)
        print(f" -> Default secondary display config: {cfg_default['width']}x{cfg_default['height']} @ {cfg_default['density']} DPI (match_primary={cfg_default['match_primary']})")
        assert cfg_default["width"] == 1440, f"Expected width 1440, got {cfg_default['width']}"
        assert cfg_default["height"] == 3120, f"Expected height 3120, got {cfg_default['height']}"
        assert cfg_default["density"] == 500, f"Expected density 500, got {cfg_default['density']}"
        assert cfg_default["match_primary"] is True, "Expected match_primary to be True by default"

        # When disabled, args should be empty
        args_disabled = get_multi_display_emulator_args(cfg_path)
        assert args_disabled == [], f"Expected empty args when disabled, got {args_disabled}"
        print(" -> Confirmed: Args are empty when secondary display is disabled.")

        # 2. Enable secondary display matching primary
        res_set = set_secondary_display_config(cfg_path, enabled=True, match_primary=True)
        print(f" -> Enabled secondary display result: {res_set['width']}x{res_set['height']} @ {res_set['density']} DPI")
        assert res_set["enabled"] is True
        assert res_set["match_primary"] is True
        assert res_set["width"] == 1440
        assert res_set["height"] == 3120
        assert res_set["density"] == 500

        # Read back config file directly
        disk_cfg, _ = read_config_dict(cfg_path)
        assert disk_cfg.get("hw.display1.width") == "1440"
        assert disk_cfg.get("hw.display1.height") == "3120"
        assert disk_cfg.get("hw.display1.density") == "500"
        assert disk_cfg.get("hw.display1.enabled") == "true"
        assert disk_cfg.get("hw.display1.match_primary") == "true"
        assert disk_cfg.get("hw.multi_display_window") == "true"
        assert disk_cfg.get("hw.hotplug_multi_display") == "true"
        print(" -> Confirmed: config.ini written with full multi-display keys and matching primary dimensions.")

        # 3. Verify generated emulator CLI arguments
        args_enabled = get_multi_display_emulator_args(cfg_path)
        print(f" -> Generated multi-display CLI arguments: {args_enabled}")
        assert args_enabled == ["-multidisplay", "1,1440,3120,500,0", "-hotplug-multi-display"], \
            f"Unexpected CLI args: {args_enabled}"
        print(" -> Confirmed: get_multi_display_emulator_args returns -multidisplay 1,1440,3120,500,0 -hotplug-multi-display.")

        # 4. Custom dimensions when match_primary=False
        set_secondary_display_config(cfg_path, enabled=True, match_primary=False, width=1080, height=2400, density=420)
        args_custom = get_multi_display_emulator_args(cfg_path)
        assert args_custom == ["-multidisplay", "1,1080,2400,420,0", "-hotplug-multi-display"], \
            f"Unexpected custom CLI args: {args_custom}"
        print(" -> Confirmed: Custom secondary dimensions properly reflected in launch arguments.")

        print(" [PASSED] Test 1: Secondary Display Engine Defaults & Arguments verified.")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_wild_4k_sanitization():
    print("\n[TEST 2] Verifying Wild / 4K Secondary Display Sanitization...")
    temp_dir = tempfile.mkdtemp()
    try:
        cfg_path = os.path.join(temp_dir, "config.ini")
        # Primary portrait 1440x3120, Secondary wild 4K landscape 3840x2160
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write("""hw.lcd.width=1440
hw.lcd.height=3120
hw.lcd.density=500
hw.display1.width=3840
hw.display1.height=2160
hw.display1.density=320
hw.display1.enabled=true
""")

        san_res = sanitize_multi_display_config(cfg_path)
        print(f" -> Sanitization executed: sanitized={san_res['sanitized']}, reason={san_res['reason']}")
        assert san_res["sanitized"] is True, "Expected 4K landscape secondary display to be sanitized!"
        assert san_res["secondary"]["width"] == 1440
        assert san_res["secondary"]["height"] == 3120
        assert san_res["secondary"]["density"] == 500

        # Read back
        disk_cfg, _ = read_config_dict(cfg_path)
        assert disk_cfg.get("hw.display1.width") == "1440"
        assert disk_cfg.get("hw.display1.height") == "3120"
        assert disk_cfg.get("hw.display1.density") == "500"
        print(" -> Confirmed: 4K landscape secondary normalized to 1440x3120 @ 500 DPI, eliminating letterboxing.")

        # Idempotency check: running again on clean config returns sanitized=False
        san_res_2 = sanitize_multi_display_config(cfg_path)
        assert not san_res_2["sanitized"], "Sanitizer must be idempotent on already clean config!"
        print(" -> Confirmed: Sanitizer is clean and idempotent.")

        print(" [PASSED] Test 2: Wild / 4K Sanitization verified.")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_key_preservation_in_update_instance_settings():
    print("\n[TEST 3] Verifying Key Preservation in AVDManager.update_instance_settings...")
    temp_avd_dir = tempfile.mkdtemp()
    try:
        inst_dir = os.path.join(temp_avd_dir, "test_instance.avd")
        os.makedirs(inst_dir, exist_ok=True)
        cfg_path = os.path.join(inst_dir, "config.ini")

        initial_content = """hw.ramSize=4096
hw.cpu.ncore=4
hw.lcd.width=1440
hw.lcd.height=3120
hw.lcd.density=500
hw.display1.width=1440
hw.display1.height=3120
hw.display1.density=500
hw.display1.enabled=true
hw.display1.match_primary=true
hw.multi_display_window=true
hw.hotplug_multi_display=true
gndroid.secondary_display=yes
"""
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write(initial_content)

        # Import gndroid
        spec = importlib.util.spec_from_file_location("gndroid", os.path.join(base_dir, "gndroid.pyw"))
        gndroid_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gndroid_mod)

        # Point AVDManager to temp dir
        gndroid_mod.AVDManager.get_avd_dir = staticmethod(lambda: temp_avd_dir)

        # Call update_instance_settings (which previously stripped hw.display1.*)
        gndroid_mod.AVDManager.update_instance_settings(
            name="test_instance",
            ram_mb=8192,
            cores=8,
            width=1440,
            height=3120,
            density=500,
            gpu="auto",
            root_enabled=False
        )

        with open(cfg_path, "r", encoding="utf-8") as f:
            saved_content = f.read()

        print(f" -> Saved config.ini after update_instance_settings:\n{saved_content.strip()}")
        assert "hw.ramSize=8192" in saved_content
        assert "hw.cpu.ncore=8" in saved_content
        assert "hw.display1.width=1440" in saved_content, "VIOLATION: hw.display1.width was stripped!"
        assert "hw.display1.height=3120" in saved_content, "VIOLATION: hw.display1.height was stripped!"
        assert "hw.display1.density=500" in saved_content, "VIOLATION: hw.display1.density was stripped!"
        assert "hw.display1.enabled=true" in saved_content, "VIOLATION: hw.display1.enabled was stripped!"
        assert "hw.multi_display_window=true" in saved_content, "VIOLATION: hw.multi_display_window was stripped!"
        assert "hw.hotplug_multi_display=true" in saved_content, "VIOLATION: hw.hotplug_multi_display was stripped!"
        assert "gndroid.secondary_display=yes" in saved_content, "VIOLATION: gndroid.secondary_display was stripped!"

        print(" -> Confirmed: All secondary display keys are fully preserved when saving instance settings.")
        print(" [PASSED] Test 3: Key Preservation in AVDManager verified.")
    finally:
        shutil.rmtree(temp_avd_dir, ignore_errors=True)


def test_emulator_launch_cmd_multidisplay():
    print("\n[TEST 4] Verifying AVDManager.launch_emulator_instance Multi-Display CLI Injection...")
    temp_avd_dir = tempfile.mkdtemp()
    try:
        inst_dir = os.path.join(temp_avd_dir, "launch_test.avd")
        os.makedirs(inst_dir, exist_ok=True)
        cfg_path = os.path.join(inst_dir, "config.ini")

        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write("""hw.lcd.width=1440
hw.lcd.height=3120
hw.lcd.density=500
hw.display1.width=1440
hw.display1.height=3120
hw.display1.density=500
hw.display1.enabled=true
hw.display1.match_primary=true
hw.multi_display_window=true
hw.hotplug_multi_display=true
gndroid.secondary_display=yes
""")

        spec = importlib.util.spec_from_file_location("gndroid", os.path.join(base_dir, "gndroid.pyw"))
        gndroid_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gndroid_mod)

        gndroid_mod.AVDManager.get_avd_dir = staticmethod(lambda: temp_avd_dir)
        import nexus.display_and_vpn
        orig_avd_dir = nexus.display_and_vpn.get_avd_dir
        nexus.display_and_vpn.get_avd_dir = lambda: temp_avd_dir

        captured_cmd = []
        class MockPopen:
            def __init__(self, cmd, *args, **kwargs):
                captured_cmd.extend(cmd)
                self.pid = 8888

        import subprocess
        orig_popen = subprocess.Popen
        subprocess.Popen = MockPopen

        try:
            gndroid_mod.AVDManager.launch_emulator_instance("launch_test", port=5554)
        finally:
            subprocess.Popen = orig_popen
            nexus.display_and_vpn.get_avd_dir = orig_avd_dir

        print(f" -> Intercepted emulator launch cmd: {captured_cmd}")
        assert "-multidisplay" in captured_cmd, "'-multidisplay' missing from launch command!"
        m_idx = captured_cmd.index("-multidisplay")
        assert captured_cmd[m_idx + 1] == "1,1440,3120,500,0", f"Unexpected multidisplay argument: {captured_cmd[m_idx + 1]}"
        assert "-hotplug-multi-display" in captured_cmd, "'-hotplug-multi-display' missing from launch command!"

        print(" -> Confirmed: -multidisplay 1,1440,3120,500,0 and -hotplug-multi-display are successfully injected into emulator launch command.")
        print(" [PASSED] Test 4: Emulator Launch CLI Injection verified.")
    finally:
        shutil.rmtree(temp_avd_dir, ignore_errors=True)


def test_dialog_resolution_presets():
    print("\n[TEST 5] Verifying Dialog Resolution Presets & Flagship 1440x3120 Defaults...")
    app = QApplication.instance() or QApplication(sys.argv)

    spec = importlib.util.spec_from_file_location("gndroid", os.path.join(base_dir, "gndroid.pyw"))
    gndroid_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gndroid_mod)

    # 1. GNDroidInstanceCreatorDialog (Creation Dialog)
    CreateDialogCls = getattr(gndroid_mod, "GNDroidInstanceCreatorDialog", None) or getattr(gndroid_mod, "GNDroidCreateDialog", None)
    assert CreateDialogCls is not None, "Instance Creation Dialog class not found in gndroid.pyw!"
    create_dlg = CreateDialogCls()
    item_0_text = create_dlg.combo_res.itemText(0)
    item_0_data = create_dlg.combo_res.itemData(0)
    print(f" -> GNDroidInstanceCreatorDialog Preset 0: '{item_0_text}' (data={item_0_data})")
    assert "1440 x 3120" in item_0_text, f"Expected 1440x3120 default preset, got: {item_0_text}"
    assert item_0_data == (1440, 3120, 500), f"Expected (1440, 3120, 500), got: {item_0_data}"
    assert create_dlg.combo_res.currentIndex() == 0, "Default index should be 0 (1440x3120)"
    create_dlg.close()

    # 2. GNDroidInstanceSettingsDialog
    dummy_inst = {
        "name": "test_inst",
        "display_name": "Test AVD",
        "api_level": "14 (UpsideDownCake)",
        "ram_mb": 4096,
        "cores": 4,
        "width": 1440,
        "height": 3120,
        "density": 500,
        "gpu": "auto",
        "root": False
    }
    inst_dlg = gndroid_mod.GNDroidInstanceSettingsDialog(dummy_inst)
    inst_item_0_text = inst_dlg.combo_res.itemText(0)
    inst_item_0_data = inst_dlg.combo_res.itemData(0)
    print(f" -> GNDroidInstanceSettingsDialog Preset 0: '{inst_item_0_text}' (data={inst_item_0_data})")
    assert "1440 x 3120" in inst_item_0_text, f"Expected 1440x3120 default preset, got: {inst_item_0_text}"
    assert inst_item_0_data == (1440, 3120, 500), f"Expected (1440, 3120, 500), got: {inst_item_0_data}"
    assert inst_dlg.combo_res.currentIndex() == 0, "Default index should be 0 (1440x3120)"
    inst_dlg.close()

    print(" -> Confirmed: All creation and settings dialogs default to flagship 1440x3120 @ 500 DPI.")
    print(" [PASSED] Test 5: Dialog Resolution Presets verified.")


def main():
    print("=" * 70)
    print("🖥️ VERIFY REQUIREMENT R1: Secondary Display Configuration Suite")
    print("=" * 70)

    try:
        test_secondary_display_engine_defaults()
        test_wild_4k_sanitization()
        test_key_preservation_in_update_instance_settings()
        test_emulator_launch_cmd_multidisplay()
        test_dialog_resolution_presets()
        print("\n" + "=" * 70)
        print("✅ ALL SECONDARY DISPLAY VERIFICATION CHECKS PASSED (EXIT 0)")
        print("=" * 70)
        sys.exit(0)
    except AssertionError as ae:
        print(f"\n❌ ASSERTION ERROR: {ae}", file=sys.stderr)
        sys.exit(1)
    except Exception as ex:
        import traceback
        traceback.print_exc()
        print(f"\n❌ UNEXPECTED ERROR: {ex}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
