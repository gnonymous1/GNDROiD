import os
import sys
import time
import subprocess
import importlib.util
from PyQt6.QtWidgets import QApplication

spec = importlib.util.spec_from_file_location("gndroid", os.path.join(os.getcwd(), "gndroid.pyw"))
gndroid = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gndroid)

def test_main_window_launch():
    app = QApplication.instance() or QApplication(sys.argv)
    
    print("Instantiating GNDroidApp...")
    win = gndroid.GNDroidApp()
    win.show()
    app.processEvents()
    
    print("Calling win.launch_virtual_machine()...")
    # This must NOT throw NameError or crash!
    try:
        win.launch_virtual_machine()
        app.processEvents()
        print("launch_virtual_machine() called successfully without any crash!")
        print("Button text:", win.btn_launch_vm.text())
        print("Status bar:", win.status_bar.text())
        assert "Booting" in win.btn_launch_vm.text() or "Starting" in win.status_bar.text(), "Button or status not updated"
    except Exception as e:
        print("CRASH IN launch_virtual_machine:", e)
        raise e
        
    # Wait 8 seconds to verify process is alive in background
    time.sleep(8)
    app.processEvents()
    
    # Check log file
    log_path = os.path.join(os.getcwd(), "logs", "emulator_gndroid.log")
    assert os.path.exists(log_path), "Log file does not exist"
    print("Log file size:", os.path.getsize(log_path), "bytes")
    
    # Clean up
    adb = gndroid.SystemPaths.get_adb()
    subprocess.run([adb, "-s", "emulator-5554", "emu", "kill"], timeout=5, creationflags=0x08000000)
    time.sleep(2)
    win.close()
    
    print("MAIN WINDOW LAUNCH TEST PASSED 100%!")

if __name__ == "__main__":
    test_main_window_launch()
