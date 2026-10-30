"""
gndroid App Launcher & Desktop Shortcut Runner
Developed by Ghulam Nabi Kalhoro
"""

import sys
import os
import subprocess
import time

def get_base_dir() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def get_adb() -> str:
    base = get_base_dir()
    for cand in [
        os.path.join(base, "adb.exe"),
        os.path.join(base, "dist", "gndroid", "adb.exe"),
        os.path.join(base, "dist", "AndroidMobilePlayer", "adb.exe"),
    ]:
        if os.path.exists(cand):
            return cand
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    cand = os.path.join(local_app_data, "Android", "Sdk", "platform-tools", "adb.exe")
    return cand if os.path.exists(cand) else "adb"

def get_scrcpy() -> str:
    base = get_base_dir()
    for cand in [
        os.path.join(base, "scrcpy.exe"),
        os.path.join(base, "dist", "gndroid", "scrcpy.exe"),
        os.path.join(base, "dist", "AndroidMobilePlayer", "scrcpy.exe"),
    ]:
        if os.path.exists(cand):
            return cand
    return "scrcpy"

def is_scrcpy_running() -> bool:
    try:
        out = subprocess.check_output(
            ["tasklist", "/fi", "imagename eq scrcpy.exe"],
            text=True, creationflags=0x08000000
        )
        return "scrcpy.exe" in out.lower()
    except Exception:
        return False

def launch_app(package_name: str, app_title: str = "", user_id: int = 0, window: bool = False, serial: str = ""):
    if not app_title:
        app_title = package_name.split(".")[-1].capitalize()

    # Dedicated floating window mode
    if window:
        try:
            from nexus.app_cloner_and_window import AppWindowManager, find_active_serial
            target_serial = serial or find_active_serial()
            AppWindowManager.launch_app_in_dedicated_window(
                serial=target_serial,
                package_name=package_name,
                app_title=app_title,
                user_id=user_id
            )
            return
        except Exception:
            pass

    adb = get_adb()
    scrcpy = get_scrcpy()
    base = get_base_dir()

    # 1. Bring app to foreground on device
    try:
        cmd = [adb]
        if serial:
            cmd.extend(["-s", serial])
        if user_id != 0:
            cmd.extend(["shell", "am", "start", "--user", str(user_id), package_name])
        else:
            cmd.extend(["shell", "monkey", "-p", package_name, "-c", "android.intent.category.LAUNCHER", "1"])
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000, timeout=3)
    except Exception:
        pass

    # 2. Check if scrcpy is already active
    if not is_scrcpy_running():
        # Start scrcpy and companion sidebar
        gndroid_exe = os.path.join(base, "gndroid.exe")
        gndroid_pyw = os.path.join(base, "gndroid.pyw")
        if os.path.exists(gndroid_exe):
            subprocess.Popen([gndroid_exe, "mirror"], cwd=base, creationflags=0x08000000)
        elif os.path.exists(gndroid_pyw):
            subprocess.Popen(["pythonw.exe", gndroid_pyw, "--mirror"], cwd=base, creationflags=0x08000000)
        else:
            cmd = [scrcpy, "-d", "--stay-awake", "--shortcut-mod=lalt", "--no-audio", "--window-title", "gndroid", "--pause-on-exit=false"]
            subprocess.Popen(cmd, cwd=os.path.dirname(scrcpy), creationflags=0x08000000, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

if __name__ == "__main__":
    args = sys.argv[1:]
    if "--app" in args:
        idx = args.index("--app")
        pkg = args[idx + 1] if idx + 1 < len(args) else ""
        user_id = 0
        if "--user" in args:
            u_idx = args.index("--user")
            if u_idx + 1 < len(args):
                try: user_id = int(args[u_idx + 1])
                except ValueError: user_id = 0
        window = ("--window" in args or "-w" in args)
        title = ""
        if "--title" in args:
            t_idx = args.index("--title")
            if t_idx + 1 < len(args): title = args[t_idx + 1]
        serial = ""
        if "--serial" in args:
            s_idx = args.index("--serial")
            if s_idx + 1 < len(args): serial = args[s_idx + 1]
        if pkg:
            launch_app(pkg, title, user_id=user_id, window=window, serial=serial)
            sys.exit(0)
    elif len(args) > 0:
        pkg = args[0]
        title = args[1] if len(args) > 1 else ""
        launch_app(pkg, title)
    else:
        print("Usage: gndroid_app_launcher.py [--app <pkg>] [--user <id>] [--window] [--title <title>]")
