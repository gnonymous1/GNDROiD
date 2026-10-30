import os
import sys
import importlib.util
from PyQt6.QtWidgets import QApplication

spec = importlib.util.spec_from_file_location("gndroid", os.path.join(os.getcwd(), "gndroid.pyw"))
gndroid = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gndroid)

def test_settings_save():
    app = QApplication.instance() or QApplication(sys.argv)
    
    dlg = gndroid.GNDroidSettingsDialog(target_serial="emulator-5554", instance_name="gndroid")
    
    # Check original
    orig_cfg = gndroid.AVDManager.get_instance_full_config("gndroid")
    print("Original RAM:", orig_cfg.get("hw.ramSize"))
    print("Original Cores:", orig_cfg.get("hw.cpu.ncore"))
    print("Original Display Name:", orig_cfg.get("avd.ini.displayname"))
    
    # Modify values in UI
    dlg.txt_display_name.setText("GNDROiD Flagship Ultra")
    # Change RAM to 8192 MB (index 2)
    dlg.combo_ram.setCurrentIndex(2) # 8 GB
    # Change Cores to 8 (index 3)
    dlg.combo_cores.setCurrentIndex(3) # 8 Cores
    # Change GPU to Host
    dlg.combo_gpu.setCurrentIndex(1) # host
    # Change Resolution preset to Flagship Smartphone FHD+ (1080x2400)
    dlg.combo_res_preset.setCurrentIndex(1)
    
    # Save directly via AVDManager to test backend writing
    w = dlg.spin_width.value()
    h = dlg.spin_height.value()
    d = dlg.spin_density.value()
    ram = dlg.combo_ram.currentData()
    cores = dlg.combo_cores.currentData()
    gpu = dlg.combo_gpu.currentData()
    disp_name = dlg.txt_display_name.text()
    
    print(f"Modifying to: Name='{disp_name}', RAM={ram}, Cores={cores}, GPU={gpu}, Res={w}x{h}@{d}")
    
    cfg_update = {
        "avd.ini.displayname": disp_name,
        "hw.ramSize": str(ram),
        "hw.cpu.ncore": str(cores),
        "hw.gpu.mode": str(gpu),
        "hw.lcd.width": str(w),
        "hw.lcd.height": str(h),
        "hw.lcd.density": str(d)
    }
    
    assert gndroid.AVDManager.save_full_instance_config("gndroid", cfg_update), "Save failed!"
    
    # Verify by re-reading config.ini
    new_cfg = gndroid.AVDManager.get_instance_full_config("gndroid")
    print("Updated RAM:", new_cfg.get("hw.ramSize"))
    print("Updated Cores:", new_cfg.get("hw.cpu.ncore"))
    print("Updated GPU:", new_cfg.get("hw.gpu.mode"))
    print("Updated Display Name:", new_cfg.get("avd.ini.displayname"))
    print("Updated Resolution:", f"{new_cfg.get('hw.lcd.width')}x{new_cfg.get('hw.lcd.height')}@{new_cfg.get('hw.lcd.density')}")
    
    assert new_cfg.get("hw.ramSize") == "8192", "RAM size was not saved correctly"
    assert new_cfg.get("hw.cpu.ncore") == "8", "CPU cores was not saved correctly"
    assert new_cfg.get("hw.gpu.mode") == "host", "GPU mode was not saved correctly"
    assert new_cfg.get("avd.ini.displayname") == "GNDROiD Flagship Ultra", "Display name was not saved correctly"
    assert new_cfg.get("hw.lcd.width") == "1080", "Width was not saved correctly"
    assert new_cfg.get("hw.lcd.height") == "2400", "Height was not saved correctly"
    
    # Restore original flagship config (4096 RAM, 4 Cores, 1440x3120, auto GPU, GNDROiD Flagship)
    restore_cfg = {
        "avd.ini.displayname": "GNDROiD Flagship",
        "hw.ramSize": "4096",
        "hw.cpu.ncore": "4",
        "hw.gpu.mode": "auto",
        "hw.lcd.width": "1440",
        "hw.lcd.height": "3120",
        "hw.lcd.density": "500"
    }
    gndroid.AVDManager.save_full_instance_config("gndroid", restore_cfg)
    print("Restored original flagship config cleanly.")
    
    dlg.close()
    print("SAVE TEST PASSED 100%!")

if __name__ == "__main__":
    test_settings_save()

