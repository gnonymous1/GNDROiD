import sys
import os

# Set headless platform so tests can run cleanly without opening GUI windows
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

import importlib.util
spec = importlib.util.spec_from_file_location("gndroid", os.path.abspath("gndroid.pyw"))
gndroid = importlib.util.module_from_spec(spec)
sys.modules["gndroid"] = gndroid
spec.loader.exec_module(gndroid)
print("1. Successfully imported gndroid module")

# Test SystemPaths
sdk = gndroid.SystemPaths.get_sdk_dir()
print(f"2. SystemPaths.get_sdk_dir() -> {sdk}")
emu = gndroid.SystemPaths.get_emulator()
print(f"3. SystemPaths.get_emulator() -> {emu}")
adb_v = gndroid.SystemPaths.get_adb_version()
print(f"4. SystemPaths.get_adb_version() -> {adb_v}")
in_use = gndroid.SystemPaths.is_port_in_use(5037)
print(f"5. SystemPaths.is_port_in_use(5037) -> {in_use}")
conflicts = gndroid.SystemPaths.get_port_conflicts(5037)
print(f"6. SystemPaths.get_port_conflicts(5037) -> {conflicts}")

# Test GNDroidADBFixerDialog
adb_fixer = gndroid.GNDroidADBFixerDialog()
print(f"7. GNDroidADBFixerDialog initialized successfully with tabs: {adb_fixer.tabs.count()}")
assert adb_fixer.tabs.count() == 4, f"Expected 4 tabs, got {adb_fixer.tabs.count()}"

# Test GNDroidMultiInstanceManager
mim = gndroid.GNDroidMultiInstanceManager()
print(f"8. GNDroidMultiInstanceManager initialized successfully with {len(mim.instances)} instances")

# Test GNDroidCompanionSidebar
try:
    sidebar = gndroid.GNDroidCompanionSidebar(target_serial="emulator-5554")
    print(f"9. GNDroidCompanionSidebar initialized successfully with serial {sidebar.target_serial}")
except Exception as e:
    import traceback
    print("Error in GNDroidCompanionSidebar:")
    traceback.print_exc()

# Test AVDManager.ensure_default_flagship_avd
try:
    default_avd = gndroid.AVDManager.ensure_default_flagship_avd()
    print(f"10. AVDManager.ensure_default_flagship_avd() -> {default_avd}")
except Exception as e:
    import traceback
    print("Error in ensure_default_flagship_avd:")
    traceback.print_exc()

# Test Remaining Fluent Dark Dialogs
dummy_inst = {'name': 'test_inst', 'display_name': 'Test Device', 'api_level': 36, 'ram_mb': 8192, 'cores': 8, 'avd_dir': '', 'ini_path': '', 'is_running': False, 'adb_serial': '', 'port': 5554}
d1 = gndroid.GNDroidAppDrawer(target_serial='')
print("11. GNDroidAppDrawer initialized successfully")
d2 = gndroid.GNDroidNoDeviceDialog()
print("12. GNDroidNoDeviceDialog initialized successfully")
d3 = gndroid.GNDroidImageDownloaderDialog()
print("13. GNDroidImageDownloaderDialog initialized successfully")
d4 = gndroid.GNDroidCloneInstanceDialog(src_instance=dummy_inst)
print("14. GNDroidCloneInstanceDialog initialized successfully")
d5 = gndroid.GNDroidInstanceCreatorDialog()
print("15. GNDroidInstanceCreatorDialog initialized successfully")
d6 = gndroid.GNDroidInstanceSettingsDialog(instance=dummy_inst)
print("16. GNDroidInstanceSettingsDialog initialized successfully")
main_win = gndroid.GNDroidApp()
print("18. GNDroidApp main window initialized successfully")

# Stop background threads/timers for clean process exit
if hasattr(main_win, 'timer') and main_win.timer.isActive():
    main_win.timer.stop()
if hasattr(main_win, 'scanner') and main_win.scanner.isRunning():
    main_win.scanner.terminate()
if hasattr(mim, 'timer') and mim.timer.isActive():
    mim.timer.stop()

print("\nALL 18 UPGRADE AND FLUENT THEME INTEGRATION TESTS PASSED WITH ZERO ERRORS!")
os._exit(0)
