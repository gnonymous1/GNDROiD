#!/usr/bin/env python3
"""
scripts/test_challenger_m4_ui_adversarial.py
============================================
Adversarial UI, Aspect Ratio, Geometry & Modal Stress Test Suite for Milestone M4 (Requirement R5 / R4):
GNDroidWirelessPairingDialog, QR Rendering & Ribbon Integration Verification.

Authored by: challenger_m4_2 (Role: Wireless UI & Aspect Ratio Adversarial Challenger)
Operating System: Windows | Integrity Mode: Strict Empirical Verification

Challenge Dimensions:
1. VIRTUAL SCREEN DIMENSIONS & BOUNDING BOX STRESS:
   - Verify dialog bounding box containment across 6 standard desktop/laptop displays:
     1024x768 (XGA), 1280x720 (720p HD), 1366x768 (WXGA), 1920x1080 (1080p FHD),
     2560x1440 (2K QHD), and 3840x2160 (4K UHD).
   - Verify minimum sizing boundary enforcement (setMinimumSize 560x680, defaults 580x710).
   - Adversarial shrinking resistance (<560x680 rejected by Qt layout constraints).
   - Dynamic expansion stress up to 1600x1200 with layout containment invariance.
2. QR CODE STRICT 1:1 ASPECT RATIO, FINDER PATTERN MICRO-INSPECTION & QSS AUDIT:
   - Strict 1:1 aspect ratio on lbl_qr_code (220x220, width == height).
   - Strict 1:1 aspect ratio on rendered QPixmap (200x200, width == height).
   - Micro-inspection of 3 corner finder patterns (Top-Left, Top-Right, Bottom-Left)
     verifying concentric 7x7 outer dark border, 5x5 light ring, and 3x3 dark core.
   - Verification that Bottom-Right does NOT have a false finder pattern.
   - Quiet zone (border >= 2 modules) preservation and zero edge-cropping.
   - Multi-payload stress: default payload, minimal payload, ultra-long payload (100+ chars),
     and special character payload.
   - Static and dynamic QSS audit confirming 0 occurrences of invalid 'margin: 0 auto;'.
3. BUTTON BOUNDING BOXES, ENABLING, CLICKABILITY & SIGNAL VERIFICATION:
   - Full containment of btn_done and btn_cancel inside dlg.rect().
   - Non-overlapping geometries between buttons and tab container.
   - Minimum height >= 38px, pointing hand cursor, enabled state.
   - Simulated click execution triggering QDialog.accept() and QDialog.reject().
   - Containment invariance under multiple resized window geometries.
4. TAB SWITCHING ROBUSTNESS & ANTI-SQUISHING UNDER RAPID CYCLING:
   - Verify Tab 1 (QR Zero-Cable) controls and initial state.
   - Verify Tab 2 (1-Click TCP 5555) controls and dimensions.
   - 100-cycle rapid tab switching stress test (Tab 0 <-> Tab 1).
   - Post-cycle verification: zero layout corruption, zero squishing, 1:1 QR aspect preserved.
5. RIBBON BUTTON INTEGRATION IN MAIN WINDOW & COMPANION SIDEBAR:
   - GNDroidApp main window: btn_wireless_pairing exists, styled, tooltipped, and
     invokes open_wireless_pairing_dialog().
   - GNDroidCompanionSidebar: btn_wireless exists, styled with 'wireless' icon, Alt+W shortcut,
     and invokes action_wireless_pairing().
   - Clean headless instantiation, modal execution, and teardown with 0 unhandled exceptions.
"""

import os
import sys
import io
import time
import importlib.util
from typing import Dict, Any, List, Tuple

# Force headless Qt platform for test runner
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
from PyQt6.QtWidgets import (
    QApplication, QDialog, QLabel, QPushButton, QLineEdit,
    QComboBox, QTextEdit, QCheckBox, QWidget, QFrame
)
from PyQt6.QtCore import Qt, QRect, QPoint, QSize

from nexus.wireless_mirror import WirelessPairingEngine


def log_challenge(title: str):
    print("\n" + "=" * 78)
    print(f"🔥 CHALLENGE: {title}")
    print("=" * 78)


def load_gndroid_module():
    """Dynamically loads gndroid.pyw."""
    gndroid_path = os.path.join(base_dir, "gndroid.pyw")
    spec = importlib.util.spec_from_file_location("gndroid", gndroid_path)
    gndroid_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gndroid_mod)
    return gndroid_mod


# =============================================================================
# CHALLENGE 1: Virtual Screen Dimensions & Bounding Box Stress
# =============================================================================
def test_challenge_1_screen_dimensions_and_bounding_boxes(gndroid_mod, app):
    log_challenge("1. Virtual Screen Dimensions & Bounding Box Stress")

    dlg = gndroid_mod.GNDroidWirelessPairingDialog(target_serial="emulator-5554", parent=None)
    dlg.show()
    app.processEvents()

    # 1. Verify Minimum Sizing Constraints
    min_w = dlg.minimumWidth()
    min_h = dlg.minimumHeight()
    print(f" -> Reported Minimum Dialog Size: {min_w}x{min_h}")
    assert min_w >= 560, f"Expected minimum width >= 560, got {min_w}"
    assert min_h >= 680, f"Expected minimum height >= 680, got {min_h}"

    w, h = dlg.width(), dlg.height()
    print(f" -> Default Initial Dialog Size: {w}x{h}")
    assert w >= min_w, f"Initial width {w} violates minimum {min_w}"
    assert h >= min_h, f"Initial height {h} violates minimum {min_h}"

    # 2. Virtual Screen Resolutions
    screen_resolutions = [
        ("1024x768 (XGA Baseline)", 1024, 768),
        ("1280x720 (720p HD)", 1280, 720),
        ("1366x768 (Budget Laptop)", 1366, 768),
        ("1920x1080 (1080p FHD)", 1920, 1080),
        ("2560x1440 (2K QHD)", 2560, 1440),
        ("3840x2160 (4K UHD)", 3840, 2160),
    ]

    for label, scr_w, scr_h in screen_resolutions:
        virtual_screen_rect = QRect(0, 0, scr_w, scr_h)
        # Check default dialog dimensions fit in virtual screen
        assert dlg.width() <= scr_w, f"Dialog width ({dlg.width()}) exceeds {label} width ({scr_w})!"
        assert dlg.height() <= scr_h, f"Dialog height ({dlg.height()}) exceeds {label} height ({scr_h})!"

        # Simulate Centering on Screen
        center_x = max(0, (scr_w - dlg.width()) // 2)
        center_y = max(0, (scr_h - dlg.height()) // 2)
        dialog_sim_rect = QRect(center_x, center_y, dlg.width(), dlg.height())

        assert virtual_screen_rect.contains(dialog_sim_rect), (
            f"Simulated dialog rect {dialog_sim_rect} extends outside {label} boundaries {virtual_screen_rect}!"
        )
        print(f" -> [OK] Fits cleanly and centers inside {label}: placement {dialog_sim_rect}")

    # 3. Adversarial Shrink Resistance Test
    print(" -> Adversarial Attempt: Forcing dialog resize to 300x300 (below minimum)...")
    dlg.resize(300, 300)
    app.processEvents()
    curr_w, curr_h = dlg.width(), dlg.height()
    print(f" -> Enforced size after shrink attempt: {curr_w}x{curr_h}")
    assert curr_w >= min_w, f"Shrink resistance failed: width {curr_w} < minimum {min_w}!"
    assert curr_h >= min_h, f"Shrink resistance failed: height {curr_h} < minimum {min_h}!"

    # 4. Adversarial Expansion Stress Test
    expansion_sizes = [(800, 900), (1200, 1000), (1600, 1200)]
    for target_w, target_h in expansion_sizes:
        print(f" -> Adversarial Expansion to {target_w}x{target_h}...")
        dlg.resize(target_w, target_h)
        app.processEvents()

        dlg_rect = dlg.rect()
        done_geo = dlg.btn_done.geometry()
        cancel_geo = dlg.btn_cancel.geometry()
        tabs_geo = dlg.tabs.geometry()

        assert dlg_rect.contains(done_geo), f"Done button escaped dialog rect during resize {target_w}x{target_h}!"
        assert dlg_rect.contains(cancel_geo), f"Cancel button escaped dialog rect during resize {target_w}x{target_h}!"
        assert dlg_rect.contains(tabs_geo), f"Tabs escaped dialog rect during resize {target_w}x{target_h}!"
        assert dlg.lbl_qr_code.width() == 220, "QR label width distorted during expansion!"
        assert dlg.lbl_qr_code.height() == 220, "QR label height distorted during expansion!"

    # Restore default
    dlg.resize(580, 710)
    app.processEvents()

    dlg.close()
    if dlg.qr_worker and dlg.qr_worker.isRunning():
        dlg.qr_worker.stop()

    print(" [PASSED] Challenge 1: Virtual screen geometry and bounding box stress verified 100%.")


# =============================================================================
# CHALLENGE 2: QR Code Strict 1:1 Aspect Ratio, Finder Pattern Micro-Inspection & QSS
# =============================================================================
def inspect_qr_finder_patterns(img_bytes: bytes) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Performs mathematical micro-inspection on raw QR PNG image bytes:
    - Confirms active matrix 1:1 aspect ratio.
    - Confirms intact 7x7 outer dark border, 5x5 light ring, and 3x3 dark core
      at Top-Left (TL), Top-Right (TR), and Bottom-Left (BL).
    - Confirms Bottom-Right (BR) does NOT have a finder pattern.
    - Confirms quiet zone border.
    """
    img = Image.open(io.BytesIO(img_bytes))
    w, h = img.size
    if w != h:
        return False, f"Image not square: {w}x{h}", {}

    gray = img.convert("L")

    # Find matrix bounds
    min_x, max_x = w, 0
    min_y, max_y = h, 0
    for y in range(h):
        for x in range(w):
            if gray.getpixel((x, y)) < 128:
                if x < min_x: min_x = x
                if x > max_x: max_x = x
                if y < min_y: min_y = y
                if y > max_y: max_y = y

    mat_w = max_x - min_x + 1
    mat_h = max_y - min_y + 1
    aspect_ratio = mat_w / mat_h
    if not (0.99 <= aspect_ratio <= 1.01):
        return False, f"Distorted matrix aspect ratio: {aspect_ratio:.4f} ({mat_w}x{mat_h})", {}

    # Estimate module size from finder pattern outer dimension (always 7 modules)
    # Scan from min_x at center of top finder pattern:
    # Top-Left finder pattern is located at (min_x, min_y) to (min_x + 7*mod, min_y + 7*mod)
    # Let's count consecutive dark pixels along top edge of TL finder pattern
    dark_run_x = 0
    for x in range(min_x, max_x):
        if gray.getpixel((x, min_y)) < 128:
            dark_run_x += 1
        else:
            break

    module_size = dark_run_x / 7.0
    if module_size < 1.0:
        return False, f"Module size calculation too small: {module_size}", {}

    finder_px = int(round(module_size * 7))

    # Helper to check a finder pattern region
    def check_finder(x_start: int, y_start: int) -> bool:
        # Check center core (should be dark)
        cx = int(x_start + finder_px / 2.0)
        cy = int(y_start + finder_px / 2.0)
        center_dark = gray.getpixel((cx, cy)) < 128

        # Check corners of 7x7 outer box (should be dark)
        c_tl = gray.getpixel((x_start, y_start)) < 128
        c_tr = gray.getpixel((x_start + finder_px - 1, y_start)) < 128
        c_bl = gray.getpixel((x_start, y_start + finder_px - 1)) < 128
        c_br = gray.getpixel((x_start + finder_px - 1, y_start + finder_px - 1)) < 128

        # Check light ring (midpoint between outer border and center core)
        lx = int(x_start + module_size * 1.5)
        ly = int(y_start + finder_px / 2.0)
        ring_light = gray.getpixel((lx, ly)) > 128

        return center_dark and c_tl and c_tr and c_bl and c_br and ring_light

    # Check Top-Left (TL)
    tl_ok = check_finder(min_x, min_y)

    # Check Top-Right (TR)
    tr_ok = check_finder(max_x - finder_px + 1, min_y)

    # Check Bottom-Left (BL)
    bl_ok = check_finder(min_x, max_y - finder_px + 1)

    # Check Bottom-Right (BR) - MUST NOT BE FINDER PATTERN
    br_cx = int(max_x - finder_px / 2.0)
    br_cy = int(max_y - finder_px / 2.0)
    br_has_finder = check_finder(max_x - finder_px + 1, max_y - finder_px + 1)

    metrics = {
        "img_size": f"{w}x{h}",
        "matrix_size": f"{mat_w}x{mat_h}",
        "aspect_ratio": aspect_ratio,
        "module_size": module_size,
        "tl_intact": tl_ok,
        "tr_intact": tr_ok,
        "bl_intact": bl_ok,
        "br_finder_absent": not br_has_finder,
    }

    if not (tl_ok and tr_ok and bl_ok):
        return False, f"Finder pattern defect: TL={tl_ok}, TR={tr_ok}, BL={bl_ok}", metrics

    if br_has_finder:
        return False, "False finder pattern detected at Bottom-Right corner!", metrics

    # Quiet zone check: at least 2 pixels of white border around matrix
    if min_x < 2 or min_y < 2 or (w - max_x) < 2 or (h - max_y) < 2:
        return False, f"Quiet zone violated or cropped: min_x={min_x}, min_y={min_y}, w={w}, h={h}", metrics

    return True, "All finder patterns and aspect ratio verified", metrics


def test_challenge_2_qr_aspect_ratio_and_patterns(gndroid_mod, app):
    log_challenge("2. QR Code Strict 1:1 Aspect Ratio, Finder Pattern Micro-Inspection & QSS")

    # 1. UI Label Aspect Ratio & Stylesheet Verification
    dlg = gndroid_mod.GNDroidWirelessPairingDialog(target_serial="emulator-5554", parent=None)
    dlg.show()
    app.processEvents()

    lbl_qr = dlg.lbl_qr_code
    print(f" -> lbl_qr_code geometry: {lbl_qr.width()}x{lbl_qr.height()}")
    assert lbl_qr.width() == 220, f"Expected width 220, got {lbl_qr.width()}"
    assert lbl_qr.height() == 220, f"Expected height 220, got {lbl_qr.height()}"
    assert lbl_qr.width() == lbl_qr.height(), "lbl_qr_code is not a strict 1:1 square!"
    assert lbl_qr.alignment() == Qt.AlignmentFlag.AlignCenter, "QR label alignment is not centered!"

    # 2. Rendered QPixmap Verification
    # Wait up to 2 seconds for qr_worker to populate pixmap
    timeout = time.time() + 2.0
    while time.time() < timeout:
        app.processEvents()
        if lbl_qr.pixmap() and not lbl_qr.pixmap().isNull():
            break
        time.sleep(0.05)

    pix = lbl_qr.pixmap()
    assert pix is not None and not pix.isNull(), "lbl_qr_code pixmap is null or not rendered!"
    print(f" -> lbl_qr_code rendered pixmap dimensions: {pix.width()}x{pix.height()}")
    assert pix.width() == pix.height(), f"Rendered pixmap is distorted: {pix.width()}x{pix.height()}"
    assert pix.width() == 200, f"Expected 200x200 scaled pixmap, got {pix.width()}x{pix.height()}"

    # 3. Micro-Inspection across diverse adversarial payloads
    test_payloads = [
        ("Default AOSP Payload", "WIFI:T:ADB;S:GNDROiD-TEST;P:654321;;"),
        ("Minimal Short Payload", "WIFI:T:ADB;S:G;P:1;;"),
        ("Ultra-Long Payload (100+ chars)", "WIFI:T:ADB;S:GNDROiD-ENTERPRISE-SCALE-MULTI-CLOUD-ROUTING-GATEWAY-NODE-ALPHA-01;P:998877665544;;"),
        ("Special Characters Payload", "WIFI:T:ADB;S:GNDROiD_Office@5GHz#Mesh-LAN;P:123456;;"),
    ]

    for label, payload in test_payloads:
        raw_png = WirelessPairingEngine.generate_qr_png_bytes(payload, box_size=5, border=2)
        ok, msg, metrics = inspect_qr_finder_patterns(raw_png)
        print(f" -> Testing {label}:")
        print(f"    Image: {metrics.get('img_size')}, Matrix: {metrics.get('matrix_size')}, Ratio: {metrics.get('aspect_ratio', 0):.4f}")
        print(f"    TL Intact: {metrics.get('tl_intact')}, TR Intact: {metrics.get('tr_intact')}, BL Intact: {metrics.get('bl_intact')}")
        print(f"    BR Finder Absent: {metrics.get('br_finder_absent')}")
        assert ok, f"QR finder pattern micro-inspection failed for {label}: {msg}"

    # 4. QSS Audit — Zero Occurrence of Invalid 'margin: 0 auto;'
    print(" -> Scanning dialog and child widget stylesheets for invalid 'margin: 0 auto'...")
    all_widgets = [dlg] + dlg.findChildren(QWidget)
    for w_elem in all_widgets:
        ss = w_elem.styleSheet()
        assert "margin: 0 auto" not in ss, f"Violation: 'margin: 0 auto' found in stylesheet for {w_elem}!"
        assert "margin: 0px auto" not in ss, f"Violation: 'margin: 0px auto' found in stylesheet for {w_elem}!"

    # Also check source files statically
    with open(os.path.join(base_dir, "gndroid.pyw"), "r", encoding="utf-8") as f:
        gndroid_content = f.read()
    assert "margin: 0 auto" not in gndroid_content, "Violation: 'margin: 0 auto;' present in gndroid.pyw!"
    assert "margin: 0px auto" not in gndroid_content, "Violation: 'margin: 0px auto;' present in gndroid.pyw!"

    with open(os.path.join(base_dir, "nexus", "wireless_mirror.py"), "r", encoding="utf-8") as f:
        mirror_content = f.read()
    assert "margin: 0 auto" not in mirror_content, "Violation: 'margin: 0 auto;' present in wireless_mirror.py!"

    print(" -> Confirmed: Zero occurrences of invalid 'margin: 0 auto;' across all QSS and source files.")

    dlg.close()
    if dlg.qr_worker and dlg.qr_worker.isRunning():
        dlg.qr_worker.stop()

    print(" [PASSED] Challenge 2: QR aspect ratio, finder patterns, and QSS audit verified 100%.")


# =============================================================================
# CHALLENGE 3: Button Bounding Boxes, Enabling, Clickability & Signal Verification
# =============================================================================
def test_challenge_3_buttons_geometry_and_clicks(gndroid_mod, app):
    log_challenge("3. Button Bounding Boxes, Enabling, Clickability & Signal Verification")

    dlg = gndroid_mod.GNDroidWirelessPairingDialog(target_serial="emulator-5554", parent=None)
    dlg.show()
    app.processEvents()

    assert hasattr(dlg, "btn_done"), "Attribute 'btn_done' missing on GNDroidWirelessPairingDialog!"
    assert hasattr(dlg, "btn_cancel"), "Attribute 'btn_cancel' missing on GNDroidWirelessPairingDialog!"

    btn_done = dlg.btn_done
    btn_cancel = dlg.btn_cancel

    # 1. State & Styling Checks
    assert btn_done.isVisible(), "btn_done is not visible!"
    assert btn_cancel.isVisible(), "btn_cancel is not visible!"
    assert btn_done.isEnabled(), "btn_done is disabled!"
    assert btn_cancel.isEnabled(), "btn_cancel is disabled!"
    assert btn_done.cursor().shape() == Qt.CursorShape.PointingHandCursor, "btn_done cursor not pointing hand!"
    assert btn_cancel.cursor().shape() == Qt.CursorShape.PointingHandCursor, "btn_cancel cursor not pointing hand!"
    assert btn_done.minimumHeight() >= 38, f"btn_done minimumHeight ({btn_done.minimumHeight()}) < 38"
    assert btn_cancel.minimumHeight() >= 38, f"btn_cancel minimumHeight ({btn_cancel.minimumHeight()}) < 38"

    # 2. Geometric Containment Checks
    dlg_rect = dlg.rect()
    done_geo = btn_done.geometry()
    cancel_geo = btn_cancel.geometry()
    tabs_geo = dlg.tabs.geometry()

    print(f" -> Dialog Rect:       {dlg_rect}")
    print(f" -> btn_done Rect:     {done_geo}")
    print(f" -> btn_cancel Rect:   {cancel_geo}")
    print(f" -> tabs Rect:         {tabs_geo}")

    assert dlg_rect.contains(done_geo), f"btn_done {done_geo} is outside dialog rect {dlg_rect}!"
    assert dlg_rect.contains(cancel_geo), f"btn_cancel {cancel_geo} is outside dialog rect {dlg_rect}!"
    assert not done_geo.intersects(cancel_geo), "btn_done and btn_cancel intersect each other!"
    assert not tabs_geo.intersects(done_geo), "tabs and btn_done intersect!"
    assert not tabs_geo.intersects(cancel_geo), "tabs and btn_cancel intersect!"

    # 3. Simulated Click Action Verification (btn_done -> accept)
    print(" -> Testing btn_done click -> accept() invocation...")
    accepted_signals = []
    dlg.accepted.connect(lambda: accepted_signals.append(True))
    btn_done.click()
    app.processEvents()

    assert len(accepted_signals) == 1, "Clicking btn_done did not emit accepted signal!"
    assert dlg.result() == QDialog.DialogCode.Accepted, f"Expected result Accepted, got {dlg.result()}"
    print(" -> Confirmed: btn_done click properly accepted dialog.")

    # 4. Simulated Click Action Verification (btn_cancel -> reject)
    print(" -> Testing btn_cancel click -> reject() invocation...")
    dlg2 = gndroid_mod.GNDroidWirelessPairingDialog(target_serial="emulator-5554", parent=None)
    dlg2.show()
    app.processEvents()

    rejected_signals = []
    dlg2.rejected.connect(lambda: rejected_signals.append(True))
    dlg2.btn_cancel.click()
    app.processEvents()

    assert len(rejected_signals) == 1, "Clicking btn_cancel did not emit rejected signal!"
    assert dlg2.result() == QDialog.DialogCode.Rejected, f"Expected result Rejected, got {dlg2.result()}"
    print(" -> Confirmed: btn_cancel click properly rejected dialog.")

    # Clean up
    if dlg.qr_worker and dlg.qr_worker.isRunning():
        dlg.qr_worker.stop()
    if dlg2.qr_worker and dlg2.qr_worker.isRunning():
        dlg2.qr_worker.stop()

    print(" [PASSED] Challenge 3: Button bounding boxes, enabling, clickability and signals verified 100%.")


# =============================================================================
# CHALLENGE 4: Tab Switching Robustness & Anti-Squishing Under Rapid Cycling
# =============================================================================
def test_challenge_4_tab_switching_anti_squish(gndroid_mod, app):
    log_challenge("4. Tab Switching Robustness & Anti-Squishing Under Rapid Cycling")

    dlg = gndroid_mod.GNDroidWirelessPairingDialog(target_serial="emulator-5554", parent=None)
    dlg.show()
    app.processEvents()

    assert dlg.tabs.count() == 2, f"Expected 2 tabs, got {dlg.tabs.count()}"

    # Verify Tab 1 Baseline
    assert dlg.tabs.currentIndex() == 0, "Default tab should be Tab 0 (QR Pairing)!"
    assert dlg.tab_qr.isVisible(), "Tab 1 (tab_qr) should be visible by default!"
    initial_qr_w = dlg.lbl_qr_code.width()
    initial_qr_h = dlg.lbl_qr_code.height()
    print(f" -> Baseline Tab 1 QR label size: {initial_qr_w}x{initial_qr_h}")
    assert initial_qr_w == 220 and initial_qr_h == 220, "QR label baseline distorted!"

    # Switch to Tab 2 and Verify Controls
    dlg.tabs.setCurrentIndex(1)
    app.processEvents()
    assert dlg.tab_tcp.isVisible(), "Tab 2 (tab_tcp) should be visible after switch!"
    assert not dlg.tab_qr.isVisible(), "Tab 1 (tab_qr) should be hidden after switch!"

    assert dlg.combo_tcp_devices.height() >= 30, "combo_tcp_devices squished!"
    assert dlg.txt_tcp_ip.height() >= 30, "txt_tcp_ip squished!"
    assert dlg.btn_switch_tcp.height() >= 38, "btn_switch_tcp squished!"
    assert dlg.txt_tcp_log.height() >= 100, "txt_tcp_log squished!"
    assert dlg.chk_watchdog.isChecked() is True, "chk_watchdog should be checked by default!"
    print(" -> Tab 2 controls verified with valid positive geometries.")

    # 100-Cycle Rapid Alternation Stress Test
    print(" -> Executing 100 rapid tab switching cycles to stress layout recalculation engine...")
    for i in range(100):
        target_idx = (i + 1) % 2
        dlg.tabs.setCurrentIndex(target_idx)
        app.processEvents()

    # Final Switch Back to Tab 0
    dlg.tabs.setCurrentIndex(0)
    app.processEvents()

    final_qr_w = dlg.lbl_qr_code.width()
    final_qr_h = dlg.lbl_qr_code.height()
    print(f" -> Post-stress Tab 1 QR label size: {final_qr_w}x{final_qr_h}")
    assert final_qr_w == initial_qr_w, f"QR label width shifted from {initial_qr_w} to {final_qr_w}!"
    assert final_qr_h == initial_qr_h, f"QR label height shifted from {initial_qr_h} to {final_qr_h}!"
    assert final_qr_w == final_qr_h, "QR label aspect ratio distorted after tab cycling!"

    done_geo = dlg.btn_done.geometry()
    cancel_geo = dlg.btn_cancel.geometry()
    dlg_rect = dlg.rect()
    assert dlg_rect.contains(done_geo), "btn_done escaped dialog rect after cycling!"
    assert dlg_rect.contains(cancel_geo), "btn_cancel escaped dialog rect after cycling!"

    dlg.close()
    if dlg.qr_worker and dlg.qr_worker.isRunning():
        dlg.qr_worker.stop()

    print(" [PASSED] Challenge 4: Tab switching robustness and anti-squishing verified 100%.")


# =============================================================================
# CHALLENGE 5: Ribbon Button Integration in Main Window & Companion Sidebar
# =============================================================================
def test_challenge_5_ribbon_integration(gndroid_mod, app):
    log_challenge("5. Ribbon Button Integration in Main Window & Companion Sidebar")

    # 1. Inspect GNDroidApp (Main Window)
    print(" -> Verifying GNDroidApp main window ribbon button...")
    assert hasattr(gndroid_mod, "GNDroidApp"), "GNDroidApp class not found in gndroid.pyw!"

    # Create dummy instance of GNDroidApp (with background scanner mocked to avoid thread leaks)
    orig_scanner_start = gndroid_mod.DeviceScannerWorker.start
    gndroid_mod.DeviceScannerWorker.start = lambda self: None

    main_win = None
    try:
        main_win = gndroid_mod.GNDroidApp()
        assert hasattr(main_win, "btn_wireless_pairing"), "btn_wireless_pairing missing from GNDroidApp!"
        btn_wp = main_win.btn_wireless_pairing

        assert isinstance(btn_wp, QPushButton), "btn_wireless_pairing is not a QPushButton!"
        assert "Wireless Debugging" in btn_wp.text(), f"Unexpected button text: {btn_wp.text()}"
        assert btn_wp.objectName() == "btnWirelessPairing", f"Unexpected objectName: {btn_wp.objectName()}"
        assert "SPAKE2" in btn_wp.toolTip(), f"Expected SPAKE2 in tooltip: {btn_wp.toolTip()}"
        print(f" -> Found btn_wireless_pairing: text='{btn_wp.text()}', tooltip='{btn_wp.toolTip()}'")

        # Test open_wireless_pairing_dialog invocation with mocked exec
        exec_called = []
        orig_dlg_exec = gndroid_mod.GNDroidWirelessPairingDialog.exec

        def mock_exec(dlg_self):
            exec_called.append(dlg_self)
            dlg_self.show()
            app.processEvents()
            dlg_self.close()
            if dlg_self.qr_worker and dlg_self.qr_worker.isRunning():
                dlg_self.qr_worker.stop()
            return QDialog.DialogCode.Accepted

        gndroid_mod.GNDroidWirelessPairingDialog.exec = mock_exec
        try:
            main_win.open_wireless_pairing_dialog()
            assert len(exec_called) == 1, "open_wireless_pairing_dialog did not execute dialog!"
            opened_dlg = exec_called[0]
            assert isinstance(opened_dlg, gndroid_mod.GNDroidWirelessPairingDialog)
            print(" -> Confirmed: GNDroidApp.open_wireless_pairing_dialog() opened dialog cleanly.")
        finally:
            gndroid_mod.GNDroidWirelessPairingDialog.exec = orig_dlg_exec

    finally:
        gndroid_mod.DeviceScannerWorker.start = orig_scanner_start
        if main_win:
            main_win.close()

    # 2. Inspect GNDroidCompanionSidebar
    print("\n -> Verifying GNDroidCompanionSidebar ribbon button...")
    assert hasattr(gndroid_mod, "GNDroidCompanionSidebar"), "GNDroidCompanionSidebar missing in gndroid.pyw!"

    sidebar = gndroid_mod.GNDroidCompanionSidebar(target_serial="emulator-5554", parent=None)
    try:
        # Search for ribbon button with icon_type "wireless"
        ribbon_buttons = sidebar.findChildren(gndroid_mod.GNDroidRibbonButton)
        wireless_btns = [b for b in ribbon_buttons if getattr(b, "icon_type", "") == "wireless"]
        assert len(wireless_btns) >= 1, "No GNDroidRibbonButton with icon_type='wireless' found in sidebar!"

        w_btn = wireless_btns[0]
        print(f" -> Found sidebar wireless ribbon button: tooltip='{w_btn.toolTip()}', shortcut='{w_btn.shortcut_hint}'")
        assert "Wireless Debugging" in w_btn.toolTip(), f"Unexpected tooltip: {w_btn.toolTip()}"
        assert w_btn.shortcut_hint == "Alt+W", f"Expected shortcut Alt+W, got {w_btn.shortcut_hint}"

        # Test action_wireless_pairing invocation with mocked exec
        sidebar_exec_called = []
        orig_dlg_exec = gndroid_mod.GNDroidWirelessPairingDialog.exec

        def mock_sidebar_exec(dlg_self):
            sidebar_exec_called.append(dlg_self)
            assert dlg_self.target_serial == "emulator-5554", f"Expected serial emulator-5554, got {dlg_self.target_serial}"
            dlg_self.show()
            app.processEvents()
            dlg_self.close()
            if dlg_self.qr_worker and dlg_self.qr_worker.isRunning():
                dlg_self.qr_worker.stop()
            return QDialog.DialogCode.Accepted

        gndroid_mod.GNDroidWirelessPairingDialog.exec = mock_sidebar_exec
        try:
            sidebar.action_wireless_pairing()
            assert len(sidebar_exec_called) == 1, "action_wireless_pairing did not execute dialog!"
            print(" -> Confirmed: GNDroidCompanionSidebar.action_wireless_pairing() opened dialog cleanly with target serial.")
        finally:
            gndroid_mod.GNDroidWirelessPairingDialog.exec = orig_dlg_exec

    finally:
        sidebar.close()

    print(" [PASSED] Challenge 5: Ribbon button integrations verified 100%.")


# =============================================================================
# MAIN RUNNER
# =============================================================================
def main():
    print("=" * 78)
    print("📡 EMPIRICAL ADVERSARIAL CHALLENGER (m4_2): UI & Aspect Ratio Stress Suite")
    print("=" * 78)

    app = QApplication.instance() or QApplication(sys.argv)
    gndroid_mod = load_gndroid_module()

    start_time = time.time()
    try:
        test_challenge_1_screen_dimensions_and_bounding_boxes(gndroid_mod, app)
        test_challenge_2_qr_aspect_ratio_and_patterns(gndroid_mod, app)
        test_challenge_3_buttons_geometry_and_clicks(gndroid_mod, app)
        test_challenge_4_tab_switching_anti_squish(gndroid_mod, app)
        test_challenge_5_ribbon_integration(gndroid_mod, app)

        elapsed = time.time() - start_time
        print("\n" + "=" * 78)
        print(f"🏆 ALL 5 ADVERSARIAL CHALLENGE SUITES PASSED EMPIRICALLY ({elapsed:.2f}s) — EXIT 0")
        print("=" * 78)
        sys.exit(0)

    except AssertionError as ae:
        print(f"\n❌ EMPIRICAL REJECTION — ASSERTION ERROR: {ae}", file=sys.stderr)
        sys.exit(1)
    except Exception as ex:
        import traceback
        traceback.print_exc()
        print(f"\n❌ EMPIRICAL REJECTION — UNEXPECTED EXCEPTION: {ex}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
