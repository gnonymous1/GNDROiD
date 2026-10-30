#!/usr/bin/env python3
"""
scripts/verify_wireless_debugging.py
====================================
Comprehensive Automated Verification Suite for Milestone M4 (Requirement R5):
Wireless Debugging Research, Provisioning, and Dual-Engine Integration.

Tests:
1. QR Pairing Payload Schema Conformance (AOSP Standard WIFI:T:ADB;S:...;P:...;;)
2. QR Code Image & Pixmap Generation with 1:1 Aspect Ratio Verification
3. ADB Pair & Connect Command Generation and Execution Contract
4. TCP 5555 IP Discovery, Mode Switching, and Watchdog Reconnection Contract
5. Research Report Completeness & Institutional Comparison Verification
6. UI Ribbon Button & Screen-Fitted Pairing Dialog Verification (Headless Qt)
"""

import os
import sys
import re
import io
import time
import socket
import tempfile
import threading
import subprocess
from typing import Dict, Any, List

# Force headless offscreen Qt platform for test runner
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

from PIL import Image
from PyQt6.QtWidgets import QApplication, QDialog, QLabel, QPushButton, QLineEdit, QComboBox, QTextEdit, QCheckBox
from PyQt6.QtCore import Qt, QRect

from nexus.wireless_mirror import (
    WirelessPairingEngine,
    WirelessReconnectionWatchdog,
    WirelessMirrorManager,
    get_lan_diagnostic_info,
)


def test_1_qr_pairing_payload_schema():
    print("\n[TEST 1] Verifying QR Pairing Payload Schema Conformance...")

    # Test default generation
    svc_name, pwd, payload = WirelessPairingEngine.generate_pairing_credentials()
    print(f" -> Generated Service Name: {svc_name}")
    print(f" -> Generated Password:     {pwd}")
    print(f" -> Generated Payload:      {payload}")

    assert svc_name.startswith("GNDROiD-"), f"Service name must start with 'GNDROiD-', got {svc_name}"
    assert len(pwd) == 6 and pwd.isdigit(), f"Password must be 6 digits, got {pwd}"
    
    schema_regex = r"^WIFI:T:ADB;S:GNDROiD-[A-Fa-f0-9]+;P:\d{6};;$"
    assert re.match(schema_regex, payload), f"Payload violates AOSP schema: {payload}"
    print(" -> Confirmed: Default payload matches standard AOSP regex pattern.")

    # Test custom payload generator contract from PROJECT.md
    custom_svc = "GNDROiD-TEST-SVC"
    custom_pin = "789123"
    custom_payload = WirelessPairingEngine.generate_qr_payload(custom_svc, custom_pin)
    expected_payload = f"WIFI:T:ADB;S:{custom_svc};P:{custom_pin};;"
    assert custom_payload == expected_payload, f"Expected {expected_payload}, got {custom_payload}"
    print(f" -> Confirmed: generate_qr_payload contract matches expected: {custom_payload}")

    print(" [PASSED] Test 1: QR pairing payload schema conformance verified 100%.")


def test_2_qr_code_image_and_aspect_ratio():
    print("\n[TEST 2] Verifying QR Code Image & Pixmap Generation with 1:1 Aspect Ratio...")

    payload = "WIFI:T:ADB;S:GNDROiD-VERIFY;P:654321;;"
    raw_bytes = WirelessPairingEngine.generate_qr_png_bytes(payload, box_size=5, border=2)
    assert len(raw_bytes) > 100, "Generated PNG bytes are too short!"

    # Load with PIL
    img = Image.open(io.BytesIO(raw_bytes))
    w, h = img.size
    print(f" -> Raw QR image dimensions: {w}x{h}")
    assert w == h, f"QR image dimensions are not square: {w}x{h}"

    # Verify bounding box and finder patterns
    gray = img.convert("L")
    min_x, max_x = w, 0
    min_y, max_y = h, 0

    for y in range(h):
        for x in range(w):
            if gray.getpixel((x, y)) < 128:  # Dark module
                if x < min_x: min_x = x
                if x > max_x: max_x = x
                if y < min_y: min_y = y
                if y > max_y: max_y = y

    qr_w = (max_x - min_x + 1)
    qr_h = (max_y - min_y + 1)
    aspect_ratio = qr_w / qr_h
    print(f" -> Measured active module bounding box: {qr_w}x{qr_h} (aspect ratio: {aspect_ratio:.3f})")
    assert 0.98 <= aspect_ratio <= 1.02, f"QR code bounding box is distorted: {aspect_ratio}"

    # Verify 3 finder patterns in corners
    tl_dark = any(gray.getpixel((min_x + dx, min_y + dy)) < 128 for dx in range(12) for dy in range(12))
    tr_dark = any(gray.getpixel((max_x - dx, min_y + dy)) < 128 for dx in range(12) for dy in range(12))
    bl_dark = any(gray.getpixel((min_x + dx, max_y - dy)) < 128 for dx in range(12) for dy in range(12))
    assert tl_dark and tr_dark and bl_dark, "QR code finder patterns missing or cropped!"
    print(" -> Confirmed: All 3 corner finder patterns detected cleanly.")

    # Test QPixmap generator
    pix = WirelessPairingEngine.generate_qr_pixmap(payload, box_size=5, border=2)
    assert pix is not None and not pix.isNull(), "QPixmap generation failed or returned null!"
    assert pix.width() == pix.height(), f"QPixmap is not square: {pix.width()}x{pix.height()}"
    print(f" -> Confirmed: QPixmap generated cleanly with dimensions {pix.width()}x{pix.height()}.")

    print(" [PASSED] Test 2: QR code image and 1:1 aspect ratio verified 100%.")


def test_3_adb_pair_and_connect_contract():
    print("\n[TEST 3] Verifying ADB Pair & Connect Command Generation and Execution Contract...")

    # We create a dummy mock script or intercept subprocess calls to verify execution parameters
    orig_run = subprocess.run

    intercepted_calls = []

    def mock_run(cmd, *args, **kwargs):
        intercepted_calls.append(list(cmd))
        class DummyProc:
            returncode = 0
            stdout = "Successfully paired to 192.168.1.150:41234 [guid=12345]\n" if "pair" in cmd else "connected to 192.168.1.150:5555\n"
            stderr = ""
        return DummyProc()

    subprocess.run = mock_run

    try:
        # 1. Test pair_device
        ok, msg = WirelessPairingEngine.pair_device("192.168.1.150:41234", "123456", adb_bin="adb")
        assert ok, f"pair_device returned False: {msg}"
        print(f" -> pair_device executed: {intercepted_calls[-1]}")
        assert intercepted_calls[-1][:3] == ["adb", "pair", "192.168.1.150:41234"], "Invalid adb pair command!"
        assert intercepted_calls[-1][3] == "123456", "Password argument missing from adb pair!"

        # 2. Test connect_device
        ok_c, msg_c = WirelessPairingEngine.connect_device("192.168.1.150:5555", adb_bin="adb")
        assert ok_c, f"connect_device returned False: {msg_c}"
        print(f" -> connect_device executed: {intercepted_calls[-1]}")
        assert intercepted_calls[-1] == ["adb", "connect", "192.168.1.150:5555"], "Invalid adb connect command!"

        # 3. Test pair_and_connect pipeline
        ok_all, msg_all = WirelessPairingEngine.pair_and_connect(
            "192.168.1.150:41234",
            "123456",
            connect_host_port="192.168.1.150:41892",
            adb_bin="adb"
        )
        assert ok_all, f"pair_and_connect returned False: {msg_all}"
        print(f" -> pair_and_connect pipeline succeeded: {msg_all}")

    finally:
        subprocess.run = orig_run

    print(" [PASSED] Test 3: ADB pair & connect command generation contract verified 100%.")


def test_4_tcp_5555_provisioning_and_watchdog():
    print("\n[TEST 4] Verifying TCP 5555 IP Discovery, Mode Switching, and Watchdog Contract...")

    # 1. Test query_device_lan_ip with simulated outputs
    orig_check_output = subprocess.check_output
    orig_run = subprocess.run

    def mock_check_output(cmd, *args, **kwargs):
        cmd_str = " ".join(cmd)
        if "ip -f inet addr show wlan0" in cmd_str:
            return "2: wlan0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc mq state UP\n    inet 192.168.1.188/24 brd 192.168.1.255 scope global wlan0\n"
        if "ip route get" in cmd_str:
            return "8.8.8.8 via 192.168.1.1 dev wlan0 src 192.168.1.188\n"
        if "getprop dhcp.wlan0.ipaddress" in cmd_str:
            return "192.168.1.188\n"
        return ""

    def mock_run(cmd, *args, **kwargs):
        class DummyProc:
            returncode = 0
            stdout = "restarting in TCP mode port: 5555\n" if "tcpip" in cmd else "connected to 192.168.1.188:5555\n"
            stderr = ""
        return DummyProc()

    subprocess.check_output = mock_check_output
    subprocess.run = mock_run

    try:
        ip = WirelessPairingEngine.query_device_lan_ip("emulator-5554", adb_bin="adb")
        print(f" -> Discovered IP via wlan0 mock: {ip}")
        assert ip == "192.168.1.188", f"Expected 192.168.1.188, got {ip}"

        # Test enable_tcpip_mode
        ok_tcp, msg_tcp = WirelessPairingEngine.enable_tcpip_mode("emulator-5554", port=5555, adb_bin="adb")
        assert ok_tcp, f"enable_tcpip_mode failed: {msg_tcp}"
        print(f" -> enable_tcpip_mode returned: ok={ok_tcp}, msg={msg_tcp}")

        # Test provision_tcp_5555 pipeline
        prov_ok, prov_msg, target = WirelessPairingEngine.provision_tcp_5555("emulator-5554", port=5555, adb_bin="adb")
        assert prov_ok, f"provision_tcp_5555 failed: {prov_msg}"
        assert target == "192.168.1.188:5555", f"Expected target 192.168.1.188:5555, got {target}"
        print(f" -> provision_tcp_5555 pipeline returned: target={target}, msg={prov_msg}")

    finally:
        subprocess.check_output = orig_check_output
        subprocess.run = orig_run

    # 2. Test WirelessReconnectionWatchdog lifecycle
    print(" -> Testing WirelessReconnectionWatchdog thread lifecycle...")
    status_events = []

    def on_status_change(t, alive, msg):
        status_events.append((t, alive, msg))

    watchdog = WirelessReconnectionWatchdog(
        targets=["127.0.0.1:5555"],
        check_interval=1.0,
        adb_bin="adb",
        on_status_change=on_status_change
    )

    # Test dynamic target modification
    watchdog.add_target("192.168.1.188:5555")
    assert "192.168.1.188:5555" in watchdog.targets, "Target was not added to watchdog!"
    watchdog.remove_target("127.0.0.1:5555")
    assert "127.0.0.1:5555" not in watchdog.targets, "Target was not removed from watchdog!"

    # Start and stop watchdog thread
    watchdog.start()
    assert watchdog.is_alive(), "Watchdog thread is not running after start()!"
    time.sleep(0.3)
    watchdog.stop(timeout=1.0)
    assert not watchdog.is_alive(), "Watchdog thread did not stop cleanly!"
    print(" -> Confirmed: Watchdog thread start, monitor loop, and clean stop validated.")

    print(" [PASSED] Test 4: TCP 5555 IP discovery and watchdog contract verified 100%.")


def test_5_research_report_completeness():
    print("\n[TEST 5] Verifying Research Report Completeness in docs/WIRELESS_DEBUGGING_RESEARCH_REPORT.md...")
    report_path = os.path.join(base_dir, "docs", "WIRELESS_DEBUGGING_RESEARCH_REPORT.md")
    assert os.path.exists(report_path), f"Report not found at {report_path}"

    with open(report_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Verify key sections and technical topics
    required_topics = [
        "AOSP Wireless Debugging",
        "SPAKE2",
        "TLS 1.3",
        "_adb-tls-pairing",
        "_adb-tls-connect",
        "WIFI:T:ADB;S:",
        "Shizuku",
        "Binder IPC",
        "IShizukuService",
        "UID 2000",
        "LADB",
        "loopback",
        "127.0.0.1",
        "Traditional ADB over TCP/IP",
        "5555",
        "service.adb.tcp.port",
        "Comparative Matrix",
        "Dual-Engine",
        "WirelessReconnectionWatchdog",
    ]

    for topic in required_topics:
        assert topic in content, f"Required topic '{topic}' missing from research report!"
        print(f" -> Found required topic: '{topic}'")

    report_len = len(content.splitlines())
    print(f" -> Report verified: {report_len} lines, {len(content)} characters.")
    assert report_len >= 200, f"Report is too brief ({report_len} lines); institutional depth required."

    print(" [PASSED] Test 5: Research report completeness verified 100%.")


def test_6_ui_ribbon_and_dialog_verification():
    print("\n[TEST 6] Verifying UI Ribbon Button & Screen-Fitted Dialog Geometry...")
    app = QApplication.instance() or QApplication(sys.argv)

    # Import gndroid dynamically
    import importlib.util
    spec = importlib.util.spec_from_file_location("gndroid", os.path.join(base_dir, "gndroid.pyw"))
    gndroid_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gndroid_mod)

    # 1. Instantiate GNDroidWirelessPairingDialog
    dlg = gndroid_mod.GNDroidWirelessPairingDialog(target_serial="emulator-5554", parent=None)
    dlg.show()
    app.processEvents()

    # 2. Verify dimensions & minimum sizing
    w, h = dlg.width(), dlg.height()
    min_w, min_h = dlg.minimumWidth(), dlg.minimumHeight()
    print(f" -> Dialog geometry: {w}x{h} (minimum: {min_w}x{min_h})")
    assert min_w >= 540, f"Expected min width >= 540, got {min_w}"
    assert min_h >= 640, f"Expected min height >= 640, got {min_h}"
    assert w >= 540 and h >= 640, f"Dialog dimensions smaller than minimum: {w}x{h}"

    # 3. Verify QR code label and 1:1 aspect ratio
    assert hasattr(dlg, "lbl_qr_code"), "lbl_qr_code not found on dialog!"
    lbl_qr = dlg.lbl_qr_code
    qr_w, qr_h = lbl_qr.width(), lbl_qr.height()
    print(f" -> QR label geometry: {qr_w}x{qr_h}")
    assert qr_w == qr_h, f"QR label is not 1:1 square: {qr_w}x{qr_h}"
    assert "margin: 0 auto" not in lbl_qr.styleSheet(), "Invalid 'margin: 0 auto' found in QR label stylesheet!"

    # 4. Verify Done and Cancel buttons visibility and geometry
    assert hasattr(dlg, "btn_done"), "btn_done not found on dialog!"
    assert hasattr(dlg, "btn_cancel"), "btn_cancel not found on dialog!"
    btn_done = dlg.btn_done
    btn_cancel = dlg.btn_cancel

    dlg_rect = dlg.rect()
    done_geo = btn_done.geometry()
    print(f" -> Done button geometry: {done_geo}, Dialog rect: {dlg_rect}")
    assert dlg_rect.contains(done_geo), f"Done button is outside dialog rect! {done_geo}"
    assert btn_done.isVisible(), "Done button is not visible!"
    assert btn_done.height() >= 36, f"Done button height too small: {btn_done.height()}"

    cancel_geo = btn_cancel.geometry()
    assert dlg_rect.contains(cancel_geo), f"Cancel button is outside dialog rect! {cancel_geo}"
    assert btn_cancel.isVisible(), "Cancel button is not visible!"

    # 5. Verify Tab 2 controls exist
    assert hasattr(dlg, "btn_switch_tcp"), "btn_switch_tcp not found on dialog!"
    assert hasattr(dlg, "chk_watchdog"), "chk_watchdog not found on dialog!"
    assert hasattr(dlg, "txt_tcp_log"), "txt_tcp_log not found on dialog!"

    dlg.close()
    if dlg.qr_worker and dlg.qr_worker.isRunning():
        dlg.qr_worker.stop()

    print(" [PASSED] Test 6: UI ribbon & dialog geometry verified 100%.")


def main():
    print("=" * 70)
    print("📡 VERIFY REQUIREMENT R5: Wireless Debugging & Provisioning Suite")
    print("=" * 70)

    # Initialize QApplication for offscreen rendering & QPixmap generation
    app = QApplication.instance() or QApplication(sys.argv)

    try:
        test_1_qr_pairing_payload_schema()
        test_2_qr_code_image_and_aspect_ratio()
        test_3_adb_pair_and_connect_contract()
        test_4_tcp_5555_provisioning_and_watchdog()
        test_5_research_report_completeness()
        test_6_ui_ribbon_and_dialog_verification()

        print("\n" + "=" * 70)
        print("✅ ALL WIRELESS DEBUGGING VERIFICATION CHECKS PASSED (EXIT 0)")
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
