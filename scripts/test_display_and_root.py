import os
import sys
import importlib.util

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

spec = importlib.util.spec_from_file_location('gndroid', 'gndroid.pyw')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

mod.AVDManager.reset_instance_display('gndroid', 1440, 3120, 500)
insts = mod.AVDManager.list_instances()
print(f"Total instances: {len(insts)}")
for i in insts:
    print(f"Instance: {i['name']} | Resolution: {i['width']}x{i['height']} @ {i['density']} DPI | Root: {i['root']}")

root_check = mod.AVDManager.check_live_root()
print(f"Live Root Check: {root_check}")
