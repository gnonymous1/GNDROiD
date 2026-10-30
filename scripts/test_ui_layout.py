import os
import sys
import importlib.util

sys.stdout.reconfigure(encoding='utf-8')
from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)
spec = importlib.util.spec_from_file_location('gndroid', 'gndroid.pyw')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

mgr = mod.GNDroidMultiInstanceManager()
col_w = mgr.table.columnWidth(5)
print(f"Table Column 5 Width: {col_w}")
assert col_w >= 300, f"Expected Column 5 >= 300, got {col_w}"
print("✓ Multi-Instance Manager layout validated!")

# Check main app
main_win = mod.GNDroidApp()
print(f"Main App Window Title: {main_win.windowTitle()}")
assert "GNDROiD" in main_win.windowTitle()
print("✓ Main App branding validated!")
os._exit(0)
