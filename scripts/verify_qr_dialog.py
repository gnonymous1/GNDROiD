#!/usr/bin/env python3
"""
scripts/verify_qr_dialog.py
===========================
Automated verification suite for Requirement R4:
1. Screen-fitted QR code dialog sizing (minimum 440x490, dynamic sizing).
2. Elimination of invalid QSS 'margin: 0 auto;' on QR label.
3. Undistorted 1:1 square QR code aspect ratio with intact finder patterns.
4. "✓ Done" button complete visibility, styling, and operability without clipping.
"""

import os
import sys
import io
import re
import qrcode
from PIL import Image

# Force offscreen Qt rendering for automated / headless environments
os.environ["QT_QPA_PLATFORM"] = "offscreen"

# Ensure UTF-8 stdout on Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from PyQt6.QtWidgets import QApplication, QDialog, QLabel, QPushButton, QLineEdit
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QPixmap

def verify_code_integrity():
    print("\n[CHECK 1] Static Code Integrity Check in gndroid.pyw...")
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    gndroid_path = os.path.join(base_dir, "gndroid.pyw")
    assert os.path.exists(gndroid_path), f"gndroid.pyw not found at {gndroid_path}"

    with open(gndroid_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Ensure 'margin: 0 auto' is completely removed
    assert "margin: 0 auto" not in content, "VIOLATION: 'margin: 0 auto;' still present in gndroid.pyw!"
    print(" -> Confirmed: 'margin: 0 auto;' is completely eliminated from QSS.")

    # 2. Ensure hardcoded setFixedSize(420, 430) is replaced with setMinimumSize(440, 490)
    assert "setFixedSize(420, 430)" not in content, "VIOLATION: Hardcoded 'setFixedSize(420, 430)' still present in gndroid.pyw!"
    assert "setMinimumSize(440, 490)" in content, "VIOLATION: 'setMinimumSize(440, 490)' not found in gndroid.pyw!"
    print(" -> Confirmed: Dynamic minimum sizing 'setMinimumSize(440, 490)' implemented.")

    # 3. Ensure Done button minimum height and pointing hand cursor
    assert "btn_c.setMinimumHeight(38)" in content, "VIOLATION: 'btn_c.setMinimumHeight(38)' not found!"
    assert "btn_c.setCursor(Qt.CursorShape.PointingHandCursor)" in content, "VIOLATION: Done button cursor not set!"
    print(" -> Confirmed: Done button has proper minimum height and pointing hand cursor.")

    print(" [PASSED] Check 1: Static code integrity verified successfully.")


def verify_dialog_runtime_rendering():
    print("\n[CHECK 2] Runtime Rendering & Geometry Verification...")
    app = QApplication.instance() or QApplication(sys.argv)

    # Import gndroid dynamically
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, base_dir)
    import importlib.util
    spec = importlib.util.spec_from_file_location("gndroid", os.path.join(base_dir, "gndroid.pyw"))
    gndroid_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gndroid_mod)

    # Capture dialog instance during action_show_mobile_download_qr
    captured_dialogs = []
    orig_exec = QDialog.exec

    def mock_exec(dlg_self):
        captured_dialogs.append(dlg_self)
        dlg_self.show()
        app.processEvents()
        return QDialog.DialogCode.Accepted

    QDialog.exec = mock_exec

    # Create dummy parent widget
    from PyQt6.QtWidgets import QWidget
    dummy_parent = QWidget()

    # Mock NexusCompanionManager to return valid URL
    orig_start = gndroid_mod.NexusCompanionManager.start_download_server
    test_url = "http://192.168.1.105:8088/NexusAI_Mobile_Client.apk"
    gndroid_mod.NexusCompanionManager.start_download_server = staticmethod(lambda: test_url)

    try:
        # Call action_show_mobile_download_qr on GNDroidADBFixerDialog
        gndroid_mod.GNDroidADBFixerDialog.action_show_mobile_download_qr(dummy_parent)
    finally:
        QDialog.exec = orig_exec
        gndroid_mod.NexusCompanionManager.start_download_server = orig_start

    assert len(captured_dialogs) == 1, "Expected exactly 1 captured dialog from action_show_mobile_download_qr"
    dlg = captured_dialogs[0]

    # Inspect dialog dimensions
    w, h = dlg.width(), dlg.height()
    min_w, min_h = dlg.minimumWidth(), dlg.minimumHeight()
    print(f" -> Dialog dimensions: width={w}, height={h} (minimum={min_w}x{min_h})")
    assert min_w >= 440, f"Expected minimum width >= 440, got {min_w}"
    assert min_h >= 490, f"Expected minimum height >= 490, got {min_h}"
    assert w >= 440, f"Expected dialog width >= 440, got {w}"
    assert h >= 490, f"Expected dialog height >= 490, got {h}"

    # Find widgets
    lbl_qr = None
    btn_done = None
    url_box = None

    for child in dlg.findChildren(QLabel):
        if child.pixmap() and not child.pixmap().isNull():
            lbl_qr = child
            break

    for child in dlg.findChildren(QPushButton):
        if "Done" in child.text():
            btn_done = child
            break

    for child in dlg.findChildren(QLineEdit):
        if child.text() == test_url:
            url_box = child
            break

    assert lbl_qr is not None, "QR code QLabel not found in dialog!"
    assert btn_done is not None, "'✓ Done' QPushButton not found in dialog!"
    assert url_box is not None, "URL QLineEdit not found in dialog!"

    # 1. Verify QR Label Stylesheet & Sizing
    qr_style = lbl_qr.styleSheet()
    print(f" -> QR Label stylesheet: {qr_style}")
    assert "margin: 0 auto" not in qr_style, "QR label stylesheet contains invalid 'margin: 0 auto'!"
    assert lbl_qr.width() == 220, f"Expected QR label width 220, got {lbl_qr.width()}"
    assert lbl_qr.height() == 220, f"Expected QR label height 220, got {lbl_qr.height()}"

    # 2. Verify QR Pixmap 1:1 Aspect Ratio
    pix = lbl_qr.pixmap()
    print(f" -> QR Pixmap dimensions: {pix.width()}x{pix.height()}")
    assert pix.width() == pix.height(), f"QR pixmap is not 1:1 square: {pix.width()}x{pix.height()}"
    assert pix.width() >= 190, f"QR pixmap too small: {pix.width()}"

    # 3. Verify Done Button Visibility & Geometry
    btn_geo = btn_done.geometry()
    dlg_rect = dlg.rect()
    print(f" -> Done button geometry: {btn_geo}, Dialog rect: {dlg_rect}")
    assert dlg_rect.contains(btn_geo), f"Done button {btn_geo} is clipped outside dialog rect {dlg_rect}!"
    assert btn_geo.bottom() < dlg_rect.bottom(), f"Done button bottom ({btn_geo.bottom()}) clipped below dialog ({dlg_rect.bottom()})!"
    assert btn_done.height() >= 36, f"Done button height too small: {btn_done.height()}"
    assert btn_done.isVisible(), "Done button is not visible!"

    # 4. Render screenshot and inspect pixel array
    pix_dialog = dlg.grab()
    img_bytes = io.BytesIO()
    # Save to buffer
    img_pil = Image.fromqpixmap(pix_dialog) if hasattr(Image, "fromqpixmap") else None
    if img_pil is None:
        # Convert QPixmap to QImage and PIL Image
        qimg = pix_dialog.toImage()
        buffer = qimg.bits().asstring(qimg.sizeInBytes())
        img_pil = Image.frombuffer("RGBA", (qimg.width(), qimg.height()), buffer, "raw", "BGRA", 0, 1)

    artifacts_dir = os.path.join(base_dir, "artifacts")
    os.makedirs(artifacts_dir, exist_ok=True)
    out_png = os.path.join(artifacts_dir, "qr_dialog_verified.png")
    img_pil.save(out_png)
    print(f" -> Saved rendered dialog to: {out_png}")

    # Inspect QR code bounding box in rendered dialog
    # Map QR label coordinates into dialog image
    lbl_geo = lbl_qr.geometry()
    qr_crop = img_pil.crop((lbl_geo.left(), lbl_geo.top(), lbl_geo.right(), lbl_geo.bottom()))
    qr_crop_path = os.path.join(artifacts_dir, "qr_code_crop.png")
    qr_crop.save(qr_crop_path)

    # Check non-white bounding box
    qr_gray = qr_crop.convert("L")
    w_crop, h_crop = qr_gray.size
    min_x, max_x = w_crop, 0
    min_y, max_y = h_crop, 0

    for y in range(h_crop):
        for x in range(w_crop):
            if qr_gray.getpixel((x, y)) < 128:  # Dark pixel
                if x < min_x: min_x = x
                if x > max_x: max_x = x
                if y < min_y: min_y = y
                if y > max_y: max_y = y

    qr_w = (max_x - min_x + 1)
    qr_h = (max_y - min_y + 1)
    aspect_ratio = qr_w / qr_h
    print(f" -> Measured QR pixel bounding box: {qr_w}x{qr_h} (aspect ratio: {aspect_ratio:.3f})")
    assert 0.96 <= aspect_ratio <= 1.04, f"QR code is distorted! Expected aspect ratio ~1.00, got {aspect_ratio:.3f}"

    # Verify 3 Corner Finder Patterns (Top-Left, Top-Right, Bottom-Left)
    # Check that dark modules exist near the corners of the QR bounding box
    tl_dark = any(qr_gray.getpixel((min_x + dx, min_y + dy)) < 128 for dx in range(15) for dy in range(15))
    tr_dark = any(qr_gray.getpixel((max_x - dx, min_y + dy)) < 128 for dx in range(15) for dy in range(15))
    bl_dark = any(qr_gray.getpixel((min_x + dx, max_y - dy)) < 128 for dx in range(15) for dy in range(15))
    print(f" -> Finder patterns detected: Top-Left={tl_dark}, Top-Right={tr_dark}, Bottom-Left={bl_dark}")
    assert tl_dark and tr_dark and bl_dark, "QR code finder patterns are missing or truncated!"

    dlg.close()
    print(" [PASSED] Check 2: Runtime rendering, 1:1 QR aspect ratio, and button visibility verified.")


def main():
    print("=" * 70)
    print("🔍 VERIFY REQUIREMENT R4: Screen-Fitted QR Code Modal Suite")
    print("=" * 70)

    try:
        verify_code_integrity()
        verify_dialog_runtime_rendering()
        print("\n" + "=" * 70)
        print("✅ ALL QR CODE DIALOG VERIFICATION CHECKS PASSED (EXIT 0)")
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
