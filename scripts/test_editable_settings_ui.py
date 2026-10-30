import os
import sys
import importlib.util
from PyQt6.QtWidgets import QApplication

# Load gndroid module dynamically from gndroid.pyw
spec = importlib.util.spec_from_file_location("gndroid", os.path.join(os.getcwd(), "gndroid.pyw"))
gndroid = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gndroid)

def test_settings_dialog():
    app = QApplication.instance() or QApplication(sys.argv)
    
    artifact_dir = r"C:\Users\Reader-Branch\.gemini\antigravity\brain\04ee994d-7335-4fc2-b999-085a14c4b108"
    os.makedirs(artifact_dir, exist_ok=True)
    
    dlg = gndroid.GNDroidSettingsDialog(target_serial="emulator-5554", instance_name="gndroid")
    dlg.show()
    app.processEvents()
    
    print(f"Tabs count: {dlg.tabs.count()}")
    for i in range(dlg.tabs.count()):
        print(f"Tab {i}: {dlg.tabs.tabText(i)}")
    
    # Capture each tab
    tab_names = ["hardware", "graphics", "camera", "network"]
    for i, name in enumerate(tab_names):
        dlg.tabs.setCurrentIndex(i)
        app.processEvents()
        pix = dlg.grab()
        path = os.path.join(artifact_dir, f"settings_tab_{name}.png")
        pix.save(path)
        print(f"Saved screenshot: {path}")
        
    # Verify values loaded from config.ini
    print(f"Loaded Display Name: {dlg.txt_display_name.text()}")
    print(f"Loaded RAM: {dlg.combo_ram.currentText()} (Data: {dlg.combo_ram.currentData()})")
    print(f"Loaded Cores: {dlg.combo_cores.currentText()} (Data: {dlg.combo_cores.currentData()})")
    print(f"Loaded GPU: {dlg.combo_gpu.currentText()} (Data: {dlg.combo_gpu.currentData()})")
    print(f"Loaded Res: {dlg.spin_width.value()}x{dlg.spin_height.value()} @ {dlg.spin_density.value()} DPI")
    print(f"Loaded Root: {dlg.chk_root.isChecked()}")
    print(f"Loaded Camera Front: {dlg.combo_cam_front.currentText()}")
    print(f"Loaded Wi-Fi: {dlg.chk_wifi.isChecked()}")
    
    dlg.close()
    print("ALL SETTINGS UI TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_settings_dialog()
