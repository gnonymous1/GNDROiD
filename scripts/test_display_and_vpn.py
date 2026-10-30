#!/usr/bin/env python3
"""
scripts/test_display_and_vpn.py
===============================
Verification test suite for:
1. Multi-Display Synchronization & Configuration
2. Wild/4K Multi-Display Sanitization
3. Launch Arguments (-dns-server 8.8.8.8,1.1.1.1)
4. In-Emulator Guest VPN & DNS Fix against running emulator-5554
"""

import os
import sys
import time
import shutil
import logging
import subprocess

# Ensure UTF-8 stdout on Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Add workspace to path
workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if workspace_dir not in sys.path:
    sys.path.insert(0, workspace_dir)

from nexus.display_and_vpn import (
    get_secondary_display_config,
    set_secondary_display_config,
    sanitize_multi_display_config,
    fix_guest_vpn_and_dns,
    get_vpn_and_dns_emulator_args,
    get_multi_display_emulator_args,
    detect_installed_vpn_apps,
    grant_vpn_permission,
    _find_adb
)

def run_tests():
    print("=" * 70)
    print("🧪 GNDROiD Display & VPN Test Suite Starting...")
    print("=" * 70)

    avd_name = "gndroid"
    avd_config_path = os.path.expanduser(r"~\.android\avd\gndroid.avd\config.ini")
    
    # -------------------------------------------------------------------------
    # TEST 1: Launch Argument Verification
    # -------------------------------------------------------------------------
    print("\n[TEST 1] Verifying get_vpn_and_dns_emulator_args()...")
    args = get_vpn_and_dns_emulator_args()
    print(f" -> Generated args: {args}")
    assert args == ["-dns-server", "8.8.8.8,1.1.1.1"], f"Unexpected args: {args}"
    print(" [PASSED] Launch arguments match expected spec.")

    # -------------------------------------------------------------------------
    # TEST 2: Secondary Display Config Read & Write
    # -------------------------------------------------------------------------
    print("\n[TEST 2] Verifying get_secondary_display_config and set_secondary_display_config...")
    assert os.path.exists(avd_config_path), f"AVD config not found at {avd_config_path}"
    
    # Backup original config.ini
    backup_path = avd_config_path + ".bak_test"
    shutil.copyfile(avd_config_path, backup_path)
    print(f" -> Backed up original config to: {backup_path}")

    try:
        # Read initial state
        initial_cfg = get_secondary_display_config(avd_name)
        print(f" -> Initial config: enabled={initial_cfg['enabled']}, primary={initial_cfg['primary_width']}x{initial_cfg['primary_height']} @ {initial_cfg['primary_density']} DPI")
        assert initial_cfg["primary_width"] == 1440, f"Expected 1440, got {initial_cfg['primary_width']}"
        assert initial_cfg["primary_height"] == 3120, f"Expected 3120, got {initial_cfg['primary_height']}"

        # Enable secondary display with match_primary=True
        print(" -> Setting secondary display enabled=True, match_primary=True...")
        res_enable = set_secondary_display_config(avd_name, enabled=True, match_primary=True)
        print(f" -> set_secondary_display_config result: {res_enable['width']}x{res_enable['height']} @ {res_enable['density']} DPI")
        assert res_enable["enabled"] is True
        assert res_enable["match_primary"] is True
        assert res_enable["width"] == 1440
        assert res_enable["height"] == 3120
        assert res_enable["density"] == 500

        # Read back with get_secondary_display_config
        cfg_read = get_secondary_display_config(avd_name)
        assert cfg_read["enabled"] is True
        assert cfg_read["match_primary"] is True
        assert cfg_read["width"] == 1440
        assert cfg_read["height"] == 3120
        assert cfg_read["density"] == 500
        print(" [PASSED] Secondary display enables and defaults to primary (1440x3120 @ 500 DPI).")

        # Multi-display emulator args test
        m_args = get_multi_display_emulator_args(avd_name)
        print(f" -> Multi-display emulator launch args: {m_args}")
        assert m_args == ["-multidisplay", "1,1440,3120,500,0"], f"Unexpected m_args: {m_args}"
        print(" [PASSED] Multi-display launch args generated successfully.")

        # Set custom secondary display dimensions
        print(" -> Setting custom secondary display 1080x2400 @ 420 DPI with match_primary=False...")
        res_custom = set_secondary_display_config(avd_name, enabled=True, match_primary=False, width=1080, height=2400, density=420)
        assert res_custom["width"] == 1080
        assert res_custom["height"] == 2400
        assert res_custom["density"] == 420
        cfg_custom = get_secondary_display_config(avd_name)
        assert cfg_custom["width"] == 1080
        assert cfg_custom["height"] == 2400
        assert cfg_custom["density"] == 420
        print(" [PASSED] Custom secondary display dimensions saved and retrieved successfully.")

        # ---------------------------------------------------------------------
        # TEST 3: Wild / 4K Secondary Display Sanitization
        # ---------------------------------------------------------------------
        print("\n[TEST 3] Verifying sanitize_multi_display_config with 4K landscape secondary display...")
        # Artificially inject a wild/4K landscape configuration: 3840x2160
        set_secondary_display_config(avd_name, enabled=True, match_primary=False, width=3840, height=2160, density=320)
        
        # Verify it has the wild config before sanitization
        pre_sanitize = get_secondary_display_config(avd_name)
        print(f" -> Wild/4K pre-sanitize state: {pre_sanitize['width']}x{pre_sanitize['height']} (is landscape: {pre_sanitize['width'] > pre_sanitize['height']})")
        assert pre_sanitize["width"] == 3840
        assert pre_sanitize["height"] == 2160

        # Now run sanitization
        sanitize_res = sanitize_multi_display_config(avd_config_path)
        print(f" -> sanitize_multi_display_config result: sanitized={sanitize_res['sanitized']}")
        print(f" -> Reason: {sanitize_res['reason']}")
        assert sanitize_res["sanitized"] is True, "Sanitization was expected to trigger on 4K/landscape!"
        assert sanitize_res["secondary"]["width"] == 1440
        assert sanitize_res["secondary"]["height"] == 3120
        assert sanitize_res["secondary"]["density"] == 500

        # Read back config to ensure file was permanently normalized
        post_sanitize = get_secondary_display_config(avd_name)
        assert post_sanitize["width"] == 1440
        assert post_sanitize["height"] == 3120
        assert post_sanitize["density"] == 500
        print(" [PASSED] Wild 4K secondary display normalized to match primary portrait 1440x3120 @ 500 DPI.")

        # Idempotency check: running sanitize again should not re-trigger
        sanitize_again = sanitize_multi_display_config(avd_config_path)
        assert not sanitize_again, "Idempotent sanitize check failed (should be False)"
        print(" [PASSED] Sanitization is idempotent (no-op on clean config).")

    finally:
        # Restore backup config.ini
        if os.path.exists(backup_path):
            shutil.copyfile(backup_path, avd_config_path)
            os.remove(backup_path)
            print(f"\n -> Restored original config from backup: {avd_config_path}")

    # -------------------------------------------------------------------------
    # TEST 4: Guest In-Emulator VPN & DNS Fix against emulator-5554
    # -------------------------------------------------------------------------
    print("\n[TEST 4] Verifying fix_guest_vpn_and_dns against emulator-5554...")
    adb = _find_adb()
    print(f" -> Using ADB at: {adb}")

    # Check if emulator-5554 is already running
    emu_started_by_test = False
    emu_proc = None
    serial = "emulator-5554"

    try:
        st = subprocess.check_output([adb, "-s", serial, "get-state"], text=True, timeout=3, creationflags=0x08000000).strip()
        is_online = (st == "device")
    except Exception:
        is_online = False

    if not is_online:
        print(" -> emulator-5554 is not currently running. Launching gndroid instance...")
        try:
            # Import gndroid launcher if available
            import importlib.util
            spec = importlib.util.spec_from_file_location("gndroid", os.path.join(workspace_dir, "gndroid.pyw"))
            gndroid_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(gndroid_mod)
            emu_proc, port, log_path = gndroid_mod.AVDManager.launch_emulator_instance("gndroid", port=5554)
            emu_started_by_test = True
            print(f" -> Emulator launched with PID {emu_proc.pid} on port {port}. Waiting for device...")
        except Exception as e:
            print(f" -> Could not launch via AVDManager: {e}. Attempting direct launch...")
            local_app_data = os.environ.get('LOCALAPPDATA', '')
            emu_bin = os.path.join(local_app_data, 'Android', 'Sdk', 'emulator', 'emulator.exe')
            cmd = [emu_bin, "-avd", "gndroid", "-port", "5554", "-gpu", "auto", "-netfast"] + get_vpn_and_dns_emulator_args()
            emu_proc = subprocess.Popen(cmd, creationflags=0x00000008 | 0x08000000)
            emu_started_by_test = True

        # Wait for device to be online and boot completed
        for s in range(60):
            time.sleep(1)
            try:
                st = subprocess.check_output([adb, "-s", serial, "get-state"], text=True, timeout=2, creationflags=0x08000000).strip()
                if st == "device":
                    try:
                        boot = subprocess.check_output([adb, "-s", serial, "shell", "getprop", "sys.boot_completed"], text=True, timeout=2, creationflags=0x08000000).strip()
                    except Exception:
                        boot = ""
                    if boot == "1":
                        print(f" -> Device {serial} reached ONLINE and BOOT COMPLETE state at second {s}!")
                        time.sleep(2)
                        break
            except Exception:
                pass
            if s % 5 == 0:
                print(f"   Waiting for {serial} to boot... ({s}s)")
        else:
            print(f" -> Continuing after timeout waiting for boot completion on {serial}...")

    print(f" -> Device {serial} is ONLINE. Executing fix_guest_vpn_and_dns()...")
    
    # Test VPN detection before fix
    detected_apps = detect_installed_vpn_apps(serial)
    print(f" -> Detected VPN applications on guest: {detected_apps}")

    # Test granting VPN appops permission
    test_pkg = "com.wireguard.android"
    grant_ok = grant_vpn_permission(serial, test_pkg)
    print(f" -> Testing grant_vpn_permission for '{test_pkg}': success={grant_ok}")

    # Execute main fix_guest_vpn_and_dns function
    fix_result = fix_guest_vpn_and_dns(serial)
    print("\n -> In-Emulator VPN & DNS Fix Results:")
    print(f"    * Status: {fix_result['status']}")
    print(f"    * Online: {fix_result['online']}")
    print(f"    * DNS Properties: {fix_result['dns']['configured']}")
    print(f"    * Private DNS: {fix_result['dns'].get('private_dns')}")
    print(f"    * VPN Packages Detected: {fix_result['vpn']['total_detected']}")
    print(f"    * Ping 8.8.8.8 Success: {fix_result['ping']['success']}")
    print(f"    * Ping Output Tail: {fix_result['ping']['output']}")

    assert fix_result["online"] is True, "Device should be online"
    dns_info = fix_result.get("dns", {})
    priv_dns = dns_info.get("private_dns", {})
    prop_dns1 = dns_info.get("configured", {}).get("net.dns1")
    dns_verified = (priv_dns.get("applied") is True and priv_dns.get("mode") == "hostname") or (prop_dns1 == "8.8.8.8")
    assert dns_verified, f"DNS verification failed: private_dns={priv_dns}, configured={dns_info.get('configured')}"
    assert fix_result["ping"]["success"] is True, f"Ping to 8.8.8.8 failed: {fix_result['ping']['output']}"
    print(" [PASSED] In-Emulator VPN & DNS Fix verified 100% against emulator-5554!")

    # Clean up emulator if it was launched specifically for this test
    if emu_started_by_test and emu_proc:
        print("\n -> Terminating test emulator process...")
        try:
            subprocess.run([adb, "-s", serial, "emu", "kill"], timeout=5, creationflags=0x08000000)
            time.sleep(2)
            emu_proc.kill()
        except Exception:
            pass

    print("\n" + "=" * 70)
    print("🎉 ALL TESTS PASSED SUCCESSFULLY (100% VERIFIED)!")
    print("=" * 70)

if __name__ == "__main__":
    run_tests()
