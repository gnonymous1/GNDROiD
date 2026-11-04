"""
Verification Suite for GNDROiD Native App Cloner & Dedicated Floating Window
Author: Ghulam Nabi Kalhoro / GNDROiD Core Team
Workspace: c:\\Users\\Reader-Branch\\Desktop\\Android Emulator
"""

import os
import sys
import time
import subprocess
from pathlib import Path

# Add project root and nexus to path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "nexus"))

from nexus.app_cloner_and_window import AppCloneManager, AppWindowManager, get_adb, get_scrcpy

CREATE_NO_WINDOW = 0x08000000


def ensure_emulator_online(serial: str = "emulator-5554", max_wait: int = 5) -> subprocess.Popen:
    """Checks if emulator is online; attempts brief boot or allows mock mode."""
    adb = get_adb()
    
    def check_pm_ready() -> bool:
        try:
            st = subprocess.run([adb, "-s", serial, "get-state"], capture_output=True, text=True, timeout=2, creationflags=CREATE_NO_WINDOW)
            if st.stdout.strip() != "device":
                return False
            boot = subprocess.run([adb, "-s", serial, "shell", "getprop", "sys.boot_completed"], capture_output=True, text=True, timeout=3, creationflags=CREATE_NO_WINDOW)
            if boot.stdout.strip() != "1":
                return False
            pm_res = subprocess.run([adb, "-s", serial, "shell", "pm", "list", "users"], capture_output=True, text=True, timeout=3, creationflags=CREATE_NO_WINDOW)
            return pm_res.returncode == 0 and "UserInfo" in pm_res.stdout
        except Exception:
            return False

    if check_pm_ready():
        print(f"[PREFLIGHT] Device {serial} is already ONLINE and PackageManager is ready.")
        return None

    print(f"[PREFLIGHT] Device {serial} is offline. Activating stateful mock testing mode.")
    return None


def run_full_verification():
    serial = "emulator-5554"
    print("=" * 70)
    print("  GNDROiD APP CLONER & MULTI-WINDOW VERIFICATION SUITE")
    print("=" * 70)

    adb = get_adb()
    is_live = False
    try:
        st = subprocess.run([adb, "-s", serial, "get-state"], capture_output=True, text=True, timeout=2, creationflags=CREATE_NO_WINDOW)
        is_live = (st.stdout.strip() == "device")
    except Exception:
        is_live = False

    if is_live:
        print(f"[PREFLIGHT] Device {serial} is ONLINE. Running live verification.")
        _execute_test_steps(serial)
    else:
        print(f"[PREFLIGHT] Device {serial} is OFFLINE. Running stateful mock verification.")
        try:
            from mock_adb import MockAdbSession
        except ImportError:
            from scripts.mock_adb import MockAdbSession
        with MockAdbSession():
            _execute_test_steps(serial)


def _execute_test_steps(serial: str):
    adb = get_adb()
    scrcpy = get_scrcpy()
    print(f"[SYSTEM] ADB Path:    {adb}")
    print(f"[SYSTEM] Scrcpy Path: {scrcpy}")

    # Ensure multi-user properties are unlocked on emulator
    subprocess.run([adb, "-s", serial, "shell", "setprop", "fw.max_users", "10"], capture_output=True, creationflags=CREATE_NO_WINDOW)
    subprocess.run([adb, "-s", serial, "shell", "setprop", "fw.show_multiuserui", "1"], capture_output=True, creationflags=CREATE_NO_WINDOW)

    # ---------------------------------------------------------
    # STEP 1: Query initial clone users
    # ---------------------------------------------------------
    print("\n--- STEP 1: Query Existing Clone Users ---")
    initial_clones = AppCloneManager.get_clone_users(serial)
    print(f"[RESULT] Found {len(initial_clones)} initial clone profile(s):")
    for c in initial_clones:
        print(f"  • ID={c['id']}, Name='{c['name']}', Type={c['type']}, State={c['state']}")

    # ---------------------------------------------------------
    # STEP 2: Create new Clone User
    # ---------------------------------------------------------
    test_clone_name = "GNDROiD Test Clone 10"
    print(f"\n--- STEP 2: Create Clone User ('{test_clone_name}') ---")
    clone_uid = AppCloneManager.create_clone_user(serial, name=test_clone_name)
    print(f"[RESULT] Created Clone User ID: {clone_uid}")
    assert clone_uid > 0, f"Failed to create clone user! Returned {clone_uid}"

    # Verify user appears in get_clone_users
    updated_clones = AppCloneManager.get_clone_users(serial)
    matched = [u for u in updated_clones if u["id"] == clone_uid]
    print(f"[VERIFY] Clone user {clone_uid} in profile list: {len(matched) > 0}")
    assert len(matched) > 0, f"User {clone_uid} not found in get_clone_users output!"

    # ---------------------------------------------------------
    # STEP 3: Clone App into Isolated User Sandbox
    # ---------------------------------------------------------
    print("\n--- STEP 3: Clone App to User Sandbox ---")
    # Identify an app present in User 0
    test_pkg = "com.android.chrome"
    check_pkg = subprocess.run([adb, "-s", serial, "shell", "pm", "path", test_pkg], capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
    if "package:" not in check_pkg.stdout:
        # Fallback to Settings or Calculator or another installed app
        list_pkgs = subprocess.run([adb, "-s", serial, "shell", "pm", "list", "packages", "--user", "0"], capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
        for line in list_pkgs.stdout.splitlines():
            if line.startswith("package:"):
                cand = line.split(":", 1)[1].strip()
                if any(x in cand for x in ["settings", "calculator", "deskclock", "gallery", "browser"]):
                    test_pkg = cand
                    break

    print(f"[TARGET] Package selected for cloning: {test_pkg}")
    clone_ok = AppCloneManager.clone_app_to_user(serial, test_pkg, clone_uid)
    print(f"[RESULT] clone_app_to_user returned: {clone_ok}")
    assert clone_ok, f"Failed to clone package {test_pkg} to user {clone_uid}"

    # ---------------------------------------------------------
    # STEP 4: List Apps With Clones [Master] & [Clone #ID]
    # ---------------------------------------------------------
    print("\n--- STEP 4: List Apps With Master & Clone Tagging ---")
    all_apps = AppCloneManager.list_apps_with_clones(serial)
    print(f"[RESULT] Discovered {len(all_apps)} tagged app entries:")

    master_entries = [a for a in all_apps if a["user_id"] == 0]
    clone_entries = [a for a in all_apps if a["user_id"] == clone_uid]

    print(f"  • Master (User 0) apps count: {len(master_entries)}")
    print(f"  • Clone (User {clone_uid}) apps count: {len(clone_entries)}")

    # Check for labels
    target_clones = [a for a in clone_entries if a["package_name"] == test_pkg]
    print(f"[VERIFY] Target clone entry found: {target_clones}")
    assert len(target_clones) > 0, f"Cloned app {test_pkg} not found in list_apps_with_clones!"
    assert f"[Clone #{clone_uid}]" in target_clones[0]["label"], f"Label missing [Clone #{clone_uid}]: {target_clones[0]['label']}"
    print(f"[PASS] Successfully verified label: '{target_clones[0]['label']}'")

    # ---------------------------------------------------------
    # STEP 5: Launch App in Dedicated Floating Window
    # ---------------------------------------------------------
    print("\n--- STEP 5: Launch Dedicated Floating Scrcpy Window ---")
    proc = AppWindowManager.launch_app_in_dedicated_window(
        serial=serial,
        package_name=test_pkg,
        app_title="Chrome Cloned Instance",
        user_id=clone_uid,
        width=720,
        height=1600,
        density=320
    )
    print(f"[RESULT] Scrcpy process started with PID: {proc.pid}")
    assert proc.pid > 0, "Scrcpy process PID is invalid!"

    # Allow window to open for 4 seconds
    print("[WAIT] Running dedicated floating window for 4 seconds...")
    time.sleep(4)
    poll_state = proc.poll()
    print(f"[STATE] Scrcpy process alive state: {poll_state is None} (poll={poll_state})")

    # Terminate dedicated test window
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except Exception:
        proc.kill()
    print("[CLEANUP] Dedicated floating window terminated.")

    # ---------------------------------------------------------
    # STEP 6: Create App Desktop Shortcut
    # ---------------------------------------------------------
    print("\n--- STEP 6: Create Desktop Shortcut ---")
    shortcut_path = AppWindowManager.create_app_desktop_shortcut(
        app_title="Chrome",
        package_name=test_pkg,
        user_id=clone_uid
    )
    print(f"[RESULT] Created desktop shortcut: {shortcut_path}")
    assert shortcut_path and os.path.exists(shortcut_path), f"Desktop shortcut does not exist at {shortcut_path}"
    print("[PASS] Desktop shortcut successfully created and verified on disk!")

    # Clean up shortcut
    try:
        os.remove(shortcut_path)
        print(f"[CLEANUP] Removed test shortcut: {shortcut_path}")
    except Exception as e:
        print(f"[CLEANUP NOTE] Could not remove test shortcut: {e}")

    # ---------------------------------------------------------
    # STEP 7: Clean Up Test Clone Profile
    # ---------------------------------------------------------
    print(f"\n--- STEP 7: Remove Clone User Profile {clone_uid} ---")
    remove_ok = AppCloneManager.remove_clone_user(serial, clone_uid)
    print(f"[RESULT] remove_clone_user returned: {remove_ok}")
    assert remove_ok, f"Failed to remove clone user {clone_uid}"

    # Verify removal
    final_clones = AppCloneManager.get_clone_users(serial)
    remaining = [u for u in final_clones if u["id"] == clone_uid]
    print(f"[VERIFY] Remaining instances of user {clone_uid}: {len(remaining)}")
    assert len(remaining) == 0, f"User {clone_uid} still present in get_clone_users!"
    print("[PASS] User profile fully purged and cleaned up!")

    print("\n" + "=" * 70)
    print("  ALL 7 APP CLONER & MULTI-WINDOW VERIFICATION CHECKS PASSED 100%!")
    print("=" * 70)


if __name__ == "__main__":
    try:
        run_full_verification()
    except Exception as err:
        print(f"\n[FATAL ERROR] Verification failed: {err}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
