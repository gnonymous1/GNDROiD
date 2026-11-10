"""
scripts/sync_all_locations.py
=============================
Synchronizes updated GNDROiD core files and nexus engines to:
1. dist/gndroid/
2. C:\\Users\\Reader-Branch\\AppData\\Local\\Programs\\GNDROiD\\
"""

import os
import shutil

src_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
appdata_root = r"C:\Users\Reader-Branch\AppData\Local\Programs\GNDROiD"
dist_root = os.path.join(src_root, "dist", "gndroid")

targets = [dist_root, appdata_root]

files_to_copy = [
    ("gndroid.pyw", "gndroid.pyw"),
    (os.path.join("nexus", "network_bridge.py"), os.path.join("nexus", "network_bridge.py")),
    (os.path.join("nexus", "display_and_vpn.py"), os.path.join("nexus", "display_and_vpn.py")),
    (os.path.join("nexus", "GNDROiD_Companion.apk"), os.path.join("nexus", "GNDROiD_Companion.apk")),
    (os.path.join("nexus", "gndroid_companion_client.py"), os.path.join("nexus", "gndroid_companion_client.py")),
    (os.path.join("nexus", "wireless_mirror.py"), os.path.join("nexus", "wireless_mirror.py")),
]

for target in targets:
    if not os.path.exists(target):
        print(f"Target directory {target} does not exist, skipping.")
        continue
    print(f"\n--- Syncing to {target} ---")
    for rel_src, rel_dst in files_to_copy:
        s = os.path.join(src_root, rel_src)
        d = os.path.join(target, rel_dst)
        os.makedirs(os.path.dirname(d), exist_ok=True)
        if os.path.exists(s):
            shutil.copy2(s, d)
            sz = os.path.getsize(d)
            print(f"Copied {rel_src} -> {rel_dst} ({sz} bytes)")
        else:
            print(f"Source file {s} not found!")

print("\nAll target locations synchronized successfully!")
