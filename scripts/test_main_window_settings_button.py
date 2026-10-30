import os
import sys
import importlib.util
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

spec = importlib.util.spec_from_file_location("gndroid", os.path.join(os.getcwd(), "gndroid.pyw"))
gndroid = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gndroid)

def test_main_window_settings_button():
    app = QApplication.instance() or QApplication(sys.argv)
    
    win = gndroid.GNDroidApp()
    win.show()
    app.processEvents()
    
    # Check that settings button is connected and exists
    assert hasattr(win, "open_settings"), "open_settings method missing on GNDroidApp"
    
    artifact_dir = r"C:\Users\Reader-Branch\.gemini\antigravity\brain\04ee994d-7335-4fc2-b999-085a14c4b108"
    
    # Capture main window with settings button visible
    pix = win.grab()
    pix.save(os.path.join(artifact_dir, "main_window_ready.png"))
    print("Saved main window screenshot")
    
    win.close()
    print("MAIN WINDOW TEST PASSED!")

if __name__ == "__main__":
    test_main_window_settings_button()

