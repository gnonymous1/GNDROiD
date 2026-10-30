#!/usr/bin/env python3
"""
scripts/test_challenger_m1_2_adversarial.py
===========================================
Empirical Challenger Adversarial Test Suite for Milestone M1 (UI & Display Subsystem):
Requirement R1: Secondary Display Consistency, Presets, Sanitization, Persistence & CLI Generation.

Test Matrix:
1. Preset resolution & aspect ratio matching (1440x3120 @ 500 DPI).
2. Adversarial edge cases:
   - Odd resolutions (1337x2777)
   - Extreme 4K landscape (3840x2160)
   - Extreme 8K landscape (7680x4320)
   - Ultra-wide (2560x1080)
   - Micro-screens (120x120)
   - Zero dimensions (0x0 with enabled=true)
   - Negative dimensions (-1440x-3120 with enabled=true)
   - Corrupt/non-numeric dimensions
3. Sanitization verification:
   - Normalization of invalid/wild resolutions to prevent emulator crashing or primary letterboxing.
4. Multi-instance persistence:
   - Concurrent/multi-instance config preservation across simulated AVDManager.update_instance_settings.
5. QEMU CLI generation:
   - Format compliance: -multidisplay 1,<w>,<h>,<dpi>,0 and -hotplug-multi-display.
   - Behavior when disabled or invalid.
"""

import os
import sys
import tempfile
import shutil
import importlib.util
from typing import Dict, Any, List

# Ensure UTF-8 stdout
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

os.environ["QT_QPA_PLATFORM"] = "offscreen"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from nexus.display_and_vpn import (
    get_secondary_display_config,
    set_secondary_display_config,
    get_multi_display_emulator_args,
    sanitize_multi_display_config,
    read_config_dict,
    write_config_keys,
    MultiDisplayArgs
)


class AdversarialTestRunner:
    def __init__(self):
        self.results: List[Dict[str, Any]] = []
        self.temp_dir = tempfile.mkdtemp(prefix="adv_test_m1_")

    def cleanup(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def log(self, category: str, name: str, passed: bool, details: str):
        self.results.append({
            "category": category,
            "name": name,
            "passed": passed,
            "details": details
        })
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {category} :: {name}")
        print(f"       Details: {details}")

    def test_section_1_default_presets_and_aspect_ratio(self):
        print("\n=== SECTION 1: Default Presets & Aspect Ratio Matching ===")
        cfg_path = os.path.join(self.temp_dir, "default_preset.ini")
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write("hw.lcd.width=1440\nhw.lcd.height=3120\nhw.lcd.density=500\n")

        # Check default resolution query
        sec_cfg = get_secondary_display_config(cfg_path)
        p_w = sec_cfg.get("primary_width")
        p_h = sec_cfg.get("primary_height")
        p_d = sec_cfg.get("primary_density")
        s_w = sec_cfg.get("width")
        s_h = sec_cfg.get("height")
        s_d = sec_cfg.get("density")
        match = sec_cfg.get("match_primary")

        aspect_primary = p_h / p_w if p_w else 0
        aspect_secondary = s_h / s_w if s_w else 0

        cond1 = (s_w == 1440 and s_h == 3120 and s_d == 500)
        cond2 = abs(aspect_primary - aspect_secondary) < 0.001
        cond3 = (match is True)

        self.log(
            "Presets",
            "Default Secondary Display Matches Primary Flagship (1440x3120@500DPI)",
            cond1 and cond2 and cond3,
            f"Primary={p_w}x{p_h}@{p_d}, Secondary={s_w}x{s_h}@{s_d}, MatchPrimary={match}, AspectRatioDiff={abs(aspect_primary - aspect_secondary):.4f}"
        )

        # Check UI Dialog Presets in gndroid.pyw
        try:
            spec = importlib.util.spec_from_file_location("gndroid", os.path.join(BASE_DIR, "gndroid.pyw"))
            gndroid_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(gndroid_mod)
            from PyQt6.QtWidgets import QApplication
            app = QApplication.instance() or QApplication([])

            dlg_creator = gndroid_mod.GNDroidInstanceCreatorDialog()
            creator_preset_0 = dlg_creator.combo_res.itemData(0)
            creator_text_0 = dlg_creator.combo_res.itemText(0)

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
            dlg_settings = gndroid_mod.GNDroidInstanceSettingsDialog(dummy_inst)
            settings_preset_0 = dlg_settings.combo_res.itemData(0)
            settings_text_0 = dlg_settings.combo_res.itemText(0)

            creator_ok = (creator_preset_0 == (1440, 3120, 500)) and ("1440 x 3120" in creator_text_0)
            settings_ok = (settings_preset_0 == (1440, 3120, 500)) and ("1440 x 3120" in settings_text_0)

            self.log(
                "Presets",
                "Creator & Settings Dialog Preset 0 is Flagship 1440x3120@500DPI",
                creator_ok and settings_ok,
                f"CreatorPreset0='{creator_text_0}', SettingsPreset0='{settings_text_0}'"
            )
        except Exception as e:
            self.log("Presets", "Creator & Settings Dialog Presets Check", False, f"Exception: {e}")

    def test_section_2_adversarial_edge_cases_and_sanitization(self):
        print("\n=== SECTION 2: Adversarial Edge Cases & Sanitization ===")
        test_matrix = [
            {
                "id": "odd_resolution",
                "desc": "Odd portrait resolution (1337x2777 @ 450 DPI)",
                "kvs": {
                    "hw.lcd.width": "1440", "hw.lcd.height": "3120", "hw.lcd.density": "500",
                    "hw.display1.width": "1337", "hw.display1.height": "2777", "hw.display1.density": "450",
                    "hw.display1.enabled": "true"
                },
                "expect_sanitized": True,
                "expect_width": 1440, "expect_height": 3120, "expect_density": 500
            },
            {
                "id": "extreme_4k_landscape",
                "desc": "Extreme 4K landscape (3840x2160 @ 320 DPI)",
                "kvs": {
                    "hw.lcd.width": "1440", "hw.lcd.height": "3120", "hw.lcd.density": "500",
                    "hw.display1.width": "3840", "hw.display1.height": "2160", "hw.display1.density": "320",
                    "hw.display1.enabled": "true"
                },
                "expect_sanitized": True,
                "expect_width": 1440, "expect_height": 3120, "expect_density": 500
            },
            {
                "id": "extreme_8k_landscape",
                "desc": "Extreme 8K landscape (7680x4320 @ 640 DPI)",
                "kvs": {
                    "hw.lcd.width": "1440", "hw.lcd.height": "3120", "hw.lcd.density": "500",
                    "hw.display1.width": "7680", "hw.display1.height": "4320", "hw.display1.density": "640",
                    "hw.display1.enabled": "true"
                },
                "expect_sanitized": True,
                "expect_width": 1440, "expect_height": 3120, "expect_density": 500
            },
            {
                "id": "ultrawide",
                "desc": "Ultra-wide resolution (2560x1080 @ 300 DPI)",
                "kvs": {
                    "hw.lcd.width": "1440", "hw.lcd.height": "3120", "hw.lcd.density": "500",
                    "hw.display1.width": "2560", "hw.display1.height": "1080", "hw.display1.density": "300",
                    "hw.display1.enabled": "true"
                },
                "expect_sanitized": True,
                "expect_width": 1440, "expect_height": 3120, "expect_density": 500
            },
            {
                "id": "microscreen",
                "desc": "Micro-screen (120x120 @ 160 DPI)",
                "kvs": {
                    "hw.lcd.width": "1440", "hw.lcd.height": "3120", "hw.lcd.density": "500",
                    "hw.display1.width": "120", "hw.display1.height": "120", "hw.display1.density": "160",
                    "hw.display1.enabled": "true"
                },
                "expect_sanitized": True,
                "expect_width": 1440, "expect_height": 3120, "expect_density": 500
            },
            {
                "id": "zero_dimensions",
                "desc": "Zero dimensions (0x0 @ 0 DPI with enabled=true)",
                "kvs": {
                    "hw.lcd.width": "1440", "hw.lcd.height": "3120", "hw.lcd.density": "500",
                    "hw.display1.width": "0", "hw.display1.height": "0", "hw.display1.density": "0",
                    "hw.display1.enabled": "true"
                },
                "expect_safe_args": True,  # Must NOT generate invalid QEMU CLI arguments like -multidisplay 1,0,0,500,0
            },
            {
                "id": "negative_dimensions",
                "desc": "Negative dimensions (-1440x-3120 @ -500 DPI with enabled=true)",
                "kvs": {
                    "hw.lcd.width": "1440", "hw.lcd.height": "3120", "hw.lcd.density": "500",
                    "hw.display1.width": "-1440", "hw.display1.height": "-3120", "hw.display1.density": "-500",
                    "hw.display1.enabled": "true"
                },
                "expect_safe_args": True,  # Must NOT generate negative CLI arguments
            },
            {
                "id": "corrupt_string_dimensions",
                "desc": "Corrupt/non-numeric dimensions ('invalid' with enabled=true)",
                "kvs": {
                    "hw.lcd.width": "1440", "hw.lcd.height": "3120", "hw.lcd.density": "500",
                    "hw.display1.width": "invalid", "hw.display1.height": "corrupt", "hw.display1.density": "bad",
                    "hw.display1.enabled": "true"
                },
                "expect_safe_args": True,  # Must handle gracefully without unhandled exception crashing callers
            }
        ]

        for case in test_matrix:
            cid = case["id"]
            cdesc = case["desc"]
            cfg_path = os.path.join(self.temp_dir, f"test_{cid}.ini")
            with open(cfg_path, "w", encoding="utf-8") as f:
                for k, v in case["kvs"].items():
                    f.write(f"{k}={v}\n")

            try:
                san_res = sanitize_multi_display_config(cfg_path)
                sec_cfg = get_secondary_display_config(cfg_path)
                cli_args = get_multi_display_emulator_args(cfg_path)

                if "expect_sanitized" in case:
                    passed = (
                        bool(san_res) == case["expect_sanitized"] and
                        sec_cfg.get("width") == case["expect_width"] and
                        sec_cfg.get("height") == case["expect_height"] and
                        sec_cfg.get("density") == case["expect_density"]
                    )
                    details = (
                        f"Sanitized={bool(san_res)} (Reason: {san_res.get('reason')}), "
                        f"Resolved={sec_cfg.get('width')}x{sec_cfg.get('height')}@{sec_cfg.get('density')}, "
                        f"CLI={cli_args}"
                    )
                    self.log("Sanitization", cdesc, passed, details)

                elif "expect_safe_args" in case:
                    # Critical edge case test for zero / negative / corrupt dimensions
                    # If enabled=true but dimensions <= 0, QEMU CLI args must NOT contain 0 or negative dimensions
                    has_invalid_dims_in_args = False
                    for a in cli_args:
                        if a.startswith("1,"):
                            parts = a.split(",")
                            if len(parts) >= 3:
                                try:
                                    w_arg = int(parts[1])
                                    h_arg = int(parts[2])
                                    if w_arg <= 0 or h_arg <= 0:
                                        has_invalid_dims_in_args = True
                                except ValueError:
                                    has_invalid_dims_in_args = True
                    is_safe = not has_invalid_dims_in_args
                    details = (
                        f"Sanitized={bool(san_res)} (Reason: {san_res.get('reason')}), "
                        f"Resolved={sec_cfg.get('width')}x{sec_cfg.get('height')}@{sec_cfg.get('density')}, "
                        f"CLI={cli_args}, "
                        f"InvalidDimsInArgs={has_invalid_dims_in_args}"
                    )
                    self.log("Sanitization", cdesc, is_safe, details)
            except Exception as e:
                self.log("Sanitization", cdesc, False, f"Unhandled Exception during sanitization/config retrieval: {type(e).__name__}: {e}")

    def test_section_3_multi_instance_persistence(self):
        print("\n=== SECTION 3: Multi-Instance Settings Persistence ===")
        instances = ["inst_alpha", "inst_beta", "inst_gamma"]
        avd_base = os.path.join(self.temp_dir, "avds")
        os.makedirs(avd_base, exist_ok=True)

        spec = importlib.util.spec_from_file_location("gndroid", os.path.join(BASE_DIR, "gndroid.pyw"))
        gndroid_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gndroid_mod)
        gndroid_mod.AVDManager.get_avd_dir = staticmethod(lambda: avd_base)

        import nexus.display_and_vpn
        orig_avd_dir = nexus.display_and_vpn.get_avd_dir
        nexus.display_and_vpn.get_avd_dir = lambda: avd_base

        try:
            # Setup initial instances with diverse configs
            for idx, inst in enumerate(instances):
                inst_dir = os.path.join(avd_base, f"{inst}.avd")
                os.makedirs(inst_dir, exist_ok=True)
                cfg_path = os.path.join(inst_dir, "config.ini")
                content = f"""hw.ramSize=4096
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
gndroid.instance_id={idx}
"""
                with open(cfg_path, "w", encoding="utf-8") as f:
                    f.write(content)

            # Perform simulated AVDManager.update_instance_settings across all instances
            all_preserved = True
            mismatch_reports = []
            for idx, inst in enumerate(instances):
                new_ram = 8192 + idx * 1024
                new_cores = 8
                gndroid_mod.AVDManager.update_instance_settings(
                    name=inst,
                    ram_mb=new_ram,
                    cores=new_cores,
                    width=1440,
                    height=3120,
                    density=500,
                    gpu="auto",
                    root_enabled=(idx % 2 == 1)
                )

                cfg_path = os.path.join(avd_base, f"{inst}.avd", "config.ini")
                with open(cfg_path, "r", encoding="utf-8") as f:
                    saved = f.read()

                required_keys = [
                    f"hw.ramSize={new_ram}",
                    "hw.cpu.ncore=8",
                    "hw.display1.width=1440",
                    "hw.display1.height=3120",
                    "hw.display1.density=500",
                    "hw.display1.enabled=true",
                    "hw.multi_display_window=true",
                    "hw.hotplug_multi_display=true",
                    "gndroid.secondary_display=yes"
                ]
                missing = [k for k in required_keys if k not in saved]
                if missing:
                    all_preserved = False
                    mismatch_reports.append(f"{inst} missing keys: {missing}")

            self.log(
                "Persistence",
                "AVDManager.update_instance_settings Preserves Multi-Display Keys Across Instances",
                all_preserved,
                "All keys intact across instances" if all_preserved else "; ".join(mismatch_reports)
            )
        finally:
            nexus.display_and_vpn.get_avd_dir = orig_avd_dir

    def test_section_4_qemu_cli_generation(self):
        print("\n=== SECTION 4: QEMU CLI Generation ===")
        cfg_path = os.path.join(self.temp_dir, "cli_gen.ini")

        # 1. Secondary display enabled
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write("""hw.lcd.width=1440
hw.lcd.height=3120
hw.lcd.density=500
hw.display1.width=1440
hw.display1.height=3120
hw.display1.density=500
hw.display1.flag=0
hw.display1.enabled=true
""")
        args = get_multi_display_emulator_args(cfg_path)
        expected_flag = "-hotplug-multi-display"
        expected_multidisplay = "-multidisplay"
        expected_param = "1,1440,3120,500,0"

        cond_has_md = expected_multidisplay in args
        cond_has_param = expected_param in args
        cond_has_hotplug = expected_flag in args

        self.log(
            "CLI Generation",
            "Multi-Display Enabled Generates Correct -multidisplay & -hotplug-multi-display",
            cond_has_md and cond_has_param and cond_has_hotplug,
            f"Generated args: {args}"
        )

        # 2. Secondary display disabled
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write("""hw.lcd.width=1440
hw.lcd.height=3120
hw.lcd.density=500
hw.display1.width=0
hw.display1.height=0
hw.display1.density=0
hw.display1.enabled=false
""")
        args_disabled = get_multi_display_emulator_args(cfg_path)
        self.log(
            "CLI Generation",
            "Multi-Display Disabled Generates Empty Args",
            len(args_disabled) == 0,
            f"Generated args: {args_disabled}"
        )

    def run_all(self):
        print("=" * 70)
        print("EMPIRICAL ADVERSARIAL STRESS TEST HARNESS — REQUIREMENT R1")
        print("=" * 70)
        self.test_section_1_default_presets_and_aspect_ratio()
        self.test_section_2_adversarial_edge_cases_and_sanitization()
        self.test_section_3_multi_instance_persistence()
        self.test_section_4_qemu_cli_generation()
        self.cleanup()

        total = len(self.results)
        passed = sum(1 for r in self.results if r["passed"])
        failed = total - passed
        print("\n" + "=" * 70)
        print(f"ADVERSARIAL SUMMARY: Total={total}, Passed={passed}, Failed={failed}")
        print("=" * 70)
        return failed == 0


if __name__ == "__main__":
    runner = AdversarialTestRunner()
    success = runner.run_all()
    sys.exit(0 if success else 1)
