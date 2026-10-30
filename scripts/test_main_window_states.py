import os
import sys
import time
from PyQt6.QtWidgets import QApplication

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gndroid

app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)

artifact_dir = r"C:\Users\Reader-Branch\.gemini\antigravity\brain\04ee994d-7335-4fc2-b999-085a14c4b108"
os.makedirs(artifact_dir, exist_ok=True)

w = gndroid.GNDroidApp()
w.show()
app.processEvents()
time.sleep(0.3)
app.processEvents()

# 1. Capture Stopped State
pix_stopped = w.grab()
pix_stopped.save(os.path.join(artifact_dir, "main_window_stopped_state.png"))
print("Saved main_window_stopped_state.png")
print("Stopped primary button:", w.btn_launch_vm.text())
print("Stopped secondary button:", w.btn_mirror_usb.text())

# 2. Simulate Running State
w.dev_combo.setItemData(0, {
    "type": "vm", "name": "gndroid", "running": True,
    "serial": "emulator-5554", "api": 34, "inst": None
})
w.dev_combo.setItemText(0, "🟢 [A34] GNDROiD Flagship (Running • Normal Android VM • Port 5554)")
w.on_device_selection_changed(0)
app.processEvents()
time.sleep(0.3)
app.processEvents()

pix_running = w.grab()
pix_running.save(os.path.join(artifact_dir, "main_window_running_state.png"))
print("Saved main_window_running_state.png")
print("Running primary button:", w.btn_launch_vm.text())
print("Running secondary button:", w.btn_mirror_usb.text())

w.close()
print("All states successfully tested and captured!")
