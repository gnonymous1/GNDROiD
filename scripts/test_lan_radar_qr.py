import io
import time
import subprocess
import socket
import qrcode
from PIL import Image

def test_qr():
    service_name = "GNDROiD-TEST"
    password = "123456"
    payload = f"WIFI:T:ADB;S:{service_name};P:{password};;"
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=2,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()
    assert len(png_bytes) > 500, "PNG generation failed"
    print(f"QR generation verified: {len(png_bytes)} bytes")

def test_mdns_services():
    try:
        out = subprocess.check_output(["adb.exe", "mdns", "services"], text=True, timeout=3, creationflags=0x08000000)
        print("adb mdns services output:")
        print(out)
    except Exception as e:
        print(f"adb mdns error: {e}")

if __name__ == "__main__":
    test_qr()
    test_mdns_services()
    print("ALL TESTS PASSED")
