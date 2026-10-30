import os
import sys
import time
import importlib.util

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

# Load gndroid module dynamically
spec = importlib.util.spec_from_file_location("gndroid", "gndroid.pyw")
gndroid = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gndroid)

app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)

artifact_dir = r"C:\Users\Reader-Branch\.gemini\antigravity-ide\brain\bb5689a9-975e-46e3-a3e8-1320dea29659"
os.makedirs(artifact_dir, exist_ok=True)

# 1. Test ADB Fixer Dialog & Wireless LAN Tab
dlg = gndroid.GNDroidADBFixerDialog("emulator-5554")
dlg.tabs.setCurrentIndex(1)
dlg.show()
app.processEvents()

# Capture default view
time.sleep(0.5)
app.processEvents()
pix = dlg.grab()
pix.save(os.path.join(artifact_dir, "fixer_dialog_lan_tab.png"))
print("Saved fixer_dialog_lan_tab.png")

# Populate simulated LAN device
dummy_devs = [
    {
        "type": "mdns_connect",
        "model": "Samsung Galaxy S24 Ultra",
        "ip": "192.168.100.45",
        "port": 42153,
        "serial": "192.168.100.45:42153",
        "status": "Ready to Pair / Connect"
    },
    {
        "type": "standard_port",
        "model": "Google Pixel 8 Pro",
        "ip": "192.168.100.82",
        "port": 5555,
        "serial": "192.168.100.82:5555",
        "status": "Online (TCP/IP Port 5555)"
    }
]
dlg.on_radar_updated(dummy_devs)
app.processEvents()
pix_pop = dlg.grab()
pix_pop.save(os.path.join(artifact_dir, "fixer_dialog_lan_tab_populated.png"))
print("Saved fixer_dialog_lan_tab_populated.png")
dlg.close()

# 2. Test Instance Settings Dialog with Live Root & Screen Glitch Fixer
insts = gndroid.AVDManager.list_instances()
inst = insts[0] if insts else {
    "name": "gndroid", "display_name": "GNDROiD Flagship", "api_level": 36,
    "ram_mb": 4096, "cores": 4, "width": 1440, "height": 3120, "density": 500,
    "gpu": "auto", "root": True
}
dlg_settings = gndroid.GNDroidInstanceSettingsDialog(inst)
dlg_settings.show()
app.processEvents()
time.sleep(0.3)
app.processEvents()
pix_settings = dlg_settings.grab()
pix_settings.save(os.path.join(artifact_dir, "instance_settings_dialog_fixed.png"))
print("Saved instance_settings_dialog_fixed.png")
dlg_settings.close()

# 3. Test Multi Instance Manager with Fix Screen Glitch Button
dlg_manager = gndroid.GNDroidMultiInstanceManager()
dlg_manager.show()
app.processEvents()
time.sleep(0.3)
app.processEvents()
pix_manager = dlg_manager.grab()
pix_manager.save(os.path.join(artifact_dir, "multi_instance_manager_fixed.png"))
print("Saved multi_instance_manager_fixed.png")
dlg_manager.close()

print("All UI test captures successfully generated!")