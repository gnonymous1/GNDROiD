#!/usr/bin/env python3
"""
scripts/test_reviewer_adversarial_m1.py
======================================
Independent Adversarial Stress-Test Suite for Reviewer 2 (Milestone M1):
1. Layout Stability & High-DPI Behavior (QR Dialog - R4).
2. Multi-Instance Settings Lifecycle (Key Preservation & INI Key Spacing - R1).
3. Fallback Handling (Zero / Negative Dimensions & Disabled Displays - R1).
4. Sanitization Logic against Wild / Non-numeric / Malformed Resolutions - R1).
5. Code Integrity & Distribution Parity Check.
"""

import os
import sys
import io
import re
import tempfile
import shutil
import importlib.util
from PIL import Image

# Force offscreen Qt rendering
os.environ["QT_QPA_PLATFORM"] = "offscreen"

# Ensure UTF-8 stdout on Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from PyQt6.QtWidgets import QApplication, QDialog, QLabel, QPushButton, QLineEdit, QWidget
from PyQt6.QtCore import Qt, QRect

from nexus.display_and_vpn import (
    get_secondary_display_config,
    set_secondary_display_config,
    get_multi_display_emulator_args,
    sanitize_multi_display_config,
    read_config_dict,
    write_config_keys,
    resolve_config_path
)


def load_gndroid_module():
    spec = importlib.util.spec_from_file_location("gndroid", os.path.join(base_dir, "gndroid.pyw"))
    gndroid_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gndroid_mod)
    return gndroid_mod


# =============================================================================
# SUITE 1: Layout Stability, High-DPI Behavior & Event Handling (R4)
# =============================================================================

def test_qr_dialog_adversarial():
    print("\n" + "=" * 70)
    print("🥊 [ADVERSARIAL CHECK 1] QR Dialog Layout Stability & High-DPI")
    print("=" * 70)

    app = QApplication.instance() or QApplication(sys.argv)
    gndroid_mod = load_gndroid_module()

    test_scenarios = [
        ("Standard URL", "http://192.168.1.105:8088/NexusAI_Mobile_Client.apk"),
        ("Extreme Long URL", "http://192.168.1.105:8088/NexusAI_Mobile_Client_v2.2.1_build20261030_sha256_abcdef1234567890abcdef1234567890_x86_64_enterprise_signed.apk?token=xyz987654321&session=active_client_channel_routing"),
    ]

    for name, test_url in test_scenarios:
        print(f"\n--- Testing Scenario: {name} ---")
        captured = []
        orig_exec = QDialog.exec

        def mock_exec(dlg_self):
            captured.append(dlg_self)
            dlg_self.show()
            app.processEvents()
            return QDialog.DialogCode.Accepted

        QDialog.exec = mock_exec
        orig_start = gndroid_mod.NexusCompanionManager.start_download_server
        gndroid_mod.NexusCompanionManager.start_download_server = staticmethod(lambda: test_url)

        try:
            dummy_parent = QWidget()
            gndroid_mod.GNDroidADBFixerDialog.action_show_mobile_download_qr(dummy_parent)
        finally:
            QDialog.exec = orig_exec
            gndroid_mod.NexusCompanionManager.start_download_server = orig_start

        assert len(captured) == 1, "Failed to capture dialog"
        dlg = captured[0]

        dlg_rect = dlg.rect()
        print(f" -> Dialog rect: {dlg_rect} (min: {dlg.minimumWidth()}x{dlg.minimumHeight()})")

        btn_done = None
        lbl_qr = None
        for child in dlg.findChildren(QPushButton):
            if "Done" in child.text():
                btn_done = child
                break
        for child in dlg.findChildren(QLabel):
            if child.pixmap() and not child.pixmap().isNull():
                lbl_qr = child
                break

        assert btn_done is not None, "Done button not found!"
        assert lbl_qr is not None, "QR label not found!"

        btn_geo = btn_done.geometry()
        print(f" -> Done button geometry: {btn_geo}, Visible: {btn_done.isVisible()}")

        assert dlg_rect.contains(btn_geo), f"FAIL: Done button {btn_geo} is clipped by dialog rect {dlg_rect}!"
        margin_bottom = dlg_rect.bottom() - btn_geo.bottom()
        print(f" -> Clearance below Done button: {margin_bottom}px")
        assert margin_bottom >= 15, f"FAIL: Done button too close to bottom boundary ({margin_bottom}px)"
        assert btn_geo.height() >= 38, f"FAIL: Done button height squeezed to {btn_geo.height()}px"

        pix = lbl_qr.pixmap()
        assert pix.width() == pix.height(), f"FAIL: Pixmap not square: {pix.width()}x{pix.height()}"

        dlg.close()

    print(" [PASSED] Check 1: QR Dialog Layout Stability & High-DPI passed.")


# =============================================================================
# SUITE 2: Multi-Instance Settings Lifecycle & Key Preservation (R1)
# =============================================================================

def test_multi_instance_lifecycle():
    print("\n" + "=" * 70)
    print("🥊 [ADVERSARIAL CHECK 2] Multi-Instance Settings Lifecycle & Cross-Talk")
    print("=" * 70)

    temp_avd_dir = tempfile.mkdtemp()
    try:
        gndroid_mod = load_gndroid_module()
        gndroid_mod.AVDManager.get_avd_dir = staticmethod(lambda: temp_avd_dir)

        import nexus.display_and_vpn
        orig_avd_dir = nexus.display_and_vpn.get_avd_dir
        nexus.display_and_vpn.get_avd_dir = lambda: temp_avd_dir

        try:
            # Instance 1: Flagship (secondary match_primary=True)
            inst1_dir = os.path.join(temp_avd_dir, "inst_flagship.avd")
            os.makedirs(inst1_dir, exist_ok=True)
            with open(os.path.join(inst1_dir, "config.ini"), "w", encoding="utf-8") as f:
                f.write("""hw.ramSize = 4096
hw.cpu.ncore = 4
hw.lcd.width = 1440
hw.lcd.height = 3120
hw.lcd.density = 500
hw.display1.width = 1440
hw.display1.height = 3120
hw.display1.density = 500
hw.display1.enabled = true
hw.display1.match_primary = true
hw.multi_display_window = true
hw.hotplug_multi_display = true
gndroid.secondary_display = yes
hw.gpu.mode = auto
gndroid.root = no
""")

            # Instance 2: Custom Secondary (1080x1920, match_primary=False)
            inst2_dir = os.path.join(temp_avd_dir, "inst_custom.avd")
            os.makedirs(inst2_dir, exist_ok=True)
            with open(os.path.join(inst2_dir, "config.ini"), "w", encoding="utf-8") as f:
                f.write("""hw.ramSize = 6144
hw.cpu.ncore = 6
hw.lcd.width = 1080
hw.lcd.height = 2400
hw.lcd.density = 420
hw.display1.width = 1080
hw.display1.height = 1920
hw.display1.density = 320
hw.display1.enabled = true
hw.display1.match_primary = false
hw.multi_display_window = true
hw.hotplug_multi_display = true
gndroid.secondary_display = yes
hw.gpu.mode = auto
gndroid.root = no
""")

            # Update settings on inst_flagship
            print(" -> Updating settings on inst_flagship...")
            gndroid_mod.AVDManager.update_instance_settings(
                name="inst_flagship", ram_mb=8192, cores=8,
                width=1440, height=3120, density=500, gpu="host", root_enabled=True
            )

            cfg1, lines1 = read_config_dict(os.path.join(inst1_dir, "config.ini"))
            assert cfg1.get("hw.display1.enabled") == "true"
            assert cfg1.get("hw.display1.width") == "1440"
            assert cfg1.get("hw.display1.height") == "3120"
            assert cfg1.get("hw.display1.match_primary") == "true"

            # Check for INI key duplication bug on spaced keys
            with open(os.path.join(inst1_dir, "config.ini"), "r", encoding="utf-8") as f:
                raw_lines1 = f.readlines()
            ram_lines = [l.strip() for l in raw_lines1 if "hw.ramSize" in l]
            print(f" -> hw.ramSize lines found in config.ini: {ram_lines}")
            if len(ram_lines) > 1:
                print(" ⚠️ FINDING CONFIRMED: Duplicate INI keys created when config.ini has spaced keys (e.g. 'hw.ramSize = ...')!")

            print(" [PASSED] Check 2: Multi-Instance Settings Lifecycle passed.")
        finally:
            nexus.display_and_vpn.get_avd_dir = orig_avd_dir
    finally:
        shutil.rmtree(temp_avd_dir, ignore_errors=True)


# =============================================================================
# SUITE 3: Fallback & Zero-Dimension Argument Injection Check (R1)
# =============================================================================

def test_zero_dimension_fallback():
    print("\n" + "=" * 70)
    print("🥊 [ADVERSARIAL CHECK 3] Fallback on Zero / Negative Dimensions")
    print("=" * 70)

    temp_dir = tempfile.mkdtemp()
    try:
        cfg_path = os.path.join(temp_dir, "config.ini")
        # Enabled is true, but width and height are 0
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write("""hw.lcd.width=1440
hw.lcd.height=3120
hw.lcd.density=500
hw.display1.width=0
hw.display1.height=0
hw.display1.density=0
hw.display1.enabled=true
""")
        cfg = get_secondary_display_config(cfg_path)
        args = get_multi_display_emulator_args(cfg_path)
        print(f" -> get_secondary_display_config width={cfg['width']}, height={cfg['height']}")
        print(f" -> get_multi_display_emulator_args: {args}")

        if args == ["-multidisplay", "1,0,0,500,0", "-hotplug-multi-display"]:
            print(" ⚠️ FINDING CONFIRMED: Injects '-multidisplay 1,0,0,500,0' with zero width/height into QEMU!")

        # Negative dimensions
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write("""hw.lcd.width=1440
hw.lcd.height=3120
hw.lcd.density=500
hw.display1.width=-500
hw.display1.height=-800
hw.display1.enabled=true
""")
        args_neg = get_multi_display_emulator_args(cfg_path)
        print(f" -> get_multi_display_emulator_args with negative dims: {args_neg}")
        if "-500" in str(args_neg):
            print(" ⚠️ FINDING CONFIRMED: Negative display dimensions injected into QEMU arguments!")

        print(" [PASSED] Check 3: Fallback & Zero-Dimension diagnostics completed.")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# =============================================================================
# SUITE 4: Non-Numeric / Malformed Input Crash Check (R1)
# =============================================================================

def test_malformed_input_handling():
    print("\n" + "=" * 70)
    print("🥊 [ADVERSARIAL CHECK 4] Malformed / Non-Numeric Input Robustness")
    print("=" * 70)

    temp_dir = tempfile.mkdtemp()
    try:
        cfg_path = os.path.join(temp_dir, "config.ini")
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write("""hw.lcd.width=1440
hw.lcd.height=3120
hw.display1.width=1440px
hw.display1.enabled=true
""")
        try:
            sanitize_multi_display_config(cfg_path)
            print(" -> Sanitizer handled '1440px' cleanly.")
        except ValueError as ve:
            print(f" ⚠️ FINDING CONFIRMED: sanitize_multi_display_config crashes on non-numeric input: {ve}")

        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write("""hw.lcd.width=1440
hw.lcd.height=3120
hw.display1.width=
hw.display1.enabled=true
""")
        try:
            sanitize_multi_display_config(cfg_path)
            print(" -> Sanitizer handled empty string cleanly.")
        except ValueError as ve:
            print(f" ⚠️ FINDING CONFIRMED: sanitize_multi_display_config crashes on empty key value: {ve}")

        print(" [PASSED] Check 4: Malformed input diagnostics completed.")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# =============================================================================
# SUITE 5: Active Integrity & Distribution Parity Check
# =============================================================================

def test_active_integrity():
    print("\n" + "=" * 70)
    print("🥊 [ADVERSARIAL CHECK 5] Active Integrity & Distribution Parity")
    print("=" * 70)

    files_to_check = [
        os.path.join(base_dir, "gndroid.pyw"),
        os.path.join(base_dir, "nexus", "display_and_vpn.py")
    ]

    suspicious_patterns = [
        r"if\s+name\s*==\s*['\"]launch_test['\"]",
        r"if\s+instance_name\s*==\s*['\"]test",
        r"#\s*mock\s+for\s+test",
    ]

    for fpath in files_to_check:
        print(f" -> Scanning {os.path.relpath(fpath, base_dir)} for hardcoded test branches...")
        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        for pat in suspicious_patterns:
            match = re.search(pat, content)
            assert match is None, f"INTEGRITY VIOLATION: Suspicious pattern '{pat}' in {fpath}"

    print(" -> Confirmed: Zero hardcoded test mocks in production code.")

    # Check distribution parity
    dist_gndroid = os.path.join(base_dir, "dist", "gndroid", "gndroid.pyw")
    if os.path.exists(dist_gndroid):
        with open(os.path.join(base_dir, "gndroid.pyw"), "r", encoding="utf-8") as f1, \
             open(dist_gndroid, "r", encoding="utf-8") as f2:
            assert f1.read() == f2.read(), "VIOLATION: dist/gndroid/gndroid.pyw out of sync!"
        print(" -> Confirmed: dist/gndroid/gndroid.pyw in sync.")

    print(" [PASSED] Check 5: Active Integrity & Distribution Parity passed.")


def main():
    print("=" * 70)
    print("🕵️ REVIEWER 2 ADVERSARIAL DIAGNOSTIC SUITE (M1)")
    print("=" * 70)
    test_qr_dialog_adversarial()
    test_multi_instance_lifecycle()
    test_zero_dimension_fallback()
    test_malformed_input_handling()
    test_active_integrity()
    print("\n" + "=" * 70)
    print("✅ ALL ADVERSARIAL DIAGNOSTICS COMPLETED")
    print("=" * 70)


if __name__ == "__main__":
    main()
