"""
GNDROiD — Native CLI Runner and Process Orchestrator
Developed by Ghulam Nabi Kalhoro
Version: 2.2.2
"""

import os
import sys
import subprocess
import shutil
import argparse
import time
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008

def find_workspace_root() -> str:
    # 1. Try executable's directory
    exe_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    if os.path.exists(os.path.join(exe_dir, "gndroid.pyw")):
        return exe_dir
    parent = os.path.dirname(exe_dir)
    if os.path.exists(os.path.join(parent, "gndroid.pyw")):
        return parent
    grandparent = os.path.dirname(parent)
    if os.path.exists(os.path.join(grandparent, "gndroid.pyw")):
        return grandparent

    # 2. Try current working directory
    cwd = os.getcwd()
    if os.path.exists(os.path.join(cwd, "gndroid.pyw")):
        return cwd

    # 3. Try standard installation path
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    inst_path = os.path.join(local_app_data, "Programs", "GNDROiD")
    if os.path.exists(os.path.join(inst_path, "gndroid.pyw")):
        return inst_path
    
    pf_path = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "GNDROiD")
    if os.path.exists(os.path.join(pf_path, "gndroid.pyw")):
        return pf_path

    return cwd

def find_python_executable(gui: bool = True) -> str:
    name = "pythonw.exe" if gui else "python.exe"
    user_profile = os.environ.get("USERPROFILE", "")
    candidates = [
        os.path.join(user_profile, "AppData", "Local", "Programs", "Python", "Python314", name),
        os.path.join(user_profile, "AppData", "Local", "Programs", "Python", "Python310", name),
        os.path.join(user_profile, "AppData", "Local", "Programs", "Python", "Python312", name),
        os.path.join(user_profile, "AppData", "Local", "Programs", "Python", "Python311", name),
        os.path.join(r"C:\Python314", name),
        os.path.join(r"C:\Program Files", "Python314", name),
        os.path.join(r"C:\Program Files", "Python310", name),
    ]

    for cand in candidates:
        if os.path.exists(cand):
            return cand

    which_py = shutil.which(name)
    if which_py:
        return which_py
    
    which_py_cli = shutil.which("python.exe")
    if which_py_cli:
        return which_py_cli

    return name

def find_adb() -> str:
    root = find_workspace_root()
    candidates = [
        os.path.join(root, "adb.exe"),
        os.path.join(root, "dist", "gndroid", "adb.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk", "platform-tools", "adb.exe"),
        r"C:\ProgramData\chocolatey\lib\scrcpy\tools\adb.exe",
    ]
    for cand in candidates:
        if os.path.exists(cand):
            return cand
    return shutil.which("adb") or "adb"

def ensure_adb_server():
    adb = find_adb()
    try:
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            if s.connect_ex(("127.0.0.1", 5037)) == 0:
                return
    except Exception:
        pass

    try:
        subprocess.run([adb, "start-server"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW, timeout=5)
    except Exception:
        pass

def launch_python_script(script_args: list, silent: bool = False):
    root = find_workspace_root()
    script_path = os.path.join(root, "gndroid.pyw")
    if not os.path.exists(script_path):
        print(f"Error: GNDROiD core script not found at {script_path}")
        sys.exit(1)

    python = find_python_executable(gui=True)
    cmd = [python, script_path] + script_args

    creation_flags = DETACHED_PROCESS if sys.platform == "win32" else 0
    try:
        subprocess.Popen(cmd, cwd=root, creationflags=creation_flags)
        if not silent:
            print("⚡ GNDROiD process spawned successfully in background.")
    except Exception as e:
        print(f"[-] Failed to launch GNDROiD: {e}")
        sys.exit(1)

def cmd_devices():
    ensure_adb_server()
    adb = find_adb()
    print("============================================================")
    print("  GNDROiD — Connected Android Devices & Virtual Machines     ")
    print("============================================================")
    try:
        out = subprocess.check_output([adb, "devices", "-l"], text=True, creationflags=CREATE_NO_WINDOW)
        lines = [line.strip() for line in out.strip().splitlines() if line.strip()]
        count = 0
        for line in lines[1:]:
            parts = line.split()
            if len(parts) >= 2:
                serial = parts[0]
                state = parts[1]
                extra = " ".join(parts[2:]) if len(parts) > 2 else ""

                if serial.startswith("emulator-"):
                    dev_type = "🖥 Virtual Machine"
                elif ":" in serial:
                    dev_type = "📶 Wireless Wi-Fi"
                else:
                    dev_type = "📱 Physical USB"

                status_badge = "🟢 ONLINE" if state == "device" else ("🟡 UNAUTHORIZED" if state == "unauthorized" else "🔴 OFFLINE")
                print(f"  {status_badge} | {serial:<22} | {dev_type:<16} | {extra}")
                count += 1

        if count == 0:
            print("  No active Android devices or emulators detected.")
            print("\n  Quick Actions:")
            print("    • Connect phone via USB cable and allow USB debugging")
            print("    • Run 'gndroid fix' to configure wireless Wi-Fi streaming")
            print("    • Run 'gndroid multi' to start a virtual machine clone")
        else:
            print(f"\n  Total active targets: {count}")
    except Exception as e:
        print(f"[-] Failed to query ADB: {e}")
    print("============================================================")

def cmd_clean():
    adb = find_adb()
    print("Cleaning zombie ADB server processes and port 5037 conflicts...")
    try:
        subprocess.run([adb, "kill-server"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
        subprocess.run(["taskkill", "/F", "/IM", "scrcpy.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
    except Exception:
        pass
    ensure_adb_server()
    print("✓ ADB server restarted cleanly on port 5037. All zombie blockers cleared.")

def cmd_shortcuts():
    print("Refreshing GNDROiD desktop shortcuts...")
    root = find_workspace_root()
    script = os.path.join(root, "gndroid.pyw")
    python = find_python_executable(gui=False)
    try:
        res = subprocess.run([python, script, "--install-shortcuts"], cwd=root, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
        if res.returncode == 0:
            print("✓ Desktop shortcuts (GNDROiD, GNDROiD Multi-Instance, GNDROiD Mirror, GNDROiD Wireless LAN, GNDROiD ADB Doctor) updated.")
        else:
            # Fallback direct creation via PowerShell WScript.Shell
            install_shortcuts_powershell(root)
    except Exception:
        install_shortcuts_powershell(root)

def install_shortcuts_powershell(root: str):
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    icon = os.path.join(root, "gndroid.ico")
    exe_target = sys.argv[0] if sys.argv[0].endswith(".exe") else os.path.join(root, "gndroid.exe")
    
    ps_code = f"""
    $WshShell = New-Object -ComObject WScript.Shell
    $shortcuts = @(
        @{{ Name = "GNDROiD.lnk"; Args = ""; Desc = "GNDROiD Master Suite" }},
        @{{ Name = "GNDROiD Mirror.lnk"; Args = "mirror"; Desc = "GNDROiD Phone Mirroring" }},
        @{{ Name = "GNDROiD Multi-Instance.lnk"; Args = "multi"; Desc = "GNDROiD Multi-Instance Manager" }},
        @{{ Name = "GNDROiD Wireless LAN.lnk"; Args = "lan"; Desc = "GNDROiD Wireless LAN Mode" }},
        @{{ Name = "GNDROiD ADB Doctor.lnk"; Args = "fix"; Desc = "GNDROiD ADB Doctor" }}
    )
    foreach ($s in $shortcuts) {{
        $lnk = Join-Path "{desktop}" $s.Name
        $sc = $WshShell.CreateShortcut($lnk)
        $sc.TargetPath = "{exe_target}"
        $sc.Arguments = $s.Args
        $sc.WorkingDirectory = "{root}"
        $sc.Description = $s.Desc
        if (Test-Path "{icon}") {{ $sc.IconLocation = "{icon},0" }}
        $sc.Save()
    }}
    """
    subprocess.run(["powershell", "-NoProfile", "-Command", ps_code], creationflags=CREATE_NO_WINDOW)
    print("✓ Verified all 5 desktop shortcuts (GNDROiD, Multi, Mirror, LAN, Doctor) exist on Desktop")

def main():
    parser = argparse.ArgumentParser(
        prog="gndroid",
        description="GNDROiD — High-Performance Android Virtual Machine & Physical Phone Suite CLI"
    )
    parser.add_argument("--version", action="version", version="gndroid 2.2.2")
    
    subparsers = parser.add_subparsers(dest="command")

    # gui
    subparsers.add_parser("gui", help="Launch the main Fluent Light GUI Controller (default when double-clicked)")

    # launch
    launch_parser = subparsers.add_parser("launch", help="Launch a virtual machine instance or the main controller")
    launch_parser.add_argument("--avd", "-a", help="Optional AVD name to launch directly")

    # mirror
    mirror_parser = subparsers.add_parser("mirror", help="Start phone mirroring with docked companion sidebar")
    mirror_parser.add_argument("--serial", "-s", help="Optional target serial (USB or IP:Port)")

    # multi
    subparsers.add_parser("multi", help="Open the Multi-Instance Manager for parallel clones and batch management")

    # fix
    subparsers.add_parser("fix", help="Open ADB Doctor & Troubleshooting Suite")

    # lan
    subparsers.add_parser("lan", help="Open Wireless LAN & Wi-Fi Mode directly")

    # download
    subparsers.add_parser("download", help="Open 1-Click Android OS System Image Downloader")

    # devices
    subparsers.add_parser("devices", help="Query and list connected physical phones, Wi-Fi devices, and running VMs")

    # clean
    subparsers.add_parser("clean", help="Terminate zombie port 5037 blockers and restart ADB server")

    # shortcuts
    subparsers.add_parser("shortcuts", help="Re-generate Windows desktop shortcuts pointing directly to gndroid.exe")

    # If no arguments provided: launch GUI silently
    if len(sys.argv) == 1:
        launch_python_script([], silent=True)
        return

    # Parse args
    args, unknown = parser.parse_known_args()

    if args.command is None or args.command == "gui":
        launch_python_script(unknown, silent=False)
    elif args.command == "launch":
        avd_args = ["--avd", args.avd] if args.avd else []
        launch_python_script(avd_args + unknown, silent=False)
    elif args.command == "mirror":
        mirror_args = ["--mirror", args.serial] if args.serial else ["--mirror"]
        launch_python_script(mirror_args + unknown, silent=False)
    elif args.command == "multi":
        launch_python_script(["--multi"] + unknown, silent=False)
    elif args.command == "fix":
        launch_python_script(["--adb-fixer"] + unknown, silent=False)
    elif args.command == "lan":
        launch_python_script(["--lan"] + unknown, silent=False)
    elif args.command == "download":
        launch_python_script(["--download-image"] + unknown, silent=False)
    elif args.command == "devices":
        cmd_devices()
    elif args.command == "clean":
        cmd_clean()
    elif args.command == "shortcuts":
        cmd_shortcuts()
    else:
        launch_python_script([args.command] + unknown, silent=False)

if __name__ == "__main__":
    main()

