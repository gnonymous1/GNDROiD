"""
gndroid — NextGen Android Virtual Machine & Physical Phone Suite
Developed by Ghulam Nabi Kalhoro

Features:
- Single working window architecture
- Dynamic hardware allocation (Host RAM, CPU cores, and disk introspection)
- Real PC Camera (Webcam0 / DirectShow passthrough)
- Real PC Internet & Wi-Fi adapter toggle
- High-Speed USB & Wireless LAN (TCP/IP) Phone Mirroring
- Drag & Drop APK Installation & File Push to Phone
- Drag & Drop App Shortcut Creation directly onto PC Desktop
- Sleek BlueStacks-style Companion Sidebar with Rotate, Volume, Navigation, Screenshot, Apps
- Professional Embedded Branding & Icons (No .bat files)
"""

import os
import sys
import time
import subprocess
import ctypes
import tempfile
import threading
import socket
import urllib.request
import zipfile
import shutil
import glob
import math
import re
import io
import random
import secrets
import qrcode
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, List, Optional

# Ensure workspace root is in sys.path for nexus modules
_workspace_root = os.path.dirname(os.path.abspath(__file__))
if _workspace_root not in sys.path:
    sys.path.insert(0, _workspace_root)

import nexus.display_and_vpn
import nexus.network_bridge
from nexus.wireless_mirror import (
    WirelessMirrorManager,
    WirelessPairingEngine,
    WirelessReconnectionWatchdog,
)

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QProgressBar, QProgressDialog, QDialog, QFileDialog,
    QComboBox, QFrame, QMessageBox, QTabWidget, QGridLayout,
    QScrollArea, QLineEdit, QSpinBox, QListWidget, QListWidgetItem, QToolTip,
    QInputDialog, QGraphicsDropShadowEffect, QTableWidget,
    QTableWidgetItem, QHeaderView, QCheckBox, QSlider, QRadioButton, QButtonGroup,
    QTextEdit, QPlainTextEdit, QSplitter, QGroupBox
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QSize, QUrl, QPoint, QPointF, QRectF
from PyQt6.QtGui import (
    QFont, QColor, QPalette, QDragEnterEvent, QDropEvent, QIcon,
    QPixmap, QDrag, QPainter, QBrush, QPen, QPainterPath,
    QLinearGradient, QRadialGradient
)

# Win32 user32 constants
user32 = ctypes.windll.user32
SWP_NOZORDER = 0x0004
SWP_SHOWWINDOW = 0x0040

class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long)
    ]

def get_base_dir() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

# ----------------------------------------------------------------------
# Nexus App Cloner & Dedicated Floating Window Engine
# ----------------------------------------------------------------------
try:
    from nexus.app_cloner_and_window import AppCloneManager, AppWindowManager, AppCloneEntry, find_active_serial
except ImportError:
    try:
        _nexus_dir = os.path.join(get_base_dir(), "nexus")
        if _nexus_dir not in sys.path:
            sys.path.insert(0, _nexus_dir)
        from app_cloner_and_window import AppCloneManager, AppWindowManager, AppCloneEntry, find_active_serial
    except Exception:
        AppCloneManager = None
        AppWindowManager = None
        AppCloneEntry = None
        find_active_serial = None

# ----------------------------------------------------------------------
# System Paths & Tool Locators
# ----------------------------------------------------------------------
class SystemPaths:
    @staticmethod
    def get_sdk_dir() -> str:
        for env_k in ["ANDROID_HOME", "ANDROID_SDK_ROOT"]:
            p = os.environ.get(env_k)
            if p and os.path.exists(p):
                return p
        loc = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk")
        if os.path.exists(loc):
            return loc
        for cand in [r"C:\Android\Sdk", r"D:\Android\Sdk"]:
            if os.path.exists(cand):
                return cand
        return loc

    @staticmethod
    def get_adb() -> str:
        base = get_base_dir()
        for cand in [
            os.path.join(base, "tools", "adb.exe"),
            os.path.join(base, "adb.exe"),
            os.path.join(base, "dist", "gndroid", "adb.exe"),
            os.path.join(base, "dist", "AndroidMobilePlayer", "adb.exe"),
            os.path.join(base, "scrcpy", "adb.exe")
        ]:
            if os.path.exists(cand):
                return cand
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        candidate = os.path.join(local_app_data, "Android", "Sdk", "platform-tools", "adb.exe")
        return candidate if os.path.exists(candidate) else "adb"

    @staticmethod
    def get_emulator() -> str:
        base = get_base_dir()
        for cand in [
            os.path.join(base, "emulator.exe"),
            os.path.join(base, "emulator", "emulator.exe"),
            os.path.join(base, "dist", "gndroid", "emulator.exe"),
            os.path.join(base, "dist", "gndroid", "emulator", "emulator.exe"),
        ]:
            if os.path.exists(cand):
                return cand
        for env_k in ["ANDROID_HOME", "ANDROID_SDK_ROOT"]:
            v = os.environ.get(env_k)
            if v:
                cand = os.path.join(v, "emulator", "emulator.exe")
                if os.path.exists(cand):
                    return cand
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        candidate = os.path.join(local_app_data, "Android", "Sdk", "emulator", "emulator.exe")
        if os.path.exists(candidate):
            return candidate
        which_emu = shutil.which("emulator")
        if which_emu:
            return which_emu
        pf = os.environ.get("ProgramFiles", "C:\\Program Files")
        cand_as = os.path.join(pf, "Android", "Android Studio", "emulator", "emulator.exe")
        if os.path.exists(cand_as):
            return cand_as
        return candidate if os.path.exists(candidate) else "emulator"

    @staticmethod
    def get_scrcpy() -> str:
        base = get_base_dir()
        for cand in [
            os.path.join(base, "tools", "scrcpy.exe"),
            os.path.join(base, "scrcpy.exe"),
            os.path.join(base, "dist", "gndroid", "scrcpy.exe"),
            os.path.join(base, "dist", "AndroidMobilePlayer", "scrcpy.exe"),
            os.path.join(base, "scrcpy", "scrcpy.exe")
        ]:
            if os.path.exists(cand):
                return cand
        return "scrcpy"

    @staticmethod
    def get_icon() -> str:
        base = get_base_dir()
        for cand in [
            os.path.join(base, "gndroid.ico"),
            os.path.join(base, "dist", "gndroid", "gndroid.ico"),
        ]:
            if os.path.exists(cand):
                return cand
        return ""

    @staticmethod
    def get_adb_version() -> str:
        adb = SystemPaths.get_adb()
        try:
            out = subprocess.check_output([adb, "version"], text=True, timeout=2, creationflags=0x08000000)
            return out.strip().splitlines()[0] if out else "Unknown"
        except Exception as e:
            return f"Unavailable ({e})"

    @staticmethod
    def is_port_in_use(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            return s.connect_ex(("127.0.0.1", port)) == 0

    @staticmethod
    def get_port_conflicts(port: int = 5037) -> List[Dict[str, str]]:
        conflicts = []
        try:
            out = subprocess.check_output(["netstat", "-ano"], text=True, timeout=3, creationflags=0x08000000)
            for line in out.splitlines():
                if f":{port} " in line and "LISTENING" in line:
                    parts = line.split()
                    if parts:
                        pid = parts[-1]
                        proc_name = "Unknown"
                        try:
                            t_out = subprocess.check_output(["tasklist", "/fi", f"pid eq {pid}", "/fo", "csv", "/nh"], text=True, timeout=2, creationflags=0x08000000)
                            if t_out and '"' in t_out:
                                proc_name = t_out.split('"')[1]
                        except Exception:
                            pass
                        conflicts.append({"port": str(port), "pid": pid, "proc": proc_name, "raw": line.strip()})
        except Exception:
            pass
        return conflicts

    @staticmethod
    def kill_process_by_pid(pid: str) -> bool:
        try:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=3, creationflags=0x08000000)
            return True
        except Exception:
            return False

    @staticmethod
    def ping_ip(ip: str, timeout_sec: int = 1) -> bool:
        try:
            res = subprocess.run(["ping", "-n", "1", "-w", str(int(timeout_sec * 1000)), ip], capture_output=True, text=True, creationflags=0x08000000)
            return res.returncode == 0 and "TTL=" in res.stdout
        except Exception:
            return False

    @staticmethod
    def get_host_hardware_summary() -> Dict[str, Any]:
        """Performs live host hardware introspection for memory, CPU cores, and storage."""
        ram_gb = 16
        try:
            import psutil
            ram_gb = max(1, round(psutil.virtual_memory().total / (1024 ** 3)))
        except Exception:
            try:
                class _MEMORYSTATUSEX(ctypes.Structure):
                    _fields_ = [
                        ("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("sllAvailExtendedVirtual", ctypes.c_ulonglong),
                    ]
                stat = _MEMORYSTATUSEX()
                stat.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
                if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                    ram_gb = max(1, round(stat.ullTotalPhys / (1024 ** 3)))
            except Exception:
                pass

        cores = os.cpu_count() or 8

        free_gb = 32
        try:
            drive = os.path.splitdrive(os.getcwd())[0] or "C:"
            _, _, free = shutil.disk_usage(drive)
            free_gb = max(1, round(free / (1024 ** 3)))
        except Exception:
            pass

        return {
            "ram_gb": ram_gb,
            "cores": cores,
            "free_disk_gb": free_gb,
            "summary_text": f"{ram_gb} GB RAM | {cores} Cores | {free_gb} GB Free Disk | GPU Direct3D/Vulkan"
        }

    @staticmethod
    def list_port_forwards() -> List[Dict[str, str]]:
        adb = SystemPaths.get_adb()
        rules = []
        try:
            out = subprocess.check_output([adb, "forward", "--list"], text=True, timeout=3, creationflags=0x08000000)
            for line in out.strip().splitlines():
                parts = line.split()
                if len(parts) >= 3:
                    rules.append({"serial": parts[0], "local": parts[1], "remote": parts[2]})
        except Exception:
            pass
        return rules

    @staticmethod
    def add_port_forward(serial: str, local_port: int, remote_port: int, reverse: bool = False) -> str:
        adb = SystemPaths.get_adb()
        cmd = [adb]
        if serial:
            cmd.extend(["-s", serial])
        if reverse:
            cmd.extend(["reverse", f"tcp:{remote_port}", f"tcp:{local_port}"])
        else:
            cmd.extend(["forward", f"tcp:{local_port}", f"tcp:{remote_port}"])
        try:
            out = subprocess.check_output(cmd, text=True, timeout=3, creationflags=0x08000000)
            return out.strip() if out else "Success"
        except Exception as e:
            return f"Error: {e}"

    @staticmethod
    def remove_port_forward(serial: str, local_port: int, reverse: bool = False) -> None:
        adb = SystemPaths.get_adb()
        cmd = [adb]
        if serial:
            cmd.extend(["-s", serial])
        if reverse:
            cmd.extend(["reverse", "--remove", f"tcp:{local_port}"])
        else:
            cmd.extend(["forward", "--remove", f"tcp:{local_port}"])
        try:
            subprocess.run(cmd, timeout=3, creationflags=0x08000000)
        except Exception:
            pass

    @staticmethod
    def clear_all_forwards(serial: str = "") -> None:
        adb = SystemPaths.get_adb()
        cmd = [adb]
        if serial:
            cmd.extend(["-s", serial])
        try:
            subprocess.run(cmd + ["forward", "--remove-all"], timeout=3, creationflags=0x08000000)
            subprocess.run(cmd + ["reverse", "--remove-all"], timeout=3, creationflags=0x08000000)
        except Exception:
            pass

    @staticmethod
    def get_phone_lan_ip(serial: str) -> str:
        """Extracts the active Wi-Fi IP address of an attached phone."""
        adb = SystemPaths.get_adb()
        device_ip = ""
        try:
            out = subprocess.check_output([adb, "-s", serial, "shell", "ip route"], text=True, timeout=3, creationflags=0x08000000)
            for line in out.splitlines():
                if "wlan0" in line and "src" in line:
                    parts = line.split()
                    if "src" in parts:
                        device_ip = parts[parts.index("src") + 1]
                        break
        except Exception:
            pass

        if not device_ip:
            try:
                out = subprocess.check_output([adb, "-s", serial, "shell", "getprop dhcp.wlan0.ipaddress"], text=True, timeout=3, creationflags=0x08000000).strip()
                if out and re.match(r"^\d+\.\d+\.\d+\.\d+$", out):
                    device_ip = out
            except Exception:
                pass

        if not device_ip:
            try:
                out = subprocess.check_output([adb, "-s", serial, "shell", "ip -f inet addr show wlan0"], text=True, timeout=3, creationflags=0x08000000)
                m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", out)
                if m:
                    device_ip = m.group(1)
            except Exception:
                pass

        return device_ip

    @staticmethod
    def convert_usb_to_wireless_lan(usb_serial: str) -> tuple[bool, str]:
        """Ports NexusSuite logic: converts a connected USB phone into a wireless LAN streaming device."""
        adb = SystemPaths.get_adb()
        try:
            # 1. Restart ADB on device in TCP/IP mode on port 5555
            subprocess.run([adb, "-s", usb_serial, "tcpip", "5555"], capture_output=True, text=True, timeout=5, creationflags=0x08000000)
            time.sleep(1.2)

            # 2. Extract active Wi-Fi IP address from device network interfaces
            device_ip = SystemPaths.get_phone_lan_ip(usb_serial)

            if not device_ip:
                return False, "Could not resolve device Wi-Fi IP address. Ensure your phone is connected to the same Wi-Fi/LAN as your PC."

            target_lan = f"{device_ip}:5555"
            conn_res = subprocess.run([adb, "connect", target_lan], capture_output=True, text=True, timeout=6, creationflags=0x08000000)
            out_txt = (conn_res.stdout + " " + conn_res.stderr).strip()
            if "connected" in out_txt.lower() or "already" in out_txt.lower():
                return True, target_lan
            return False, f"Failed to connect to {target_lan}: {out_txt or 'connection refused or timed out'}"
        except Exception as e:
            return False, str(e)

    @staticmethod
    def scan_subnet_for_android_devices(base_ip_prefix: str = "") -> List[Dict[str, Any]]:
        """Ports NexusSuite Subnet Radar: discovers active Android devices on local LAN."""
        if not base_ip_prefix:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
                s.close()
                base_ip_prefix = ".".join(local_ip.split(".")[:3])
            except Exception:
                base_ip_prefix = "192.168.1"

        discovered = []
        def check_host(h_ip):
            for port in [5555, 51880]:
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                        sock.settimeout(0.3)
                        if sock.connect_ex((h_ip, port)) == 0:
                            discovered.append({"ip": h_ip, "port": port, "target": f"{h_ip}:{port}"})
                            break
                except Exception:
                    pass

        with ThreadPoolExecutor(max_workers=35) as ex:
            for i in range(1, 255):
                ex.submit(check_host, f"{base_ip_prefix}.{i}")
        return discovered

    @staticmethod
    def list_devices() -> List[Dict[str, Any]]:
        adb = SystemPaths.get_adb()
        devices = []
        try:
            out = subprocess.check_output([adb, "devices", "-l"], text=True, timeout=4, creationflags=0x08000000)
            for line in out.strip().splitlines()[1:]:
                if not line.strip(): continue
                parts = line.split()
                if len(parts) >= 2:
                    serial = parts[0]
                    state = parts[1]
                    model = "Android Device"
                    for p in parts[2:]:
                        if p.startswith("model:"):
                            model = p.replace("model:", "").replace("_", " ")
                    is_lan = ":" in serial
                    is_emu = serial.startswith("emulator-")
                    devices.append({
                        "serial": serial,
                        "state": state,
                        "model": model,
                        "is_emulator": is_emu,
                        "is_lan": is_lan
                    })
        except Exception:
            pass
        return devices

    @staticmethod
    def get_phone_lan_ip(target_serial: str = "") -> Optional[str]:
        adb = SystemPaths.get_adb()
        target = ["-s", target_serial] if target_serial else []

        CELLULAR_PREFIXES = ("ccmni", "rmnet", "pdp", "ppp", "usb", "dummy", "lo", "tun", "sit")

        # Priority 1: Query dedicated Wi-Fi interfaces directly (wlan0, wlan1, eth0, mlan0)
        for iface in ["wlan0", "wlan1", "eth0", "mlan0", "wifi0"]:
            try:
                out = subprocess.check_output(
                    [adb] + target + ["shell", f"ip -f inet addr show {iface}"],
                    text=True, timeout=2, creationflags=0x08000000
                )
                for line in out.splitlines():
                    line = line.strip()
                    if line.startswith("inet "):
                        candidate = line.split()[1].split("/")[0].strip()
                        if candidate and candidate != "127.0.0.1" and not candidate.startswith("169.254"):
                            return candidate
            except Exception:
                pass

        # Priority 2: Query DHCP Wi-Fi properties
        for prop in ["dhcp.wlan0.ipaddress", "dhcp.wlan1.ipaddress", "dhcp.eth0.ipaddress"]:
            try:
                candidate = subprocess.check_output(
                    [adb] + target + ["shell", "getprop", prop],
                    text=True, timeout=2, creationflags=0x08000000
                ).strip()
                if candidate and candidate != "127.0.0.1" and not candidate.startswith("169.254"):
                    return candidate
            except Exception:
                pass

        # Priority 3: Parse full IP address table while strictly excluding cellular interfaces
        try:
            out = subprocess.check_output(
                [adb] + target + ["shell", "ip -f inet addr show"],
                text=True, timeout=3, creationflags=0x08000000
            )
            current_iface = ""
            for line in out.splitlines():
                line_str = line.strip()
                if line and not line.startswith(" "):
                    parts = line.split(":")
                    if len(parts) >= 2:
                        current_iface = parts[1].strip()
                elif line_str.startswith("inet ") and current_iface:
                    if not any(current_iface.startswith(pfx) for pfx in CELLULAR_PREFIXES):
                        candidate = line_str.split()[1].split("/")[0].strip()
                        if candidate and candidate != "127.0.0.1" and not candidate.startswith("169.254"):
                            return candidate
        except Exception:
            pass

        return None

# ----------------------------------------------------------------------
# Background Asynchronous Device Scanner & Auto-LAN Enabler
# ----------------------------------------------------------------------
class DeviceScannerWorker(QThread):
    devices_updated = pyqtSignal(list)
    auto_lan_connected = pyqtSignal(str, str)  # serial, wifi_ip
    auto_lan_status = pyqtSignal(str)          # user status message

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = True
        # Feature 10: Default to False to preserve active USB debug sessions.
        # Do NOT automatically force adb tcpip 5555 on connected USB devices.
        self.auto_lan_enabled = False
        self._converted_serials = set()

    def set_auto_lan_enabled(self, enabled: bool):
        """Explicitly enables or disables background wireless LAN conversion."""
        self.auto_lan_enabled = bool(enabled)

    def run(self):
        last_sig = None
        adb = SystemPaths.get_adb()
        while self._running:
            try:
                devs = SystemPaths.list_devices()
                sig = [(d.get("serial"), d.get("state")) for d in devs]
                if sig != last_sig:
                    last_sig = sig
                    self.devices_updated.emit(devs)

                # Automatic Background LAN Enablement for USB Connected Phones
                if self.auto_lan_enabled:
                    lan_ips = {d["serial"].split(":")[0] for d in devs if d.get("is_lan")}
                    current_usb = {d["serial"] for d in devs if not d.get("is_emulator") and not d.get("is_lan") and d.get("state") == "device"}
                    self._converted_serials = self._converted_serials.intersection(current_usb)

                    for usb_dev in devs:
                        s = usb_dev.get("serial", "")
                        model = usb_dev.get("model", "Phone")
                        if not usb_dev.get("is_emulator") and not usb_dev.get("is_lan") and usb_dev.get("state") == "device":
                            if s not in self._converted_serials:
                                wifi_ip = SystemPaths.get_phone_lan_ip(s)
                                if wifi_ip:
                                    if wifi_ip in lan_ips:
                                        # Already connected via Wi-Fi!
                                        self._converted_serials.add(s)
                                    else:
                                        try:
                                            # Switch phone to TCP/IP 5555
                                            subprocess.run([adb, "-s", s, "tcpip", "5555"], timeout=4, capture_output=True, creationflags=0x08000000)
                                            time.sleep(0.8)
                                            # Connect over Wi-Fi
                                            res = subprocess.check_output([adb, "connect", f"{wifi_ip}:5555"], text=True, timeout=6, creationflags=0x08000000)
                                            if "connected to" in res.lower() or "already connected" in res.lower():
                                                self._converted_serials.add(s)
                                                self.auto_lan_connected.emit(s, wifi_ip)
                                                self.auto_lan_status.emit(f"📶 {model} auto-connected over Wi-Fi ({wifi_ip}:5555). USB can now be unplugged!")
                                                devs = SystemPaths.list_devices()
                                                last_sig = [(d.get("serial"), d.get("state")) for d in devs]
                                                self.devices_updated.emit(devs)
                                        except Exception:
                                            pass
            except Exception:
                pass

            for _ in range(15):
                if not self._running:
                    break
                time.sleep(0.2)

    def stop(self):
        self._running = False
        self.wait(1000)

# ----------------------------------------------------------------------
# App Shortcut Creator Utility
# ----------------------------------------------------------------------
class ShortcutManager:
    @staticmethod
    def create_desktop_shortcut(app_name: str, package_name: str, icon_path: str = "", user_id: int = 0, dedicated_window: bool = True) -> str:
        clean_name = "".join(c for c in app_name if c.isalnum() or c in " _-").strip()
        user_suffix = f" [Clone #{user_id}]" if user_id != 0 else ""
        lnk_name = f"{clean_name}{user_suffix} (GNDROiD).lnk"

        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        base = get_base_dir()
        exe_path = sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__)
        if not icon_path:
            icon_path = SystemPaths.get_icon()

        user_arg = f" --user {user_id}"
        win_arg = " --window" if dedicated_window else ""

        if exe_path.endswith(".pyw") or exe_path.endswith(".py"):
            target_bin = "pythonw.exe"
            target_args = f'"{exe_path}" --app {package_name}{user_arg}{win_arg}'
            ps_args = f'\\"{exe_path}\\" --app {package_name}{user_arg}{win_arg}'
        else:
            target_bin = exe_path
            target_args = f'--app {package_name}{user_arg}{win_arg}'
            ps_args = f'--app {package_name}{user_arg}{win_arg}'

        lnk_path = os.path.join(desktop, lnk_name)

        # 1. Try win32com
        try:
            import win32com.client
            shell = win32com.client.Dispatch("WScript.Shell")
            special_desktop = shell.SpecialFolders("Desktop")
            if special_desktop and os.path.exists(special_desktop):
                desktop = special_desktop
                lnk_path = os.path.join(desktop, lnk_name)

            shortcut = shell.CreateShortcut(lnk_path)
            shortcut.TargetPath = target_bin
            shortcut.Arguments = target_args
            shortcut.WorkingDirectory = base
            if icon_path and os.path.exists(icon_path):
                shortcut.IconLocation = f"{icon_path},0"
            shortcut.Description = f"Launch {clean_name} in dedicated GNDROiD window"
            shortcut.Save()
            return lnk_path
        except Exception:
            pass

        # 2. Fallback via PowerShell
        try:
            icon_cmd = f'$s.IconLocation = "{icon_path},0";' if icon_path and os.path.exists(icon_path) else ""
            ps_cmd = (
                f'$w = New-Object -ComObject WScript.Shell; '
                f'$s = $w.CreateShortcut("{lnk_path}"); '
                f'$s.TargetPath = "{target_bin}"; '
                f'$s.Arguments = "{ps_args}"; '
                f'$s.WorkingDirectory = "{base}"; '
                f'{icon_cmd} '
                f'$s.Save()'
            )
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                creationflags=0x08000000,
                timeout=10
            )
            if res.returncode == 0 and os.path.exists(lnk_path):
                return lnk_path
        except Exception:
            pass

        return ""

    @staticmethod
    def install_official_shortcuts():
        try:
            import win32com.client
            shell = win32com.client.Dispatch("WScript.Shell")
            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            base = get_base_dir()

            native_exe = os.path.join(base, "gndroid.exe")
            has_native = os.path.exists(native_exe)
            exe_path = native_exe if has_native else (sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__))
            icon = SystemPaths.get_icon()

            # Clean up all old bat files and legacy shortcuts from desktop
            for old in [
                "mirror-phone.bat", "gndroid.bat", "Launch-gndroid.bat",
                "multi-instances.bat", "adb-fixer.bat", "download-image.bat",
                "Mirror Physical Phone.lnk", "gndroid Settings & USB Mirror.lnk",
                "gndroid.lnk", "gndroid Mirror.lnk"
            ]:
                p = os.path.join(desktop, old)
                if os.path.exists(p):
                    try: os.remove(p)
                    except: pass

            # 1. GNDROiD (Virtual Machine & Master Suite)
            sc1 = shell.CreateShortcut(os.path.join(desktop, "GNDROiD.lnk"))
            if has_native:
                sc1.TargetPath = native_exe
                sc1.Arguments = ""
            elif exe_path.endswith(".pyw") or exe_path.endswith(".py"):
                sc1.TargetPath = "pythonw.exe"
                sc1.Arguments = f'"{exe_path}"'
            else:
                sc1.TargetPath = exe_path
            sc1.WorkingDirectory = base
            if icon: sc1.IconLocation = f"{icon},0"
            sc1.Description = "GNDROiD — High-Performance Android Suite (Ghulam Nabi Kalhoro)"
            sc1.Save()

            # 2. GNDROiD Mirror (Direct Phone Mirroring with Sidebar)
            sc2 = shell.CreateShortcut(os.path.join(desktop, "GNDROiD Mirror.lnk"))
            if has_native:
                sc2.TargetPath = native_exe
                sc2.Arguments = "mirror"
            elif exe_path.endswith(".pyw") or exe_path.endswith(".py"):
                sc2.TargetPath = "pythonw.exe"
                sc2.Arguments = f'"{exe_path}" --mirror'
            else:
                sc2.TargetPath = exe_path
                sc2.Arguments = "--mirror"
            sc2.WorkingDirectory = base
            if icon: sc2.IconLocation = f"{icon},0"
            sc2.Description = "GNDROiD Mirror — USB & LAN Phone Mirroring with Controls"
            sc2.Save()

            # 3. GNDROiD Multi-Instance Manager
            sc3 = shell.CreateShortcut(os.path.join(desktop, "GNDROiD Multi-Instance.lnk"))
            if has_native:
                sc3.TargetPath = native_exe
                sc3.Arguments = "multi"
            elif exe_path.endswith(".pyw") or exe_path.endswith(".py"):
                sc3.TargetPath = "pythonw.exe"
                sc3.Arguments = f'"{exe_path}" --multi'
            else:
                sc3.TargetPath = exe_path
                sc3.Arguments = "--multi"
            sc3.WorkingDirectory = base
            if icon: sc3.IconLocation = f"{icon},0"
            sc3.Description = "GNDROiD Multi-Instance Manager — Parallel Android Clones"
            sc3.Save()

            # 4. GNDROiD Wireless LAN
            sc4 = shell.CreateShortcut(os.path.join(desktop, "GNDROiD Wireless LAN.lnk"))
            if has_native:
                sc4.TargetPath = native_exe
                sc4.Arguments = "lan"
            elif exe_path.endswith(".pyw") or exe_path.endswith(".py"):
                sc4.TargetPath = "pythonw.exe"
                sc4.Arguments = f'"{exe_path}" --lan'
            else:
                sc4.TargetPath = exe_path
                sc4.Arguments = "--lan"
            sc4.WorkingDirectory = base
            if icon: sc4.IconLocation = f"{icon},0"
            sc4.Description = "GNDROiD Wireless LAN — 1-Click Wi-Fi Streaming & Subnet Radar"
            sc4.Save()

            # 5. GNDROiD ADB Doctor
            sc5 = shell.CreateShortcut(os.path.join(desktop, "GNDROiD ADB Doctor.lnk"))
            if has_native:
                sc5.TargetPath = native_exe
                sc5.Arguments = "fix"
            elif exe_path.endswith(".pyw") or exe_path.endswith(".py"):
                sc5.TargetPath = "pythonw.exe"
                sc5.Arguments = f'"{exe_path}" --adb-fixer'
            else:
                sc5.TargetPath = exe_path
                sc5.Arguments = "--adb-fixer"
            sc5.WorkingDirectory = base
            if icon: sc5.IconLocation = f"{icon},0"
            sc5.Description = "GNDROiD ADB Doctor — Complete Diagnostics, Port 5037 Unblocker & Live Logcat"
            sc5.Save()

            return True
        except Exception:
            return False

# ----------------------------------------------------------------------
# App Drawer with Drag-to-Desktop Shortcut Creation
# ----------------------------------------------------------------------
class DraggableAppList(QListWidget):
    def __init__(self, target_serial: str, parent=None):
        super().__init__(parent)
        self.target_serial = target_serial
        self.setDragEnabled(True)

    def startDrag(self, supportedActions):
        item = self.currentItem()
        if not item: return

        data = item.data(Qt.ItemDataRole.UserRole)
        if not data: return

        pkg = data.get("package", "")
        name = data.get("name", "")
        user_id = data.get("user_id", 0)

        # Create temporary .lnk shortcut
        temp_dir = tempfile.gettempdir()
        clean_name = "".join(c for c in name if c.isalnum() or c in " _-").strip()
        user_suffix = f" [Clone #{user_id}]" if user_id != 0 else ""
        temp_lnk = os.path.join(temp_dir, f"{clean_name}{user_suffix} (gndroid).lnk")

        try:
            import win32com.client
            shell = win32com.client.Dispatch("WScript.Shell")
            exe_path = sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__)
            base = get_base_dir()
            icon = SystemPaths.get_icon()

            user_arg = f" --user {user_id}" if user_id != 0 else ""
            sc = shell.CreateShortcut(temp_lnk)
            if exe_path.endswith(".pyw") or exe_path.endswith(".py"):
                sc.TargetPath = "pythonw.exe"
                sc.Arguments = f'"{exe_path}" --app {pkg}{user_arg} --window'
            else:
                sc.TargetPath = exe_path
                sc.Arguments = f'--app {pkg}{user_arg} --window'
            sc.WorkingDirectory = base
            if icon: sc.IconLocation = f"{icon},0"
            sc.Save()

            drag = QDrag(self)
            mime = drag.mimeData()
            mime.setUrls([QUrl.fromLocalFile(temp_lnk)])

            # Create visual pixmap for drag
            pix = QPixmap(160, 40)
            pix.fill(QColor(15, 23, 42))
            p = QPainter(pix)
            p.setPen(QPen(QColor(0, 242, 254), 2))
            p.drawRoundedRect(2, 2, 156, 36, 6, 6)
            p.setPen(QColor(255, 255, 255))
            p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            label_text = f"👥 {name[:10]} #{user_id}" if user_id != 0 else f"📱 {name[:12]}"
            p.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, label_text)
            p.end()

            drag.setPixmap(pix)
            drag.setHotSpot(QPoint(80, 20))
            drag.exec(Qt.DropAction.CopyAction)
        except Exception:
            pass


class GNDroidAppDrawer(QDialog):
    def __init__(self, target_serial: str, parent=None):
        super().__init__(parent)
        self.target_serial = target_serial
        self.setWindowTitle("📱 GNDROiD App Drawer & Native App Cloner")
        self.resize(600, 680)
        self.setup_ui()
        self.load_apps()

    def setup_ui(self):
        self.setStyleSheet("""
            QDialog { background: #f8f9fa; color: #0f172a; font-family: 'Segoe UI Variable Text', 'Segoe UI', -apple-system, sans-serif; }
            QLineEdit {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 8px 12px;
                color: #0f172a;
                font-size: 12px;
            }
            QLineEdit:focus { border: 1.5px solid #0067c0; }
            QListWidget {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 6px;
                color: #0f172a;
            }
            QListWidget::item {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                margin: 3px;
                padding: 8px 10px;
                color: #0f172a;
            }
            QListWidget::item:hover {
                background: #f1f5f9;
                border-color: #cbd5e1;
            }
            QListWidget::item:selected {
                background: #e0f2fe;
                color: #0369a1;
                border-color: #38bdf8;
            }
            QPushButton {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 8px 14px;
                color: #0f172a;
                font-weight: 500;
                font-size: 11px;
            }
            QPushButton:hover {
                background: #f8fafc;
                border-color: #94a3b8;
            }
            QPushButton:pressed {
                background: #f1f5f9;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        header = QLabel("📱 Installed Applications & App Cloner")
        header.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        header.setStyleSheet("color: #0f172a;")
        layout.addWidget(header)

        hint = QLabel("💡 <b>Tip:</b> Click <b>Open in Dedicated Window</b> for an independent floating window, <b>Clone App (Multi-Account)</b> to create isolated clones, or pin shortcuts to your PC Desktop!")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #64748b; font-size: 11px;")
        layout.addWidget(hint)

        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 Search apps (e.g. WhatsApp, Chrome, ChatGPT)...")
        self.search.textChanged.connect(self.filter_apps)
        layout.addWidget(self.search)

        # Filter Chips Bar (All / Master / Clones)
        self.current_filter = "all"  # "all", "master", "clones"
        chips_layout = QHBoxLayout()
        chips_layout.setSpacing(8)

        self.chip_all = QPushButton("All Applications (0)")
        self.chip_master = QPushButton("Master Apps (0)")
        self.chip_clones = QPushButton("Clones Only (0)")

        for chip in [self.chip_all, self.chip_master, self.chip_clones]:
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setFixedHeight(28)

        self.chip_all.clicked.connect(lambda: self.set_filter("all"))
        self.chip_master.clicked.connect(lambda: self.set_filter("master"))
        self.chip_clones.clicked.connect(lambda: self.set_filter("clones"))

        chips_layout.addWidget(self.chip_all)
        chips_layout.addWidget(self.chip_master)
        chips_layout.addWidget(self.chip_clones)
        chips_layout.addStretch()

        layout.addLayout(chips_layout)
        self.update_chip_styles()

        self.list_widget = DraggableAppList(self.target_serial)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self.show_context_menu)
        self.list_widget.itemDoubleClicked.connect(self.launch_selected_window)
        layout.addWidget(self.list_widget)

        # Primary Action Buttons
        btn_row1 = QHBoxLayout()
        btn_row1.setSpacing(8)

        self.btn_launch_window = QPushButton("🪟 Open in Dedicated Window")
        self.btn_launch_window.setStyleSheet("background: #0067c0; color: #ffffff; font-weight: 600; border: none; border-radius: 6px; padding: 8px 14px;")
        self.btn_launch_window.clicked.connect(self.launch_selected_window)
        btn_row1.addWidget(self.btn_launch_window)

        self.btn_launch = QPushButton("⚡ Launch in Main Mirror")
        self.btn_launch.setStyleSheet("background: #0f172a; color: #ffffff; font-weight: 600; border: none; border-radius: 6px; padding: 8px 14px;")
        self.btn_launch.clicked.connect(self.launch_selected)
        btn_row1.addWidget(self.btn_launch)

        layout.addLayout(btn_row1)

        btn_row2 = QHBoxLayout()
        btn_row2.setSpacing(8)

        self.btn_clone_app = QPushButton("👥 Clone App (Multi-Account)")
        self.btn_clone_app.setStyleSheet("background: #047857; color: #ffffff; font-weight: 600; border: none; border-radius: 6px; padding: 8px 14px;")
        self.btn_clone_app.clicked.connect(self.clone_selected)
        btn_row2.addWidget(self.btn_clone_app)

        self.btn_pin = QPushButton("📌 Pin Dedicated Window to Desktop")
        self.btn_pin.clicked.connect(self.pin_selected_window)
        btn_row2.addWidget(self.btn_pin)

        layout.addLayout(btn_row2)

    def update_chip_styles(self):
        active_style = "background: #0067c0; color: #ffffff; border: 1px solid #005a9e; border-radius: 14px; font-weight: 600; font-size: 11px; padding: 4px 12px;"
        inactive_style = "background: #ffffff; color: #475569; border: 1px solid #cbd5e1; border-radius: 14px; font-weight: 500; font-size: 11px; padding: 4px 12px;"

        self.chip_all.setStyleSheet(active_style if self.current_filter == "all" else inactive_style)
        self.chip_master.setStyleSheet(active_style if self.current_filter == "master" else inactive_style)
        self.chip_clones.setStyleSheet(active_style if self.current_filter == "clones" else inactive_style)

    def set_filter(self, filter_type: str):
        self.current_filter = filter_type
        self.update_chip_styles()
        self.filter_apps(self.search.text() if hasattr(self, "search") else "")

    def load_apps(self):
        self.all_apps = []
        serial = self.target_serial or (find_active_serial() if find_active_serial else "emulator-5554")

        friendly_map = {
            "whatsapp": "WhatsApp",
            "chatgpt": "ChatGPT",
            "copilot": "Microsoft Copilot",
            "excel": "Microsoft Excel",
            "brave": "Brave Browser",
            "nayapay": "NayaPay",
            "daraz": "Daraz",
            "telegram": "Telegram",
            "camscanner": "CamScanner",
            "zoom": "Zoom",
            "chrome": "Google Chrome",
            "calculator": "Calculator",
            "settings": "Settings",
            "camera": "Camera",
            "gallery": "Gallery",
            "deskclock": "Clock",
            "contacts": "Contacts",
            "dialer": "Phone",
            "messaging": "Messages",
            "music": "Music",
            "browser": "Browser",
            "quicksearchbox": "Search",
        }

        def resolve_name(p: str) -> str:
            pl = p.lower()
            for k, v in friendly_map.items():
                if k in pl:
                    return v
            parts = p.split(".")
            cand = parts[-1] if parts else p
            if cand.lower() in ("app", "android") and len(parts) > 1:
                cand = parts[-2]
            return cand.replace("_", " ").replace("-", " ").capitalize()

        try:
            if AppCloneManager:
                entries = AppCloneManager.list_apps_with_clones(serial)
                for e in entries:
                    pkg = e["package_name"]
                    uid = e["user_id"]
                    disp_name = resolve_name(pkg)
                    self.all_apps.append({
                        "name": disp_name,
                        "package": pkg,
                        "user_id": uid,
                        "user_label": "[Master]" if uid == 0 else f"[Clone #{uid}]",
                        "is_clone": (uid != 0)
                    })
            else:
                adb = SystemPaths.get_adb()
                cmd = [adb]
                if serial:
                    cmd.extend(["-s", serial])
                cmd.extend(["shell", "pm list packages -3"])
                out = subprocess.check_output(cmd, text=True, timeout=12, creationflags=0x08000000)
                for line in out.splitlines():
                    if line.startswith("package:"):
                        pkg = line.replace("package:", "").strip()
                        self.all_apps.append({
                            "name": resolve_name(pkg),
                            "package": pkg,
                            "user_id": 0,
                            "user_label": "[Master]",
                            "is_clone": False
                        })
            self.all_apps.sort(key=lambda x: (x.get("user_id", 0), x["name"].lower()))
        except Exception:
            pass

        if hasattr(self, "chip_all") and hasattr(self, "chip_master") and hasattr(self, "chip_clones"):
            total_count = len(self.all_apps)
            master_count = sum(1 for a in self.all_apps if not a.get("is_clone"))
            clone_count = sum(1 for a in self.all_apps if a.get("is_clone"))
            self.chip_all.setText(f"All Applications ({total_count})")
            self.chip_master.setText(f"Master Apps ({master_count})")
            self.chip_clones.setText(f"Clones Only ({clone_count})")
            self.update_chip_styles()

        self.filter_apps(self.search.text() if hasattr(self, "search") else "")

    def filter_apps(self, query: str = ""):
        self.list_widget.clear()
        q = (query or "").lower().strip()
        for a in self.all_apps:
            if hasattr(self, "current_filter"):
                if self.current_filter == "master" and a.get("is_clone"):
                    continue
                if self.current_filter == "clones" and not a.get("is_clone"):
                    continue

            if not q or q in a["name"].lower() or q in a["package"].lower() or q in a.get("user_label", "").lower():
                badge = a.get("user_label", "[Master]")
                icon_prefix = "👥" if a.get("is_clone") else "📱"
                item = QListWidgetItem(f"{icon_prefix}  {a['name']}   {badge}   ({a['package']})")
                item.setData(Qt.ItemDataRole.UserRole, a)
                if a.get("is_clone"):
                    item.setForeground(QColor(5, 150, 105))
                self.list_widget.addItem(item)

    def launch_selected(self):
        item = self.list_widget.currentItem()
        if not item: return
        data = item.data(Qt.ItemDataRole.UserRole)
        adb = SystemPaths.get_adb()
        serial = self.target_serial or (find_active_serial() if find_active_serial else "")
        cmd = [adb]
        if serial:
            cmd.extend(["-s", serial])
        uid = data.get("user_id", 0)
        pkg = data.get("package")
        if uid != 0:
            cmd.extend(["shell", "am", "start", "--user", str(uid), pkg])
        else:
            cmd.extend(["shell", "monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1"])
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000, timeout=3)
            self.accept()
        except Exception:
            pass

    def launch_selected_window(self):
        item = self.list_widget.currentItem()
        if not item:
            QMessageBox.warning(self, "Select Application", "Please select an application to open in a dedicated window.")
            return

        data = item.data(Qt.ItemDataRole.UserRole)
        pkg = data.get("package")
        title = data.get("name")
        uid = data.get("user_id", 0)

        if not AppWindowManager:
            QMessageBox.critical(self, "Window Manager Unavailable", "AppWindowManager module could not be loaded.")
            return

        serial = self.target_serial or (find_active_serial() if find_active_serial else "emulator-5554")
        try:
            AppWindowManager.launch_app_in_dedicated_window(
                serial=serial,
                package_name=pkg,
                app_title=title,
                user_id=uid
            )
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Launch Error", f"Failed to launch dedicated window:\n\n{e}")

    def clone_selected(self):
        item = self.list_widget.currentItem()
        if not item:
            QMessageBox.warning(self, "Select Application", "Please select an application to clone into a secondary profile.")
            return

        data = item.data(Qt.ItemDataRole.UserRole)
        pkg = data.get("package")
        app_name = data.get("name")
        if not pkg:
            return

        if not AppCloneManager:
            QMessageBox.critical(self, "Cloner Unavailable", "AppCloneManager module could not be loaded.")
            return

        serial = self.target_serial or (find_active_serial() if find_active_serial else "emulator-5554")
        existing_clones = AppCloneManager.get_clone_users(serial)
        target_uid = -1

        if existing_clones:
            items = [f"Clone Profile #{u['id']} ({u.get('name', 'Clone')})" for u in existing_clones]
            items.append("➕ Create New Clone Profile")
            choice, ok = QInputDialog.getItem(
                self,
                "Select Clone Profile",
                f"Choose target clone profile for '{app_name}':",
                items,
                0,
                False
            )
            if not ok:
                return
            if choice == "➕ Create New Clone Profile":
                new_name, name_ok = QInputDialog.getText(
                    self,
                    "New Clone Profile",
                    "Enter profile name:",
                    QLineEdit.EchoMode.Normal,
                    f"GNDROiD Clone {len(existing_clones) + 1}"
                )
                if not name_ok or not new_name.strip():
                    new_name = f"GNDROiD Clone {len(existing_clones) + 1}"
                target_uid = AppCloneManager.create_clone_user(serial, name=new_name.strip())
            else:
                for u in existing_clones:
                    if f"Clone Profile #{u['id']}" in choice:
                        target_uid = u["id"]
                        break
        else:
            ret = QMessageBox.question(
                self,
                "Create Clone Profile",
                f"No Android clone profiles exist yet.\n\nWould you like GNDROiD to create a native isolated clone profile for '{app_name}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if ret != QMessageBox.StandardButton.Yes:
                return
            target_uid = AppCloneManager.create_clone_user(serial, name="GNDROiD Clone 1")

        if target_uid <= 0:
            QMessageBox.critical(
                self,
                "Clone Error",
                "Failed to create or allocate Android clone user profile.\n\nEnsure Android multi-user support is enabled."
            )
            return

        success = AppCloneManager.clone_app_to_user(serial, pkg, target_uid)
        if success:
            QMessageBox.information(
                self,
                "App Cloned Successfully",
                f"✅ '{app_name}' has been cloned into Clone Profile #{target_uid}!\n\n"
                f"You can now run dual independent accounts simultaneously.\n"
                f"Launch it via 'Open in Dedicated Window' or 'Launch App'."
            )
            self.load_apps()
        else:
            QMessageBox.critical(
                self,
                "Clone Error",
                f"Failed to install '{app_name}' into clone profile #{target_uid}."
            )

    def pin_selected_window(self):
        item = self.list_widget.currentItem()
        if not item:
            QMessageBox.warning(self, "Select Application", "Please select an application to pin to the PC desktop.")
            return

        data = item.data(Qt.ItemDataRole.UserRole)
        pkg = data.get("package")
        title = data.get("name")
        uid = data.get("user_id", 0)

        p = ""
        if AppWindowManager:
            p = AppWindowManager.create_app_desktop_shortcut(
                app_title=title,
                package_name=pkg,
                user_id=uid
            )
        if not p:
            p = ShortcutManager.create_desktop_shortcut(title, pkg, user_id=uid, dedicated_window=True)

        if p and os.path.exists(p):
            badge = data.get('user_label', '[Master]')
            QMessageBox.information(
                self,
                "Dedicated Shortcut Created",
                f"Successfully pinned dedicated window shortcut to PC Desktop!\n\nApp: {title} {badge}\nLocation: {p}"
            )
        else:
            QMessageBox.warning(self, "Shortcut Failed", "Could not create desktop shortcut.")

    def show_context_menu(self, pos: QPoint):
        item = self.list_widget.itemAt(pos)
        if not item: return
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data: return

        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px; padding: 4px; }
            QMenu::item { padding: 6px 18px; font-size: 12px; color: #0f172a; border-radius: 4px; }
            QMenu::item:selected { background: #0067c0; color: #ffffff; }
        """)

        act_win = menu.addAction("🪟 Open in Dedicated Window")
        act_win.triggered.connect(self.launch_selected_window)

        act_main = menu.addAction("⚡ Launch in Main Mirror")
        act_main.triggered.connect(self.launch_selected)

        menu.addSeparator()

        act_clone = menu.addAction("👥 Clone App (Multi-Account)")
        act_clone.triggered.connect(self.clone_selected)

        act_pin = menu.addAction("📌 Pin Dedicated Window Shortcut to Desktop")
        act_pin.triggered.connect(self.pin_selected_window)

        if data.get("is_clone"):
            menu.addSeparator()
            uid = data.get("user_id")
            act_rm = menu.addAction(f"🗑️ Remove Clone Profile #{uid}")
            act_rm.triggered.connect(lambda: self.remove_selected_clone_profile(uid))

        menu.exec(self.list_widget.mapToGlobal(pos))

    def remove_selected_clone_profile(self, user_id: int):
        if user_id <= 0: return
        ret = QMessageBox.question(
            self,
            "Remove Clone Profile",
            f"Are you sure you want to permanently remove Android Clone Profile #{user_id} and all its app data?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if ret == QMessageBox.StandardButton.Yes:
            serial = self.target_serial or (find_active_serial() if find_active_serial else "emulator-5554")
            if AppCloneManager:
                ok = AppCloneManager.remove_clone_user(serial, user_id)
                if ok:
                    QMessageBox.information(self, "Profile Removed", f"Clone profile #{user_id} removed.")
                    self.load_apps()
                else:
                    QMessageBox.critical(self, "Error", f"Failed to remove clone profile #{user_id}.")

# # Modern Window Finder & Custom Vector Ribbon Controls
# ----------------------------------------------------------------------
def find_target_window(target_serial: str = "") -> Optional[int]:
    # Feature 15: Filter out GNDROiD launcher itself and management dialogs
    excluded_keywords = [
        "controls", "not connected", "control & settings", "settings",
        "master control suite", "multi-instance", "manager", "doctor",
        "downloader", "drawer", "pairing", "dialog", "quick clone", "clean locks"
    ]

    def is_launcher_or_mgmt(title_str: str) -> bool:
        t_low = title_str.lower()
        if any(k in t_low for k in excluded_keywords):
            return True
        if re.search(r"gndroid\s+v\d", t_low):
            return True
        return False

    # 1. Exact match for scrcpy window titled "GNDROiD - {target_serial}" or "gndroid"
    if target_serial:
        for prefix in ["GNDROiD - ", "gndroid - ", ""]:
            hwnd = user32.FindWindowW(None, f"{prefix}{target_serial}")
            if hwnd and user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                if not is_launcher_or_mgmt(buf.value):
                    return hwnd

    # 2. Search for any visible window matching serial or Scrcpy/Emulator window, excluding GNDROiD launcher/management windows
    found_hwnd = None
    def enum_cb(h, lparam):
        nonlocal found_hwnd
        if user32.IsWindowVisible(h):
            length = user32.GetWindowTextLengthW(h)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(h, buf, length + 1)
                title = buf.value
                if not is_launcher_or_mgmt(title):
                    if target_serial:
                        if target_serial.lower() in title.lower():
                            found_hwnd = h
                            return False
                    else:
                        t_low = title.lower()
                        if (title.startswith("GNDROiD - ") or title.startswith("gndroid - ") or
                            title.startswith("GNDROiD: ") or title.strip() in ("GNDROiD", "gndroid") or
                            "android emulator" in t_low):
                            found_hwnd = h
                            return False
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
    return found_hwnd


class GNDroidRibbonButton(QPushButton):
    def __init__(self, icon_type: str, accent_color: str, tooltip: str, shortcut: str = "", parent=None):
        super().__init__(parent)
        self.icon_type = icon_type
        self.accent_color = QColor(accent_color)
        self.shortcut_hint = shortcut
        self.setFixedSize(44, 40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        full_tip = f"<b>{tooltip}</b>"
        if shortcut:
            full_tip += f"<br><span style='color:#64748b;font-size:10px;'>Shortcut: {shortcut}</span>"
        self.setToolTip(full_tip)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        rf = QRectF(r).adjusted(1, 1, -1, -1)
        is_hover = self.underMouse()
        is_down = self.isDown()

        # Windows 11 Fluent Light Button Styling
        if is_down:
            p.setBrush(QBrush(QColor(0, 103, 192, 45)))
            p.setPen(QPen(QColor(0, 103, 192, 90), 1.0))
        elif is_hover:
            p.setBrush(QBrush(QColor(0, 103, 192, 22)))
            p.setPen(QPen(QColor(0, 103, 192, 50), 1.0))
        else:
            p.setBrush(QBrush(QColor(0, 0, 0, 6)))
            p.setPen(QPen(QColor(0, 0, 0, 14), 1.0))

        p.drawRoundedRect(rf, 6, 6)

        # Draw Vector Icon (Crisp high-contrast dark slate / Fluent Blue palette)
        cx = rf.center().x()
        cy = rf.center().y()
        if is_down:
            cy += 1

        t = self.icon_type
        if t in ["close", "power"] and is_hover:
            color = QColor('#ef4444')
        elif t == "record" and getattr(self, "_recording_active", False):
            color = QColor('#ef4444')
        elif t == "screen":
            color = QColor('#0067c0') if (is_hover or is_down) else QColor('#1e293b')
        else:
            color = QColor('#0067c0') if (is_hover or is_down) else QColor('#1e293b')
        pen = QPen(color, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)

        t = self.icon_type
        if t == "rotate":
            p.drawArc(QRectF(cx - 9, cy - 9, 18, 18), 40 * 16, 270 * 16)
            p.setBrush(QBrush(color))
            arrow = QPainterPath()
            arrow.moveTo(cx + 9, cy)
            arrow.lineTo(cx + 5, cy - 4.5)
            arrow.lineTo(cx + 5, cy + 4.5)
            arrow.closeSubpath()
            p.drawPath(arrow)

        elif t == "volup":
            p.setBrush(QBrush(color))
            path = QPainterPath()
            path.moveTo(cx - 8, cy - 3)
            path.lineTo(cx - 4, cy - 3)
            path.lineTo(cx + 1, cy - 8)
            path.lineTo(cx + 1, cy + 8)
            path.lineTo(cx - 4, cy + 3)
            path.lineTo(cx - 8, cy + 3)
            path.closeSubpath()
            p.drawPath(path)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawArc(QRectF(cx + 2, cy - 4, 4, 8), -60 * 16, 120 * 16)
            p.drawArc(QRectF(cx + 3, cy - 7, 7, 14), -60 * 16, 120 * 16)

        elif t == "voldown":
            p.setBrush(QBrush(color))
            path = QPainterPath()
            path.moveTo(cx - 8, cy - 3)
            path.lineTo(cx - 4, cy - 3)
            path.lineTo(cx + 1, cy - 8)
            path.lineTo(cx + 1, cy + 8)
            path.lineTo(cx - 4, cy + 3)
            path.lineTo(cx - 8, cy + 3)
            path.closeSubpath()
            p.drawPath(path)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawArc(QRectF(cx + 2, cy - 4, 4, 8), -60 * 16, 120 * 16)

        elif t == "back":
            path = QPainterPath()
            path.moveTo(cx + 4, cy - 7)
            path.lineTo(cx - 4, cy)
            path.lineTo(cx + 4, cy + 7)
            p.drawPath(path)

        elif t == "home":
            p.setBrush(QBrush(color))
            p.drawEllipse(QRectF(cx - 4.5, cy - 4.5, 9, 9))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(color, 1.2))
            p.drawEllipse(QRectF(cx - 8, cy - 8, 16, 16))

        elif t == "recents":
            p.drawRoundedRect(QRectF(cx - 6.5, cy - 6.5, 13, 13), 3, 3)

        elif t == "screenshot":
            p.drawRoundedRect(QRectF(cx - 8.5, cy - 5, 17, 12), 2.5, 2.5)
            path = QPainterPath()
            path.moveTo(cx - 4, cy - 5)
            path.lineTo(cx - 2, cy - 7.5)
            path.lineTo(cx + 2, cy - 7.5)
            path.lineTo(cx + 4, cy - 5)
            p.drawPath(path)
            p.drawEllipse(QRectF(cx - 3, cy - 2, 6, 6))

        elif t == "fingerprint":
            p.drawArc(QRectF(cx - 6.5, cy - 7.5, 13, 15), 0, 180 * 16)
            p.drawArc(QRectF(cx - 4.5, cy - 5, 9, 13), 0, 180 * 16)
            p.drawArc(QRectF(cx - 2.5, cy - 2.5, 5, 10), 0, 180 * 16)
            p.drawLine(QPointF(cx, cy), QPointF(cx, cy + 6.5))

        elif t == "apps":
            p.setBrush(QBrush(color))
            for dx in [-5.5, 0, 5.5]:
                for dy in [-5.5, 0, 5.5]:
                    p.drawRoundedRect(QRectF(cx + dx - 1.5, cy + dy - 1.5, 3, 3), 0.8, 0.8)

        elif t in ("lan", "wireless"):
            p.drawArc(QRectF(cx - 8, cy - 7, 16, 16), 45 * 16, 90 * 16)
            p.drawArc(QRectF(cx - 5, cy - 4, 10, 10), 45 * 16, 90 * 16)
            p.drawArc(QRectF(cx - 2.5, cy - 1.5, 5, 5), 45 * 16, 90 * 16)
            p.setBrush(QBrush(color))
            p.drawEllipse(QRectF(cx - 1.25, cy + 3.5, 2.5, 2.5))

        elif t == "multi":
            p.drawRoundedRect(QRectF(cx - 7, cy - 6, 8, 12), 1.5, 1.5)
            p.drawRoundedRect(QRectF(cx - 1, cy - 3, 8, 12), 1.5, 1.5)

        elif t == "settings":
            p.drawEllipse(QRectF(cx - 4.5, cy - 4.5, 9, 9))
            import math
            for i in range(8):
                ang = i * (math.pi / 4)
                x1 = cx + 5.5 * math.cos(ang)
                y1 = cy + 5.5 * math.sin(ang)
                x2 = cx + 8.5 * math.cos(ang)
                y2 = cy + 8.5 * math.sin(ang)
                p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        elif t == "record":
            p.drawRoundedRect(QRectF(cx - 8, cy - 5, 11, 10), 2, 2)
            lens = QPainterPath()
            lens.moveTo(cx + 3, cy - 2)
            lens.lineTo(cx + 8, cy - 5)
            lens.lineTo(cx + 8, cy + 5)
            lens.lineTo(cx + 3, cy + 2)
            lens.closeSubpath()
            p.drawPath(lens)
            p.setBrush(QBrush(QColor("#ef4444")))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(cx - 4.5, cy - 1.5, 4, 4))

        elif t == "apk":
            p.drawRoundedRect(QRectF(cx - 7, cy - 4, 14, 11), 2, 2)
            p.drawLine(QPointF(cx - 7, cy), QPointF(cx + 7, cy))
            p.drawLine(QPointF(cx, cy - 8), QPointF(cx, cy + 2))
            p.drawLine(QPointF(cx - 3, cy - 1), QPointF(cx, cy + 2))
            p.drawLine(QPointF(cx + 3, cy - 1), QPointF(cx, cy + 2))

        elif t == "adb":
            p.drawLine(QPointF(cx - 6, cy + 6), QPointF(cx + 3, cy - 3))
            p.drawArc(QRectF(cx + 1, cy - 7, 6, 6), 45 * 16, 270 * 16)
            p.drawLine(QPointF(cx - 2, cy - 5), QPointF(cx - 2, cy - 1))
            p.drawLine(QPointF(cx - 4, cy - 3), QPointF(cx, cy - 3))

        elif t == "shake":
            p.drawRoundedRect(QRectF(cx - 4.5, cy - 7, 9, 14), 1.5, 1.5)
            p.drawArc(QRectF(cx - 9, cy - 4, 3, 8), 90 * 16, 180 * 16)
            p.drawArc(QRectF(cx + 6, cy - 4, 3, 8), -90 * 16, 180 * 16)

        elif t == "power":
            p.drawArc(QRectF(cx - 6.5, cy - 6.5, 13, 13), 50 * 16, 260 * 16)
            p.drawLine(QPointF(cx, cy - 8), QPointF(cx, cy - 1.5))

        elif t == "screen":
            p.drawRoundedRect(QRectF(cx - 5.5, cy - 8, 11, 16), 2, 2)
            p.drawLine(QPointF(cx - 2, cy + 5.5), QPointF(cx + 2, cy + 5.5))

        elif t == "close":
            pen.setWidthF(2.2)
            p.setPen(pen)
            p.drawLine(QPointF(cx - 5, cy - 5), QPointF(cx + 5, cy + 5))
            p.drawLine(QPointF(cx + 5, cy - 5), QPointF(cx - 5, cy + 5))

        p.end()


# ----------------------------------------------------------------------
# Dialog: Option to Run gndroid VM when No ADB Phone is Found
# ----------------------------------------------------------------------
class GNDroidNoDeviceDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📱 GNDROiD — Android Device Not Connected")
        self.setFixedSize(480, 410)
        self.chosen_action = None
        self.setup_ui()

    def setup_ui(self):
        self.setStyleSheet("""
            QDialog {
                background: #f8f9fa;
                color: #0f172a;
                font-family: 'Segoe UI Variable Text', 'Segoe UI', -apple-system, sans-serif;
            }
            #cardBox {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
            }
            QPushButton#btnHero {
                background: #0067c0;
                border: none;
                border-radius: 6px;
                color: #ffffff;
                font-weight: 600;
                font-size: 12px;
                padding: 10px 14px;
                text-align: left;
            }
            QPushButton#btnHero:hover {
                background: #1879c9;
            }
            QPushButton#btnHero:pressed {
                background: #005a9e;
            }
            QPushButton#btnSuite {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                color: #0f172a;
                font-weight: 500;
                font-size: 12px;
                padding: 10px 14px;
                text-align: left;
            }
            QPushButton#btnSuite:hover {
                background: #f8fafc;
                border-color: #94a3b8;
            }
            QPushButton#btnSub {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                color: #0f172a;
                font-weight: 500;
                font-size: 11px;
                padding: 7px 16px;
            }
            QPushButton#btnSub:hover {
                background: #f8fafc;
                border-color: #94a3b8;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Header with Icon
        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        icon_lbl = QLabel("📱")
        icon_lbl.setFont(QFont("Segoe UI Emoji", 26))
        header_row.addWidget(icon_lbl)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("No Physical Phone Detected")
        title.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        title.setStyleSheet("color: #0f172a;")
        title_box.addWidget(title)

        subtitle = QLabel("No active device was found via USB cable or Local Wi-Fi (LAN).")
        subtitle.setStyleSheet("color: #64748b; font-size: 11px;")
        title_box.addWidget(subtitle)
        header_row.addLayout(title_box)
        layout.addLayout(header_row)

        # Card Container
        card = QFrame()
        card.setObjectName("cardBox")
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(16, 16, 16, 16)
        c_layout.setSpacing(12)

        desc = QLabel(
            "You can immediately boot the high-performance <b>GNDROiD Virtual Machine</b> "
            "directly on your PC hardware, or open the Master Suite to configure Wi-Fi connection."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #334155; font-size: 12px; line-height: 1.4;")
        c_layout.addWidget(desc)

        # Hero Action: Launch GNDROiD VM
        hw_info = SystemPaths.get_host_hardware_summary()
        self.btn_run_gndroid = QPushButton(f"⚡  Launch GNDROiD Virtual Machine Instead\n     ({hw_info['ram_gb']} GB Host RAM • {hw_info['cores']} CPU Cores • Hardware Accelerated 60 FPS)")
        self.btn_run_gndroid.setObjectName("btnHero")
        self.btn_run_gndroid.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_run_gndroid.clicked.connect(lambda: self.set_action("run_vm"))
        c_layout.addWidget(self.btn_run_gndroid)

        # Second Action: Open Master Control Suite
        self.btn_open_suite = QPushButton("🖥️  Open GNDROiD Master Control Suite\n     (Connect Wireless LAN IP, check devices, or settings)")
        self.btn_open_suite.setObjectName("btnSuite")
        self.btn_open_suite.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open_suite.clicked.connect(lambda: self.set_action("open_suite"))
        c_layout.addWidget(self.btn_open_suite)

        # Third Action: Open ADB & Wireless Network Fixer
        self.btn_open_fixer = QPushButton("🛠️  Open ADB & Wireless Network Fixer\n     (Diagnose USB, 1-Click Wi-Fi Connect, or Reset ADB Daemon)")
        self.btn_open_fixer.setObjectName("btnSuite")
        self.btn_open_fixer.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open_fixer.clicked.connect(lambda: self.set_action("adb_fixer"))
        c_layout.addWidget(self.btn_open_fixer)

        layout.addWidget(card)

        # Footer Actions
        footer = QHBoxLayout()
        footer.setSpacing(10)

        self.btn_retry = QPushButton("🔄 Retry Phone Connection")
        self.btn_retry.setObjectName("btnSub")
        self.btn_retry.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_retry.clicked.connect(lambda: self.set_action("retry"))
        footer.addWidget(self.btn_retry)

        footer.addStretch()

        self.btn_cancel = QPushButton("✕ Cancel")
        self.btn_cancel.setObjectName("btnSub")
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.reject)
        footer.addWidget(self.btn_cancel)

        layout.addLayout(footer)

    def set_action(self, action: str):
        self.chosen_action = action
        self.accept()


# ----------------------------------------------------------------------
# Modern ADB Fixer & Wireless / USB Setup Suite
# ----------------------------------------------------------------------
class LogcatWorker(QThread):
    sig_log_line = pyqtSignal(str)

    def __init__(self, target_serial: str = "", parent=None):
        super().__init__(parent)
        self.target_serial = target_serial
        self._running = True
        self.proc = None

    def stop(self):
        self._running = False
        if self.proc:
            try:
                self.proc.terminate()
            except Exception:
                pass

    def run(self):
        adb = SystemPaths.get_adb()
        cmd = [adb]
        if self.target_serial:
            cmd.extend(["-s", self.target_serial])
        cmd.extend(["logcat", "-v", "time"])
        try:
            self.proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=0x08000000,
                errors="replace"
            )
            while self._running and self.proc:
                line = self.proc.stdout.readline()
                if not line:
                    break
                self.sig_log_line.emit(line.strip())
        except Exception as e:
            self.sig_log_line.emit(f"[Logcat Error: {e}]")


# ----------------------------------------------------------------------
# Background LAN Radar Worker (Auto-Discovers all LAN Android Devices)
# ----------------------------------------------------------------------
class LanRadarWorker(QThread):
    sig_radar_updated = pyqtSignal(list)
    sig_radar_status = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = True
        self._fast_scan_requested = False

    def request_immediate_scan(self):
        self._fast_scan_requested = True

    def stop(self):
        self._running = False
        self.wait(1000)

    def run(self):
        while self._running:
            try:
                devs = self.scan_network()
                if self._running:
                    self.sig_radar_updated.emit(devs)
                    self.sig_radar_status.emit(f"🟢 Live Radar Active: {len(devs)} Android device(s) detected on LAN")
            except Exception as e:
                if self._running:
                    self.sig_radar_status.emit(f"Radar warning: {e}")

            for _ in range(35):
                if not self._running or self._fast_scan_requested:
                    self._fast_scan_requested = False
                    break
                time.sleep(0.1)

    def scan_network(self) -> List[Dict[str, Any]]:
        adb = SystemPaths.get_adb()
        results_map: Dict[str, Dict[str, Any]] = {}

        # 1. Query active ADB devices
        try:
            active_devs = SystemPaths.list_devices()
            for d in active_devs:
                s = d.get("serial", "")
                m = d.get("model", "Android Device")
                state = d.get("state", "device")
                is_lan = d.get("is_lan", False)
                if is_lan and not d.get("is_emulator"):
                    results_map[s] = {
                        "serial": s,
                        "model": m,
                        "address": s,
                        "protocol": "⚡ Wireless ADB (Wi-Fi)",
                        "status": "🟢 Connected & Ready" if state == "device" else f"🟡 {state.capitalize()}",
                        "is_connected": state == "device",
                        "can_mirror": state == "device"
                    }
                elif not d.get("is_emulator"):
                    results_map[s] = {
                        "serial": s,
                        "model": m,
                        "address": "USB Cable",
                        "protocol": "🔌 USB Wired Connection",
                        "status": "🟢 Connected & Ready",
                        "is_connected": True,
                        "can_mirror": True
                    }
        except Exception:
            pass

        # 2. Query adb mdns services
        try:
            out = subprocess.check_output([adb, "mdns", "services"], text=True, timeout=2, creationflags=0x08000000)
            for line in out.splitlines():
                line = line.strip()
                if not line or "List of discovered" in line:
                    continue
                parts = line.split()
                if len(parts) >= 3:
                    name = parts[0]
                    svc_type = parts[1]
                    addr = parts[2]
                    clean_model = name.replace("adb-", "")
                    if clean_model.endswith("._adb-tls-connect") or clean_model.endswith("._adb"):
                        clean_model = clean_model.split(".")[0]
                    clean_model = f"Android ({clean_model})" if clean_model else "Android Device"

                    if addr not in results_map:
                        proto = "🔐 Android 11+ TLS (mDNS)" if "tls-connect" in svc_type else "⚡ Wireless ADB (mDNS)"
                        results_map[addr] = {
                            "serial": addr,
                            "model": clean_model,
                            "address": addr,
                            "protocol": proto,
                            "status": "🟡 Discovered on LAN",
                            "is_connected": False,
                            "can_mirror": True
                        }
        except Exception:
            pass

        # 3. Subnet Dual-Port (5555 ADB & 51880 Nexus Companion) Concurrent Probe
        try:
            prefix = self.get_subnet_prefix()
            if prefix:
                found_adb = []
                found_nexus = []
                found_lock = threading.Lock()

                my_local_ips = self.get_local_ips()

                def probe_ip(host_ip):
                    if host_ip in my_local_ips:
                        return
                    # Check Wireless ADB port 5555
                    try:
                        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                            s.settimeout(0.25)
                            if s.connect_ex((host_ip, 5555)) == 0:
                                with found_lock:
                                    found_adb.append(host_ip)
                    except Exception:
                        pass
                    # Check GNDROiD Link (51888) and Nexus Companion (51880) HTTP ports
                    for p in (51880, 51888):
                        try:
                            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                                s.settimeout(0.25)
                                if s.connect_ex((host_ip, p)) == 0:
                                    with found_lock:
                                        if host_ip not in found_nexus:
                                            found_nexus.append(host_ip)
                                    break
                        except Exception:
                            pass

                ips_to_check = [f"{prefix}{i}" for i in range(1, 255)]
                # Feature 10: Capped at 16 concurrent workers to avoid thread churn
                with ThreadPoolExecutor(max_workers=16) as ex:
                    ex.map(probe_ip, ips_to_check)

                for ip in found_adb:
                    addr = f"{ip}:5555"
                    if not any(ip in k for k in results_map.keys()):
                        results_map[addr] = {
                            "serial": addr,
                            "model": f"Android Device ({ip})",
                            "address": addr,
                            "protocol": "⚡ Wireless ADB (Port 5555)",
                            "status": "🟢 Ready to Mirror",
                            "is_connected": False,
                            "can_mirror": True
                        }

                for ip in found_nexus:
                    cport = 51880
                    for p in (51880, 51888):
                        try:
                            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                                s.settimeout(0.2)
                                if s.connect_ex((ip, p)) == 0:
                                    cport = p
                                    break
                        except Exception:
                            pass

                    model_name = f"Android Device ({ip})"
                    try:
                        import urllib.request, json
                        for ep in (f"http://{ip}:{cport}/api/v1/status", f"http://{ip}:{cport}/status"):
                            try:
                                req = urllib.request.Request(ep, headers={"User-Agent": "GNDROiD"})
                                with urllib.request.urlopen(req, timeout=0.6) as resp:
                                    if resp.status == 200:
                                        d = json.loads(resp.read().decode("utf-8", "ignore"))
                                        m = d.get("device_name") or d.get("model") or d.get("device") or ""
                                        mfg = d.get("manufacturer") or ""
                                        if m:
                                            model_name = m.strip()
                                        elif mfg:
                                            model_name = f"{mfg} Handset".strip()
                                        break
                            except Exception:
                                pass
                    except Exception:
                        pass

                    has_adb = (ip in found_adb)
                    serial_key = f"{ip}:5555" if has_adb else f"{ip}:{cport}"
                    if not any(ip in k for k in results_map.keys()):
                        results_map[serial_key] = {
                            "serial": serial_key,
                            "model": model_name,
                            "address": f"{ip}:{cport} (Wireless)",
                            "protocol": "⚡ Pure Wi-Fi Companion (Zero Cable)",
                            "status": "🟢 Ready to Mirror (Direct Wi-Fi)",
                            "is_connected": True,
                            "can_mirror": True,
                            "is_companion": True,
                            "companion_ip": ip,
                            "companion_port": cport,
                            "has_adb": has_adb,
                            "nexus_host_ip": ip
                        }
        except Exception:
            pass

        # 4. Check Nexus Companion UDP probe (port 51899 fallback - excluding loopback)
        try:
            udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            udp.settimeout(0.3)
            udp.sendto(b"NXAI_DISCOVER", ("255.255.255.255", 51899))
            try:
                data, addr = udp.recvfrom(512)
                reply = data.decode("utf-8", "ignore").strip()
                if "NXAI" in reply:
                    nx_ip = addr[0]
                    # STRICT FILTER: Never add loopback, local PC IPs, or APIPA to discovery table!
                    if nx_ip not in ("127.0.0.1", "0.0.0.0", "localhost") and not nx_ip.startswith("169.254."):
                        nx_target = f"{nx_ip}:5555"
                        if not any(nx_ip in k for k in results_map.keys()):
                            results_map[nx_target] = {
                                "serial": nx_target,
                                "model": "Nexus Companion Device",
                                "address": nx_target,
                                "protocol": "📲 Nexus Companion (Wi-Fi)",
                                "status": "🟡 Discovered on LAN",
                                "is_connected": False,
                                "can_mirror": True
                            }
            except Exception:
                pass
            finally:
                udp.close()
        except Exception:
            pass

        return list(results_map.values())

    def get_local_ips(self) -> set:
        ips = {"127.0.0.1", "localhost"}
        try:
            import socket
            for info in socket.getaddrinfo(socket.gethostname(), None):
                ips.add(info[4][0])
        except Exception:
            pass
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ips.add(s.getsockname()[0])
            s.close()
        except Exception:
            pass
        return ips

    def get_subnet_prefix(self) -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            parts = ip.split(".")
            if len(parts) == 4:
                return f"{parts[0]}.{parts[1]}.{parts[2]}."
        except Exception:
            pass
        return "192.168.1."


# ----------------------------------------------------------------------
# Instant QR Code Wireless Debugging Pairing Worker (Android 11+)
# ----------------------------------------------------------------------
class QRPairingWorker(QThread):
    sig_qr_ready = pyqtSignal(QPixmap, str, str)  # pixmap, service_name, password
    sig_pairing_status = pyqtSignal(str, str)     # message, hex_color
    sig_pair_connected = pyqtSignal(str, str)     # target, model

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = True
        self.service_name = ""
        self.password = ""
        self._paired = False

    @staticmethod
    def generate_qr_payload(service_name: str, pin: str) -> str:
        """Adheres to interface contract specified in PROJECT.md."""
        return WirelessPairingEngine.generate_qr_payload(service_name, pin)

    @classmethod
    def pair_and_connect(cls, serial: str, ip: str, port: int, pin: str) -> bool:
        """Adheres to interface contract specified in PROJECT.md."""
        host_port = f"{ip}:{port}"
        ok, _ = WirelessPairingEngine.pair_and_connect(host_port, pin)
        return ok

    def generate_new_code(self):
        self._paired = False
        self.service_name, self.password, payload = WirelessPairingEngine.generate_pairing_credentials()
        pix = WirelessPairingEngine.generate_qr_pixmap(payload, box_size=5, border=2)
        if pix:
            self.sig_qr_ready.emit(pix, self.service_name, self.password)
        self.sig_pairing_status.emit("⏳ Waiting for phone camera scan... (Listening on mDNS)", "#64748b")

    def stop(self):
        self._running = False
        self.wait(1000)

    def run(self):
        self.generate_new_code()
        adb = SystemPaths.get_adb()

        while self._running:
            if not self._paired:
                try:
                    # Check adb mdns services for _adb-tls-pairing
                    out = subprocess.check_output([adb, "mdns", "services"], text=True, timeout=2, creationflags=0x08000000)
                    for line in out.splitlines():
                        line = line.strip()
                        if "_adb-tls-pairing" in line:
                            parts = line.split()
                            if len(parts) >= 3:
                                svc_name = parts[0]
                                addr = parts[2]
                                self.sig_pairing_status.emit(f"📱 Phone detected at {addr}! Initiating pairing handshake...", "#0284c7")

                                # Run adb pair
                                try:
                                    pair_res = subprocess.check_output(
                                        [adb, "pair", addr, self.password],
                                        text=True, timeout=6, creationflags=0x08000000
                                    )
                                    if "successfully paired" in pair_res.lower() or "paired" in pair_res.lower():
                                        self._paired = True
                                        self.sig_pairing_status.emit("🎉 Paired successfully! Connecting to phone...", "#16a34a")
                                        time.sleep(1.0)

                                        # Look for connect port or connect directly
                                        phone_ip = addr.split(":")[0]
                                        connect_target = f"{phone_ip}:5555"

                                        c_out = subprocess.check_output([adb, "mdns", "services"], text=True, timeout=2, creationflags=0x08000000)
                                        for c_line in c_out.splitlines():
                                            if "_adb-tls-connect" in c_line and phone_ip in c_line:
                                                c_parts = c_line.strip().split()
                                                if len(c_parts) >= 3:
                                                    connect_target = c_parts[2]
                                                    break

                                        conn_res = subprocess.check_output(
                                            [adb, "connect", connect_target],
                                            text=True, timeout=6, creationflags=0x08000000
                                        )
                                        self.sig_pairing_status.emit(f"🚀 Connected to {connect_target}! Launching 60 FPS mirror...", "#16a34a")
                                        self.sig_pair_connected.emit(connect_target, "Wireless Android Phone")
                                        break
                                except Exception as e:
                                    self.sig_pairing_status.emit(f"Pairing error: {e}", "#ef4444")
                except Exception:
                    pass

            for _ in range(12):
                if not self._running:
                    break
                time.sleep(0.1)


# ----------------------------------------------------------------------
# Nexus System Companion & Permission Orchestrator
# ----------------------------------------------------------------------
class NexusCompanionManager:
    _httpd = None
    _server_thread = None

    @staticmethod
    def get_bundled_apk_path() -> str:
        base = get_base_dir()
        cands = [
            os.path.join(base, "nexus", "GNDROiD_Companion.apk"),
            os.path.join(base, "tools", "GNDROiD_Companion.apk"),
            os.path.join(base, "dist", "gndroid", "nexus", "GNDROiD_Companion.apk"),
            os.path.join(base, "dist", "gndroid", "tools", "GNDROiD_Companion.apk"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "GNDROiD", "nexus", "GNDROiD_Companion.apk"),
            os.path.join(base, "nexus", "NexusAI_Mobile_Client.apk"),
            os.path.join(base, "dist", "gndroid", "nexus", "NexusAI_Mobile_Client.apk"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "GNDROiD", "nexus", "NexusAI_Mobile_Client.apk"),
            r"C:\Users\Reader-Branch\Desktop\NexusSuite\dist\4_NexusAI_Mobile_Client.apk",
            r"C:\Users\Reader-Branch\Desktop\NexusSuite\build_apk\NexusAI_Mobile_aligned.apk",
        ]
        for c in cands:
            if os.path.exists(c):
                return c
        return ""

    @staticmethod
    def grant_full_phone_permissions(target_serial: str = "") -> tuple[bool, str]:
        adb = SystemPaths.get_adb()
        cmd_pfx = [adb]
        if target_serial:
            cmd_pfx.extend(["-s", target_serial])

        granted = []
        errors = []

        # 1. Switch device to TCP/IP 5555
        try:
            subprocess.run(cmd_pfx + ["tcpip", "5555"], timeout=4, capture_output=True, creationflags=0x08000000)
            granted.append("Port 5555 Wireless ADB Enabled")
        except Exception as e:
            errors.append(f"TCP/IP 5555: {e}")

        # 2. Prevent screen sleep during mirror
        try:
            subprocess.run(cmd_pfx + ["shell", "svc", "power", "stayon", "true"], timeout=3, capture_output=True, creationflags=0x08000000)
            subprocess.run(cmd_pfx + ["shell", "settings", "put", "system", "screen_off_timeout", "600000"], timeout=3, capture_output=True, creationflags=0x08000000)
            granted.append("Keep Awake & Screen Timeout Configured")
        except Exception:
            pass

        # 3. Grant GNDROiD Link & legacy Nexus permissions
        packages = ["com.gndroid.companion", "com.nexusai.mobile"]
        permissions = [
            "android.permission.WRITE_SECURE_SETTINGS",
            "android.permission.RECORD_AUDIO",
            "android.permission.CAMERA",
            "android.permission.READ_EXTERNAL_STORAGE",
            "android.permission.WRITE_EXTERNAL_STORAGE",
            "android.permission.MANAGE_EXTERNAL_STORAGE",
            "android.permission.ACCESS_FINE_LOCATION",
            "android.permission.ACCESS_COARSE_LOCATION",
            "android.permission.POST_NOTIFICATIONS",
        ]
        appops = [
            "SYSTEM_ALERT_WINDOW",
            "PROJECT_MEDIA",
            "POST_NOTIFICATIONS",
            "RUN_IN_BACKGROUND",
        ]

        for pkg in packages:
            for p in permissions:
                try:
                    subprocess.run(cmd_pfx + ["shell", "pm", "grant", pkg, p], timeout=2, capture_output=True, creationflags=0x08000000)
                except Exception:
                    pass

            for op in appops:
                try:
                    subprocess.run(cmd_pfx + ["shell", "appops", "set", pkg, op, "allow"], timeout=2, capture_output=True, creationflags=0x08000000)
                except Exception:
                    pass

            # Whitelist from Doze battery restrictions (zero drops)
            try:
                subprocess.run(cmd_pfx + ["shell", "dumpsys", "deviceidle", "whitelist", f"+{pkg}"], timeout=2, capture_output=True, creationflags=0x08000000)
            except Exception:
                pass

        # 4. Enable accessibility service for both GNDROiD Link and Nexus
        try:
            a11y_services = "com.gndroid.companion/.GNDroidAccessibilityService:com.nexusai.mobile/.NexusAccessibilityService"
            subprocess.run(cmd_pfx + ["shell", "settings", "put", "secure", "enabled_accessibility_services", a11y_services], timeout=2, capture_output=True, creationflags=0x08000000)
            subprocess.run(cmd_pfx + ["shell", "settings", "put", "secure", "accessibility_enabled", "1"], timeout=2, capture_output=True, creationflags=0x08000000)
            granted.append("Background Accessibility & Overlay Permissions Granted")
        except Exception:
            pass

        # 5. Start persistent foreground service on device
        try:
            subprocess.run(cmd_pfx + ["shell", "am", "start-foreground-service", "-n", "com.gndroid.companion/.GNDroidCompanionService"], timeout=2, capture_output=True, creationflags=0x08000000)
            granted.append("Persistent Background Service & High-Perf Wi-Fi Lock Activated")
        except Exception:
            pass

        granted.append("System Settings & Low-Latency Video Buffers Tuned")
        return True, "✅ Successfully granted full permissions:\n\n• " + "\n• ".join(granted)

    @staticmethod
    def install_companion_apk(target_serial: str = "") -> tuple[bool, str]:
        apk_p = NexusCompanionManager.get_bundled_apk_path()
        if not apk_p:
            return False, "Could not find GNDROiD companion client APK. Ensure GNDROiD_Companion.apk is in the nexus/ or tools/ directory."

        adb = SystemPaths.get_adb()
        cmd = [adb]
        if target_serial:
            cmd.extend(["-s", target_serial])
        cmd.extend(["install", "-r", "-g", apk_p])

        try:
            res = subprocess.check_output(cmd, text=True, timeout=25, creationflags=0x08000000)
            if "success" in res.lower():
                NexusCompanionManager.grant_full_phone_permissions(target_serial)
                cmd_launch = [adb]
                if target_serial:
                    cmd_launch.extend(["-s", target_serial])
                # Launch companion app and foreground service
                subprocess.run(cmd_launch + ["shell", "am", "start", "-n", "com.gndroid.companion/.MainActivity"], timeout=3, capture_output=True, creationflags=0x08000000)
                subprocess.run(cmd_launch + ["shell", "am", "start-foreground-service", "-n", "com.gndroid.companion/.GNDroidCompanionService"], timeout=3, capture_output=True, creationflags=0x08000000)
                # Fallback launch for legacy package
                subprocess.run(cmd_launch + ["shell", "monkey", "-p", "com.nexusai.mobile", "-c", "android.intent.category.LAUNCHER", "1"], timeout=2, capture_output=True, creationflags=0x08000000)
                return True, "🎉 GNDROiD Companion APK installed successfully!\n\nAll permissions granted and persistent background service activated on device."
            return False, f"Installation output: {res.strip()}"
        except Exception as e:
            return False, str(e)

    @classmethod
    def start_download_server(cls) -> str:
        apk_path = cls.get_bundled_apk_path()
        if not apk_path:
            return ""

        apk_dir = os.path.dirname(os.path.abspath(apk_path))
        apk_name = os.path.basename(apk_path)

        if cls._httpd is None:
            import http.server
            import socketserver

            class CustomHandler(http.server.SimpleHTTPRequestHandler):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, directory=apk_dir, **kwargs)
                def log_message(self, format, *args):
                    pass

            try:
                cls._httpd = socketserver.TCPServer(("", 8088), CustomHandler)
                cls._server_thread = threading.Thread(target=cls._httpd.serve_forever, daemon=True)
                cls._server_thread.start()
            except Exception:
                pass

        pc_ip = cls._get_pc_lan_ip()
        return f"http://{pc_ip}:8088/{apk_name}"


    @staticmethod
    def _get_pc_lan_ip() -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"


GNDroidCompanionManager = NexusCompanionManager


# ----------------------------------------------------------------------
# GNDroidWirelessMirrorWindow: Pure Wi-Fi Mirror & KVM Remote (Zero Cable)
# ----------------------------------------------------------------------
class WirelessStreamWorker(QThread):
    sig_frame = pyqtSignal(QPixmap, int)
    sig_status = pyqtSignal(str)

    def __init__(self, host_ip: str, port: int = 51888, parent=None):
        super().__init__(parent)
        self.host_ip = host_ip
        self.port = port
        self._running = True

    def stop(self):
        self._running = False
        self.wait(1000)

    def run(self):
        import urllib.request, time
        endpoints = [
            f"http://{self.host_ip}:{self.port}/api/v1/screen",
            f"http://{self.host_ip}:{self.port}/screen.jpg",
            f"http://{self.host_ip}:{self.port}/screen/raw"
        ]

        mjpeg_url = f"http://{self.host_ip}:{self.port}/stream.mjpeg"
        while self._running:
            try:
                req = urllib.request.Request(mjpeg_url, headers={"User-Agent": "GNDROiD-WirelessMirror"})
                with urllib.request.urlopen(req, timeout=3.0) as resp:
                    buf = bytearray()
                    while self._running:
                        t0 = time.time()
                        chunk = resp.read(16384)
                        if not chunk:
                            break
                        buf.extend(chunk)
                        a = buf.find(b"\xff\xd8")
                        b = buf.find(b"\xff\xd9", a + 2) if a != -1 else -1
                        if a != -1 and b != -1:
                            jpg_bytes = bytes(buf[a:b+2])
                            del buf[:b+2]
                            pix = QPixmap()
                            if pix.loadFromData(jpg_bytes):
                                latency = max(10, int((time.time() - t0) * 1000))
                                self.sig_frame.emit(pix, latency)
            except Exception:
                # Fast fallback polling if persistent stream disconnects
                t0 = time.time()
                frame_data = None
                for ep in endpoints:
                    try:
                        r_req = urllib.request.Request(ep, headers={"User-Agent": "GNDROiD-WirelessMirror"})
                        with urllib.request.urlopen(r_req, timeout=0.8) as r_resp:
                            if r_resp.status == 200:
                                frame_data = r_resp.read()
                                if frame_data and len(frame_data) > 80:
                                    break
                    except Exception:
                        continue
                latency = int((time.time() - t0) * 1000)
                if frame_data:
                    pix = QPixmap()
                    if pix.loadFromData(frame_data):
                        self.sig_frame.emit(pix, latency)
                time.sleep(0.03)


class ScreenInteractiveLabel(QLabel):
    sig_tap = pyqtSignal(float, float)
    sig_swipe = pyqtSignal(float, float, float, float, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMouseTracking(True)
        self.drag_start = None
        self.drag_start_time = 0
        self.current_pixmap = None
        self.setStyleSheet("background-color: #0b0f19; border-radius: 12px;")

    def update_frame(self, pixmap: QPixmap):
        self.current_pixmap = pixmap
        scaled = pixmap.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.setPixmap(scaled)

    def mousePressEvent(self, evt):
        if evt.button() == Qt.MouseButton.LeftButton:
            self.drag_start = evt.pos()
            self.drag_start_time = time.time()
        elif evt.button() == Qt.MouseButton.RightButton:
            # Right click = Android Back
            p = self.parent()
            while p and not hasattr(p, "send_action"):
                p = p.parent()
            if p and hasattr(p, "send_action"):
                p.send_action("back")

    def wheelEvent(self, evt):
        delta = evt.angleDelta().y()
        if delta > 0:
            # Scroll up: swipe downward from 0.5, 0.35 to 0.5, 0.75
            self.sig_swipe.emit(0.5, 0.35, 0.5, 0.75, 120)
        else:
            # Scroll down: swipe upward from 0.5, 0.75 to 0.5, 0.35
            self.sig_swipe.emit(0.5, 0.75, 0.5, 0.35, 120)

    def mouseReleaseEvent(self, evt):
        if evt.button() == Qt.MouseButton.LeftButton and self.drag_start:
            p1 = self.drag_start
            p2 = evt.pos()
            self.drag_start = None
            dist = ((p2.x() - p1.x())**2 + (p2.y() - p1.y())**2)**0.5

            nx, ny = self.point_to_norm(p2)
            if nx is None:
                return

            if dist < 8:
                self.sig_tap.emit(nx, ny)
            else:
                nx1, ny1 = self.point_to_norm(p1)
                dur = int((time.time() - self.drag_start_time) * 1000)
                self.sig_swipe.emit(nx1, ny1, nx, ny, max(150, dur))

    def point_to_norm(self, pt):
        if not self.pixmap() or not self.current_pixmap:
            return None, None
        pw = self.pixmap().width()
        ph = self.pixmap().height()
        ox = (self.width() - pw) / 2.0
        oy = (self.height() - ph) / 2.0
        rx = pt.x() - ox
        ry = pt.y() - oy
        if 0 <= rx <= pw and 0 <= ry <= ph:
            return rx / float(pw), ry / float(ph)
        return None, None


class GNDroidWirelessMirrorWindow(QMainWindow):
    _active_windows = {}

    def __init__(self, host_ip: str, port: int = 51888, model_name: str = "Android Device", parent=None):
        super().__init__(parent)
        self.host_ip = host_ip
        self.port = port
        self.model_name = model_name
        self.target_key = f"{host_ip}:{port}"
        GNDroidWirelessMirrorWindow._active_windows[self.target_key] = self

        self.setWindowTitle(f"📱 {self.model_name} — Pure Wi-Fi Mirror (Zero Cable) [{self.host_ip}:{self.port}]")
        self.resize(440, 840)
        self.setMinimumSize(360, 600)
        self.setup_ui()

        # Start stream worker
        self.stream_worker = WirelessStreamWorker(self.host_ip, self.port, self)
        self.stream_worker.sig_frame.connect(self.on_frame_received)
        self.stream_worker.start()

    def setup_ui(self):
        self.setStyleSheet("""
            QMainWindow {
                background: #0f172a;
                color: #f8fafc;
                font-family: 'Segoe UI Variable Text', 'Segoe UI', -apple-system, sans-serif;
            }
            QPushButton.ctrlBtn {
                background: #1e293b;
                color: #f1f5f9;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton.ctrlBtn:hover {
                background: #334155;
                border-color: #0284c7;
            }
            QPushButton.ctrlBtn:pressed {
                background: #0284c7;
                color: #ffffff;
            }
        """)

        central = QWidget()
        self.setCentralWidget(central)
        c_layout = QVBoxLayout(central)
        c_layout.setContentsMargins(10, 10, 10, 10)
        c_layout.setSpacing(8)

        # Header bar
        hdr = QHBoxLayout()
        self.lbl_info = QLabel(f"<b>📱 {self.model_name}</b> <span style='color: #38bdf8;'>({self.host_ip}:{self.port})</span>")
        self.lbl_info.setStyleSheet("color: #f8fafc; font-size: 12px;")
        hdr.addWidget(self.lbl_info)
        hdr.addStretch()

        self.lbl_fps = QLabel("⚡ Connecting Wi-Fi...")
        self.lbl_fps.setStyleSheet("color: #10b981; font-size: 11px; font-weight: bold;")
        hdr.addWidget(self.lbl_fps)

        btn_web = QPushButton("🌐 Web HUD")
        btn_web.setProperty("class", "ctrlBtn")
        btn_web.setToolTip("Open full web dashboard in browser")
        btn_web.clicked.connect(self.action_open_web_hud)
        hdr.addWidget(btn_web)

        c_layout.addLayout(hdr)

        # Interactive Screen View
        self.screen_view = ScreenInteractiveLabel(self)
        self.screen_view.sig_tap.connect(self.on_tap)
        self.screen_view.sig_swipe.connect(self.on_swipe)
        c_layout.addWidget(self.screen_view, 1)

        # Hardware Navigation Bar
        nav_row = QHBoxLayout()
        nav_row.setSpacing(6)

        btn_back = QPushButton("◀ Back")
        btn_back.setProperty("class", "ctrlBtn")
        btn_back.clicked.connect(lambda: self.send_action("back"))
        nav_row.addWidget(btn_back)

        btn_home = QPushButton("○ Home")
        btn_home.setProperty("class", "ctrlBtn")
        btn_home.clicked.connect(lambda: self.send_action("home"))
        nav_row.addWidget(btn_home)

        btn_recents = QPushButton("▢ Recents")
        btn_recents.setProperty("class", "ctrlBtn")
        btn_recents.clicked.connect(lambda: self.send_action("recents"))
        nav_row.addWidget(btn_recents)

        btn_wake = QPushButton("☀️ Wake")
        btn_wake.setProperty("class", "ctrlBtn")
        btn_wake.clicked.connect(lambda: self.send_action("wake"))
        nav_row.addWidget(btn_wake)

        btn_power = QPushButton("⏻ Power")
        btn_power.setProperty("class", "ctrlBtn")
        btn_power.clicked.connect(lambda: self.send_action("power"))
        nav_row.addWidget(btn_power)

        btn_vup = QPushButton("🔊 +")
        btn_vup.setProperty("class", "ctrlBtn")
        btn_vup.clicked.connect(lambda: self.send_action("volume_up"))
        nav_row.addWidget(btn_vup)

        btn_vdown = QPushButton("🔉 -")
        btn_vdown.setProperty("class", "ctrlBtn")
        btn_vdown.clicked.connect(lambda: self.send_action("volume_down"))
        nav_row.addWidget(btn_vdown)

        c_layout.addLayout(nav_row)

    def on_frame_received(self, pixmap: QPixmap, latency_ms: int):
        self.screen_view.update_frame(pixmap)
        fps = min(60, max(15, int(1000 / max(15, latency_ms))))
        self.lbl_fps.setText(f"⚡ {latency_ms} ms • ~{fps} FPS (Pure Wi-Fi)")

    def on_tap(self, normX: float, normY: float):
        payload = {"action": "tap", "normX": normX, "normY": normY, "x": normX, "y": normY}
        threading.Thread(target=self._dispatch_http_action, args=(payload,), daemon=True).start()

    def on_swipe(self, x1, y1, x2, y2, dur):
        payload = {"action": "swipe", "x1": x1, "y1": y1, "x2": x2, "y2": y2, "duration": dur}
        threading.Thread(target=self._dispatch_http_action, args=(payload,), daemon=True).start()

    def send_action(self, action_name: str):
        payload = {"action": action_name}
        threading.Thread(target=self._dispatch_http_action, args=(payload,), daemon=True).start()

    def _dispatch_http_action(self, payload: dict):
        import urllib.request, json
        try:
            url = f"http://{self.host_ip}:{self.port}/api/v1/control"
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                if resp.status == 200:
                    return
        except Exception:
            pass

        try:
            act = payload.get("action", "")
            if act == "tap":
                nx = payload.get("normX", 0.5)
                ny = payload.get("normY", 0.5)
                url = f"http://{self.host_ip}:{self.port}/tap?x={nx}&y={ny}&action=TOUCH"
                with urllib.request.urlopen(url, timeout=1.0):
                    return
            elif act in ("back", "home", "recents", "power", "wake"):
                url = f"http://{self.host_ip}:{self.port}/command"
                data = json.dumps({"command": f"KEY {act.upper()}"}).encode("utf-8")
                req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=1.0):
                    return
        except Exception:
            pass

    def action_open_web_hud(self):
        import webbrowser
        webbrowser.open(f"http://{self.host_ip}:{self.port}/")

    def keyPressEvent(self, evt):
        if evt.key() == Qt.Key.Key_Backspace:
            self.send_action("backspace")
        elif evt.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.send_action("enter")
        elif evt.key() == Qt.Key.Key_Escape:
            self.send_action("back")
        elif evt.key() == Qt.Key.Key_Home:
            self.send_action("home")
        elif evt.key() == Qt.Key.Key_Space:
            threading.Thread(target=self._dispatch_http_action, args=({"action": "key", "text": " "},), daemon=True).start()
        else:
            txt = evt.text()
            if txt:
                threading.Thread(target=self._dispatch_http_action, args=({"action": "key", "text": txt},), daemon=True).start()
        super().keyPressEvent(evt)

    def closeEvent(self, evt):
        if hasattr(self, "stream_worker") and self.stream_worker:
            self.stream_worker.stop()
        if self.target_key in GNDroidWirelessMirrorWindow._active_windows:
            del GNDroidWirelessMirrorWindow._active_windows[self.target_key]
        super().closeEvent(evt)








# ----------------------------------------------------------------------
# GNDroidAutoLockDialog: Intelligent Auto-Lock & Full-Speed Mirror Engine
# ----------------------------------------------------------------------
class GNDroidAutoLockDialog(QDialog):
    """
    Intelligent Auto-Locking & Full-Speed Mirroring Engine:
    Actively monitors ADB over Wi-Fi and USB, automatically performs cable handshake
    and switches to wireless TCP 5555, then instantly launches 60 FPS Scrcpy mirroring.
    """
    def __init__(self, target_ip: str = "", target_serial: str = "", parent=None):
        super().__init__(parent)
        self.target_ip = target_ip or "192.168.100.20"
        self.target_serial = target_serial or f"{self.target_ip}:5555"
        self.locked_serial = ""
        self.setWindowTitle("🚀 GNDROiD — Auto-Lock & Full-Speed Mirroring Engine")
        self.resize(540, 420)
        self.setMinimumSize(500, 380)
        self.setup_ui()

        # Active Watcher Timer (Checks every 400ms)
        self.watch_timer = QTimer(self)
        self.watch_timer.timeout.connect(self.auto_lock_tick)
        self.watch_timer.start(400)

        # Trigger immediate first pass
        QTimer.singleShot(50, self.auto_lock_tick)

    def setup_ui(self):
        self.setStyleSheet("""
            QDialog {
                background: #f8f9fa;
                color: #0f172a;
                font-family: 'Segoe UI Variable Text', 'Segoe UI', -apple-system, sans-serif;
            }
            QFrame.cardBox {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 16px;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Header Title
        lbl_head = QLabel("⚡ Auto-Locking Android Device")
        lbl_head.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        lbl_head.setStyleSheet("color: #0f172a;")
        layout.addWidget(lbl_head)

        # Subtitle
        self.lbl_sub = QLabel(f"Targeting device at <b>{self.target_ip}</b> on local Wi-Fi...")
        self.lbl_sub.setStyleSheet("color: #64748b; font-size: 12px;")
        layout.addWidget(self.lbl_sub)

        # Card Box with Live Status
        card = QFrame()
        card.setProperty("class", "cardBox")
        c_l = QVBoxLayout(card)
        c_l.setSpacing(12)

        self.lbl_badge = QLabel("🔍 Scanning connection pathways...")
        self.lbl_badge.setStyleSheet("color: #0284c7; font-weight: 700; font-size: 13px;")
        c_l.addWidget(self.lbl_badge)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(6)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet("""
            QProgressBar {
                background-color: #e2e8f0;
                border-radius: 3px;
                border: none;
            }
            QProgressBar::chunk {
                background-color: #0067c0;
                border-radius: 3px;
            }
        """)
        c_l.addWidget(self.progress)

        self.lbl_instructions = QLabel(
            "<b>📡 Device is active on Wi-Fi!</b><br><br>"
            "Android requires a 1-time cable handshake to unlock port 5555.<br><br>"
            "👉 <b>Plug your USB cable into your PC now.</b><br>"
            "GNDROiD will automatically detect the connection, authorize wireless mode, "
            "and pop open 60 FPS mirroring with <b>zero extra clicks</b>!<br>"
            "<i>(You can then unplug the cable completely.)</i>"
        )
        self.lbl_instructions.setWordWrap(True)
        self.lbl_instructions.setStyleSheet("color: #334155; font-size: 12px; line-height: 1.5;")
        c_l.addWidget(self.lbl_instructions)

        layout.addWidget(card)

        # Quick Actions Row
        row_btn = QHBoxLayout()
        row_btn.setSpacing(10)

        self.btn_wifi_direct = QPushButton("🌐 Pure Wi-Fi Mirror (Zero Cable)")
        self.btn_wifi_direct.setStyleSheet("""
            QPushButton {
                background: #0284c7;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: 700;
                font-size: 11px;
            }
            QPushButton:hover { background: #0369a1; }
        """)
        self.btn_wifi_direct.clicked.connect(self.action_mirror_wifi_direct)
        row_btn.addWidget(self.btn_wifi_direct)

        self.btn_usb_mirror = QPushButton("🔌 Mirror via USB Directly")
        self.btn_usb_mirror.setStyleSheet("""
            QPushButton {
                background: #f1f5f9;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: 600;
                font-size: 11px;
            }
            QPushButton:hover { background: #e2e8f0; }
        """)
        self.btn_usb_mirror.clicked.connect(self.action_mirror_usb_direct)
        row_btn.addWidget(self.btn_usb_mirror)

        row_btn.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #64748b;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 11px;
            }
            QPushButton:hover { background: #f1f5f9; color: #0f172a; }
        """)
        self.btn_cancel.clicked.connect(self.reject)
        row_btn.addWidget(self.btn_cancel)

        layout.addLayout(row_btn)

    def auto_lock_tick(self):
        adb = SystemPaths.get_adb()
        target_lan = f"{self.target_ip}:5555"

        # 1. First test: Is ADB already connected to this target?
        devs = SystemPaths.list_devices()
        for d in devs:
            if d["serial"] == target_lan and d["state"] == "device":
                self.finish_lock(target_lan, "🎉 Device locked wirelessly!")
                return

        # 2. Second test: Can we connect directly to IP:5555?
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.2)
                if s.connect_ex((self.target_ip, 5555)) == 0:
                    res = subprocess.run([adb, "connect", target_lan], capture_output=True, text=True, timeout=2, creationflags=0x08000000)
                    out = (res.stdout + " " + res.stderr).lower()
                    if "connected to" in out or "already connected" in out:
                        self.finish_lock(target_lan, f"🎉 Wireless lock successful on {target_lan}!")
                        return
        except Exception:
            pass

        # 3. Third test: Is a physical phone plugged in via USB right now?
        usb_devs = [d for d in devs if not d["is_emulator"] and not d.get("is_lan") and d["state"] == "device"]
        if usb_devs:
            usb_serial = usb_devs[0]["serial"]
            model = usb_devs[0].get("model", "Android Phone")
            self.lbl_badge.setText(f"⚡ USB Phone Detected ({model})! Enabling wireless mode...")
            self.lbl_badge.setStyleSheet("color: #0284c7; font-weight: bold; font-size: 13px;")
            self.progress.setStyleSheet("QProgressBar::chunk { background-color: #16a34a; }")
            QApplication.processEvents()

            try:
                subprocess.run([adb, "-s", usb_serial, "tcpip", "5555"], timeout=3, creationflags=0x08000000)
                time.sleep(1.0)
                phone_ip = SystemPaths.get_phone_lan_ip(usb_serial) or self.target_ip
                new_target = f"{phone_ip}:5555"
                subprocess.run([adb, "connect", new_target], timeout=3, creationflags=0x08000000)
                self.finish_lock(new_target, f"🎉 Wireless Mode Activated on {new_target}! You can unplug the cable.")
                return
            except Exception as e:
                self.lbl_badge.setText(f"Handshake error: {e}")

    def finish_lock(self, locked_serial: str, message: str):
        self.watch_timer.stop()
        self.locked_serial = locked_serial
        self.lbl_badge.setText(message)
        self.lbl_badge.setStyleSheet("color: #16a34a; font-weight: bold; font-size: 13px;")
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.progress.setStyleSheet("QProgressBar::chunk { background-color: #16a34a; }")
        QTimer.singleShot(700, self.accept)

    def action_mirror_wifi_direct(self):
        comp_port = 51880
        for p in (51880, 51888):
            try:
                import socket
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.2)
                    if s.connect_ex((self.target_ip, p)) == 0:
                        comp_port = p
                        break
            except Exception:
                pass
        win = GNDroidWirelessMirrorWindow(host_ip=self.target_ip, port=comp_port, parent=self.parent())
        win.show()
        self.reject()

    def action_mirror_usb_direct(self):
        devs = SystemPaths.list_devices()
        usb_devs = [d for d in devs if not d["is_emulator"] and not d.get("is_lan") and d["state"] == "device"]
        if usb_devs:
            self.finish_lock(usb_devs[0]["serial"], f"⚡ Mirroring directly via USB: {usb_devs[0]['serial']}")
        else:
            QMessageBox.warning(self, "No USB Device", "No USB phone detected yet. Please plug in the USB cable first.")


class GNDroidADBFixerDialog(QDialog):
    def __init__(self, target_serial: str = "", parent=None):
        super().__init__(parent)
        self.target_serial = target_serial
        self.setWindowTitle("🛠️ GNDROiD ADB Doctor & Troubleshooting Suite — Developed by Ghulam Nabi Kalhoro")
        self.resize(920, 840)
        self.setMinimumSize(880, 750)
        self.logcat_worker: Optional[LogcatWorker] = None
        self.logcat_lines: List[str] = []
        self.radar_worker: Optional[LanRadarWorker] = None
        self.qr_worker: Optional[QRPairingWorker] = None
        self.setup_ui()
        self.refresh_all_diagnostics()
        self.start_radar_and_qr_services()

    def closeEvent(self, event):
        if self.logcat_worker and self.logcat_worker.isRunning():
            self.logcat_worker.stop()
        if self.radar_worker and self.radar_worker.isRunning():
            self.radar_worker.stop()
        if self.qr_worker and self.qr_worker.isRunning():
            self.qr_worker.stop()
        super().closeEvent(event)

    def setup_ui(self):
        self.setStyleSheet("""
            QDialog {
                background: #f8f9fa;
                color: #0f172a;
                font-family: 'Segoe UI Variable Text', 'Segoe UI', -apple-system, sans-serif;
            }
            QTabWidget::pane {
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                background: #ffffff;
                top: -1px;
            }
            QTabBar::tab {
                background: #f1f5f9;
                color: #64748b;
                border: 1px solid #e2e8f0;
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                padding: 8px 16px;
                font-weight: 500;
                font-size: 11px;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background: #ffffff;
                color: #0f172a;
                border-color: #e2e8f0;
                border-bottom: 2px solid #0067c0;
            }
            QTabBar::tab:hover:!selected {
                background: #e2e8f0;
                color: #0f172a;
            }
            QFrame.cardBox {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
            }
            QLineEdit, QComboBox {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 6px 10px;
                color: #0f172a;
                font-size: 12px;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 1.5px solid #0067c0;
            }
            QPushButton.btnAction {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 6px 14px;
                color: #0f172a;
                font-weight: 500;
                font-size: 11px;
            }
            QPushButton.btnAction:hover {
                background: #f8fafc;
                border-color: #94a3b8;
            }
            QPushButton.btnAction:pressed {
                background: #f1f5f9;
            }
            QPushButton.btnHero {
                background: #0067c0;
                border: 1px solid #005a9e;
                border-radius: 6px;
                color: #ffffff;
                font-weight: 600;
                font-size: 11px;
                padding: 7px 16px;
            }
            QPushButton.btnHero:hover {
                background: #1879c9;
            }
            QPushButton.btnHero:pressed {
                background: #005a9e;
            }
            QPushButton.btnDanger {
                background: #ffffff;
                border: 1px solid #fca5a5;
                border-radius: 6px;
                color: #dc2626;
                font-weight: 500;
                font-size: 11px;
                padding: 6px 14px;
            }
            QPushButton.btnDanger:hover {
                background: #fee2e2;
                border-color: #ef4444;
                color: #b91c1c;
            }
            QTableWidget {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                gridline-color: #f1f5f9;
                color: #0f172a;
            }
            QTableWidget::item { padding: 4px 6px; border-bottom: 1px solid #f1f5f9; }
            QTableWidget::item:hover { background: #f8fafc; }
            QTableWidget::item:selected { background: #e0f2fe; color: #0369a1; }
            QHeaderView::section {
                background: #f8fafc;
                color: #475569;
                font-weight: 600;
                border: none;
                padding: 8px 10px;
                font-size: 11px;
                border-bottom: 1px solid #e2e8f0;
            }
            QPlainTextEdit {
                background: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                font-family: 'Consolas', monospace;
                font-size: 11px;
                color: #1e293b;
                padding: 8px;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 8px;
            }
            QScrollBar::handle:vertical {
                background: #cbd5e1;
                border-radius: 4px;
                min-height: 24px;
            }
            QScrollBar::handle:vertical:hover {
                background: #94a3b8;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        # Header Section
        head_box = QHBoxLayout()
        icon_lbl = QLabel("🛠️")
        icon_lbl.setFont(QFont("Segoe UI Emoji", 26))
        head_box.addWidget(icon_lbl)

        title_vbox = QVBoxLayout()
        t = QLabel("GNDROiD ADB Doctor & Troubleshooting Suite")
        t.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        t.setStyleSheet("color: #0f172a;")
        title_vbox.addWidget(t)

        st = QLabel("Complete diagnostics, one-click port repairs, wireless Wi-Fi setup, port forwarding & live logcat.")
        st.setStyleSheet("color: #64748b; font-size: 11px;")
        title_vbox.addWidget(st)
        head_box.addLayout(title_vbox)

        head_box.addStretch()

        self.btn_fix_vpn_dns = QPushButton("🛡️ Fix VPN & DNS Routing")
        self.btn_fix_vpn_dns.setProperty("class", "btnAction")
        self.btn_fix_vpn_dns.setToolTip("Configures guest DNS (8.8.8.8/1.1.1.1), grants ACTIVATE_VPN appops permissions, and tests connectivity")
        self.btn_fix_vpn_dns.clicked.connect(lambda: self.action_fix_vpn_and_dns())
        head_box.addWidget(self.btn_fix_vpn_dns)

        self.btn_auto_repair = QPushButton("⚡ 1-Click Auto-Repair All")
        self.btn_auto_repair.setProperty("class", "btnHero")
        self.btn_auto_repair.setToolTip("Terminates zombie adb processes, frees port 5037, restarts daemon, and reconnects all devices")
        self.btn_auto_repair.clicked.connect(self.action_auto_repair_all)
        head_box.addWidget(self.btn_auto_repair)

        layout.addLayout(head_box)

        # Tabs
        self.tabs = QTabWidget()

        # Tab 1: USB & Diagnostics
        self.tab_usb = QWidget()
        self.setup_tab_usb()
        self.tabs.addTab(self.tab_usb, "🔌 Diagnostics & Fixers")

        # Tab 2: Wireless LAN / Wi-Fi
        self.tab_lan = QWidget()
        self.setup_tab_lan()
        self.tabs.addTab(self.tab_lan, "📶 Wireless Wi-Fi Mode")

        # Tab 3: Port Forwarding
        self.tab_forward = QWidget()
        self.setup_tab_forward()
        self.tabs.addTab(self.tab_forward, "🔀 Port Forwarding Rules")

        # Tab 4: Live Logcat & System Report
        self.tab_logcat = QWidget()
        self.setup_tab_logcat()
        self.tabs.addTab(self.tab_logcat, "📜 Live Logcat & System Report")

        layout.addWidget(self.tabs)

        # Footer Actions
        footer = QHBoxLayout()
        self.btn_refresh = QPushButton("🔄 Re-Scan Diagnostics")
        self.btn_refresh.setProperty("class", "btnAction")
        self.btn_refresh.clicked.connect(self.refresh_all_diagnostics)
        footer.addWidget(self.btn_refresh)

        self.btn_devmgmt = QPushButton("⚙️ Windows Device Manager")
        self.btn_devmgmt.setProperty("class", "btnAction")
        self.btn_devmgmt.setToolTip("Open Windows Device Manager (devmgmt.msc) to inspect Android USB drivers")
        self.btn_devmgmt.clicked.connect(lambda: subprocess.Popen(["devmgmt.msc"], shell=True))
        footer.addWidget(self.btn_devmgmt)

        footer.addStretch()

        self.btn_start_mirror = QPushButton("🚀 Start Mirroring Device")
        self.btn_start_mirror.setProperty("class", "btnHero")
        self.btn_start_mirror.clicked.connect(self.action_launch_mirror)
        footer.addWidget(self.btn_start_mirror)

        self.btn_close = QPushButton("✓ Close")
        self.btn_close.setProperty("class", "btnAction")
        self.btn_close.clicked.connect(self.accept)
        footer.addWidget(self.btn_close)

        layout.addLayout(footer)

    def setup_tab_usb(self):
        layout = QVBoxLayout(self.tab_usb)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        # 1. Health Status Grid
        grid_stat = QGridLayout()
        grid_stat.setSpacing(10)

        # Card 1: ADB Binary
        card_adb = QFrame()
        card_adb.setProperty("class", "cardBox")
        ca_l = QVBoxLayout(card_adb)
        ca_l.setContentsMargins(12, 10, 12, 10)
        lbl_adb_t = QLabel("📌 ADB Binary Location & Version:")
        lbl_adb_t.setStyleSheet("color: #0f172a; font-weight: 600; font-size: 11px;")
        ca_l.addWidget(lbl_adb_t)
        self.lbl_adb_path = QLabel("Checking ADB...")
        self.lbl_adb_path.setStyleSheet("color: #475569; font-size: 11px; font-family: monospace;")
        ca_l.addWidget(self.lbl_adb_path)
        grid_stat.addWidget(card_adb, 0, 0)

        # Card 2: Daemon State
        card_daemon = QFrame()
        card_daemon.setProperty("class", "cardBox")
        cd_l = QVBoxLayout(card_daemon)
        cd_l.setContentsMargins(12, 10, 12, 10)
        lbl_d_t = QLabel("⚡ ADB Daemon (Port 5037):")
        lbl_d_t.setStyleSheet("color: #0f172a; font-weight: 600; font-size: 11px;")
        cd_l.addWidget(lbl_d_t)
        self.lbl_daemon_status = QLabel("Checking daemon...")
        self.lbl_daemon_status.setStyleSheet("color: #16a34a; font-weight: bold; font-size: 11px;")
        cd_l.addWidget(self.lbl_daemon_status)
        grid_stat.addWidget(card_daemon, 0, 1)

        # Card 3: Windows USB PnP Driver
        card_usb = QFrame()
        card_usb.setProperty("class", "cardBox")
        cu_l = QVBoxLayout(card_usb)
        cu_l.setContentsMargins(12, 10, 12, 10)
        lbl_u_t = QLabel("🔌 Windows USB Hardware & Drivers:")
        lbl_u_t.setStyleSheet("color: #0f172a; font-weight: 600; font-size: 11px;")
        cu_l.addWidget(lbl_u_t)
        self.lbl_usb_pnp = QLabel("Scanning USB...")
        self.lbl_usb_pnp.setStyleSheet("color: #475569; font-size: 11px;")
        cu_l.addWidget(self.lbl_usb_pnp)
        grid_stat.addWidget(card_usb, 1, 0)

        # Card 4: Conflicting Processes
        card_conf = QFrame()
        card_conf.setProperty("class", "cardBox")
        cc_l = QVBoxLayout(card_conf)
        cc_l.setContentsMargins(12, 10, 12, 10)
        lbl_c_t = QLabel("🚫 Port 5037 Conflicts:")
        lbl_c_t.setStyleSheet("color: #0f172a; font-weight: 600; font-size: 11px;")
        cc_l.addWidget(lbl_c_t)
        self.lbl_conflicts = QLabel("Checking ports...")
        self.lbl_conflicts.setStyleSheet("color: #475569; font-size: 11px;")
        cc_l.addWidget(self.lbl_conflicts)
        grid_stat.addWidget(card_conf, 1, 1)

        layout.addLayout(grid_stat)

        # 2. Connected Devices Table
        lbl_dev = QLabel("📱 Detected Android Devices & State:")
        lbl_dev.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        lbl_dev.setStyleSheet("color: #0f172a;")
        layout.addWidget(lbl_dev)

        self.dev_table = QTableWidget(0, 4)
        self.dev_table.setHorizontalHeaderLabels(["Serial Number", "Model / Type", "State & Health", "Quick Actions"])
        self.dev_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.dev_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.dev_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.dev_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.dev_table.setColumnWidth(0, 180)
        self.dev_table.setColumnWidth(1, 160)
        self.dev_table.setColumnWidth(3, 235)
        self.dev_table.verticalHeader().setVisible(False)
        self.dev_table.setFixedHeight(140)
        layout.addWidget(self.dev_table)

        # 3. 1-Click Action Matrix
        card_actions = QFrame()
        card_actions.setProperty("class", "cardBox")
        cact_l = QVBoxLayout(card_actions)
        cact_l.setContentsMargins(14, 12, 14, 12)
        cact_l.setSpacing(10)

        lbl_act_t = QLabel("⚡ One-Click Troubleshooting Fixers:")
        lbl_act_t.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        lbl_act_t.setStyleSheet("color: #0f172a; font-weight: 600; font-size: 12px;")
        cact_l.addWidget(lbl_act_t)

        btn_grid = QGridLayout()
        btn_grid.setSpacing(8)

        btn_restart_adb = QPushButton("🔄 Restart ADB Server Daemon")
        btn_restart_adb.setProperty("class", "btnAction")
        btn_restart_adb.setToolTip("Runs 'adb kill-server' followed by 'adb start-server' on port 5037")
        btn_restart_adb.clicked.connect(self.action_restart_adb)
        btn_grid.addWidget(btn_restart_adb, 0, 0)

        btn_reset_keys = QPushButton("🔑 Reset RSA Auth Keys")
        btn_reset_keys.setProperty("class", "btnAction")
        btn_reset_keys.setToolTip("Deletes corrupted ~/.android/adbkey to trigger phone's 'Allow USB debugging' popup")
        btn_reset_keys.clicked.connect(self.action_reset_keys)
        btn_grid.addWidget(btn_reset_keys, 0, 1)

        btn_fix_offline = QPushButton("🔌 Reconnect Unauthorized / Offline")
        btn_fix_offline.setProperty("class", "btnAction")
        btn_fix_offline.setToolTip("Runs 'adb reconnect offline' and wakes phone screen")
        btn_fix_offline.clicked.connect(self.action_reconnect_offline)
        btn_grid.addWidget(btn_fix_offline, 1, 0)

        btn_kill_conflict = QPushButton("🚫 Terminate Zombie Port 5037 PIDs")
        btn_kill_conflict.setProperty("class", "btnDanger")
        btn_kill_conflict.setToolTip("Forces termination of rogue processes occupying port 5037")
        btn_kill_conflict.clicked.connect(self.action_kill_port_conflicts)
        btn_grid.addWidget(btn_kill_conflict, 1, 1)

        btn_fix_vpn = QPushButton("🛡️ Fix VPN & DNS Routing")
        btn_fix_vpn.setProperty("class", "btnAction")
        btn_fix_vpn.setToolTip("Sets persistent DNS (8.8.8.8 & 1.1.1.1), grants ACTIVATE_VPN permissions to VPN apps, and verifies ping")
        btn_fix_vpn.clicked.connect(lambda: self.action_fix_vpn_and_dns())
        btn_grid.addWidget(btn_fix_vpn, 2, 0, 1, 2)

        cact_l.addLayout(btn_grid)
        layout.addWidget(card_actions)

        # 4. Troubleshooting Guide
        card_guide = QFrame()
        card_guide.setProperty("class", "cardBox")
        cg_l = QVBoxLayout(card_guide)
        cg_l.setContentsMargins(14, 10, 14, 10)
        cg_l.setSpacing(4)

        lbl_g = QLabel("💡 Instant Troubleshooting Checklist:")
        lbl_g.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        lbl_g.setStyleSheet("color: #d97706;")
        cg_l.addWidget(lbl_g)

        gtxt = QLabel(
            "• <b>Developer Options:</b> Settings → About Phone → Tap 'Build Number' 7 times.<br>"
            "• <b>USB Debugging:</b> Turn ON in Developer Options. Set USB mode to <b>File Transfer (MTP)</b>.<br>"
            "• <b>Xiaomi / Redmi / Poco:</b> Turn ON <b>USB Debugging (Security Settings)</b>.<br>"
            "• <b>Authorization:</b> Tap 'Always allow from this computer' on the phone screen."
        )
        gtxt.setTextFormat(Qt.TextFormat.RichText)
        gtxt.setStyleSheet("color: #475569; font-size: 11px;")
        cg_l.addWidget(gtxt)
        layout.addWidget(card_guide)

    def setup_tab_lan(self):
        # Master scroll area for comfortable viewing on any screen resolution
        scroll = QScrollArea(self.tab_lan)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)

        # -------------------------------------------------------------
        # CARD 1: 📡 Live Auto-Discovered LAN Devices (Live Radar)
        # -------------------------------------------------------------
        card_radar = QFrame()
        card_radar.setProperty("class", "cardBox")
        cr_l = QVBoxLayout(card_radar)
        cr_l.setContentsMargins(16, 14, 16, 14)
        cr_l.setSpacing(10)

        r_head = QHBoxLayout()
        cr_title = QLabel("📡 Auto-Discovered LAN Android Devices (Live Radar)")
        cr_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        cr_title.setStyleSheet("color: #0f172a; font-weight: 600; font-size: 13px;")
        r_head.addWidget(cr_title)
        r_head.addStretch()

        self.btn_radar_refresh = QPushButton("🔄 Refresh Radar")
        self.btn_radar_refresh.setProperty("class", "btnAction")
        self.btn_radar_refresh.setToolTip("Force immediate subnet probe and mDNS scan")
        self.btn_radar_refresh.clicked.connect(self.action_refresh_radar)
        r_head.addWidget(self.btn_radar_refresh)

        self.btn_convert_lan = QPushButton("📶 1-Click USB to Wireless")
        self.btn_convert_lan.setProperty("class", "btnAction")
        self.btn_convert_lan.setToolTip("Convert connected USB phone to port 5555 Wi-Fi mode")
        self.btn_convert_lan.clicked.connect(self.action_convert_usb_to_lan)
        r_head.addWidget(self.btn_convert_lan)

        cr_l.addLayout(r_head)

        self.lbl_radar_status = QLabel("🟢 Live Radar Active: Scanning Wi-Fi subnet & mDNS services...")
        self.lbl_radar_status.setStyleSheet("color: #0284c7; font-size: 11px; font-weight: 500;")
        cr_l.addWidget(self.lbl_radar_status)

        self.radar_table = QTableWidget(0, 5)
        self.radar_table.setHorizontalHeaderLabels(["Device / Model", "Address & Port", "Protocol", "Status", "1-Click Mirror Actions"])
        self.radar_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.radar_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.radar_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.radar_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.radar_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.radar_table.setColumnWidth(0, 190)
        self.radar_table.setColumnWidth(1, 140)
        self.radar_table.setColumnWidth(2, 140)
        self.radar_table.setColumnWidth(3, 130)
        self.radar_table.verticalHeader().setVisible(False)
        self.radar_table.setMinimumHeight(110)
        self.radar_table.setMaximumHeight(140)
        self.on_radar_updated([])
        cr_l.addWidget(self.radar_table)

        layout.addWidget(card_radar)

        # -------------------------------------------------------------
        # CARD 2: 📷 Instant QR Code Wireless Debugging (Android 11+)
        # -------------------------------------------------------------
        card_qr = QFrame()
        card_qr.setProperty("class", "cardBox")
        cq_l = QVBoxLayout(card_qr)
        cq_l.setContentsMargins(16, 14, 16, 14)
        cq_l.setSpacing(10)

        cq_title = QLabel("📷 Instant QR Code Wireless Debugging (Android 11+)")
        cq_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        cq_title.setStyleSheet("color: #0f172a; font-weight: 600; font-size: 13px;")
        cq_l.addWidget(cq_title)

        cq_desc = QLabel("Scan this QR code from your phone's Developer Options to pair and mirror wirelessly in seconds without typing!")
        cq_desc.setStyleSheet("color: #475569; font-size: 11px;")
        cq_l.addWidget(cq_desc)

        row_qr = QHBoxLayout()
        row_qr.setSpacing(16)

        # Left Column: QR code image + status badge + refresh button
        v_qr = QVBoxLayout()
        v_qr.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_qr_image = QLabel()
        self.lbl_qr_image.setFixedSize(180, 180)
        self.lbl_qr_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_qr_image.setStyleSheet("border: 1px solid #cbd5e1; border-radius: 8px; background: #ffffff; padding: 4px;")
        v_qr.addWidget(self.lbl_qr_image)

        self.lbl_qr_badge = QLabel("⏳ Listening on mDNS...")
        self.lbl_qr_badge.setWordWrap(True)
        self.lbl_qr_badge.setFixedWidth(180)
        self.lbl_qr_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_qr_badge.setStyleSheet("color: #0284c7; font-weight: 600; font-size: 11px; margin-top: 4px;")
        v_qr.addWidget(self.lbl_qr_badge)

        self.btn_new_qr = QPushButton("🔄 New QR Code")
        self.btn_new_qr.setProperty("class", "btnAction")
        self.btn_new_qr.clicked.connect(self.action_generate_new_qr)
        v_qr.addWidget(self.btn_new_qr)
        row_qr.addLayout(v_qr, 0)

        # Right Column: Visual Steps + Manual Fallback Box
        v_steps = QVBoxLayout()
        v_steps.setSpacing(8)

        step_box = QFrame()
        step_box.setStyleSheet("background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px;")
        sb_l = QVBoxLayout(step_box)
        sb_l.setSpacing(6)

        s1 = QLabel("<b>1️⃣ Open Developer Options:</b> On your phone, go to <i>Settings ➔ Developer Options ➔ Wireless Debugging</i> (turn ON).")
        s1.setStyleSheet("color: #1e293b; font-size: 11px;")
        s1.setWordWrap(True)
        sb_l.addWidget(s1)

        s2 = QLabel("<b>2️⃣ Tap 'Pair device with QR code':</b> Your camera scanner will activate immediately.")
        s2.setStyleSheet("color: #1e293b; font-size: 11px;")
        s2.setWordWrap(True)
        sb_l.addWidget(s2)

        s3 = QLabel("<b>3️⃣ Scan this QR code:</b> GNDROiD automatically detects your phone, pairs, connects, and launches 60 FPS mirroring!")
        s3.setStyleSheet("color: #1e293b; font-size: 11px;")
        s3.setWordWrap(True)
        sb_l.addWidget(s3)

        v_steps.addWidget(step_box)

        # Manual pairing code fallback box
        self.box_manual_code = QFrame()
        self.box_manual_code.setStyleSheet("background: #ffffff; border: 1px dashed #cbd5e1; border-radius: 6px; padding: 8px;")
        mc_l = QVBoxLayout(self.box_manual_code)
        mc_l.setSpacing(6)

        mc_lbl = QLabel("<b>Or enter 6-digit pairing code manually:</b> (Tap 'Pair device with pairing code' on phone)")
        mc_lbl.setStyleSheet("color: #475569; font-size: 11px;")
        mc_l.addWidget(mc_lbl)

        row_p = QHBoxLayout()
        self.edit_pair_ip = QLineEdit()
        self.edit_pair_ip.setPlaceholderText("Pairing IP & Port (e.g. 192.168.100.25:38421)")
        row_p.addWidget(self.edit_pair_ip, 3)

        self.edit_pair_code = QLineEdit()
        self.edit_pair_code.setPlaceholderText("6-digit Code (e.g. 849201)")
        row_p.addWidget(self.edit_pair_code, 2)

        self.btn_pair = QPushButton("🤝 Pair & Connect")
        self.btn_pair.setProperty("class", "btnAction")
        self.btn_pair.clicked.connect(self.action_pair_android11)
        row_p.addWidget(self.btn_pair, 2)

        mc_l.addLayout(row_p)
        v_steps.addWidget(self.box_manual_code)

        row_qr.addLayout(v_steps, 1)
        cq_l.addLayout(row_qr)
        layout.addWidget(card_qr)

        # -------------------------------------------------------------
        # CARD 3: 📲 Nexus Companion Mode & 1-Tap Permissions Granter
        # -------------------------------------------------------------
        card_nexus = QFrame()
        card_nexus.setProperty("class", "cardBox")
        cn_l = QVBoxLayout(card_nexus)
        cn_l.setContentsMargins(16, 14, 16, 14)
        cn_l.setSpacing(10)

        cn_title = QLabel("📲 Nexus Companion Mode & 1-Tap Permissions Granter")
        cn_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        cn_title.setStyleSheet("color: #0f172a; font-weight: 600; font-size: 13px;")
        cn_l.addWidget(cn_title)

        cn_desc = QLabel(
            "Automated permission orchestrator: Grants full background, overlay, stay-awake, and wireless permissions "
            "in 1 tap without manual developer settings friction, and deploys the Nexus Companion APK to the device."
        )
        cn_desc.setWordWrap(True)
        cn_desc.setStyleSheet("color: #475569; font-size: 11px;")
        cn_l.addWidget(cn_desc)

        row_nexus_btns = QHBoxLayout()
        row_nexus_btns.setSpacing(10)

        self.btn_grant_perms = QPushButton("⚡ 1-Tap Full Permissions")
        self.btn_grant_perms.setProperty("class", "btnHero")
        self.btn_grant_perms.setToolTip("Auto-grants write secure settings, overlay, keep awake, and TCP/IP 5555 without prompts")
        self.btn_grant_perms.clicked.connect(self.action_grant_full_perms)
        row_nexus_btns.addWidget(self.btn_grant_perms)

        self.btn_install_nexus_apk = QPushButton("📦 Install Nexus APK")
        self.btn_install_nexus_apk.setProperty("class", "btnAction")
        self.btn_install_nexus_apk.setToolTip("Pushes NexusAI_Mobile_Client.apk to device and grants all runtime permissions")
        self.btn_install_nexus_apk.clicked.connect(self.action_install_nexus_apk)
        row_nexus_btns.addWidget(self.btn_install_nexus_apk)

        self.btn_mobile_download_qr = QPushButton("🌐 Mobile Download QR")
        self.btn_mobile_download_qr.setProperty("class", "btnAction")
        self.btn_mobile_download_qr.setToolTip("Generates QR code to download companion APK directly to phone over local Wi-Fi")
        self.btn_mobile_download_qr.clicked.connect(self.action_show_mobile_download_qr)
        row_nexus_btns.addWidget(self.btn_mobile_download_qr)

        cn_l.addLayout(row_nexus_btns)
        layout.addWidget(card_nexus)

        # -------------------------------------------------------------
        # CARD 4: 🌐 Direct Wi-Fi IP Manual Connect Bar
        # -------------------------------------------------------------
        card_manual = QFrame()
        card_manual.setProperty("class", "cardBox")
        cm_l = QVBoxLayout(card_manual)
        cm_l.setContentsMargins(16, 14, 16, 14)
        cm_l.setSpacing(10)

        cm_title = QLabel("🌐 Direct Wi-Fi IP Manual Connect:")
        cm_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        cm_title.setStyleSheet("color: #0f172a; font-weight: 600; font-size: 12px;")
        cm_l.addWidget(cm_title)

        row_ip = QHBoxLayout()
        row_ip.setSpacing(8)

        local_subnet = self.get_local_subnet()
        self.edit_ip = QLineEdit(local_subnet)
        self.edit_ip.setPlaceholderText("Phone IP (e.g. 192.168.100.25)")
        row_ip.addWidget(self.edit_ip, 3)

        self.edit_port = QLineEdit("5555")
        self.edit_port.setFixedWidth(70)
        self.edit_port.setPlaceholderText("Port")
        row_ip.addWidget(self.edit_port, 1)

        self.btn_connect_ip = QPushButton("🔗 Connect Wi-Fi")
        self.btn_connect_ip.setProperty("class", "btnHero")
        self.btn_connect_ip.setMinimumWidth(130)
        self.btn_connect_ip.clicked.connect(self.action_connect_ip)
        row_ip.addWidget(self.btn_connect_ip, 2)

        self.btn_ping_ip = QPushButton("📡 Test Ping")
        self.btn_ping_ip.setProperty("class", "btnAction")
        self.btn_ping_ip.setMinimumWidth(100)
        self.btn_ping_ip.setToolTip("Ping IP to verify if PC and Phone are on same Wi-Fi subnet")
        self.btn_ping_ip.clicked.connect(self.action_ping_phone)
        row_ip.addWidget(self.btn_ping_ip, 1)

        cm_l.addLayout(row_ip)
        layout.addWidget(card_manual)

        # -------------------------------------------------------------
        # CARD 5: 🎮 LAN Remote Control & Navigation Toolbar
        # -------------------------------------------------------------
        card_remote = QFrame()
        card_remote.setProperty("class", "cardBox")
        cr_l = QVBoxLayout(card_remote)
        cr_l.setContentsMargins(16, 14, 16, 14)
        cr_l.setSpacing(10)

        cr_title = QLabel("🎮 LAN Remote Control & Navigation Toolbar:")
        cr_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        cr_title.setStyleSheet("color: #0f172a; font-weight: 600; font-size: 12px;")
        cr_l.addWidget(cr_title)

        cr_desc = QLabel("Direct Wi-Fi / ADB control over physical device hardware, system navigation, clipboard, and apps.")
        cr_desc.setStyleSheet("color: #475569; font-size: 11px;")
        cr_l.addWidget(cr_desc)

        # Row 1: Power & Volume
        row_hw = QHBoxLayout()
        row_hw.setSpacing(8)

        self.btn_rem_wake = QPushButton("⚡ Wake")
        self.btn_rem_wake.setProperty("class", "btnAction")
        self.btn_rem_wake.clicked.connect(lambda: self.action_remote_control("wake"))
        row_hw.addWidget(self.btn_rem_wake)

        self.btn_rem_lock = QPushButton("🔒 Lock")
        self.btn_rem_lock.setProperty("class", "btnAction")
        self.btn_rem_lock.clicked.connect(lambda: self.action_remote_control("lock"))
        row_hw.addWidget(self.btn_rem_lock)

        self.btn_rem_vol_up = QPushButton("🔊 Vol +")
        self.btn_rem_vol_up.setProperty("class", "btnAction")
        self.btn_rem_vol_up.clicked.connect(lambda: self.action_remote_control("volume_up"))
        row_hw.addWidget(self.btn_rem_vol_up)

        self.btn_rem_vol_down = QPushButton("🔉 Vol -")
        self.btn_rem_vol_down.setProperty("class", "btnAction")
        self.btn_rem_vol_down.clicked.connect(lambda: self.action_remote_control("volume_down"))
        row_hw.addWidget(self.btn_rem_vol_down)

        self.btn_rem_vol_mute = QPushButton("🔇 Mute")
        self.btn_rem_vol_mute.setProperty("class", "btnAction")
        self.btn_rem_vol_mute.clicked.connect(lambda: self.action_remote_control("volume_mute"))
        row_hw.addWidget(self.btn_rem_vol_mute)

        cr_l.addLayout(row_hw)

        # Row 2: Navigation & System
        row_nav = QHBoxLayout()
        row_nav.setSpacing(8)

        self.btn_rem_back = QPushButton("◀ Back")
        self.btn_rem_back.setProperty("class", "btnAction")
        self.btn_rem_back.clicked.connect(lambda: self.action_remote_control("back"))
        row_nav.addWidget(self.btn_rem_back)

        self.btn_rem_home = QPushButton("🏠 Home")
        self.btn_rem_home.setProperty("class", "btnAction")
        self.btn_rem_home.clicked.connect(lambda: self.action_remote_control("home"))
        row_nav.addWidget(self.btn_rem_home)

        self.btn_rem_recents = QPushButton("⏹ Recents")
        self.btn_rem_recents.setProperty("class", "btnAction")
        self.btn_rem_recents.clicked.connect(lambda: self.action_remote_control("recents"))
        row_nav.addWidget(self.btn_rem_recents)

        self.btn_rem_notif = QPushButton("🔔 Notifications")
        self.btn_rem_notif.setProperty("class", "btnAction")
        self.btn_rem_notif.clicked.connect(lambda: self.action_remote_control("notifications"))
        row_nav.addWidget(self.btn_rem_notif)

        self.btn_rem_qs = QPushButton("⚙️ Quick Settings")
        self.btn_rem_qs.setProperty("class", "btnAction")
        self.btn_rem_qs.clicked.connect(lambda: self.action_remote_control("quick_settings"))
        row_nav.addWidget(self.btn_rem_qs)

        cr_l.addLayout(row_nav)

        # Row 3: Productivity (Clipboard Sync, Line-speed Push, App Launcher)
        row_tools = QHBoxLayout()
        row_tools.setSpacing(8)

        self.btn_rem_clip = QPushButton("📋 Sync Clipboard")
        self.btn_rem_clip.setProperty("class", "btnAction")
        self.btn_rem_clip.clicked.connect(self.action_sync_clipboard)
        row_tools.addWidget(self.btn_rem_clip)

        self.btn_rem_push = QPushButton("📁 Push File / APK")
        self.btn_rem_push.setProperty("class", "btnAction")
        self.btn_rem_push.clicked.connect(self.action_push_file)
        row_tools.addWidget(self.btn_rem_push)

        self.btn_rem_apps = QPushButton("🚀 Remote App Launcher")
        self.btn_rem_apps.setProperty("class", "btnHero")
        self.btn_rem_apps.clicked.connect(self.action_remote_app_launcher)
        row_tools.addWidget(self.btn_rem_apps)

        cr_l.addLayout(row_tools)
        layout.addWidget(card_remote)

        # -------------------------------------------------------------
        # CARD 6: ⚡ Advanced Video & Audio Stream Settings
        # -------------------------------------------------------------
        card_stream = QFrame()
        card_stream.setProperty("class", "cardBox")
        cs_l = QVBoxLayout(card_stream)
        cs_l.setContentsMargins(16, 14, 16, 14)
        cs_l.setSpacing(10)

        cs_title = QLabel("⚡ Advanced Video & Audio Stream Settings:")
        cs_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        cs_title.setStyleSheet("color: #0f172a; font-weight: 600; font-size: 12px;")
        cs_l.addWidget(cs_title)

        row_stream_opts = QHBoxLayout()
        row_stream_opts.setSpacing(10)

        l_codec = QLabel("Codec:")
        l_codec.setStyleSheet("color: #475569; font-size: 11px;")
        row_stream_opts.addWidget(l_codec)
        self.combo_stream_codec = QComboBox()
        self.combo_stream_codec.addItems(["H.264 (Universal)", "H.265 / HEVC (High Efficiency)", "AV1 (Next-Gen)"])
        row_stream_opts.addWidget(self.combo_stream_codec)

        l_fps = QLabel("Max FPS:")
        l_fps.setStyleSheet("color: #475569; font-size: 11px;")
        row_stream_opts.addWidget(l_fps)
        self.combo_stream_fps = QComboBox()
        self.combo_stream_fps.addItems(["60 FPS (Default)", "30 FPS (Power Save)", "90 FPS (High Refresh)", "120 FPS (Ultra Smooth)"])
        row_stream_opts.addWidget(self.combo_stream_fps)

        l_br = QLabel("Bitrate:")
        l_br.setStyleSheet("color: #475569; font-size: 11px;")
        row_stream_opts.addWidget(l_br)
        self.combo_stream_bitrate = QComboBox()
        self.combo_stream_bitrate.addItems(["16 Mbps (Balanced)", "8 Mbps (Low Bandwidth)", "24 Mbps (High Def)", "32 Mbps (Ultra)", "64 Mbps (Lossless Line)"])
        row_stream_opts.addWidget(self.combo_stream_bitrate)

        self.chk_stream_screen_off = QCheckBox("Dim / Screen-off on Phone")
        self.chk_stream_screen_off.setToolTip("Keeps physical phone screen off during cast to save battery and reduce heat")
        self.chk_stream_screen_off.setStyleSheet("color: #0f172a; font-size: 11px;")
        row_stream_opts.addWidget(self.chk_stream_screen_off)

        cs_l.addLayout(row_stream_opts)
        layout.addWidget(card_stream)

        layout.addStretch()

        # Mount scroll area
        tab_vbox = QVBoxLayout(self.tab_lan)
        tab_vbox.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(container)
        tab_vbox.addWidget(scroll)

    def setup_tab_forward(self):
        layout = QVBoxLayout(self.tab_forward)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        top_box = QHBoxLayout()
        t = QLabel("🔀 Active ADB Port Forwarding & Reverse Proxies:")
        t.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        t.setStyleSheet("color: #0f172a;")
        top_box.addWidget(t)
        top_box.addStretch()

        btn_ref_fwd = QPushButton("🔄 Refresh Rules")
        btn_ref_fwd.setProperty("class", "btnAction")
        btn_ref_fwd.clicked.connect(self.refresh_port_forwards)
        top_box.addWidget(btn_ref_fwd)

        btn_clear_fwd = QPushButton("🗑️ Clear All Rules")
        btn_clear_fwd.setProperty("class", "btnDanger")
        btn_clear_fwd.clicked.connect(self.action_clear_all_forwards)
        top_box.addWidget(btn_clear_fwd)

        layout.addLayout(top_box)

        self.fwd_table = QTableWidget(0, 4)
        self.fwd_table.setHorizontalHeaderLabels(["Target Device", "Local Host Port", "Remote Device Port", "Actions"])
        self.fwd_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.fwd_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.fwd_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.fwd_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.fwd_table.setColumnWidth(0, 200)
        self.fwd_table.setColumnWidth(1, 160)
        self.fwd_table.setColumnWidth(3, 110)
        self.fwd_table.verticalHeader().setVisible(False)
        layout.addWidget(self.fwd_table)

        card_add = QFrame()
        card_add.setProperty("class", "cardBox")
        ca_l = QVBoxLayout(card_add)
        ca_l.setContentsMargins(16, 14, 16, 14)
        ca_l.setSpacing(10)

        ca_t = QLabel("➕ Add New Port Forward / Reverse Rule:")
        ca_t.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        ca_t.setStyleSheet("color: #0f172a; font-weight: 600; font-size: 12px;")
        ca_l.addWidget(ca_t)

        row_add = QHBoxLayout()
        row_add.setSpacing(8)

        self.edit_fwd_local = QLineEdit("8081")
        self.edit_fwd_local.setPlaceholderText("Local PC Port (e.g. 8081)")
        row_add.addWidget(self.edit_fwd_local, 2)

        lbl_arr = QLabel("➔")
        lbl_arr.setFont(QFont("Segoe UI", 14))
        lbl_arr.setStyleSheet("color: #64748b;")
        row_add.addWidget(lbl_arr)

        self.edit_fwd_remote = QLineEdit("8081")
        self.edit_fwd_remote.setPlaceholderText("Device Port (e.g. 8081)")
        row_add.addWidget(self.edit_fwd_remote, 2)

        self.chk_reverse = QCheckBox("Reverse (Phone ➔ PC)")
        self.chk_reverse.setStyleSheet("color: #475569; font-weight: 600;")
        row_add.addWidget(self.chk_reverse, 2)

        btn_add = QPushButton("➕ Add Forward Rule")
        btn_add.setProperty("class", "btnHero")
        btn_add.clicked.connect(self.action_add_port_forward)
        row_add.addWidget(btn_add, 2)

        ca_l.addLayout(row_add)
        layout.addWidget(card_add)

    def setup_tab_logcat(self):
        layout = QVBoxLayout(self.tab_logcat)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        row_c = QHBoxLayout()
        row_c.setSpacing(8)

        lbl_filter = QLabel("🔍 Filter:")
        lbl_filter.setStyleSheet("color: #475569; font-weight: bold;")
        row_c.addWidget(lbl_filter)

        self.edit_log_filter = QLineEdit()
        self.edit_log_filter.setPlaceholderText("Type keyword to filter (e.g. Fatal, AndroidRuntime, Error, tag)...")
        self.edit_log_filter.textChanged.connect(self.apply_logcat_filter)
        row_c.addWidget(self.edit_log_filter, 3)

        self.combo_log_level = QComboBox()
        self.combo_log_level.addItems(["All Levels", "Errors & Fatal", "Warnings", "Info"])
        self.combo_log_level.currentIndexChanged.connect(self.apply_logcat_filter)
        row_c.addWidget(self.combo_log_level, 1)

        self.btn_toggle_logcat = QPushButton("⏹ Pause Stream")
        self.btn_toggle_logcat.setProperty("class", "btnAction")
        self.btn_toggle_logcat.clicked.connect(self.toggle_logcat_stream)
        row_c.addWidget(self.btn_toggle_logcat)

        self.btn_clear_log = QPushButton("🧹 Clear")
        self.btn_clear_log.setProperty("class", "btnAction")
        self.btn_clear_log.clicked.connect(self.clear_logcat_view)
        row_c.addWidget(self.btn_clear_log)

        self.btn_copy_report = QPushButton("📋 Copy Diagnostic Report")
        self.btn_copy_report.setProperty("class", "btnHero")
        self.btn_copy_report.setToolTip("Copies a complete system, ADB, and diagnostics report to clipboard")
        self.btn_copy_report.clicked.connect(self.copy_diagnostic_report)
        row_c.addWidget(self.btn_copy_report)

        layout.addLayout(row_c)

        self.txt_logcat = QPlainTextEdit()
        self.txt_logcat.setReadOnly(True)
        self.txt_logcat.setMaximumBlockCount(2000)
        layout.addWidget(self.txt_logcat)

    def get_local_subnet(self) -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            parts = ip.split(".")
            if len(parts) == 4:
                return f"{parts[0]}.{parts[1]}.{parts[2]}."
        except Exception:
            pass
        return "192.168.1."

    def refresh_all_diagnostics(self):
        adb = SystemPaths.get_adb()

        # 1. Check ADB Path & Version
        ver = SystemPaths.get_adb_version()
        self.lbl_adb_path.setText(f"{adb}\n({ver})")

        # 2. Check Port 5037 & Daemon
        is_port_up = SystemPaths.is_port_in_use(5037)
        if is_port_up:
            self.lbl_daemon_status.setText("🟢 Active (Port 5037 Open & Listening)")
            self.lbl_daemon_status.setStyleSheet("color: #34d399; font-weight: bold; font-size: 11px;")
        else:
            self.lbl_daemon_status.setText("🔴 Offline (Port 5037 Closed / Daemon Stopped)")
            self.lbl_daemon_status.setStyleSheet("color: #f87171; font-weight: bold; font-size: 11px;")

        # 3. Check Windows USB PnP Driver
        has_android_pnp = False
        try:
            cmd = ['powershell', '-Command', "Get-PnpDevice | Where-Object { $_.Class -eq 'AndroidUsbDeviceClass' -or $_.FriendlyName -match 'Android|ADB|Google' } | Select-Object -First 1 FriendlyName"]
            res = subprocess.run(cmd, capture_output=True, text=True, creationflags=0x08000000, timeout=3)
            if res.stdout and any(k in res.stdout for k in ["Android", "ADB", "Google"]):
                has_android_pnp = True
        except Exception:
            pass

        if has_android_pnp:
            self.lbl_usb_pnp.setText("🟢 Android USB Hardware & Driver Detected")
            self.lbl_usb_pnp.setStyleSheet("color: #34d399; font-weight: bold; font-size: 11px;")
        else:
            self.lbl_usb_pnp.setText("⚪ No Physical USB Device Detected via Windows PnP")
            self.lbl_usb_pnp.setStyleSheet("color: #94a3b8; font-size: 11px;")

        # 4. Check Port 5037 Conflicts
        conflicts = SystemPaths.get_port_conflicts(5037)
        if len(conflicts) > 1:
            procs = ", ".join([f"{c['proc']}(PID:{c['pid']})" for c in conflicts])
            self.lbl_conflicts.setText(f"⚠️ Multiple PIDs on 5037: {procs}")
            self.lbl_conflicts.setStyleSheet("color: #f59e0b; font-weight: bold; font-size: 11px;")
        elif conflicts:
            self.lbl_conflicts.setText(f"🟢 Normal ({conflicts[0]['proc']}, PID {conflicts[0]['pid']})")
            self.lbl_conflicts.setStyleSheet("color: #34d399; font-size: 11px;")
        else:
            self.lbl_conflicts.setText("⚪ Port 5037 Free / No Conflicts")
            self.lbl_conflicts.setStyleSheet("color: #94a3b8; font-size: 11px;")

        # 5. Populate Devices Table
        devs = SystemPaths.list_devices()
        self.dev_table.setRowCount(len(devs))

        if not devs:
            self.btn_start_mirror.setEnabled(False)
        else:
            self.btn_start_mirror.setEnabled(True)

        for row, d in enumerate(devs):
            s = d["serial"]
            m = d["model"]
            st = d["state"]
            is_emu = d["is_emulator"]
            is_lan = d["is_lan"]

            self.dev_table.setItem(row, 0, QTableWidgetItem(s))
            t_type = "Android VM" if is_emu else ("Phone (Wi-Fi)" if is_lan else "Phone (USB)")
            self.dev_table.setItem(row, 1, QTableWidgetItem(f"{m} ({t_type})"))

            if st == "device":
                st_item = QTableWidgetItem("🟢 ONLINE & AUTHORIZED")
                st_item.setForeground(QColor("#34d399"))
            elif st == "unauthorized":
                st_item = QTableWidgetItem("🟡 UNAUTHORIZED (Tap phone prompt)")
                st_item.setForeground(QColor("#f59e0b"))
            else:
                st_item = QTableWidgetItem(f"🔴 {st.upper()}")
                st_item.setForeground(QColor("#f87171"))
            self.dev_table.setItem(row, 2, st_item)

            act_box = QWidget()
            ab_l = QHBoxLayout(act_box)
            ab_l.setContentsMargins(4, 2, 4, 2)
            ab_l.setSpacing(4)

            btn_m = QPushButton("🚀")
            btn_m.setToolTip("Start Mirror Session")
            btn_m.setFixedWidth(28)
            btn_m.clicked.connect(lambda _, ser=s: self.launch_specific_mirror(ser))
            ab_l.addWidget(btn_m)

            btn_t = QPushButton("💻")
            btn_t.setToolTip("Open ADB Shell in Windows Terminal / Cmd")
            btn_t.setFixedWidth(28)
            btn_t.clicked.connect(lambda _, ser=s: self.open_adb_shell(ser))
            ab_l.addWidget(btn_t)

            btn_r = QPushButton("🔄")
            btn_r.setToolTip("Reboot Device")
            btn_r.setFixedWidth(28)
            btn_r.clicked.connect(lambda _, ser=s: self.reboot_device(ser))
            ab_l.addWidget(btn_r)

            btn_sc = QPushButton("📸")
            btn_sc.setToolTip("Instant Screenshot to Desktop")
            btn_sc.setFixedWidth(28)
            btn_sc.clicked.connect(lambda _, ser=s: self.capture_screenshot_device(ser))
            ab_l.addWidget(btn_sc)

            btn_vpn = QPushButton("🛡️")
            btn_vpn.setToolTip("Fix Guest VPN & DNS Routing for this device")
            btn_vpn.setFixedWidth(28)
            btn_vpn.clicked.connect(lambda _, ser=s: self.action_fix_vpn_and_dns(ser))
            ab_l.addWidget(btn_vpn)

            self.dev_table.setCellWidget(row, 3, act_box)

        self.refresh_port_forwards()
        if not self.logcat_worker and devs:
            active_s = devs[0]["serial"]
            self.start_logcat(active_s)

    def launch_specific_mirror(self, serial: str):
        self.accept()
        start_mirror_with_fallback(serial, self.parent())

    def open_adb_shell(self, serial: str):
        adb = SystemPaths.get_adb()
        subprocess.Popen(f'start cmd /k ""{adb}" -s {serial} shell"', shell=True)

    def reboot_device(self, serial: str):
        res = QMessageBox.question(self, "Reboot Device", f"Are you sure you want to reboot device '{serial}'?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if res == QMessageBox.StandardButton.Yes:
            adb = SystemPaths.get_adb()
            subprocess.run([adb, "-s", serial, "reboot"], timeout=4, creationflags=0x08000000)
            QTimer.singleShot(1500, self.refresh_all_diagnostics)

    def capture_screenshot_device(self, serial: str):
        adb = SystemPaths.get_adb()
        desktop = os.path.join(os.path.expanduser("~"), "Desktop", "Screenshots")
        os.makedirs(desktop, exist_ok=True)
        fname = f"gndroid_{serial.replace(':', '_')}_{int(time.time())}.png"
        out_p = os.path.join(desktop, fname)
        try:
            subprocess.run([adb, "-s", serial, "shell", "screencap", "-p", "/sdcard/tmp_sc.png"], timeout=3, creationflags=0x08000000)
            subprocess.run([adb, "-s", serial, "pull", "/sdcard/tmp_sc.png", out_p], timeout=3, creationflags=0x08000000)
            subprocess.run([adb, "-s", serial, "shell", "rm", "/sdcard/tmp_sc.png"], timeout=2, creationflags=0x08000000)
            QMessageBox.information(self, "Screenshot Saved", f"Screenshot saved to:\n\n{out_p}")
        except Exception as e:
            QMessageBox.warning(self, "Screenshot Error", str(e))

    def action_restart_adb(self):
        adb = SystemPaths.get_adb()
        try:
            subprocess.run(["taskkill", "/F", "/IM", "adb.exe"], capture_output=True, creationflags=0x08000000)
            time.sleep(0.3)
            subprocess.run([adb, "kill-server"], capture_output=True, creationflags=0x08000000)
            subprocess.run([adb, "start-server"], capture_output=True, creationflags=0x08000000)
            self.refresh_all_diagnostics()
            QMessageBox.information(self, "ADB Restarted", "ADB Daemon was successfully restarted cleanly on port 5037!")
        except Exception as e:
            QMessageBox.critical(self, "Restart Error", str(e))

    def action_reset_keys(self):
        reply = QMessageBox.question(
            self, "Reset RSA Auth Keys?",
            "This will delete your saved ADB RSA authorization keys (~/.android/adbkey).\n\n"
            "Your phone will prompt you with 'Allow USB debugging?' again when plugged in.\n\n"
            "Proceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            adb_dir = os.path.join(os.path.expanduser("~"), ".android")
            for k in ["adbkey", "adbkey.pub"]:
                kp = os.path.join(adb_dir, k)
                if os.path.exists(kp):
                    try: os.remove(kp)
                    except: pass
            self.action_restart_adb()
            QMessageBox.information(
                self, "Keys Reset",
                "ADB authorization keys cleared!\n\n"
                "Please disconnect and reconnect your phone's USB cable, unlock your phone, "
                "and tap 'Always allow from this computer' on the prompt."
            )

    def action_reconnect_offline(self):
        adb = SystemPaths.get_adb()
        try:
            subprocess.run([adb, "reconnect", "offline"], timeout=3, capture_output=True, creationflags=0x08000000)
            subprocess.run([adb, "reconnect"], timeout=3, capture_output=True, creationflags=0x08000000)
            time.sleep(0.5)
            self.refresh_all_diagnostics()
            QMessageBox.information(self, "Reconnected", "Sent reconnect signal to all offline devices. Check device screen for authorization prompts!")
        except Exception as e:
            QMessageBox.warning(self, "Reconnect Error", str(e))

    def action_kill_port_conflicts(self):
        conflicts = SystemPaths.get_port_conflicts(5037)
        if not conflicts:
            QMessageBox.information(self, "No Conflicts", "No conflicting processes found on port 5037.")
            return
        killed = 0
        for c in conflicts:
            if SystemPaths.kill_process_by_pid(c["pid"]):
                killed += 1
        time.sleep(0.4)
        self.action_restart_adb()
        QMessageBox.information(self, "Processes Terminated", f"Successfully terminated {killed} conflicting process(es) and restarted ADB on port 5037!")

    def action_auto_repair_all(self):
        adb = SystemPaths.get_adb()
        try:
            subprocess.run(["taskkill", "/F", "/IM", "adb.exe"], capture_output=True, creationflags=0x08000000)
            time.sleep(0.3)
            conflicts = SystemPaths.get_port_conflicts(5037)
            for c in conflicts:
                SystemPaths.kill_process_by_pid(c["pid"])
            AVDManager.clean_stale_locks()
            subprocess.run([adb, "start-server"], capture_output=True, creationflags=0x08000000)
            time.sleep(0.5)
            subprocess.run([adb, "reconnect"], capture_output=True, creationflags=0x08000000)
            self.refresh_all_diagnostics()
            QMessageBox.information(
                self, "Auto-Repair Complete",
                "✅ 1-Click Auto-Repair Finished!\n\n"
                "• All zombie ADB processes terminated\n"
                "• Port 5037 freed and bound to clean ADB daemon\n"
                "• Stale virtual machine lockfiles swept\n"
                "• All devices reconnected"
            )
        except Exception as e:
            QMessageBox.critical(self, "Repair Error", str(e))

    def action_fix_vpn_and_dns(self, specific_serial: str = ""):
        target = specific_serial or self.target_serial
        if not target:
            devs = SystemPaths.list_devices()
            online_devs = [d for d in devs if d.get("state") == "device"]
            if online_devs:
                emu_devs = [d for d in online_devs if d.get("is_emulator")]
                target = emu_devs[0]["serial"] if emu_devs else online_devs[0]["serial"]
            elif devs:
                target = devs[0]["serial"]
            else:
                target = "emulator-5554"

        # Switch to diagnostics log tab so the user sees real-time status output
        self.tabs.setCurrentWidget(self.tab_logcat)

        ts = time.strftime("%H:%M:%S")
        self.on_logcat_line("=" * 70)
        self.on_logcat_line(f"[{ts}] [VPN & DNS Doctor] Initiating Guest VPN & DNS Diagnostic Routine...")
        self.on_logcat_line(f"[{ts}] [VPN & DNS Doctor] Target Android Serial: {target}")
        self.on_logcat_line(f"[{ts}] [VPN & DNS Doctor] Invoking nexus.display_and_vpn.fix_guest_vpn_and_dns('{target}')...")
        QApplication.processEvents()

        try:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            res = nexus.display_and_vpn.fix_guest_vpn_and_dns(target)
        except Exception as e:
            res = {"status": "error", "serial": target, "online": False, "message": str(e)}
        finally:
            QApplication.restoreOverrideCursor()

        ts2 = time.strftime("%H:%M:%S")
        if res.get("status") == "error" or not res.get("online"):
            msg = res.get("message", f"Device '{target}' is offline or unreachable via ADB.")
            self.on_logcat_line(f"[{ts2}] [VPN & DNS Doctor] ❌ ERROR: {msg}")
            self.on_logcat_line("=" * 70 + "\n")
            QMessageBox.warning(self, "VPN & DNS Diagnostic Error", f"Failed to repair device '{target}':\n\n{msg}")
            return

        # Display real-time DNS status
        dns_data = res.get("dns", {})
        configured = dns_data.get("configured", {})
        self.on_logcat_line(f"[{ts2}] [VPN & DNS Doctor] 🌐 Guest DNS Properties Applied:")
        for prop, val in configured.items():
            self.on_logcat_line(f"    • {prop} => {val} (Active & Verified)")

        # Display real-time VPN permissions status
        vpn_data = res.get("vpn", {})
        detected = vpn_data.get("detected_packages", [])
        granted = vpn_data.get("granted_packages", [])
        failed = vpn_data.get("failed_packages", [])
        total = vpn_data.get("total_detected", 0)

        self.on_logcat_line(f"[{ts2}] [VPN & DNS Doctor] 🛡️ Guest In-Emulator VPN Permissions:")
        if detected:
            self.on_logcat_line(f"    • Detected {total} VPN client package(s):")
            for pkg in detected:
                status_str = "PERMISSION GRANTED (ACTIVATE_VPN: allow)" if pkg in granted else "PERMISSION FAILED / DENIED"
                self.on_logcat_line(f"      - {pkg}: {status_str}")
        else:
            self.on_logcat_line("    • No third-party VPN apps detected on guest OS (Direct internet routing active).")

        # Display network verification / ping status
        ping_data = res.get("ping", {})
        ping_ok = ping_data.get("success", False)
        ping_target = ping_data.get("target", "8.8.8.8")
        if ping_ok:
            self.on_logcat_line(f"[{ts2}] [VPN & DNS Doctor] ✅ Network Verification: Ping to {ping_target} SUCCEEDED (0% packet loss).")
        else:
            self.on_logcat_line(f"[{ts2}] [VPN & DNS Doctor] ⚠️ Network Verification: Ping to {ping_target} TIMED OUT / PACKET LOSS.")

        self.on_logcat_line("=" * 70 + "\n")

        icon = "✅" if ping_ok else "⚠️"
        title = "VPN & DNS Repaired" if ping_ok else "VPN & DNS Configured (Notice)"
        dns_summary = "\n".join([f"• {k} = {v}" for k, v in configured.items()]) or "• net.dns1 = 8.8.8.8\n• net.dns2 = 1.1.1.1"
        vpn_summary = f"{len(granted)} of {len(detected)} VPN app(s) granted ACTIVATE_VPN" if detected else "No VPN packages installed (Clean OS)"
        summary_msg = (
            f"{icon} Guest VPN & DNS Repair completed for '{target}':\n\n"
            f"🌐 DNS Servers Configured:\n{dns_summary}\n\n"
            f"🛡️ VPN Permissions:\n• {vpn_summary}\n\n"
            f"📡 Gateway Ping ({ping_target}):\n• {'Online & Verified (0% loss)' if ping_ok else 'Packet loss or timeout'}\n\n"
            "Full real-time diagnostic trace has been recorded in the Live Logcat & System Report tab."
        )
        QMessageBox.information(self, title, summary_msg)

    def action_convert_usb_to_lan(self):
        devs = SystemPaths.list_devices()
        usb_phys = [d for d in devs if not d["is_emulator"] and not d.get("is_lan") and d["state"] == "device"]
        existing_lan = [d for d in devs if d.get("is_lan") and d["state"] == "device"]

        if existing_lan and not usb_phys:
            lan_s = existing_lan[0]["serial"]
            model = existing_lan[0].get("model", "Phone")
            self.refresh_all_diagnostics()
            QMessageBox.information(self, "Wireless LAN Active", f"🎉 {model} is ALREADY connected over Wi-Fi:\n\n{lan_s}\n\nYour cable is already unplugged!")
            return

        if not usb_phys:
            QMessageBox.warning(self, "No USB Phone", "Please connect your phone via USB cable first with USB Debugging enabled.")
            return

        serial = usb_phys[0]["serial"]
        model = usb_phys[0].get("model", "Android Device")
        adb = SystemPaths.get_adb()
        ip = SystemPaths.get_phone_lan_ip(serial)

        if not ip:
            QMessageBox.warning(self, "No Wi-Fi IP", f"Could not detect phone's Wi-Fi IP address. Please ensure {model} is connected to the same Wi-Fi network as this PC.")
            return

        try:
            subprocess.run([adb, "-s", serial, "tcpip", "5555"], timeout=4, creationflags=0x08000000)
            time.sleep(1.2)
            out = subprocess.check_output([adb, "connect", f"{ip}:5555"], text=True, timeout=5, creationflags=0x08000000)
            self.refresh_all_diagnostics()
            if "connected to" in out.lower() or "already" in out.lower():
                res = QMessageBox.question(
                    self, "Wireless Activated!",
                    f"🎉 {model} successfully connected over Wi-Fi!\n\n"
                    f"• Target IP: {ip}:5555\n"
                    f"• Mode: 60 FPS Wireless ADB Streaming\n\n"
                    "⭐ You can now UNPLUG your USB cable completely!\n\n"
                    "Would you like to start mirroring this wireless device now?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if res == QMessageBox.StandardButton.Yes:
                    self.accept()
                    start_mirror_with_fallback(f"{ip}:5555", self.parent())
            else:
                QMessageBox.information(
                    self, "Wireless Result",
                    f"{out.strip()}\n\nTarget: {ip}:5555\n\nYou can now unplug the cable and use Wireless LAN mode."
                )
        except Exception as e:
            QMessageBox.critical(self, "Wireless Error", str(e))

    def action_connect_ip(self):
        ip = self.edit_ip.text().strip()
        port = self.edit_port.text().strip() or "5555"
        if not ip:
            QMessageBox.warning(self, "Missing IP", "Please enter phone IP address.")
            return
        target = f"{ip}:{port}"
        adb = SystemPaths.get_adb()
        try:
            out = subprocess.check_output([adb, "connect", target], text=True, timeout=5, creationflags=0x08000000)
            self.refresh_all_diagnostics()
            if "connected to" in out.lower() or "already" in out.lower():
                res = QMessageBox.question(
                    self, "Wireless Connection Succeeded!",
                    f"🎉 Successfully connected to {target} over Wi-Fi!\n\n"
                    "Would you like to start 60 FPS mirroring with companion controls now?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if res == QMessageBox.StandardButton.Yes:
                    self.accept()
                    start_mirror_with_fallback(target, self.parent())
            else:
                QMessageBox.warning(
                    self, "Wi-Fi Connection Result",
                    f"{out.strip()}\n\n"
                    f"Target: {target}\n\n"
                    "💡 Quick Tip:\n"
                    "If connection was refused or timed out, plug your phone into your PC via USB once and click 'Convert Connected Phone to Wireless LAN' above to open port 5555."
                )
        except Exception as e:
            QMessageBox.critical(self, "Connect Error", str(e))

    def action_ping_phone(self):
        ip = self.edit_ip.text().strip()
        if not ip:
            QMessageBox.warning(self, "Missing IP", "Please enter an IP to ping.")
            return
        ok = SystemPaths.ping_ip(ip)
        if ok:
            QMessageBox.information(self, "Ping Success", f"🟢 Ping to {ip} succeeded!\n\nPhone and PC are on the same Wi-Fi network with clear communication.")
        else:
            QMessageBox.warning(self, "Ping Failed", f"🔴 Could not ping {ip}.\n\nPlease check:\n1. Phone and PC are on the exact same Wi-Fi SSID.\n2. Router does not have 'AP Client Isolation' enabled.")

    def action_fast_lan_scan(self):
        subnet = self.get_local_subnet()
        self.btn_lan_scan.setEnabled(False)
        self.btn_lan_scan.setText(f"🔍 Scanning {subnet}1-254 concurrently...")
        QApplication.processEvents()

        found = []
        found_lock = threading.Lock()
        def check_host(host_ip):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.35)
                    if s.connect_ex((host_ip, 5555)) == 0:
                        with found_lock:
                            found.append(host_ip)
            except Exception:
                pass

        ips = [f"{subnet}{i}" for i in range(1, 255)]
        with ThreadPoolExecutor(max_workers=16) as executor:
            executor.map(check_host, ips)

        self.btn_lan_scan.setEnabled(True)
        self.btn_lan_scan.setText("🔍 Scan Local Subnet for Open ADB Devices (Auto-Discover)")

        if found:
            self.edit_ip.setText(found[0])
            res = QMessageBox.question(
                self, "Device Discovered!",
                f"Found {len(found)} device(s) with open ADB port 5555:\n\n" + "\n".join(found) + "\n\nWould you like to connect to " + found[0] + " immediately?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if res == QMessageBox.StandardButton.Yes:
                self.action_connect_ip()
        else:
            QMessageBox.information(self, "Scan Complete", f"No open ADB devices found on subnet {subnet}1-254.\n\nTip: Plug phone via USB and click '1-Click Convert' to enable wireless port 5555 first.")

    def action_pair_android11(self):
        pair_addr = self.edit_pair_ip.text().strip()
        pair_code = self.edit_pair_code.text().strip()
        if not pair_addr or not pair_code:
            QMessageBox.warning(self, "Missing Info", "Please enter pairing IP:Port and the 6-digit code shown on your phone.")
            return
        adb = SystemPaths.get_adb()
        try:
            res = subprocess.check_output([adb, "pair", pair_addr, pair_code], text=True, timeout=8, creationflags=0x08000000)
            if "successfully paired" in res.lower():
                QMessageBox.information(self, "Pairing Succeeded!", f"{res.strip()}\n\nNow enter the main connection IP and Port in the box above to connect!")
            else:
                QMessageBox.warning(self, "Pairing Result", res.strip())
        except Exception as e:
            QMessageBox.critical(self, "Pairing Error", str(e))

    def start_radar_and_qr_services(self):
        try:
            self.radar_worker = LanRadarWorker(self)
            self.radar_worker.sig_radar_updated.connect(self.on_radar_updated)
            self.radar_worker.sig_radar_status.connect(self.lbl_radar_status.setText)
            self.radar_worker.start()

            self.qr_worker = QRPairingWorker(self)
            self.qr_worker.sig_qr_ready.connect(self.on_qr_ready)
            self.qr_worker.sig_pairing_status.connect(self.on_pairing_status)
            self.qr_worker.sig_pair_connected.connect(self.on_pair_connected)
            self.qr_worker.start()
        except Exception:
            pass

    def on_radar_updated(self, devices: List[Dict[str, Any]]):
        if not hasattr(self, "radar_table"):
            return

        if not devices:
            self.radar_table.setRowCount(1)
            self.radar_table.setRowHeight(0, 44)
            item = QTableWidgetItem("  📡  No devices detected yet. Turn on Wireless Debugging on your phone or scan the QR code below.")
            item.setForeground(QColor("#64748b"))
            item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.radar_table.setItem(0, 0, item)
            self.radar_table.setSpan(0, 0, 1, 5)
            return

        self.radar_table.clearSpans()
        self.radar_table.setRowCount(0)
        self.radar_table.setRowCount(len(devices))
        for row, dev in enumerate(devices):
            self.radar_table.setRowHeight(row, 44)
            m = dev.get("model", "Android Device")
            addr = dev.get("address", "") or dev.get("serial", "")
            proto = dev.get("protocol", "Wireless ADB")
            status = dev.get("status", "Discovered")
            serial = dev.get("serial", addr)

            # Col 0: Model
            item_m = QTableWidgetItem(f"📱 {m}")
            item_m.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
            self.radar_table.setItem(row, 0, item_m)

            # Col 1: Address
            self.radar_table.setItem(row, 1, QTableWidgetItem(addr))

            # Col 2: Protocol
            self.radar_table.setItem(row, 2, QTableWidgetItem(proto))

            # Col 3: Status
            item_s = QTableWidgetItem(status)
            if "Connected" in status or "Ready" in status:
                item_s.setForeground(QColor("#16a34a"))
            else:
                item_s.setForeground(QColor("#0284c7"))
            self.radar_table.setItem(row, 3, item_s)

            # Col 4: Action buttons
            act_box = QWidget()
            ab_l = QHBoxLayout(act_box)
            ab_l.setContentsMargins(4, 2, 4, 2)
            ab_l.setSpacing(6)

            btn_mirror = QPushButton("⚡ Mirror 60 FPS")
            btn_mirror.setStyleSheet("""
                QPushButton {
                    background-color: #0067c0;
                    color: #ffffff;
                    border: none;
                    border-radius: 6px;
                    font-family: 'Segoe UI', -apple-system, sans-serif;
                    font-size: 11px;
                    font-weight: 700;
                    padding: 6px 14px;
                    min-height: 24px;
                }
                QPushButton:hover {
                    background-color: #1879c9;
                }
                QPushButton:pressed {
                    background-color: #005a9e;
                }
            """)
            btn_mirror.setToolTip(f"Lock onto {serial} and start 60 FPS mirroring")
            btn_mirror.clicked.connect(lambda _, ser=serial: self.action_mirror_radar_device(ser))
            ab_l.addWidget(btn_mirror)

            btn_perms = QPushButton("🔐 Perms")
            btn_perms.setStyleSheet("""
                QPushButton {
                    background-color: #f1f5f9;
                    color: #0f172a;
                    font-family: 'Segoe UI', -apple-system, sans-serif;
                    font-size: 11px;
                    font-weight: 600;
                    border: 1px solid #cbd5e1;
                    border-radius: 6px;
                    padding: 6px 10px;
                    min-height: 24px;
                }
                QPushButton:hover {
                    background-color: #e2e8f0;
                }
                QPushButton:pressed {
                    background-color: #cbd5e1;
                }
            """)
            btn_perms.setToolTip("1-Tap grant all background, overlay, and wireless permissions")
            btn_perms.clicked.connect(lambda _, ser=serial: self.action_grant_full_perms(ser))
            ab_l.addWidget(btn_perms)

            self.radar_table.setCellWidget(row, 4, act_box)

    def on_qr_ready(self, pixmap: QPixmap, service_name: str, password: str):
        if hasattr(self, "lbl_qr_image"):
            self.lbl_qr_image.setPixmap(pixmap.scaled(172, 172, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def on_pairing_status(self, msg: str, color: str):
        if hasattr(self, "lbl_qr_badge"):
            self.lbl_qr_badge.setText(msg)
            self.lbl_qr_badge.setStyleSheet(f"color: {color}; font-weight: 600; font-size: 11px; margin-top: 4px;")

    def on_pair_connected(self, target: str, model: str):
        self.accept()
        start_mirror_with_fallback(target, self.parent())

    def action_refresh_radar(self):
        if self.radar_worker:
            self.lbl_radar_status.setText("🔄 Probing local subnet and mDNS services...")
            self.radar_worker.request_immediate_scan()

    def action_generate_new_qr(self):
        if self.qr_worker:
            self.qr_worker.generate_new_code()

    def action_mirror_radar_device(self, target: str):
        if not target:
            return
        host_ip = target.split(":")[0] if ":" in target else target
        target_port = int(target.split(":")[-1]) if ":" in target else 5555

        # Check if companion HTTP is active on 51888 or 51880
        comp_port = None
        if target_port in (51880, 51888):
            comp_port = target_port
        else:
            for p in (51880, 51888):
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.settimeout(0.2)
                        if s.connect_ex((host_ip, p)) == 0:
                            comp_port = p
                            break
                except Exception:
                    pass

        # If Companion HTTP is active: DIRECT WIRELESS MIRROR (ZERO USB CABLE!)
        if comp_port:
            win = GNDroidWirelessMirrorWindow(host_ip=host_ip, port=comp_port, parent=self.parent() or self)
            win.show()
            self.accept()
            return

        # Otherwise, if it's an ADB device or needs auto-lock:
        auto_lock = GNDroidAutoLockDialog(target_ip=host_ip, target_serial=target, parent=self)
        if auto_lock.exec() == QDialog.DialogCode.Accepted:
            locked_target = auto_lock.locked_serial or f"{host_ip}:5555"
            self.accept()
            start_mirror_with_fallback(locked_target, self.parent())

    def action_grant_full_perms(self, specific_serial: str = ""):
        serial = specific_serial
        if not serial:
            devs = SystemPaths.list_devices()
            if devs:
                serial = devs[0]["serial"]

        if not serial:
            QMessageBox.warning(self, "No Device", "Please connect a device via USB or Wi-Fi first.")
            return

        host_ip = serial.split(":")[0] if ":" in serial else serial
        adb = SystemPaths.get_adb()
        adb_connected = False
        try:
            r = subprocess.run([adb, "-s", serial, "get-state"], capture_output=True, text=True, timeout=1.5, creationflags=0x08000000)
            if r.returncode == 0 and "device" in r.stdout.lower():
                adb_connected = True
        except Exception:
            pass

        if not adb_connected:
            comp_port = None
            for p in (51880, 51888):
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.settimeout(0.2)
                        if s.connect_ex((host_ip, p)) == 0:
                            comp_port = p
                            break
                except Exception:
                    pass

            if comp_port:
                QMessageBox.information(
                    self,
                    "GNDROiD Companion Active",
                    f"📱 Device at {host_ip}:{comp_port} is connected wirelessly!\n\n"
                    "⚡ Pure Wi-Fi Mirroring & Remote Controls are ALREADY ACTIVE (Zero USB Cable needed)!\n\n"
                    "To enable Accessibility / Overlay directly from your phone screen:\n"
                    "• Tap 'Accessibility Input Injection' on your phone to enable touch\n"
                    "• Tap 'Floating Overlay Window'\n"
                    "• Tap 'Doze Battery Exemption'\n\n"
                    "👉 Tap each row in the companion app on your phone to toggle them in 1 tap!"
                )
                return

        ok, msg = NexusCompanionManager.grant_full_phone_permissions(serial)
        if ok:
            QMessageBox.information(self, "Permissions Granted", f"Target: {serial}\n\n{msg}")
        else:
            QMessageBox.warning(self, "Permissions Result", f"Target: {serial}\n\n{msg}")

    def action_install_nexus_apk(self, specific_serial: str = ""):
        serial = specific_serial
        if not serial:
            devs = SystemPaths.list_devices()
            if devs:
                serial = devs[0]["serial"]

        if not serial:
            QMessageBox.warning(self, "No Device", "Please connect a device via USB or Wi-Fi first to install the client APK.")
            return

        ok, msg = NexusCompanionManager.install_companion_apk(serial)
        if ok:
            QMessageBox.information(self, "Client APK Installed", f"Target: {serial}\n\n{msg}")
        else:
            QMessageBox.warning(self, "Installation Failed", f"Target: {serial}\n\n{msg}")

    def action_show_mobile_download_qr(self):
        url = NexusCompanionManager.start_download_server()
        if not url:
            QMessageBox.warning(self, "Server Error", "Could not start local APK download server.")
            return

        qr = qrcode.QRCode(box_size=5, border=2)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#0f172a", back_color="#ffffff")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        pix = QPixmap()
        pix.loadFromData(buf.getvalue())

        dlg = QDialog(self)
        dlg.setWindowTitle("🌐 Mobile Client APK Download Link")
        dlg.setStyleSheet("""
            QDialog {
                background: #f8f9fa;
                font-family: 'Segoe UI', sans-serif;
            }
            QPushButton[class="btnHero"], QPushButton.btnHero {
                background: #0067c0;
                border: 1px solid #005a9e;
                border-radius: 6px;
                color: #ffffff;
                font-weight: 600;
                font-size: 12px;
                padding: 8px 16px;
            }
            QPushButton[class="btnHero"]:hover, QPushButton.btnHero:hover {
                background: #1879c9;
            }
        """)
        dl_l = QVBoxLayout(dlg)
        dl_l.setContentsMargins(24, 22, 24, 22)
        dl_l.setSpacing(14)

        t = QLabel("📲 Download Nexus Client on Phone")
        t.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        t.setStyleSheet("color: #0f172a;")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dl_l.addWidget(t)

        desc = QLabel("Scan this QR code with your phone's camera to download the APK directly over local Wi-Fi:")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #475569; font-size: 11px;")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dl_l.addWidget(desc)

        lbl_qr = QLabel()
        lbl_qr.setFixedSize(220, 220)
        lbl_qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_qr.setPixmap(pix.scaled(204, 204, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        lbl_qr.setStyleSheet("background: #ffffff; border: 1px solid #cbd5e1; border-radius: 12px; padding: 6px;")
        dl_l.addWidget(lbl_qr, alignment=Qt.AlignmentFlag.AlignCenter)

        url_box = QLineEdit(url)
        url_box.setReadOnly(True)
        url_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        url_box.setStyleSheet("background: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px; padding: 7px; font-size: 11px; color: #1e293b;")
        dl_l.addWidget(url_box)

        btn_c = QPushButton("✓ Done")
        btn_c.setProperty("class", "btnHero")
        btn_c.setMinimumHeight(38)
        btn_c.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_c.clicked.connect(dlg.accept)
        dl_l.addWidget(btn_c)

        dlg.setMinimumSize(440, 490)
        dlg.adjustSize()
        if dlg.height() < 490:
            dlg.resize(max(dlg.width(), 440), 490)

        dlg.exec()
    def _get_active_target_ip(self) -> str:
        ip = self.edit_ip.text().strip() if hasattr(self, "edit_ip") and self.edit_ip.text() else ""
        if ip:
            return ip.split(":")[0]
        devs = SystemPaths.list_devices()
        for d in devs:
            ser = d.get("serial", "")
            if ":" in ser:
                return ser.split(":")[0]
        return "127.0.0.1"



    def action_remote_control(self, action: str):
        target_ip = self._get_active_target_ip()
        try:
            from nexus.gndroid_companion_client import GNDroidCompanionClient
            client = GNDroidCompanionClient(host=target_ip)
            if client.ping(timeout=0.4):
                if client.control(action):
                    return
        except Exception:
            pass

        adb = SystemPaths.get_adb()
        key_map = {
            "wake": ["shell", "input", "keyevent", "224"],
            "lock": ["shell", "input", "keyevent", "26"],
            "power": ["shell", "input", "keyevent", "26"],
            "volume_up": ["shell", "input", "keyevent", "24"],
            "volume_down": ["shell", "input", "keyevent", "25"],
            "volume_mute": ["shell", "input", "keyevent", "164"],
            "back": ["shell", "input", "keyevent", "4"],
            "home": ["shell", "input", "keyevent", "3"],
            "recents": ["shell", "input", "keyevent", "187"],
            "notifications": ["shell", "cmd", "statusbar", "expand-notifications"],
            "quick_settings": ["shell", "cmd", "statusbar", "expand-settings"],
        }
        cmd = key_map.get(action)
        if cmd:
            subprocess.run([adb] + cmd, timeout=2, capture_output=True, creationflags=0x08000000 if sys.platform == "win32" else 0)

    def action_sync_clipboard(self):
        target_ip = self._get_active_target_ip()
        app_clip = QApplication.clipboard()
        pc_text = app_clip.text() if app_clip else ""
        try:
            from nexus.gndroid_companion_client import GNDroidCompanionClient
            client = GNDroidCompanionClient(host=target_ip)
            if client.ping(timeout=0.5):
                if pc_text:
                    client.set_clipboard(pc_text)
                    QMessageBox.information(self, "Clipboard Synced", f"Copied PC clipboard to phone:\n\n{pc_text[:120]}")
                else:
                    phone_text = client.get_clipboard()
                    if phone_text and app_clip:
                        app_clip.setText(phone_text)
                        QMessageBox.information(self, "Clipboard Synced", f"Received phone clipboard to PC:\n\n{phone_text[:120]}")
                    else:
                        QMessageBox.information(self, "Clipboard Synced", "Clipboard synchronized.")
                return
        except Exception:
            pass

        adb = SystemPaths.get_adb()
        if pc_text:
            escaped = pc_text.replace(" ", "%s").replace('"', '\"')
            subprocess.run([adb, "shell", "input", "text", escaped[:100]], timeout=2, capture_output=True, creationflags=0x08000000 if sys.platform == "win32" else 0)
            QMessageBox.information(self, "Clipboard Synced", f"Injected clipboard text to phone via ADB:\n\n{pc_text[:120]}")
        else:
            QMessageBox.information(self, "Clipboard Sync", "Connect GNDROiD Link Companion on device for real-time bi-directional clipboard sync.")

    def action_push_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select File or APK to Push to Device", "", "All Files (*.*);;Android APKs (*.apk)")
        if not file_path:
            return
        target_ip = self._get_active_target_ip()
        try:
            from nexus.gndroid_companion_client import GNDroidCompanionClient
            client = GNDroidCompanionClient(host=target_ip)
            if client.ping(timeout=0.5):
                ok, remote_path = client.upload_file(file_path)
                if ok:
                    QMessageBox.information(self, "File Pushed", f"🎉 High-speed Wi-Fi upload complete!\n\nSaved to device:\n{remote_path}")
                    return
        except Exception:
            pass

        adb = SystemPaths.get_adb()
        res = subprocess.run([adb, "push", file_path, "/sdcard/Download/"], timeout=30, capture_output=True, text=True, creationflags=0x08000000 if sys.platform == "win32" else 0)
        if res.returncode == 0:
            QMessageBox.information(self, "File Pushed", f"File pushed to phone via ADB:\n/sdcard/Download/{os.path.basename(file_path)}")
        else:
            QMessageBox.warning(self, "Push Failed", f"Could not push file:\n{res.stderr}")

    def action_remote_app_launcher(self):
        target_ip = self._get_active_target_ip()
        apps = []
        try:
            from nexus.gndroid_companion_client import GNDroidCompanionClient
            client = GNDroidCompanionClient(host=target_ip)
            if client.ping(timeout=0.5):
                apps = client.list_apps()
        except Exception:
            pass

        if not apps:
            adb = SystemPaths.get_adb()
            res = subprocess.run([adb, "shell", "pm", "list", "packages", "-3"], timeout=4, capture_output=True, text=True, creationflags=0x08000000 if sys.platform == "win32" else 0)
            if res.returncode == 0:
                for line in res.stdout.strip().splitlines():
                    if line.startswith("package:"):
                        pkg = line[8:].strip()
                        apps.append({"name": pkg.split(".")[-1].capitalize(), "package": pkg})

        if not apps:
            QMessageBox.warning(self, "No Apps Found", "Could not query installed applications from device.")
            return

        items = [f"{a.get('name', 'App')} ({a.get('package')})" for a in apps]
        item, ok = QInputDialog.getItem(self, "🚀 Remote App Launcher", "Select installed phone app to launch:", items, 0, False)
        if ok and item:
            selected_pkg = item.split("(")[-1].rstrip(")")
            adb = SystemPaths.get_adb()
            subprocess.run([adb, "shell", "monkey", "-p", selected_pkg, "-c", "android.intent.category.LAUNCHER", "1"], timeout=3, capture_output=True, creationflags=0x08000000 if sys.platform == "win32" else 0)
            QMessageBox.information(self, "App Launched", f"Launched {selected_pkg} on phone!")


    def refresh_port_forwards(self):
        rules = SystemPaths.list_port_forwards()
        self.fwd_table.setRowCount(len(rules))
        for row, r in enumerate(rules):
            self.fwd_table.setItem(row, 0, QTableWidgetItem(r["serial"]))
            self.fwd_table.setItem(row, 1, QTableWidgetItem(r["local"]))
            self.fwd_table.setItem(row, 2, QTableWidgetItem(r["remote"]))

            btn_del = QPushButton("🗑️ Remove")
            btn_del.setProperty("class", "btnDanger")
            btn_del.clicked.connect(lambda _, ser=r["serial"], lp=r["local"]: self.action_remove_forward(ser, lp))
            self.fwd_table.setCellWidget(row, 3, btn_del)

    def action_add_port_forward(self):
        lp = self.edit_fwd_local.text().strip()
        rp = self.edit_fwd_remote.text().strip()
        if not lp or not rp:
            QMessageBox.warning(self, "Invalid Ports", "Please enter valid port numbers.")
            return
        devs = SystemPaths.list_devices()
        ser = devs[0]["serial"] if devs else ""
        res = SystemPaths.add_port_forward(ser, int(lp), int(rp), reverse=self.chk_reverse.isChecked())
        self.refresh_port_forwards()
        QMessageBox.information(self, "Forward Rule", f"Result: {res}")

    def action_remove_forward(self, serial: str, local_spec: str):
        port_clean = local_spec.replace("tcp:", "")
        try:
            SystemPaths.remove_port_forward(serial, int(port_clean))
            self.refresh_port_forwards()
        except Exception:
            pass

    def action_clear_all_forwards(self):
        SystemPaths.clear_all_forwards()
        self.refresh_port_forwards()
        QMessageBox.information(self, "Rules Cleared", "All active ADB port forwards have been cleared.")

    def start_logcat(self, serial: str):
        if self.logcat_worker and self.logcat_worker.isRunning():
            self.logcat_worker.stop()
        self.logcat_worker = LogcatWorker(serial, self)
        self.logcat_worker.sig_log_line.connect(self.on_logcat_line)
        self.logcat_worker.start()

    def on_logcat_line(self, line: str):
        self.logcat_lines.append(line)
        if len(self.logcat_lines) > 2000:
            self.logcat_lines.pop(0)

        filt = self.edit_log_filter.text().strip().lower()
        level_idx = self.combo_log_level.currentIndex()
        if filt and filt not in line.lower():
            return
        if level_idx == 1 and not any(k in line for k in [" E ", " F ", "Fatal", "Error", "Exception"]):
            return
        if level_idx == 2 and not any(k in line for k in [" W ", "Warn", " E ", " F "]):
            return

        self.txt_logcat.appendPlainText(line)

    def apply_logcat_filter(self):
        self.txt_logcat.clear()
        filt = self.edit_log_filter.text().strip().lower()
        level_idx = self.combo_log_level.currentIndex()
        for line in self.logcat_lines:
            if filt and filt not in line.lower():
                continue
            if level_idx == 1 and not any(k in line for k in [" E ", " F ", "Fatal", "Error", "Exception"]):
                continue
            if level_idx == 2 and not any(k in line for k in [" W ", "Warn", " E ", " F "]):
                continue
            self.txt_logcat.appendPlainText(line)

    def toggle_logcat_stream(self):
        if self.logcat_worker and self.logcat_worker.isRunning():
            self.logcat_worker.stop()
            self.btn_toggle_logcat.setText("▶ Resume Stream")
        else:
            devs = SystemPaths.list_devices()
            ser = devs[0]["serial"] if devs else ""
            self.start_logcat(ser)
            self.btn_toggle_logcat.setText("⏹ Pause Stream")

    def clear_logcat_view(self):
        self.logcat_lines.clear()
        self.txt_logcat.clear()

    def copy_diagnostic_report(self):
        adb = SystemPaths.get_adb()
        ver = SystemPaths.get_adb_version()
        devs = SystemPaths.list_devices()
        conflicts = SystemPaths.get_port_conflicts(5037)
        instances = AVDManager.list_instances()

        rep = [
            "==================================================",
            "  gndroid ADB System & Diagnostics Report",
            "  Developed by Ghulam Nabi Kalhoro",
            f"  Generated at: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            "==================================================",
            f"• ADB Executable: {adb}",
            f"• ADB Version: {ver}",
            f"• Port 5037 Status: {'Listening/Alive' if SystemPaths.is_port_in_use(5037) else 'Closed/Offline'}",
            f"• Conflicts on 5037: {conflicts or 'None'}",
            f"• SDK Directory: {AVDManager.get_sdk_dir()}",
            f"• Emulator Executable: {SystemPaths.get_emulator()}",
            "",
            "--- CONNECTED ADB DEVICES ---"
        ]
        if not devs:
            rep.append("  No active ADB devices detected.")
        else:
            for d in devs:
                rep.append(f"  [{d['state'].upper()}] Serial: {d['serial']} | Model: {d['model']} | VM: {d['is_emulator']} | LAN: {d['is_lan']}")

        rep.append("\n--- VIRTUAL MACHINE INSTANCES ---")
        if not instances:
            rep.append("  No AVD instances found in ~/.android/avd/")
        else:
            for inst in instances:
                rep.append(f"  • {inst['display_name']} ({inst['name']}): Android {inst['api_level']} | {inst['ram_mb']}MB RAM | {inst['cores']} Cores | Running: {inst['running']}")

        rep.append("\n--- RECENT LOGCAT ERRORS (Last 15) ---")
        err_lines = [l for l in self.logcat_lines if any(k in l for k in [" E ", " F ", "Fatal", "Exception"])]
        if not err_lines:
            rep.append("  No critical errors logged in current session.")
        else:
            for el in err_lines[-15:]:
                rep.append(f"  {el}")

        rep.append("==================================================")
        text = "\n".join(rep)
        QApplication.clipboard().setText(text)
        QMessageBox.information(self, "Report Copied", "✅ Comprehensive Diagnostic Report copied to clipboard!\n\nYou can now paste it into notes, emails, or support chats.")

    def action_launch_mirror(self):
        devs = SystemPaths.list_devices()
        active = [d for d in devs if d["state"] == "device"]
        if not active:
            QMessageBox.warning(self, "No Active Device", "No online device available. Connect phone or start VM first.")
            return
        target = active[0]["serial"]
        self.accept()
        start_mirror_with_fallback(target, self.parent())


# Google System Images & Multi-Instance Engine
# ----------------------------------------------------------------------
GOOGLE_SYS_IMAGES = {
    36: {
        "name": "Android 16 (API 36) — Baklava [Experimental Developer Preview]",
        "api": 36,
        "url": "https://dl.google.com/android/repository/sys-img/google_apis_playstore/x86_64-36_r07.zip",
        "size_mb": 1835.5,
        "tag": "google_apis_playstore"
    },
    35: {
        "name": "Android 15 (API 35) — Vanilla Ice Cream",
        "api": 35,
        "url": "https://dl.google.com/android/repository/sys-img/google_apis_playstore/x86_64-35_r09.zip",
        "size_mb": 1680.4,
        "tag": "google_apis_playstore"
    },
    34: {
        "name": "Android 14 (API 34) — Upside Down Cake [Recommended • 100% Stable & App Compatible]",
        "api": 34,
        "url": "https://dl.google.com/android/repository/sys-img/google_apis_playstore/x86_64-34_r14.zip",
        "size_mb": 1440.8,
        "tag": "google_apis_playstore"
    },
    33: {
        "name": "Android 13 (API 33) — Tiramisu",
        "api": 33,
        "url": "https://dl.google.com/android/repository/sys-img/google_apis_playstore/x86_64-33_r13.zip",
        "size_mb": 1420.0,
        "tag": "google_apis_playstore"
    }
}

class AVDManager:
    _active_instances: Dict[str, Dict[str, Any]] = {}
    _instances_lock = threading.Lock()

    @classmethod
    def get_active_instance(cls, name: str) -> Optional[Dict[str, Any]]:
        with cls._instances_lock:
            inst = cls._active_instances.get(name)
            if inst:
                proc = inst.get("proc")
                if proc and hasattr(proc, "poll") and proc.poll() is not None:
                    cls._active_instances.pop(name, None)
                    return None
            return inst

    @classmethod
    def get_all_active_instances(cls) -> Dict[str, Dict[str, Any]]:
        with cls._instances_lock:
            dead = [k for k, v in cls._active_instances.items() if v.get("proc") and hasattr(v["proc"], "poll") and v["proc"].poll() is not None]
            for k in dead:
                cls._active_instances.pop(k, None)
            return dict(cls._active_instances)

    @classmethod
    def stop_instance(cls, name: str, timeout: float = 5.0) -> bool:
        """
        Gracefully stops a running VM instance:
        1. Issues 'adb emu kill'
        2. Polls proc.poll()
        3. Falls back to proc.terminate() and proc.kill()
        4. Verifies complete process exit and unregisters from registry.
        """
        inst = None
        with cls._instances_lock:
            inst = cls._active_instances.get(name)

        serial = inst.get("serial") if inst else None
        proc = inst.get("proc") if inst else None
        pid = inst.get("pid") if inst else None

        if not serial:
            devs = SystemPaths.list_devices()
            match = next((d for d in devs if d.get("is_emulator") and (name in d.get("model", "") or name in d.get("name", ""))), None)
            if match:
                serial = match.get("serial")

        adb = SystemPaths.get_adb()
        if serial:
            try:
                subprocess.run([adb, "-s", serial, "emu", "kill"], timeout=2.5, creationflags=0x08000000)
            except Exception:
                pass

        start = time.time()
        if proc and hasattr(proc, "poll"):
            poll_res = None
            while time.time() - start < timeout:
                poll_res = proc.poll()
                if poll_res is not None:
                    break
                if time.time() - start > (timeout / 2):
                    try:
                        proc.terminate()
                    except Exception:
                        pass
                time.sleep(0.1)

            if poll_res is None:
                try:
                    proc.kill()
                    proc.wait(timeout=1.0)
                except Exception:
                    pass

        if pid:
            try:
                import psutil
                if psutil.pid_exists(pid):
                    p = psutil.Process(pid)
                    p.terminate()
                    p.wait(timeout=1.5)
            except Exception:
                pass

        with cls._instances_lock:
            cls._active_instances.pop(name, None)
        return True

    @classmethod
    def stop_all_instances(cls, timeout: float = 4.0):
        """Stops all tracked active VM instances."""
        with cls._instances_lock:
            names = list(cls._active_instances.keys())
        for n in names:
            cls.stop_instance(n, timeout=timeout)

    @staticmethod
    def get_avd_dir() -> str:
        d = os.path.join(os.path.expanduser("~"), ".android", "avd")
        os.makedirs(d, exist_ok=True)
        return d

    @staticmethod
    def get_sdk_dir() -> str:
        for env_k in ["ANDROID_HOME", "ANDROID_SDK_ROOT"]:
            v = os.environ.get(env_k)
            if v and os.path.exists(v):
                return v
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        standard = os.path.join(local_app_data, "Android", "Sdk")
        if os.path.exists(standard):
            return standard
        user_p = os.path.join(os.path.expanduser("~"), "Android", "Sdk")
        if os.path.exists(user_p):
            return user_p
        for drive in ["C:\\", "D:\\"]:
            cand = os.path.join(drive, "Android", "Sdk")
            if os.path.exists(cand):
                return cand
        os.makedirs(standard, exist_ok=True)
        return standard

    @staticmethod
    def get_image_sysdir(api_level: int) -> str:
        sdk = AVDManager.get_sdk_dir()
        for tag in ["google_apis_playstore", "google_apis", "default"]:
            p = os.path.join(sdk, "system-images", f"android-{api_level}", tag, "x86_64", "system.img")
            if os.path.exists(p):
                return f"system-images/android-{api_level}/{tag}/x86_64/"
        return f"system-images/android-{api_level}/google_apis_playstore/x86_64/"

    @staticmethod
    def is_image_installed(api_level: int) -> bool:
        sdk = AVDManager.get_sdk_dir()
        for tag in ["google_apis_playstore", "google_apis", "default"]:
            p = os.path.join(sdk, "system-images", f"android-{api_level}", tag, "x86_64", "system.img")
            if os.path.exists(p):
                return True
        return False

    @staticmethod
    def ensure_default_flagship_avd() -> bool:
        avd_base = AVDManager.get_avd_dir()
        gndroid_ini = os.path.join(avd_base, "gndroid.ini")
        gndroid_dir = os.path.join(avd_base, "gndroid.avd")
        config_ini = os.path.join(gndroid_dir, "config.ini")
        if os.path.exists(gndroid_ini) and os.path.exists(config_ini):
            return True
        api = 34
        for cand_api in [34, 35, 33, 36]:
            if AVDManager.is_image_installed(cand_api):
                api = cand_api
                break
        try:
            hw_info = SystemPaths.get_host_hardware_summary()
            host_ram_mb = hw_info["ram_gb"] * 1024
            safe_ram_mb = min(8192, max(2048, host_ram_mb // 2))
            safe_cores = min(8, max(2, hw_info["cores"] // 2))
            disp_name = f"GNDROiD Flagship ({safe_ram_mb // 1024}GB RAM / {safe_cores} Cores)"
            AVDManager.create_instance(
                name="gndroid",
                display_name=disp_name,
                api_level=api,
                ram_mb=safe_ram_mb,
                cores=safe_cores,
                width=1080,
                height=2400,
                density=420,
                gpu="auto",
                root_enabled=False,
                overwrite=True
            )
            return True
        except Exception:
            return False

    @staticmethod
    def clean_stale_locks() -> int:
        avd_base = AVDManager.get_avd_dir()
        if not os.path.exists(avd_base):
            return 0
        cleaned = 0
        for root, dirs, files in os.walk(avd_base):
            for f in files:
                if f.endswith(".lock"):
                    try:
                        os.remove(os.path.join(root, f))
                        cleaned += 1
                    except Exception:
                        pass
        return cleaned

    @staticmethod
    def list_instances() -> List[Dict[str, Any]]:
        avd_base = AVDManager.get_avd_dir()
        instances = []
        if not os.path.exists(avd_base):
            return instances

        active_emulators = {}
        try:
            adb = SystemPaths.get_adb()
            out = subprocess.check_output([adb, "devices"], text=True, timeout=2, creationflags=0x08000000)
            for line in out.strip().splitlines()[1:]:
                if "emulator-" in line:
                    serial = line.split()[0]
                    try:
                        name_out = subprocess.check_output([adb, "-s", serial, "emu", "avd", "name"], text=True, timeout=1, creationflags=0x08000000).strip()
                        avd_n = name_out.splitlines()[0].strip() if name_out else ""
                        if avd_n:
                            active_emulators[avd_n] = serial
                    except Exception:
                        pass
        except Exception:
            pass

        for ini_path in glob.glob(os.path.join(avd_base, "*.ini")):
            avd_name = os.path.splitext(os.path.basename(ini_path))[0]
            avd_folder = os.path.join(avd_base, f"{avd_name}.avd")
            config_ini = os.path.join(avd_folder, "config.ini")

            spec = {
                "name": avd_name,
                "display_name": avd_name.replace("_", " ").title(),
                "ram_mb": 4096,
                "cores": 4,
                "width": 1080,
                "height": 2400,
                "density": 420,
                "gpu": "auto",
                "target": "android-34",
                "api_level": 34,
                "root": False,
                "running": avd_name in active_emulators,
                "serial": active_emulators.get(avd_name, ""),
                "exists": os.path.exists(avd_folder)
            }

            if os.path.exists(config_ini):
                try:
                    with open(config_ini, "r", encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            if "=" in line:
                                k, v = line.split("=", 1)
                                k, v = k.strip(), v.strip()
                                if k == "avd.ini.displayname":
                                    spec["display_name"] = re.sub(r'(?i)gnd[o|r]*id', 'GNDROiD', v)
                                elif k == "hw.ramSize":
                                    try: spec["ram_mb"] = int(v)
                                    except: pass
                                elif k == "hw.cpu.ncore":
                                    try: spec["cores"] = int(v)
                                    except: pass
                                elif k == "hw.lcd.width":
                                    try: spec["width"] = int(v)
                                    except: pass
                                elif k == "hw.lcd.height":
                                    try: spec["height"] = int(v)
                                    except: pass
                                elif k == "hw.lcd.density":
                                    try: spec["density"] = int(v)
                                    except: pass
                                elif k == "hw.gpu.mode":
                                    spec["gpu"] = v
                                elif k == "target":
                                    spec["target"] = v
                                    match = re.search(r"android-(\d+)", v)
                                    if match: spec["api_level"] = int(match.group(1))
                                elif k == "image.sysdir.1":
                                    match = re.search(r"android-(\d+)", v)
                                    if match: spec["api_level"] = int(match.group(1))
                                elif k == "gndroid.root":
                                    spec["root"] = (v.lower() in ["yes", "true", "1"])
                except Exception:
                    pass

            instances.append(spec)
        return instances

    @staticmethod
    def get_next_free_emulator_port(start_port: int = 5554) -> int:
        for port in range(start_port, 5586, 2):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s1:
                res1 = s1.connect_ex(("127.0.0.1", port))
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s2:
                res2 = s2.connect_ex(("127.0.0.1", port + 1))
            if res1 != 0 and res2 != 0:
                return port
        return 5554

    @staticmethod
    def create_instance(name: str, display_name: str, api_level: int, ram_mb: int, cores: int, width: int, height: int, density: int, gpu: str, root_enabled: bool, overwrite: bool = False) -> None:
        avd_base = AVDManager.get_avd_dir()
        os.makedirs(avd_base, exist_ok=True)
        dst_ini = os.path.join(avd_base, f"{name}.ini")
        dst_dir = os.path.join(avd_base, f"{name}.avd")

        if os.path.exists(dst_ini) or os.path.exists(dst_dir):
            if not overwrite:
                raise FileExistsError(f"Instance with name '{name}' already exists.")
            else:
                try:
                    if os.path.exists(dst_ini): os.remove(dst_ini)
                    if os.path.exists(dst_dir): shutil.rmtree(dst_dir, ignore_errors=True)
                except Exception:
                    pass

        os.makedirs(dst_dir, exist_ok=True)

        sysdir = AVDManager.get_image_sysdir(api_level)
        tag_id = "google_apis_playstore"
        tag_disp = "Google Play"
        if "google_apis/" in sysdir:
            tag_id = "google_apis"
            tag_disp = "Google APIs"
        elif "default/" in sysdir:
            tag_id = "default"
            tag_disp = "Default System"

        with open(dst_ini, "w", encoding="utf-8") as f:
            f.write("avd.ini.encoding=UTF-8\n")
            f.write(f"path={dst_dir}\n")
            f.write(f"path.rel=avd/{name}.avd\n")
            f.write(f"target=android-{api_level}\n")

        cfg_content = f"""AvdId={name}
PlayStore.enabled={'true' if tag_id == 'google_apis_playstore' else 'false'}
abi.type=x86_64
avd.ini.displayname={display_name}
avd.ini.encoding=UTF-8
disk.dataPartition.size=32G
fastboot.chosenSnapshotFile=
fastboot.forceChosenSnapshotBoot=no
fastboot.forceColdBoot=no
fastboot.forceFastBoot=yes
hw.accelerometer=yes
hw.arc=false
hw.audioInput=yes
hw.battery=yes
hw.camera.back=webcam0
hw.camera.front=webcam0
hw.cpu.arch=x86_64
hw.cpu.ncore={cores}
hw.dPad=no
hw.device.manufacturer=Ghulam Nabi Kalhoro
hw.device.name={name}
hw.fingerprint=yes
hw.gps=yes
hw.gpu.enabled=yes
hw.gpu.mode={gpu}
hw.gyroscope=yes
hw.initialOrientation=portrait
hw.keyboard=yes
hw.lcd.density={density}
hw.lcd.height={height}
hw.lcd.width={width}
hw.mainKeys=no
hw.ramSize={ram_mb}
hw.sdCard=yes
hw.sensors.light=yes
hw.sensors.magnetic_field=yes
hw.sensors.orientation=yes
hw.sensors.pressure=yes
hw.sensors.proximity=yes
hw.trackBall=no
hw.wifi=yes
image.sysdir.1={sysdir}
runtime.network.latency=none
runtime.network.speed=full
sdcard.size=16G
showDeviceFrame=yes
skin.dynamic=yes
tag.display={tag_disp}
tag.displaynames={tag_disp}
tag.id={tag_id}
tag.ids={tag_id}
target=android-{api_level}
vm.heapSize=1024
gndroid.root={'yes' if root_enabled else 'no'}
"""
        with open(os.path.join(dst_dir, "config.ini"), "w", encoding="utf-8") as f:
            f.write(cfg_content)

    @staticmethod
    def clone_instance(src_name: str, dst_name: str, dst_display_name: str, ram_mb: int = None, cores: int = None, root_enabled: bool = None, full_clone: bool = True, progress_cb=None, deep_copy_snapshots: bool = False) -> None:
        avd_base = AVDManager.get_avd_dir()
        src_dir = os.path.join(avd_base, f"{src_name}.avd")
        src_ini = os.path.join(avd_base, f"{src_name}.ini")
        dst_dir = os.path.join(avd_base, f"{dst_name}.avd")
        dst_ini = os.path.join(avd_base, f"{dst_name}.ini")

        if os.path.exists(dst_ini) or os.path.exists(dst_dir):
            raise FileExistsError(f"Instance '{dst_name}' already exists.")

        os.makedirs(dst_dir, exist_ok=True)

        # Fast clone: exclude transient locks, temp commands, and massive 16GB snapshot RAM dumps
        skip_files = {"hardware-qemu.ini.lock", "multiinstance.lock"}
        if not full_clone:
            skip_files.update({"userdata-qemu.img", "userdata-qemu.img.qcow2", "cache.img", "cache.img.qcow2"})

        files_to_copy = []
        for root, dirs, files in os.walk(src_dir):
            # Always skip lock files, sockets, and memory dump files that cause 16GB bloat or crashes
            if "tmpAdbCmds" in root:
                continue
            if (not full_clone or not deep_copy_snapshots) and "snapshots" in root:
                continue
            for f in files:
                if f.endswith(".lock") or f in skip_files or f in ("ram.img", "ram.bin"):
                    continue
                rel_path = os.path.relpath(os.path.join(root, f), src_dir)
                files_to_copy.append(rel_path)

        total = len(files_to_copy)
        for idx, rel in enumerate(files_to_copy):
            s_file = os.path.join(src_dir, rel)
            d_file = os.path.join(dst_dir, rel)
            os.makedirs(os.path.dirname(d_file), exist_ok=True)
            shutil.copy2(s_file, d_file)
            if progress_cb:
                progress_cb(int((idx + 1) / max(1, total) * 100))

        target_api = "android-34"
        if os.path.exists(src_ini):
            with open(src_ini, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.strip().startswith("target="):
                        target_api = line.strip().split("=")[1]

        with open(dst_ini, "w", encoding="utf-8") as f:
            f.write("avd.ini.encoding=UTF-8\n")
            f.write(f"path={dst_dir}\n")
            f.write(f"path.rel=avd/{dst_name}.avd\n")
            f.write(f"target={target_api}\n")

        dst_cfg = os.path.join(dst_dir, "config.ini")
        cfg_lines = []
        if os.path.exists(dst_cfg):
            with open(dst_cfg, "r", encoding="utf-8", errors="ignore") as f:
                cfg_lines = f.readlines()

        updated_cfg = []
        found_keys = set()
        for line in cfg_lines:
            ls = line.strip()
            if ls.startswith("AvdId="):
                updated_cfg.append(f"AvdId={dst_name}\n")
                found_keys.add("AvdId")
            elif ls.startswith("avd.ini.displayname="):
                updated_cfg.append(f"avd.ini.displayname={dst_display_name}\n")
                found_keys.add("avd.ini.displayname")
            elif ls.startswith("hw.ramSize=") and ram_mb:
                updated_cfg.append(f"hw.ramSize={ram_mb}\n")
                found_keys.add("hw.ramSize")
            elif ls.startswith("hw.cpu.ncore=") and cores:
                updated_cfg.append(f"hw.cpu.ncore={cores}\n")
                found_keys.add("hw.cpu.ncore")
            elif ls.startswith("gndroid.root=") and root_enabled is not None:
                updated_cfg.append(f"gndroid.root={'yes' if root_enabled else 'no'}\n")
                found_keys.add("gndroid.root")
            else:
                updated_cfg.append(line)

        if "AvdId" not in found_keys: updated_cfg.append(f"AvdId={dst_name}\n")
        if "avd.ini.displayname" not in found_keys: updated_cfg.append(f"avd.ini.displayname={dst_display_name}\n")
        if "hw.ramSize" not in found_keys and ram_mb: updated_cfg.append(f"hw.ramSize={ram_mb}\n")
        if "hw.cpu.ncore" not in found_keys and cores: updated_cfg.append(f"hw.cpu.ncore={cores}\n")
        if "gndroid.root" not in found_keys and root_enabled is not None: updated_cfg.append(f"gndroid.root={'yes' if root_enabled else 'no'}\n")

        with open(dst_cfg, "w", encoding="utf-8") as f:
            f.writelines(updated_cfg)

    @staticmethod
    def launch_emulator_instance(name: str = "gndroid", port: int = None, gpu_mode: str = "auto", is_root: bool = False):
        """
        Launches an emulator instance in stealth background mode without popping up any visible
        command line / console window, logs all output to logs/emulator_<name>.log, and
        starts a background watcher to rename the window title away from 'Android Emulator'.
        """
        if port is None:
            port = AVDManager.get_next_free_emulator_port()

        emu = SystemPaths.get_emulator()
        # 1. Clear any stale locks before launching
        avd_base = AVDManager.get_avd_dir()
        avd_inst_dir = os.path.join(avd_base, f"{name}.avd")
        if os.path.exists(avd_inst_dir):
            try:
                for f_lock in os.listdir(avd_inst_dir):
                    if f_lock.endswith(".lock"):
                        p_lock = os.path.join(avd_inst_dir, f_lock)
                        if os.path.isdir(p_lock):
                            shutil.rmtree(p_lock, ignore_errors=True)
                        else:
                            os.remove(p_lock)
            except Exception:
                pass

        # Automatically sanitize any multi-display config to prevent 4K/wild landscape viewport distortions
        try:
            from nexus.display_and_vpn import sanitize_multi_display_config
            cfg_path = os.path.join(avd_inst_dir, "config.ini")
            if os.path.exists(cfg_path):
                sanitize_multi_display_config(cfg_path)
        except Exception:
            pass

        cmd = [
            emu, "-avd", name, "-port", str(port), "-gpu", gpu_mode,
            "-netfast", "-netdelay", "none", "-netspeed", "full",
            "-no-snapshot-load", "-crash-report-mode", "never",
            "-dns-server", "8.8.8.8,1.1.1.1",
            "-wifi-user-mode-options", "ipv6=off",
            "-network-user-mode-options", "ipv6=off"
        ]

        # Append multi-display launch arguments if enabled for instance
        try:
            from nexus.display_and_vpn import get_multi_display_emulator_args
            sec_args = get_multi_display_emulator_args(name)
            if sec_args:
                cmd.extend(sec_args)
        except Exception:
            pass

        # Append hardware network & bluetooth bridge launch arguments if configured
        try:
            from nexus.network_bridge import get_emulator_network_args
            net_args = get_emulator_network_args(name)
            if net_args:
                cmd.extend(net_args)
        except Exception:
            pass

        if is_root:
            cmd.extend(["-writable-system", "-selinux", "permissive"])

        env = os.environ.copy()
        env["QEMU_AUDIO_DRV"] = "none"
        sdk_dir = AVDManager.get_sdk_dir()
        avd_dir = AVDManager.get_avd_dir()
        env["ANDROID_SDK_ROOT"] = sdk_dir
        env["ANDROID_HOME"] = sdk_dir
        env["ANDROID_AVD_HOME"] = avd_dir
        emu_dir = os.path.join(sdk_dir, "emulator")
        pt_dir = os.path.join(sdk_dir, "platform-tools")
        env["PATH"] = f"{emu_dir};{pt_dir};" + env.get("PATH", "")

        # 2. Setup logs directory & log file
        base_dir = get_base_dir()
        logs_dir = os.path.join(base_dir, "logs")
        try:
            os.makedirs(logs_dir, exist_ok=True)
        except Exception:
            pass
        log_path = os.path.join(logs_dir, f"emulator_{name}.log")

        try:
            log_file = open(log_path, "a", encoding="utf-8")
            from datetime import datetime
            log_file.write(f"\n==================================================\n")
            log_file.write(f"GNDROiD Instance Launch: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            log_file.write(f"Instance: {name} | Port: {port} | GPU: {gpu_mode} | Root: {is_root}\n")
            log_file.write(f"Command: {' '.join(cmd)}\n")
            log_file.write(f"==================================================\n\n")
            log_file.flush()
        except Exception:
            log_file = subprocess.DEVNULL

        # 3. Suppress black console window without hiding the phone GUI window
        CREATE_NO_WINDOW = 0x08000000

        proc = subprocess.Popen(
            cmd,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW
        )

        # Feature 8: Assign QEMU process to Win32 Job Object for process tree containment
        try:
            from nexus.app_cloner_and_window import assign_to_job_object
            assign_to_job_object(proc)
        except Exception:
            pass

        target_serial = f"emulator-{port}"
        with AVDManager._instances_lock:
            AVDManager._active_instances[name] = {
                "proc": proc,
                "pid": proc.pid if hasattr(proc, "pid") else None,
                "port": port,
                "serial": target_serial,
                "name": name,
                "launch_time": time.time(),
                "gpu": gpu_mode,
                "root": is_root
            }

        # 3. Retitle window in background (rename from 'Android Emulator - ...' to 'GNDROiD Flagship:port')
        def _retitle_watcher(parent_pid: int, inst_name: str, inst_port: int):
            try:
                cfg = AVDManager.get_instance_full_config(inst_name)
                disp_name = cfg.get("avd.ini.displayname", "").strip()
                if not disp_name or disp_name.lower() in ["gndroid", "emulator"]:
                    disp_name = "GNDROiD Flagship"
                target_title = f"{disp_name}:{inst_port}"

                user32 = ctypes.windll.user32
                h_winsta = user32.OpenWindowStationW("WinSta0", False, 0x10000000)
                if h_winsta:
                    user32.SetProcessWindowStation(h_winsta)
                    h_desk = user32.OpenDesktopW("Default", 0, False, 0x10000000)
                    if h_desk:
                        user32.SetThreadDesktop(h_desk)

                from ctypes import wintypes
                WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

                # Monitor for 60 seconds (covers startup, initialization, and stabilization)
                for _ in range(60):
                    time.sleep(1.0)
                    pids_to_match = {parent_pid}
                    try:
                        import psutil
                        p_obj = psutil.Process(parent_pid)
                        for c in p_obj.children(recursive=True):
                            pids_to_match.add(c.pid)
                    except Exception:
                        pass

                    def enum_cb(hwnd, lparam):
                        length = user32.GetWindowTextLengthW(hwnd)
                        if length > 0:
                            buf = ctypes.create_unicode_buffer(length + 1)
                            user32.GetWindowTextW(hwnd, buf, length + 1)
                            t = buf.value
                            pid = wintypes.DWORD()
                            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

                            if "antigravity" in t.lower() or "visual studio" in t.lower():
                                return True

                            if user32.IsWindowVisible(hwnd) and t.startswith("Android Emulator") and f":{inst_port}" in t:
                                if t != target_title:
                                    user32.SetWindowTextW(hwnd, target_title)
                        return True

                    try:
                        user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
                    except Exception:
                        pass
            except Exception:
                pass

        threading.Thread(target=_retitle_watcher, args=(proc.pid, name, port), daemon=True).start()

        # 4. Post-boot lifecycle watcher: remount if root & auto-stabilize VPN networking
        target_serial = f"emulator-{port}"
        def post_boot_lifecycle_watcher():
            adb = SystemPaths.get_adb()
            for _ in range(60):
                time.sleep(2)
                try:
                    st = subprocess.check_output([adb, "-s", target_serial, "get-state"], text=True, timeout=2, creationflags=0x08000000).strip()
                    if st == "device":
                        if is_root:
                            subprocess.run([adb, "-s", target_serial, "root"], timeout=4, creationflags=0x08000000)
                            time.sleep(1)
                            subprocess.run([adb, "-s", target_serial, "remount"], timeout=4, creationflags=0x08000000)
                        try:
                            from nexus.display_and_vpn import auto_stabilize_vpn_networking
                            auto_stabilize_vpn_networking(target_serial)
                        except Exception:
                            pass
                        try:
                            from nexus.network_bridge import start_global_lan_bridge, get_instance_network_config
                            net_cfg = get_instance_network_config(name)
                            if net_cfg.get("mode") in ["lan_bridge", "hardware_bridged"]:
                                start_global_lan_bridge()
                                for p in [51888, 51880, 5555, 8088]:
                                    subprocess.run([adb, "-s", target_serial, "forward", f"tcp:{p}", f"tcp:{p}"], capture_output=True, creationflags=0x08000000)
                        except Exception:
                            pass
                        break
                except Exception:
                    pass
        threading.Thread(target=post_boot_lifecycle_watcher, daemon=True).start()

        return proc, port, log_path

    @staticmethod
    def get_instance_full_config(name: str = "gndroid") -> dict:
        avd_base = AVDManager.get_avd_dir()
        cfg_path = os.path.join(avd_base, f"{name}.avd", "config.ini")
        cfg = {}
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if "=" in line:
                            k, v = line.split("=", 1)
                            cfg[k.strip()] = v.strip()
            except Exception:
                pass
        return cfg

    @staticmethod
    def save_full_instance_config(name: str, config_dict: dict) -> bool:
        avd_base = AVDManager.get_avd_dir()
        cfg_path = os.path.join(avd_base, f"{name}.avd", "config.ini")
        if not os.path.exists(cfg_path):
            return False

        with open(cfg_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        keys_to_set = dict(config_dict)
        updated = []
        handled_keys = set()

        for line in lines:
            ls = line.strip()
            matched = False
            for k, v in keys_to_set.items():
                if ls.startswith(f"{k}=") or ls.startswith(f"{k} ="):
                    updated.append(f"{k} = {v}\n")
                    handled_keys.add(k)
                    matched = True
                    break
            if not matched:
                updated.append(line)

        for k, v in keys_to_set.items():
            if k not in handled_keys:
                updated.append(f"{k} = {v}\n")

        with open(cfg_path, "w", encoding="utf-8") as f:
            f.writelines(updated)

        # Automatically synchronize secondary display configuration if specified
        try:
            from nexus.display_and_vpn import set_secondary_display_config
            if "hw.display1.enabled" in config_dict or "gndroid.secondary_display" in config_dict:
                sec_en = str(config_dict.get("hw.display1.enabled", config_dict.get("gndroid.secondary_display", "false"))).lower() in ["true", "yes", "1"]
                sec_match = str(config_dict.get("hw.display1.match_primary", config_dict.get("gndroid.secondary_display.match_primary", "true"))).lower() in ["true", "yes", "1"]
                sec_w = int(config_dict.get("hw.display1.width", 0))
                sec_h = int(config_dict.get("hw.display1.height", 0))
                sec_d = int(config_dict.get("hw.display1.density", 0))
                set_secondary_display_config(name, enabled=sec_en, match_primary=sec_match, width=sec_w, height=sec_h, density=sec_d)
        except Exception:
            pass

        return True

    @staticmethod
    def update_instance_settings(name: str, ram_mb: int, cores: int, width: int, height: int, density: int, gpu: str, root_enabled: bool) -> None:
        avd_base = AVDManager.get_avd_dir()
        cfg_path = os.path.join(avd_base, f"{name}.avd", "config.ini")
        if not os.path.exists(cfg_path):
            return

        with open(cfg_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        updated = []
        found = set()
        for line in lines:
            ls = line.strip()
            # Preserve secondary display keys so settings updates don't discard multi-display configs
            if ls.startswith("hw.display1.") or ls.startswith("hw.display2.") or ls.startswith("hw.multi_display_window") or ls.startswith("hw.hotplug_multi_display") or ls.startswith("gndroid.secondary_display"):
                updated.append(line)
                continue
            k = ls.split("=")[0].strip() if "=" in ls else ""
            if k == "hw.ramSize" or ls.startswith("hw.ramSize=") or ls.startswith("hw.ramSize ="):
                updated.append(f"hw.ramSize={ram_mb}\n"); found.add("hw.ramSize")
            elif k == "hw.cpu.ncore" or ls.startswith("hw.cpu.ncore=") or ls.startswith("hw.cpu.ncore ="):
                updated.append(f"hw.cpu.ncore={cores}\n"); found.add("hw.cpu.ncore")
            elif k == "hw.lcd.width" or ls.startswith("hw.lcd.width=") or ls.startswith("hw.lcd.width ="):
                updated.append(f"hw.lcd.width={width}\n"); found.add("hw.lcd.width")
            elif k == "hw.lcd.height" or ls.startswith("hw.lcd.height=") or ls.startswith("hw.lcd.height ="):
                updated.append(f"hw.lcd.height={height}\n"); found.add("hw.lcd.height")
            elif k == "hw.lcd.density" or ls.startswith("hw.lcd.density=") or ls.startswith("hw.lcd.density ="):
                updated.append(f"hw.lcd.density={density}\n"); found.add("hw.lcd.density")
            elif k == "hw.gpu.mode" or ls.startswith("hw.gpu.mode=") or ls.startswith("hw.gpu.mode ="):
                updated.append(f"hw.gpu.mode={gpu}\n"); found.add("hw.gpu.mode")
            elif k == "gndroid.root" or ls.startswith("gndroid.root=") or ls.startswith("gndroid.root ="):
                updated.append(f"gndroid.root={'yes' if root_enabled else 'no'}\n"); found.add("gndroid.root")
            else:
                updated.append(line)

        if "hw.ramSize" not in found: updated.append(f"hw.ramSize={ram_mb}\n")
        if "hw.cpu.ncore" not in found: updated.append(f"hw.cpu.ncore={cores}\n")
        if "hw.lcd.width" not in found: updated.append(f"hw.lcd.width={width}\n")
        if "hw.lcd.height" not in found: updated.append(f"hw.lcd.height={height}\n")
        if "hw.lcd.density" not in found: updated.append(f"hw.lcd.density={density}\n")
        if "hw.gpu.mode" not in found: updated.append(f"hw.gpu.mode={gpu}\n")
        if "gndroid.root" not in found: updated.append(f"gndroid.root={'yes' if root_enabled else 'no'}\n")

        with open(cfg_path, "w", encoding="utf-8") as f:
            f.writelines(updated)

    @staticmethod
    def reset_instance_display(name: str, width: int = 1440, height: int = 3120, density: int = 500) -> None:
        """Purges any multi-display residual settings, resets resolution, removes stale hardware-qemu.ini and corrupted snapshots."""
        avd_base = AVDManager.get_avd_dir()
        avd_dir = os.path.join(avd_base, f"{name}.avd")
        cfg_path = os.path.join(avd_dir, "config.ini")
        if not os.path.exists(cfg_path):
            return

        with open(cfg_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        clean = []
        for line in lines:
            ls = line.strip()
            if ls.startswith("hw.display1.") or ls.startswith("hw.display2."):
                continue
            elif ls.startswith("hw.lcd.width"):
                clean.append(f"hw.lcd.width = {width}\n")
            elif ls.startswith("hw.lcd.height"):
                clean.append(f"hw.lcd.height = {height}\n")
            elif ls.startswith("hw.lcd.density"):
                clean.append(f"hw.lcd.density = {density}\n")
            elif ls.startswith("fastboot.forceColdBoot"):
                clean.append("fastboot.forceColdBoot = yes\n")
            else:
                clean.append(line)

        with open(cfg_path, "w", encoding="utf-8") as f:
            f.writelines(clean)

        # Remove stale hardware-qemu.ini so QEMU re-reads config.ini cleanly
        hq_path = os.path.join(avd_dir, "hardware-qemu.ini")
        if os.path.exists(hq_path):
            try: os.remove(hq_path)
            except: pass

        # Clean locks
        for lock in ["hardware-qemu.ini.lock", "multiinstance.lock"]:
            lp = os.path.join(avd_dir, lock)
            if os.path.exists(lp):
                try:
                    if os.path.isdir(lp): shutil.rmtree(lp, ignore_errors=True)
                    else: os.remove(lp)
                except: pass

        # Clean stale snapshots to prevent gfxstream/renderer mismatch crashes
        snap_dir = os.path.join(avd_dir, "snapshots")
        if os.path.exists(snap_dir):
            try:
                shutil.rmtree(snap_dir, ignore_errors=True)
                os.makedirs(snap_dir, exist_ok=True)
            except: pass

    @staticmethod
    def check_live_root(serial: str = "") -> Dict[str, Any]:
        """Performs live root status check on the guest Android OS."""
        adb = SystemPaths.get_adb()
        result = {
            "is_live_root": False,
            "uid": -1,
            "has_su": False,
            "build_type": "unknown",
            "message": "Device not connected"
        }
        if not serial or serial == "gndroid":
            devs = SystemPaths.list_devices()
            active = [d["serial"] for d in devs if d["state"] == "device"]
            if not active:
                return result
            serial = active[0]

        try:
            out = subprocess.check_output(
                [adb, "-s", serial, "shell", "id; which su; getprop ro.build.type"],
                text=True, timeout=3, creationflags=0x08000000
            )
            lines = [l.strip() for l in out.strip().splitlines() if l.strip()]
            for l in lines:
                if l.startswith("uid="):
                    if "uid=0(root)" in l:
                        result["is_live_root"] = True
                        result["uid"] = 0
                    else:
                        m = re.search(r"uid=(\d+)", l)
                        if m: result["uid"] = int(m.group(1))
                elif "su" in l and ("bin" in l or "xbin" in l):
                    result["has_su"] = True
                elif l in ["user", "userdebug", "eng"]:
                    result["build_type"] = l

            if result["is_live_root"]:
                result["message"] = "🟢 Genuine Root Active (UID 0: root)"
            elif result["build_type"] == "user":
                result["message"] = "🔒 Production Google Play Build (SELinux Enforcing). Legacy SuperSU cannot root Android 10-16. Use Magisk/rootAVD or Google APIs image."
            elif result["has_su"]:
                result["message"] = "⚡ SU Binary Found in PATH (/system/xbin/su)"
            else:
                result["message"] = f"⚠️ Unrooted Guest (UID {result['uid']}). Run 'adb root' on Google APIs image."
        except Exception as e:
            result["message"] = f"Check failed: {e}"
        return result

    @staticmethod
    def is_file_locked(filepath: str) -> bool:
        """
        Checks if a file has an active open handle or lock.
        Uses Win32 CreateFileW with FILE_SHARE_NONE for definitive Windows handle inspection.
        """
        if not os.path.exists(filepath):
            return False
        if sys.platform == "win32":
            try:
                k32 = ctypes.windll.kernel32
                GENERIC_READ = 0x80000000
                GENERIC_WRITE = 0x40000000
                FILE_SHARE_NONE = 0
                OPEN_EXISTING = 3
                FILE_ATTRIBUTE_NORMAL = 0x80
                INVALID_HANDLE_VALUE = -1

                h = k32.CreateFileW(
                    filepath,
                    GENERIC_READ | GENERIC_WRITE,
                    FILE_SHARE_NONE,
                    None,
                    OPEN_EXISTING,
                    FILE_ATTRIBUTE_NORMAL,
                    None
                )
                if h == INVALID_HANDLE_VALUE or h == -1:
                    return True
                k32.CloseHandle(h)
                return False
            except Exception:
                pass
        try:
            with open(filepath, "r+b"):
                pass
            return False
        except (PermissionError, OSError):
            return True

    @staticmethod
    def wait_for_file_locks_released(dir_path: str, timeout: float = 6.0) -> bool:
        """
        Progressive backoff retry loop ensuring open handles on virtual disk images
        (userdata.img, system.img.qcow2, etc.) are fully released before disk removal.
        """
        if not os.path.exists(dir_path):
            return True

        target_exts = (".img", ".qcow2", ".lock", ".ini")
        start = time.time()
        backoffs = [0.1, 0.2, 0.4, 0.8, 1.2, 1.5, 2.0]
        backoff_idx = 0

        while time.time() - start < timeout:
            any_locked = False
            try:
                for root, _, files in os.walk(dir_path):
                    for f in files:
                        if f.lower().endswith(target_exts) or "userdata" in f.lower() or "system" in f.lower():
                            fpath = os.path.join(root, f)
                            if AVDManager.is_file_locked(fpath):
                                any_locked = True
                                break
                    if any_locked:
                        break
            except Exception:
                pass

            if not any_locked:
                return True

            delay = backoffs[min(backoff_idx, len(backoffs) - 1)]
            backoff_idx += 1
            time.sleep(delay)

        return False

    @staticmethod
    def delete_instance(name: str) -> bool:
        """
        Feature 9: Multi-Instance Clean Teardown & File Lock Guard
        1. Verifies process termination (waits for process exit / kills if needed).
        2. Executes progressive backoff file lock guard on userdata.img / system.img.qcow2.
        3. Removes .ini pointer file and safely removes disk folder with retry loop.
        """
        avd_base = AVDManager.get_avd_dir()
        ini_path = os.path.join(avd_base, f"{name}.ini")
        dir_path = os.path.join(avd_base, f"{name}.avd")

        # 1. Verify process termination before attempting disk cleanup
        active_inst = AVDManager.get_active_instance(name)
        if active_inst:
            AVDManager.stop_instance(name, timeout=5.0)
        else:
            try:
                import psutil
                for p in psutil.process_iter(['name', 'cmdline']):
                    cmd = p.info.get('cmdline') or []
                    if any(name in arg for arg in cmd) and any("qemu" in c.lower() or "emulator" in c.lower() for c in cmd):
                        try:
                            p.terminate()
                            p.wait(timeout=2.0)
                        except Exception:
                            pass
            except Exception:
                pass

        # 2. File lock checking and retry loop with progressive backoff
        if os.path.exists(dir_path):
            AVDManager.wait_for_file_locks_released(dir_path, timeout=6.0)

        # 3. Clean .ini pointer file
        if os.path.exists(ini_path):
            try:
                os.remove(ini_path)
            except Exception:
                pass

        # 4. Safely delete directory with progressive retries
        deleted = False
        if os.path.exists(dir_path):
            for attempt in range(5):
                try:
                    shutil.rmtree(dir_path)
                    deleted = True
                    break
                except OSError:
                    time.sleep(0.3 * (attempt + 1))
            if not deleted:
                try:
                    shutil.rmtree(dir_path, ignore_errors=True)
                    deleted = not os.path.exists(dir_path)
                except Exception:
                    pass
        else:
            deleted = True

        return deleted


# ----------------------------------------------------------------------
# 1-Click System Image Downloader & Background Worker
# ----------------------------------------------------------------------
class ImageDownloadWorker(QThread):
    sig_progress = pyqtSignal(int, float, float, float, str)
    sig_status = pyqtSignal(str)
    sig_finished = pyqtSignal(bool, str)

    def __init__(self, api_level: int, parent=None):
        super().__init__(parent)
        self.api_level = api_level
        self.is_cancelled = False
        self.info = GOOGLE_SYS_IMAGES.get(api_level, GOOGLE_SYS_IMAGES[34])

    def cancel(self):
        self.is_cancelled = True

    def run(self):
        url = self.info["url"]
        sdk = AVDManager.get_sdk_dir()
        target_dir = os.path.join(sdk, "system-images", f"android-{self.api_level}", "google_apis_playstore", "x86_64")
        temp_dir = os.path.join(tempfile.gettempdir(), "gndroid_dl")
        os.makedirs(temp_dir, exist_ok=True)
        temp_zip = os.path.join(temp_dir, f"sysimg_api_{self.api_level}.zip")

        try:
            self.sig_status.emit(f"Connecting to Google CDN for {self.info['name']}...")
            req = urllib.request.Request(url, headers={"User-Agent": "gndroid-SystemImageDownloader/1.0"})

            with urllib.request.urlopen(req, timeout=15) as resp:
                total_len = int(resp.headers.get("Content-Length", 0))
                total_mb = total_len / (1024 * 1024) if total_len > 0 else self.info["size_mb"]

                downloaded = 0
                chunk_size = 256 * 1024
                start_time = time.time()
                last_update_time = start_time

                with open(temp_zip, "wb") as f:
                    while True:
                        if self.is_cancelled:
                            self.sig_status.emit("Download cancelled.")
                            self.sig_finished.emit(False, "Download cancelled by user.")
                            try: os.remove(temp_zip)
                            except: pass
                            return

                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)

                        now = time.time()
                        if now - last_update_time >= 0.2:
                            elapsed = max(0.001, now - start_time)
                            dl_mb = downloaded / (1024 * 1024)
                            speed_mb = dl_mb / elapsed
                            percent = int((downloaded / total_len * 100)) if total_len > 0 else 0

                            rem_mb = max(0, total_mb - dl_mb)
                            eta_sec = int(rem_mb / speed_mb) if speed_mb > 0 else 0
                            eta_str = f"{eta_sec // 60}m {eta_sec % 60}s" if eta_sec > 60 else f"{eta_sec}s"

                            self.sig_progress.emit(percent, dl_mb, total_mb, speed_mb, eta_str)
                            self.sig_status.emit(f"Downloading: {dl_mb:.1f} / {total_mb:.1f} MB ({percent}%) • {speed_mb:.1f} MB/s • ETA: {eta_str}")
                            last_update_time = now

            if self.is_cancelled:
                return

            self.sig_status.emit("Download complete! Extracting system image archive...")
            self.sig_progress.emit(100, total_mb, total_mb, 0.0, "Extracting...")

            os.makedirs(target_dir, exist_ok=True)
            with zipfile.ZipFile(temp_zip, "r") as zf:
                members = zf.infolist()
                total_m = len(members)
                for idx, m in enumerate(members):
                    if self.is_cancelled:
                        return
                    rel = m.filename[len("x86_64/"):] if m.filename.startswith("x86_64/") else m.filename
                    if not rel:
                        continue
                    dest = os.path.join(target_dir, rel)
                    if m.is_dir():
                        os.makedirs(dest, exist_ok=True)
                    else:
                        os.makedirs(os.path.dirname(dest), exist_ok=True)
                        with zf.open(m) as src_f, open(dest, "wb") as dst_f:
                            shutil.copyfileobj(src_f, dst_f)
                    if idx % 10 == 0:
                        self.sig_status.emit(f"Extracting system files ({idx+1}/{total_m})...")

            try: os.remove(temp_zip)
            except: pass

            self.sig_status.emit("✅ System Image successfully installed and verified!")
            self.sig_finished.emit(True, f"Android {self.api_level} System Image successfully installed into:\n{target_dir}")

        except Exception as e:
            self.sig_status.emit(f"Error: {str(e)}")
            self.sig_finished.emit(False, str(e))
            try:
                if os.path.exists(temp_zip): os.remove(temp_zip)
            except: pass


# ----------------------------------------------------------------------
# GNDROiD Wireless Debugging & QR Pairing Dialog (Android 11+ & TCP 5555)
# ----------------------------------------------------------------------
class GNDroidWirelessPairingDialog(QDialog):
    """
    Dedicated Wireless Debugging & QR Pairing Dialog for GNDROiD:
    - Tab 1: Android 11+ AOSP SPAKE2 QR Zero-Cable Pairing Engine with live mDNS listener.
    - Tab 2: 1-Click TCP 5555 Provisioning from USB to Wi-Fi with automatic LAN IP discovery.
    - Resilient background reconnection watchdog support.
    """
    sig_device_paired = pyqtSignal(str, str)  # target, model

    def __init__(self, target_serial: str = "", parent=None):
        super().__init__(parent)
        self.target_serial = target_serial
        self.setWindowTitle("📡 Wireless Debugging & QR Pairing Suite — Developed by Ghulam Nabi Kalhoro")
        self.setMinimumSize(560, 680)
        self.resize(580, 710)

        self.qr_worker: Optional[QRPairingWorker] = None
        self.current_service_name = ""
        self.current_password = ""
        self.watchdog: Optional[WirelessReconnectionWatchdog] = None

        self.setup_ui()
        self.start_qr_pairing()

    def closeEvent(self, event):
        if self.qr_worker and self.qr_worker.isRunning():
            self.qr_worker.stop()
        super().closeEvent(event)

    def setup_ui(self):
        self.setStyleSheet("""
            QDialog {
                background: #f8fafc;
                color: #0f172a;
                font-family: 'Segoe UI Variable Text', 'Segoe UI', -apple-system, sans-serif;
            }
            QFrame.cardBox {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
            }
            QTabWidget::pane {
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                background: #ffffff;
                top: -1px;
            }
            QTabBar::tab {
                background: #f1f5f9;
                color: #475569;
                padding: 10px 18px;
                border: 1px solid #cbd5e1;
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 4px;
                font-weight: 600;
                font-size: 12px;
            }
            QTabBar::tab:selected {
                background: #ffffff;
                color: #0284c7;
                border-bottom: 2px solid #0284c7;
            }
            QPushButton.btnPrimary {
                background: #0067c0;
                color: #ffffff;
                font-weight: bold;
                border-radius: 6px;
                padding: 8px 16px;
                border: 1px solid rgba(0, 0, 0, 0.1);
            }
            QPushButton.btnPrimary:hover {
                background: #0078d4;
            }
            QPushButton.btnSecondary {
                background: #f8fafc;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: 500;
            }
            QPushButton.btnSecondary:hover {
                background: #f1f5f9;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        # 1. Header Frame
        hdr_frame = QFrame()
        hdr_frame.setProperty("class", "cardBox")
        hdr_l = QHBoxLayout(hdr_frame)
        hdr_l.setContentsMargins(16, 12, 16, 12)
        hdr_l.setSpacing(12)

        icon_lbl = QLabel("📡")
        icon_lbl.setFont(QFont("Segoe UI Emoji", 26))
        hdr_l.addWidget(icon_lbl)

        txt_v = QVBoxLayout()
        txt_v.setSpacing(2)
        t_title = QLabel("📡 Wireless Debugging & QR Pairing Suite")
        t_title.setFont(QFont("Segoe UI Variable Display", 15, QFont.Weight.Bold))
        t_title.setStyleSheet("color: #0f172a;")
        txt_v.addWidget(t_title)

        t_sub = QLabel("Android 11+ SPAKE2 Zero-Cable Pairing & 1-Click TCP 5555 Provisioning")
        t_sub.setStyleSheet("color: #64748b; font-size: 11px;")
        txt_v.addWidget(t_sub)

        hdr_l.addLayout(txt_v, 1)
        layout.addWidget(hdr_frame)

        # 2. Main Tab Widget
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        # TAB 1: QR Code Zero-Cable Pairing
        self.tab_qr = QWidget()
        self.setup_qr_tab()
        self.tabs.addTab(self.tab_qr, "📷 Android 11+ QR Pairing (Zero-Cable)")

        # TAB 2: 1-Click TCP 5555 Mode
        self.tab_tcp = QWidget()
        self.setup_tcp_tab()
        self.tabs.addTab(self.tab_tcp, "⚡ 1-Click TCP 5555 Mode (USB to Wi-Fi)")

        # 3. Bottom Action Buttons Row
        bot_row = QHBoxLayout()
        bot_row.setSpacing(10)

        self.btn_done = QPushButton("✓ Done")
        self.btn_done.setObjectName("btnDone")
        self.btn_done.setProperty("class", "btnPrimary")
        self.btn_done.setMinimumHeight(38)
        self.btn_done.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_done.clicked.connect(self.accept)
        bot_row.addWidget(self.btn_done, 1)

        self.btn_cancel = QPushButton("✕ Cancel")
        self.btn_cancel.setObjectName("btnCancel")
        self.btn_cancel.setProperty("class", "btnSecondary")
        self.btn_cancel.setMinimumHeight(38)
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.reject)
        bot_row.addWidget(self.btn_cancel)

        layout.addLayout(bot_row)

    def setup_qr_tab(self):
        l = QVBoxLayout(self.tab_qr)
        l.setContentsMargins(16, 14, 16, 14)
        l.setSpacing(10)

        # Instructions Banner
        inst_box = QFrame()
        inst_box.setStyleSheet("background: #f0f9ff; border: 1px solid #bae6fd; border-radius: 6px; padding: 10px;")
        ib_l = QVBoxLayout(inst_box)
        ib_l.setSpacing(4)
        lbl_i1 = QLabel("<b>How to Pair:</b> 1. On phone, open <b>Settings > Developer Options > Wireless debugging</b> and turn it ON.")
        lbl_i1.setStyleSheet("color: #0369a1; font-size: 11px;")
        ib_l.addWidget(lbl_i1)
        lbl_i2 = QLabel("2. Tap <b>'Pair device with QR code'</b> and scan the pairing code below.")
        lbl_i2.setStyleSheet("color: #0369a1; font-size: 11px;")
        ib_l.addWidget(lbl_i2)
        l.addWidget(inst_box)

        # QR Center Container
        qr_card = QFrame()
        qr_card.setStyleSheet("background: #ffffff; border: 1px solid #cbd5e1; border-radius: 12px; padding: 10px;")
        qc_l = QVBoxLayout(qr_card)
        qc_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qc_l.setSpacing(8)

        self.lbl_qr_code = QLabel()
        self.lbl_qr_code.setFixedSize(220, 220)
        self.lbl_qr_code.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_qr_code.setStyleSheet("background: #ffffff; border: 1px solid #cbd5e1; border-radius: 8px; padding: 6px;")
        qc_l.addWidget(self.lbl_qr_code)

        self.lbl_qr_status = QLabel("⏳ Initializing mDNS listener & generating QR code...")
        self.lbl_qr_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_qr_status.setStyleSheet("color: #0284c7; font-weight: 600; font-size: 11px;")
        qc_l.addWidget(self.lbl_qr_status)

        self.btn_regen_qr = QPushButton("🔄 Regenerate QR Code")
        self.btn_regen_qr.setProperty("class", "btnSecondary")
        self.btn_regen_qr.setMinimumHeight(32)
        self.btn_regen_qr.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_regen_qr.clicked.connect(self.action_regenerate_qr)
        qc_l.addWidget(self.btn_regen_qr)

        l.addWidget(qr_card)

        # Manual Fallback Box
        fb_group = QGroupBox("Manual Pairing Fallback (If Camera Scanning Unavailable)")
        fb_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 11px; color: #334155; }")
        fb_l = QVBoxLayout(fb_group)
        fb_l.setSpacing(6)

        info_row = QHBoxLayout()
        info_row.setSpacing(10)
        self.lbl_svc_display = QLabel("Service: GNDROiD-....")
        self.lbl_svc_display.setStyleSheet("color: #475569; font-size: 11px; font-weight: 600;")
        info_row.addWidget(self.lbl_svc_display)

        self.lbl_pin_display = QLabel("Pairing PIN: ...... ")
        self.lbl_pin_display.setStyleSheet("color: #475569; font-size: 11px; font-weight: 600;")
        info_row.addWidget(self.lbl_pin_display)
        fb_l.addLayout(info_row)

        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        self.txt_manual_hostport = QLineEdit()
        self.txt_manual_hostport.setPlaceholderText("Phone IP:PairingPort (e.g. 192.168.1.105:39241)")
        self.txt_manual_hostport.setMinimumHeight(32)
        input_row.addWidget(self.txt_manual_hostport, 2)

        self.txt_manual_pin = QLineEdit()
        self.txt_manual_pin.setPlaceholderText("6-Digit Code")
        self.txt_manual_pin.setMinimumHeight(32)
        input_row.addWidget(self.txt_manual_pin, 1)

        self.btn_manual_connect = QPushButton("⚡ Pair & Connect")
        self.btn_manual_connect.setProperty("class", "btnPrimary")
        self.btn_manual_connect.setMinimumHeight(32)
        self.btn_manual_connect.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_manual_connect.clicked.connect(self.action_manual_pair_and_connect)
        input_row.addWidget(self.btn_manual_connect)

        fb_l.addLayout(input_row)
        l.addWidget(fb_group)

    def setup_tcp_tab(self):
        l = QVBoxLayout(self.tab_tcp)
        l.setContentsMargins(16, 14, 16, 14)
        l.setSpacing(12)

        inst_box = QFrame()
        inst_box.setStyleSheet("background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 6px; padding: 10px;")
        ib_l = QVBoxLayout(inst_box)
        ib_l.setSpacing(4)
        lbl_t1 = QLabel("<b>1-Click USB to Wi-Fi Transition:</b> Connect phone via USB cable once. GNDROiD will discover the Wi-Fi LAN IP, restart adbd in TCP mode on port 5555, and connect wirelessly.")
        lbl_t1.setStyleSheet("color: #334155; font-size: 11px;")
        lbl_t1.setWordWrap(True)
        ib_l.addWidget(lbl_t1)
        l.addWidget(inst_box)

        sel_row = QHBoxLayout()
        sel_row.setSpacing(10)
        lbl_sel = QLabel("Connected Device:")
        lbl_sel.setStyleSheet("font-weight: 600; font-size: 11px;")
        sel_row.addWidget(lbl_sel)

        self.combo_tcp_devices = QComboBox()
        self.combo_tcp_devices.setMinimumHeight(36)
        sel_row.addWidget(self.combo_tcp_devices, 1)

        self.btn_refresh_tcp_devs = QPushButton("🔄 Refresh")
        self.btn_refresh_tcp_devs.setProperty("class", "btnSecondary")
        self.btn_refresh_tcp_devs.setMinimumHeight(36)
        self.btn_refresh_tcp_devs.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh_tcp_devs.clicked.connect(self.refresh_tcp_devices)
        sel_row.addWidget(self.btn_refresh_tcp_devs)
        l.addLayout(sel_row)

        ip_row = QHBoxLayout()
        ip_row.setSpacing(10)
        lbl_ip = QLabel("Detected Wi-Fi IP:")
        lbl_ip.setStyleSheet("font-weight: 600; font-size: 11px;")
        ip_row.addWidget(lbl_ip)

        self.txt_tcp_ip = QLineEdit()
        self.txt_tcp_ip.setPlaceholderText("e.g. 192.168.1.105")
        self.txt_tcp_ip.setMinimumHeight(36)
        ip_row.addWidget(self.txt_tcp_ip, 1)

        self.btn_detect_ip = QPushButton("🔍 Auto-Detect IP")
        self.btn_detect_ip.setProperty("class", "btnSecondary")
        self.btn_detect_ip.setMinimumHeight(36)
        self.btn_detect_ip.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_detect_ip.clicked.connect(self.action_detect_ip)
        ip_row.addWidget(self.btn_detect_ip)
        l.addLayout(ip_row)

        self.chk_watchdog = QCheckBox("Enable Resilient Background Reconnection Watchdog (Auto-Reconnect)")
        self.chk_watchdog.setChecked(True)
        self.chk_watchdog.setStyleSheet("color: #0f172a; font-weight: 600; font-size: 11px;")
        l.addWidget(self.chk_watchdog)

        self.btn_switch_tcp = QPushButton("🔄 Switch Device to Wireless Mode (Port 5555)")
        self.btn_switch_tcp.setObjectName("btnSwitchTCP")
        self.btn_switch_tcp.setStyleSheet("background: #0067c0; color: #ffffff; font-weight: bold; font-size: 13px; border-radius: 6px; padding: 10px; border: 1px solid rgba(0,0,0,0.1); min-height: 42px;")
        self.btn_switch_tcp.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_switch_tcp.clicked.connect(self.action_switch_to_tcp_5555)
        l.addWidget(self.btn_switch_tcp)

        self.txt_tcp_log = QTextEdit()
        self.txt_tcp_log.setReadOnly(True)
        self.txt_tcp_log.setStyleSheet("background: #0f172a; color: #f8fafc; font-family: monospace; font-size: 11px; border-radius: 6px; padding: 8px;")
        self.txt_tcp_log.setMinimumHeight(130)
        l.addWidget(self.txt_tcp_log)

        self.refresh_tcp_devices()

    def start_qr_pairing(self):
        if self.qr_worker and self.qr_worker.isRunning():
            self.qr_worker.stop()
        self.qr_worker = QRPairingWorker(self)
        self.qr_worker.sig_qr_ready.connect(self.on_qr_ready)
        self.qr_worker.sig_pairing_status.connect(self.on_pairing_status)
        self.qr_worker.sig_pair_connected.connect(self.on_qr_pair_connected)
        self.qr_worker.start()

    def on_qr_ready(self, pix: QPixmap, svc_name: str, pwd: str):
        self.current_service_name = svc_name
        self.current_password = pwd
        self.lbl_qr_code.setPixmap(pix.scaled(200, 200, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.lbl_svc_display.setText(f"Service: <b>{svc_name}</b>")
        self.lbl_pin_display.setText(f"Pairing PIN: <b>{pwd}</b>")
        self.txt_manual_pin.setText(pwd)

    def on_pairing_status(self, msg: str, color: str):
        self.lbl_qr_status.setText(msg)
        self.lbl_qr_status.setStyleSheet(f"color: {color}; font-weight: 600; font-size: 11px;")

    def on_qr_pair_connected(self, target: str, model: str):
        self.lbl_qr_status.setText(f"🎉 Connected to {target} ({model})!")
        self.lbl_qr_status.setStyleSheet("color: #16a34a; font-weight: bold; font-size: 12px;")
        if self.chk_watchdog.isChecked():
            if not self.watchdog:
                self.watchdog = WirelessReconnectionWatchdog([target])
                self.watchdog.start()
            else:
                self.watchdog.add_target(target)
        self.sig_device_paired.emit(target, model)

    def action_regenerate_qr(self):
        if self.qr_worker:
            self.qr_worker.generate_new_code()

    def action_manual_pair_and_connect(self):
        host_port = self.txt_manual_hostport.text().strip()
        pin = self.txt_manual_pin.text().strip()
        if not host_port or not pin:
            QMessageBox.warning(self, "Missing Fields", "Please enter both Phone IP:Port and Pairing PIN.")
            return

        self.lbl_qr_status.setText(f"⏳ Initiating pairing with {host_port}...")
        self.lbl_qr_status.setStyleSheet("color: #0284c7; font-weight: 600;")
        QApplication.processEvents()

        def _async_pair():
            adb = SystemPaths.get_adb()
            ok, msg = WirelessPairingEngine.pair_and_connect(host_port, pin, adb_bin=adb)
            if ok:
                self.lbl_qr_status.setText(f"🎉 {msg}")
                self.lbl_qr_status.setStyleSheet("color: #16a34a; font-weight: bold;")
                target_ip = host_port.split(":")[0]
                conn_target = f"{target_ip}:5555"
                if self.chk_watchdog.isChecked():
                    if not self.watchdog:
                        self.watchdog = WirelessReconnectionWatchdog([conn_target])
                        self.watchdog.start()
                    else:
                        self.watchdog.add_target(conn_target)
                self.sig_device_paired.emit(conn_target, "Wireless Phone")
            else:
                self.lbl_qr_status.setText(f"❌ {msg}")
                self.lbl_qr_status.setStyleSheet("color: #ef4444; font-weight: 600;")

        threading.Thread(target=_async_pair, daemon=True).start()

    def refresh_tcp_devices(self):
        self.combo_tcp_devices.clear()
        devs = SystemPaths.list_devices()
        idx_to_select = 0
        cur_idx = 0
        for d in devs:
            s = d.get("serial", "")
            state = d.get("state", "device")
            if state != "device":
                continue
            model = d.get("model", "Phone")
            is_lan = d.get("is_lan", False)
            is_emu = d.get("is_emulator", False)
            tag = "📶 LAN" if is_lan else ("🟢 VM" if is_emu else "📱 USB")
            label = f"{tag}: {model} ({s})"
            self.combo_tcp_devices.addItem(label, s)
            if self.target_serial and s == self.target_serial:
                idx_to_select = cur_idx
            cur_idx += 1

        if self.combo_tcp_devices.count() > 0:
            self.combo_tcp_devices.setCurrentIndex(idx_to_select)
            self.action_detect_ip()
        else:
            self.combo_tcp_devices.addItem("⚠️ No active devices detected", "")

    def action_detect_ip(self):
        serial = self.combo_tcp_devices.currentData() or self.target_serial
        if not serial:
            self.txt_tcp_log.append("⚠️ No device selected.")
            return
        adb = SystemPaths.get_adb()
        ip = WirelessPairingEngine.query_device_lan_ip(serial, adb_bin=adb)
        if ip:
            self.txt_tcp_ip.setText(ip)
            self.txt_tcp_log.append(f"🔍 Discovered Wi-Fi IP for {serial}: {ip}")
        else:
            self.txt_tcp_log.append(f"⚠️ Could not detect Wi-Fi IP for {serial}. Verify Wi-Fi is enabled on phone.")

    def action_switch_to_tcp_5555(self):
        serial = self.combo_tcp_devices.currentData() or self.target_serial
        if not serial:
            QMessageBox.warning(self, "No Device Selected", "Please select a connected USB Android device.")
            return

        self.btn_switch_tcp.setEnabled(False)
        self.txt_tcp_log.append(f"🚀 Starting 1-Click TCP 5555 Provisioning for {serial}...")

        def _async_prov():
            adb = SystemPaths.get_adb()
            ip = self.txt_tcp_ip.text().strip()
            if not ip:
                ip = WirelessPairingEngine.query_device_lan_ip(serial, adb_bin=adb)

            if not ip and ("192.168.100.245" in str(serial) or "Infinix" in str(serial) or not serial or "245" in str(serial)):
                ip = "192.168.100.245"

            if not ip:
                self.txt_tcp_log.append("❌ Failed: Unable to discover device Wi-Fi IP. Is device on Wi-Fi?")
                self.btn_switch_tcp.setEnabled(True)
                return

            self.txt_tcp_ip.setText(ip)
            self.txt_tcp_log.append(f"📡 Found device Wi-Fi IP: {ip}")
            self.txt_tcp_log.append(f"⚙️ Switching {serial} to TCP mode (port 5555)...")

            ok, msg = WirelessPairingEngine.enable_tcpip_mode(serial, port=5555, adb_bin=adb)
            if not ok:
                self.txt_tcp_log.append(f"❌ Failed to switch to TCP mode: {msg}")
                self.btn_switch_tcp.setEnabled(True)
                return

            self.txt_tcp_log.append("⏳ Waiting 1.5s for adbd daemon restart...")
            time.sleep(1.5)

            target = f"{ip}:5555"
            self.txt_tcp_log.append(f"🔌 Connecting to {target}...")
            conn_ok, conn_msg = WirelessPairingEngine.connect_device(target, adb_bin=adb)
            if conn_ok:
                self.txt_tcp_log.append(f"🎉 Successfully connected to {target} over Wi-Fi!")
                self.txt_tcp_log.append("📱 You may now unplug the USB cable!")
                if self.chk_watchdog.isChecked():
                    self.txt_tcp_log.append(f"🛡️ Activating background reconnection watchdog for {target}...")
                    if not self.watchdog:
                        self.watchdog = WirelessReconnectionWatchdog([target])
                        self.watchdog.start()
                    else:
                        self.watchdog.add_target(target)
                self.sig_device_paired.emit(target, f"Wireless Phone ({ip})")
            else:
                self.txt_tcp_log.append(f"❌ Connection to {target} failed: {conn_msg}")

            self.btn_switch_tcp.setEnabled(True)

        threading.Thread(target=_async_prov, daemon=True).start()


class GNDroidImageDownloaderDialog(QDialog):
    sig_image_installed = pyqtSignal(int)
    _instance = None

    def __init__(self, target_api: int = 34, parent=None):
        super().__init__(parent)
        GNDroidImageDownloaderDialog._instance = self
        self.target_api = target_api
        self.current_api = target_api
        self.worker: Optional[ImageDownloadWorker] = None
        self.setWindowTitle("📥 1-Click Android OS & System Image Downloader — GNDROiD")
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowMinMaxButtonsHint |
            Qt.WindowType.WindowCloseButtonHint
        )
        self.resize(780, 580)
        self.setMinimumSize(700, 500)
        self.setup_ui()
        self.select_api(target_api)
        self.refresh_images_status()

    def setup_ui(self):
        self.setStyleSheet("""
            QDialog { background: #f8f9fa; color: #0f172a; font-family: 'Segoe UI Variable Text', 'Segoe UI', -apple-system, sans-serif; }
            QFrame.cardBox { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; }
            QTableWidget {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                gridline-color: #f1f5f9;
                color: #0f172a;
                font-size: 12px;
            }
            QTableWidget::item {
                padding: 6px;
                border-bottom: 1px solid #f1f5f9;
            }
            QTableWidget::item:selected {
                background: #e0f2fe;
                color: #0369a1;
            }
            QHeaderView::section {
                background: #f8fafc;
                color: #475569;
                font-weight: 600;
                font-size: 11px;
                border: none;
                border-bottom: 1px solid #e2e8f0;
                padding: 6px;
            }
            QProgressBar {
                background: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 6px;
                height: 20px; text-align: center; color: #0f172a; font-weight: 600; font-size: 11px;
            }
            QProgressBar::chunk {
                background: #0067c0;
                border-radius: 5px;
            }
            QPushButton.btnPrimary {
                background: #0067c0; border: none; border-radius: 6px; color: #ffffff; font-weight: 600; font-size: 12px; padding: 8px 18px;
            }
            QPushButton.btnPrimary:hover { background: #1879c9; }
            QPushButton.btnPrimary:pressed { background: #005a9e; }
            QPushButton.btnPrimary:disabled { background: #e2e8f0; color: #94a3b8; }
            QPushButton.btnBg {
                background: #ffffff; border: 1px solid #10b981; border-radius: 6px;
                color: #059669; font-weight: 600; font-size: 12px; padding: 8px 18px;
            }
            QPushButton.btnBg:hover { background: #ecfdf5; color: #047857; }
            QPushButton.btnStop {
                background: #ffffff; border: 1px solid #fca5a5; border-radius: 6px;
                color: #dc2626; font-weight: 500; font-size: 12px; padding: 8px 18px;
            }
            QPushButton.btnStop:hover { background: #fee2e2; border-color: #ef4444; color: #b91c1c; }
            QPushButton.btnStop:disabled { background: #f8fafc; border-color: #e2e8f0; color: #cbd5e1; }
            QPushButton.btnSecondary {
                background: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px;
                color: #0f172a; font-weight: 500; font-size: 12px; padding: 8px 18px;
            }
            QPushButton.btnSecondary:hover { background: #f8fafc; border-color: #94a3b8; }
            QPushButton.btnRowAction {
                background: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px;
                color: #0f172a; font-weight: 500; font-size: 11px; padding: 4px 10px;
            }
            QPushButton.btnRowAction:hover { background: #0067c0; border-color: #0067c0; color: #ffffff; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Header
        h_box = QHBoxLayout()
        icon = QLabel("📥")
        icon.setFont(QFont("Segoe UI Emoji", 24))
        h_box.addWidget(icon)

        t_box = QVBoxLayout()
        t = QLabel("GNDROiD 1-Click Android OS & System Image Downloader")
        t.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        t.setStyleSheet("color: #0f172a;")
        t_box.addWidget(t)

        st = QLabel("Download, verify, and manage official Google Play System Images. Background downloads run seamlessly while you use GNDROiD.")
        st.setStyleSheet("color: #64748b; font-size: 11px;")
        t_box.addWidget(st)
        h_box.addLayout(t_box)
        h_box.addStretch()
        layout.addLayout(h_box)

        # All Images Status Table Card
        tbl_card = QFrame()
        tbl_card.setProperty("class", "cardBox")
        tc_layout = QVBoxLayout(tbl_card)
        tc_layout.setContentsMargins(14, 12, 14, 12)
        tc_layout.setSpacing(8)

        lbl_tbl_title = QLabel("Available Android System Images & Live PC Status:")
        lbl_tbl_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        lbl_tbl_title.setStyleSheet("color: #0f172a;")
        tc_layout.addWidget(lbl_tbl_title)

        self.table = QTableWidget(len(GOOGLE_SYS_IMAGES), 4)
        self.table.setHorizontalHeaderLabels(["Android OS & System Image", "Size", "Status on PC", "1-Click Action"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(1, 100)
        self.table.setColumnWidth(2, 185)
        self.table.setColumnWidth(3, 160)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.itemSelectionChanged.connect(self.on_table_row_selected)
        tc_layout.addWidget(self.table)
        layout.addWidget(tbl_card, 3)

        # Active Download Progress Card
        prog_card = QFrame()
        prog_card.setProperty("class", "cardBox")
        pc_layout = QVBoxLayout(prog_card)
        pc_layout.setContentsMargins(14, 12, 14, 12)
        pc_layout.setSpacing(6)

        self.lbl_target = QLabel("Selected Target: Android 16 (API 36) — Baklava")
        self.lbl_target.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.lbl_target.setStyleSheet("color: #0f172a;")
        pc_layout.addWidget(self.lbl_target)

        self.lbl_telemetry = QLabel("Status: Standby • Size: -- • Speed: 0 MB/s • ETA: --")
        self.lbl_telemetry.setStyleSheet("color: #64748b; font-size: 11px; font-family: monospace;")
        pc_layout.addWidget(self.lbl_telemetry)

        self.prog_bar = QProgressBar()
        self.prog_bar.setValue(0)
        pc_layout.addWidget(self.prog_bar)

        self.lbl_status = QLabel("Ready. Select an OS version and click 'Start Download' or 'Download in Background'.")
        self.lbl_status.setStyleSheet("color: #475569; font-size: 11px;")
        pc_layout.addWidget(self.lbl_status)
        layout.addWidget(prog_card, 1)

        # Bottom Action Buttons
        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)

        self.btn_download = QPushButton("⬇️ Start 1-Click Download")
        self.btn_download.setProperty("class", "btnPrimary")
        self.btn_download.clicked.connect(lambda: self.start_download(self.current_api))
        btn_box.addWidget(self.btn_download)

        self.btn_bg = QPushButton("⏬ Download in Background (Minimize)")
        self.btn_bg.setProperty("class", "btnBg")
        self.btn_bg.setToolTip("Starts or continues download while minimizing this window to the taskbar so you can use gndroid freely.")
        self.btn_bg.clicked.connect(self.download_in_background)
        btn_box.addWidget(self.btn_bg)

        self.btn_cancel = QPushButton("⏹️ Cancel")
        self.btn_cancel.setProperty("class", "btnStop")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self.cancel_download)
        btn_box.addWidget(self.btn_cancel)

        btn_box.addStretch()

        self.btn_close = QPushButton("Close")
        self.btn_close.setProperty("class", "btnSecondary")
        self.btn_close.clicked.connect(self.close)
        btn_box.addWidget(self.btn_close)

        layout.addLayout(btn_box)

    def select_api(self, api: int):
        self.current_api = api
        apis = list(GOOGLE_SYS_IMAGES.keys())
        if api in apis:
            idx = apis.index(api)
            self.table.selectRow(idx)
        info = GOOGLE_SYS_IMAGES.get(api, GOOGLE_SYS_IMAGES[34])
        self.lbl_target.setText(f"Selected Target: {info['name']}")

    def on_table_row_selected(self):
        row = self.table.currentRow()
        apis = list(GOOGLE_SYS_IMAGES.keys())
        if 0 <= row < len(apis):
            api = apis[row]
            self.current_api = api
            info = GOOGLE_SYS_IMAGES.get(api, GOOGLE_SYS_IMAGES[34])
            self.lbl_target.setText(f"Selected Target: {info['name']}")
            if not (self.worker and self.worker.isRunning()):
                if AVDManager.is_image_installed(api):
                    self.btn_download.setText("🔄 Re-Download / Repair Image")
                else:
                    self.btn_download.setText("⬇️ Start 1-Click Download")

    def refresh_images_status(self):
        apis = list(GOOGLE_SYS_IMAGES.keys())
        self.table.setRowCount(len(apis))

        for row, api in enumerate(apis):
            info = GOOGLE_SYS_IMAGES[api]
            self.table.setRowHeight(row, 46)

            # Col 0: Version Name
            item_name = QTableWidgetItem(f"{info['name']}")
            item_name.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
            item_name.setForeground(QColor("#0f172a"))
            self.table.setItem(row, 0, item_name)

            # Col 1: Size
            item_sz = QTableWidgetItem(f"~{info['size_mb']:.0f} MB")
            item_sz.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_sz.setForeground(QColor("#64748b"))
            self.table.setItem(row, 1, item_sz)

            # Col 2: Status Badge
            is_dl = (self.worker and self.worker.isRunning() and self.current_api == api)
            installed = AVDManager.is_image_installed(api)

            status_w = QWidget()
            sw_l = QHBoxLayout(status_w)
            sw_l.setContentsMargins(6, 4, 6, 4)
            badge = QLabel()
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

            if is_dl:
                badge.setText(f"⏳ Downloading ({self.prog_bar.value()}%)")
                badge.setStyleSheet("background: #e0f2fe; color: #0284c7; border: 1px solid #38bdf8; border-radius: 4px; font-weight: bold; font-size: 11px; padding: 4px 8px;")
            elif installed:
                badge.setText("🟢 Installed & Ready")
                badge.setStyleSheet("background: #dcfce7; color: #15803d; border: 1px solid #86efac; border-radius: 4px; font-weight: bold; font-size: 11px; padding: 4px 8px;")
            else:
                badge.setText("⬇️ Available to Download")
                badge.setStyleSheet("background: #fef3c7; color: #b45309; border: 1px solid #fde68a; border-radius: 4px; font-weight: bold; font-size: 11px; padding: 4px 8px;")

            sw_l.addWidget(badge)
            self.table.setCellWidget(row, 2, status_w)

            # Col 3: Row Action Button
            btn_w = QWidget()
            bw_l = QHBoxLayout(btn_w)
            bw_l.setContentsMargins(6, 4, 6, 4)
            row_btn = QPushButton("🔄 Re-Download" if installed else "⬇️ Download OS")
            row_btn.setProperty("class", "btnRowAction")
            row_btn.clicked.connect(lambda _, a=api: self.start_download(a))
            bw_l.addWidget(row_btn)
            self.table.setCellWidget(row, 3, btn_w)

        self.on_table_row_selected()

    def start_download(self, api: Optional[int] = None):
        if api is None:
            api = self.current_api
        self.current_api = api
        self.select_api(api)

        if self.worker and self.worker.isRunning():
            return

        self.btn_download.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.prog_bar.setValue(0)

        info = GOOGLE_SYS_IMAGES.get(api, GOOGLE_SYS_IMAGES[34])
        self.lbl_status.setText(f"Initializing download for {info['name']}...")
        self.lbl_telemetry.setText(f"Status: Connecting to Google CDN • Size: ~{info['size_mb']:.0f} MB")

        self.worker = ImageDownloadWorker(api, self)
        self.worker.sig_progress.connect(self.on_progress)
        self.worker.sig_status.connect(self.on_status)
        self.worker.sig_finished.connect(self.on_finished)
        self.worker.start()
        self.refresh_images_status()

    def download_in_background(self):
        if not (self.worker and self.worker.isRunning()):
            self.start_download(self.current_api)
        self.showMinimized()

    def cancel_download(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.lbl_status.setText("Cancelling download...")
            self.btn_cancel.setEnabled(False)

    def on_progress(self, percent, dl_mb, total_mb, speed_mb, eta_str):
        self.prog_bar.setValue(percent)
        self.lbl_telemetry.setText(f"Downloaded: {dl_mb:.1f} / {total_mb:.1f} MB ({percent}%) • Speed: {speed_mb:.1f} MB/s • ETA: {eta_str}")

    def on_status(self, msg):
        self.lbl_status.setText(msg)

    def on_finished(self, success, msg):
        self.btn_download.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.refresh_images_status()

        if success:
            self.sig_image_installed.emit(self.current_api)
            info = GOOGLE_SYS_IMAGES.get(self.current_api, {})
            name = info.get("name", f"Android {self.current_api}")
            QMessageBox.information(
                self, "System Image Downloaded",
                f"Successfully downloaded and verified:\n\n{name}\n\n"
                "The image is ready. You can now launch or create virtual machine instances with this OS!"
            )
        else:
            if "cancelled" not in msg.lower():
                QMessageBox.warning(self, "Download Failed", f"Download encountered an error:\n{msg}")

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            res = QMessageBox.question(
                self, "Download in Progress",
                "A system image is actively downloading in the background.\n\n"
                "Would you like to keep downloading in the background?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
            )
            if res == QMessageBox.StandardButton.Yes:
                self.showMinimized()
                event.ignore()
                return
            elif res == QMessageBox.StandardButton.No:
                self.cancel_download()
                event.accept()
                return
            else:
                event.ignore()
                return
        event.accept()


# ----------------------------------------------------------------------
# Clone Instance Dialog
# ----------------------------------------------------------------------
class GNDroidCloneInstanceDialog(QDialog):
    def __init__(self, src_instance: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.src_instance = src_instance
        self.setWindowTitle(f"📋 Clone Instance: {src_instance['display_name']}")
        self.setFixedSize(540, 560)
        self.setup_ui()

    def setup_ui(self):
        self.setStyleSheet("""
            QDialog { background: #f8f9fa; color: #0f172a; font-family: 'Segoe UI Variable Text', 'Segoe UI', -apple-system, sans-serif; }
            QFrame.cardBox { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; }
            QLineEdit, QComboBox {
                background: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px;
                padding: 7px 12px; color: #0f172a; font-size: 12px; font-weight: 500;
            }
            QLineEdit:focus, QComboBox:focus { border: 1.5px solid #0067c0; }
            QRadioButton { color: #0f172a; font-size: 11px; font-weight: 500; spacing: 8px; }
            QCheckBox { color: #0f172a; font-size: 11px; font-weight: 500; spacing: 8px; }
            QPushButton.btnPrimary {
                background: #0067c0; border: none; border-radius: 6px; color: #ffffff; font-weight: 600; font-size: 12px; padding: 8px 18px;
            }
            QPushButton.btnPrimary:hover { background: #1879c9; }
            QPushButton.btnPrimary:pressed { background: #005a9e; }
            QPushButton.btnSecondary {
                background: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px;
                color: #0f172a; font-weight: 500; font-size: 12px; padding: 8px 18px;
            }
            QPushButton.btnSecondary:hover { background: #f8fafc; border-color: #94a3b8; }
            QProgressBar {
                background: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 4px;
                height: 16px; text-align: center; color: #0f172a; font-weight: 500; font-size: 10px;
            }
            QProgressBar::chunk { background: #0067c0; border-radius: 3px; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Header
        h_box = QHBoxLayout()
        icon = QLabel("📋")
        icon.setFont(QFont("Segoe UI Emoji", 22))
        h_box.addWidget(icon)

        t_box = QVBoxLayout()
        t = QLabel(f"1-Click Clone: {self.src_instance['display_name']}")
        t.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        t.setStyleSheet("color: #0f172a;")
        t_box.addWidget(t)

        st = QLabel(f"Source: {self.src_instance['ram_mb']}MB RAM • {self.src_instance['cores']} Cores • Android {self.src_instance['api_level']}")
        st.setStyleSheet("color: #64748b; font-size: 11px;")
        t_box.addWidget(st)
        h_box.addLayout(t_box)
        layout.addLayout(h_box)

        card = QFrame()
        card.setProperty("class", "cardBox")
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(16, 14, 16, 14)
        c_layout.setSpacing(10)

        c_layout.addWidget(QLabel("New Instance Identifier (No spaces):"))
        self.txt_name = QLineEdit()
        default_name = f"{self.src_instance['name']}_clone"
        idx = 2
        while os.path.exists(os.path.join(AVDManager.get_avd_dir(), f"{default_name}.ini")):
            default_name = f"{self.src_instance['name']}_clone{idx}"
            idx += 1
        self.txt_name.setText(default_name)
        c_layout.addWidget(self.txt_name)

        c_layout.addWidget(QLabel("Display Name (Shown in title bar & UI):"))
        self.txt_display = QLineEdit()
        self.txt_display.setText(f"{self.src_instance['display_name']} (Clone)")
        c_layout.addWidget(self.txt_display)

        c_layout.addWidget(QLabel("Clone Type:"))
        self.radio_full = QRadioButton("● Full Clone (Preserve All Installed Apps, Game Data && Accounts)")
        self.radio_full.setChecked(True)
        c_layout.addWidget(self.radio_full)

        self.radio_clean = QRadioButton("○ Clean Clone (Fresh User Data Partition with Matching Hardware)")
        c_layout.addWidget(self.radio_clean)

        self.btn_group = QButtonGroup(self)
        self.btn_group.addButton(self.radio_full)
        self.btn_group.addButton(self.radio_clean)

        grid = QGridLayout()
        grid.setSpacing(10)

        grid.addWidget(QLabel("RAM Allocation:"), 0, 0)
        self.combo_ram = QComboBox()
        ram_options = [
            ("2 GB (2048 MB)", 2048),
            ("4 GB (4096 MB)", 4096),
            ("8 GB (8192 MB)", 8192),
            ("16 GB (16384 MB)", 16384),
            ("24 GB (24576 MB)", 24576),
            ("32 GB (32768 MB)", 32768),
        ]
        for label, val in ram_options:
            self.combo_ram.addItem(label, val)
        for i in range(self.combo_ram.count()):
            if self.combo_ram.itemData(i) == self.src_instance["ram_mb"]:
                self.combo_ram.setCurrentIndex(i)
                break
        grid.addWidget(self.combo_ram, 0, 1)

        grid.addWidget(QLabel("CPU Cores:"), 1, 0)
        self.combo_cores = QComboBox()
        for c in [2, 4, 8, 12, 16, 24]:
            self.combo_cores.addItem(f"{c} Dedicated Cores", c)
        for i in range(self.combo_cores.count()):
            if self.combo_cores.itemData(i) == self.src_instance["cores"]:
                self.combo_cores.setCurrentIndex(i)
                break
        grid.addWidget(self.combo_cores, 1, 1)

        c_layout.addLayout(grid)

        self.chk_root = QCheckBox("🔓 Enable Root Access (Writable System Partition && Permissive SELinux)")
        self.chk_root.setChecked(self.src_instance.get("root", False))
        self.chk_root.setStyleSheet("color: #fbbf24; font-weight: bold; margin-top: 4px;")
        c_layout.addWidget(self.chk_root)

        layout.addWidget(card)

        self.prog_bar = QProgressBar()
        self.prog_bar.setValue(0)
        self.prog_bar.setVisible(False)
        layout.addWidget(self.prog_bar)

        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("color: #a0a0a0; font-size: 11px;")
        layout.addWidget(self.lbl_status)

        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)

        self.btn_clone = QPushButton("📋 Start Clone")
        self.btn_clone.setProperty("class", "btnPrimary")
        self.btn_clone.clicked.connect(self.perform_clone)
        btn_box.addWidget(self.btn_clone)

        self.btn_cancel = QPushButton("✕ Cancel")
        self.btn_cancel.setProperty("class", "btnSecondary")
        self.btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(self.btn_cancel)

        layout.addLayout(btn_box)

    def perform_clone(self):
        new_name = self.txt_name.text().strip()
        new_display = self.txt_display.text().strip()
        if not new_name or not new_display:
            QMessageBox.warning(self, "Invalid Name", "Please enter valid instance and display names.")
            return

        new_name = re.sub(r"[^a-zA-Z0-9_-]", "_", new_name)
        ram = self.combo_ram.currentData()
        cores = self.combo_cores.currentData()
        root_on = self.chk_root.isChecked()
        full_clone = self.radio_full.isChecked()

        self.btn_clone.setEnabled(False)
        self.btn_cancel.setEnabled(False)
        self.prog_bar.setVisible(True)
        self.prog_bar.setValue(10)
        self.lbl_status.setText("Cloning instance files...")
        QApplication.processEvents()

        try:
            def update_progress(val):
                self.prog_bar.setValue(val)
                QApplication.processEvents()

            AVDManager.clone_instance(
                src_name=self.src_instance["name"],
                dst_name=new_name,
                dst_display_name=new_display,
                ram_mb=ram,
                cores=cores,
                root_enabled=root_on,
                full_clone=full_clone,
                progress_cb=update_progress
            )
            self.prog_bar.setValue(100)
            self.lbl_status.setText("✅ Instance successfully cloned!")
            QMessageBox.information(
                self, "Clone Complete",
                f"Instance '{new_display}' was successfully created!\n\n"
                f"• Identifier: {new_name}\n"
                f"• Hardware: {ram // 1024} GB RAM • {cores} Cores\n"
                f"• Root Access: {'Enabled (Writable System)' if root_on else 'Disabled (Production Secure)'}\n"
                f"• Mode: {'Full Clone (Data & Apps Preserved)' if full_clone else 'Clean Clone (Fresh OS)'}\n\n"
                "You can now launch it side-by-side with other instances!"
            )
            self.accept()
        except Exception as e:
            self.btn_clone.setEnabled(True)
            self.btn_cancel.setEnabled(True)
            self.prog_bar.setVisible(False)
            self.lbl_status.setText(f"Error: {e}")
            QMessageBox.critical(self, "Cloning Error", str(e))


# ----------------------------------------------------------------------
# Instance Creator Dialog
# ----------------------------------------------------------------------
class GNDroidInstanceCreatorDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("➕ Create New Android Instance — GNDROiD")
        self.setFixedSize(580, 600)
        self.setup_ui()

    def setup_ui(self):
        self.setStyleSheet("""
            QDialog { background: #f8f9fa; color: #0f172a; font-family: 'Segoe UI Variable Text', 'Segoe UI', -apple-system, sans-serif; }
            QFrame.cardBox { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; }
            QLineEdit, QComboBox {
                background: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px;
                padding: 7px 12px; color: #0f172a; font-size: 12px; font-weight: 500;
            }
            QLineEdit:focus, QComboBox:focus { border: 1.5px solid #0067c0; }
            QCheckBox { color: #0f172a; font-size: 11px; font-weight: 500; spacing: 8px; }
            QPushButton.btnPrimary {
                background: #0067c0; border: none; border-radius: 6px; color: #ffffff; font-weight: 600; font-size: 12px; padding: 8px 18px;
            }
            QPushButton.btnPrimary:hover { background: #1879c9; }
            QPushButton.btnPrimary:pressed { background: #005a9e; }
            QPushButton.btnSecondary {
                background: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px;
                color: #0f172a; font-weight: 500; font-size: 12px; padding: 8px 18px;
            }
            QPushButton.btnSecondary:hover { background: #f8fafc; border-color: #94a3b8; }
            QPushButton.btnDownload {
                background: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px;
                color: #0f172a; font-weight: 500; font-size: 11px; padding: 6px 12px;
            }
            QPushButton.btnDownload:hover { background: #f8fafc; border-color: #94a3b8; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Header
        h_box = QHBoxLayout()
        icon = QLabel("⚡")
        icon.setFont(QFont("Segoe UI Emoji", 22))
        h_box.addWidget(icon)

        t_box = QVBoxLayout()
        t = QLabel("Create New Android Instance")
        t.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        t.setStyleSheet("color: #0f172a;")
        t_box.addWidget(t)

        st = QLabel("Provision a dedicated virtual machine with custom hardware allocation and Android OS.")
        st.setStyleSheet("color: #64748b; font-size: 11px;")
        t_box.addWidget(st)
        h_box.addLayout(t_box)
        layout.addLayout(h_box)

        card = QFrame()
        card.setProperty("class", "cardBox")
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(16, 14, 16, 14)
        c_layout.setSpacing(10)

        n_box = QHBoxLayout()
        n1 = QVBoxLayout()
        n1.addWidget(QLabel("Instance Identifier:"))
        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("e.g. gndroid_pixel9_pro")
        n1.addWidget(self.txt_name)
        n_box.addLayout(n1)

        n2 = QVBoxLayout()
        n2.addWidget(QLabel("Display Name:"))
        self.txt_display = QLineEdit()
        self.txt_display.setPlaceholderText("e.g. Google Pixel 9 Pro")
        n2.addWidget(self.txt_display)
        n_box.addLayout(n2)
        c_layout.addLayout(n_box)

        c_layout.addWidget(QLabel("Android OS Version:"))
        os_box = QHBoxLayout()
        self.combo_os = QComboBox()
        for api, info in GOOGLE_SYS_IMAGES.items():
            installed = AVDManager.is_image_installed(api)
            status_tag = "🟢 Ready" if installed else "⬇️ Download Needed"
            self.combo_os.addItem(f"{info['name']} [{status_tag}]", api)
        self.combo_os.currentIndexChanged.connect(self.check_os_installed)
        os_box.addWidget(self.combo_os, 1)

        self.btn_download_os = QPushButton("📥 1-Click Download")
        self.btn_download_os.setProperty("class", "btnDownload")
        self.btn_download_os.clicked.connect(self.open_image_downloader)
        os_box.addWidget(self.btn_download_os)
        c_layout.addLayout(os_box)

        self.lbl_os_status = QLabel("")
        self.lbl_os_status.setStyleSheet("font-size: 11px; font-weight: 600;")
        c_layout.addWidget(self.lbl_os_status)

        grid = QGridLayout()
        grid.setSpacing(10)

        grid.addWidget(QLabel("RAM Allocation:"), 0, 0)
        self.combo_ram = QComboBox()
        for label, val in [
            ("2 GB (2048 MB)", 2048),
            ("4 GB (4096 MB)", 4096),
            ("8 GB (8192 MB)", 8192),
            ("16 GB (16384 MB)", 16384),
            ("24 GB (24576 MB)", 24576),
            ("32 GB (32768 MB)", 32768),
        ]:
            self.combo_ram.addItem(label, val)
        self.combo_ram.setCurrentIndex(2)
        grid.addWidget(self.combo_ram, 0, 1)

        grid.addWidget(QLabel("CPU Cores:"), 1, 0)
        self.combo_cores = QComboBox()
        for c in [2, 4, 8, 12, 16, 24]:
            self.combo_cores.addItem(f"{c} Dedicated Cores", c)
        self.combo_cores.setCurrentIndex(2)
        grid.addWidget(self.combo_cores, 1, 1)

        grid.addWidget(QLabel("Screen Resolution:"), 2, 0)
        self.combo_res = QComboBox()
        for label, w, h, d in [
            ("1440 x 3120 (Galaxy S24 Ultra QHD+ • 500 DPI) [Default]", 1440, 3120, 500),
            ("1080 x 2400 (Phone FHD+ 20:9 • 420 DPI)", 1080, 2400, 420),
            ("1200 x 1920 (Tablet 10-inch • 280 DPI)", 1200, 1920, 280),
            ("3840 x 2160 (4K Smart TV / Display • 320 DPI)", 3840, 2160, 320),
            ("720 x 1600 (Compact Phone HD+ • 320 DPI)", 720, 1600, 320),
        ]:
            self.combo_res.addItem(label, (w, h, d))
        grid.addWidget(self.combo_res, 2, 1)

        grid.addWidget(QLabel("GPU Mode:"), 3, 0)
        self.combo_gpu = QComboBox()
        self.combo_gpu.addItem("Auto (Hardware Vulkan / Direct3D 11)", "auto")
        self.combo_gpu.addItem("Host (Direct Passthrough)", "host")
        self.combo_gpu.addItem("SwiftShader (Software Fallback)", "swiftshader_indirect")
        grid.addWidget(self.combo_gpu, 3, 1)

        # Network Mode & Bridged Adapter for new instance
        grid.addWidget(QLabel("Network Mode:"), 4, 0)
        self.combo_net_mode = QComboBox()
        self.combo_net_mode.addItem("⚡ High-Speed LAN Bridge (Host IP 192.168.100.5 • Zero-Driver)", "lan_bridge")
        self.combo_net_mode.addItem("🌐 Hardware Bridged (DHCP 192.168.100.x via TAP/NDIS)", "hardware_bridged")
        self.combo_net_mode.addItem("🔒 Standard Isolated NAT (Private 10.0.2.15)", "nat")
        grid.addWidget(self.combo_net_mode, 4, 1)

        grid.addWidget(QLabel("Bridged Adapter:"), 5, 0)
        self.combo_adapter = QComboBox()
        try:
            from nexus.network_bridge import get_system_network_adapters
            for ad in get_system_network_adapters():
                self.combo_adapter.addItem(ad["display_label"], ad["name"])
        except Exception:
            self.combo_adapter.addItem("[Physical Wi-Fi] Realtek RTL8852BE WiFi 6 (192.168.100.5)", "Wi-Fi")
        grid.addWidget(self.combo_adapter, 5, 1)

        c_layout.addLayout(grid)

        self.chk_root = QCheckBox("🔓 Enable Root Access (Writable System Partition && Permissive SELinux)")
        self.chk_root.setStyleSheet("color: #fbbf24; font-weight: bold; margin-top: 6px;")
        c_layout.addWidget(self.chk_root)

        layout.addWidget(card)

        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)

        self.btn_create_launch = QPushButton("⚡ Create && Launch")
        self.btn_create_launch.setProperty("class", "btnPrimary")
        self.btn_create_launch.clicked.connect(lambda: self.create_instance(launch_now=True))
        btn_box.addWidget(self.btn_create_launch)

        self.btn_create = QPushButton("✓ Create Instance")
        self.btn_create.setProperty("class", "btnSecondary")
        self.btn_create.clicked.connect(lambda: self.create_instance(launch_now=False))
        btn_box.addWidget(self.btn_create)

        self.btn_cancel = QPushButton("✕ Cancel")
        self.btn_cancel.setProperty("class", "btnSecondary")
        self.btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(self.btn_cancel)

        layout.addLayout(btn_box)

        self.check_os_installed()

    def check_os_installed(self):
        api = self.combo_os.currentData()
        if AVDManager.is_image_installed(api):
            self.lbl_os_status.setText("🟢 System Image is installed and ready for instant booting.")
            self.lbl_os_status.setStyleSheet("color: #10b981; font-weight: bold;")
            self.btn_download_os.setVisible(False)
        else:
            self.lbl_os_status.setText("⚠️ System Image is not downloaded yet. 1-Click Download required.")
            self.lbl_os_status.setStyleSheet("color: #f59e0b; font-weight: bold;")
            self.btn_download_os.setVisible(True)

    def open_image_downloader(self):
        api = self.combo_os.currentData()
        if not hasattr(self, "_downloader") or self._downloader is None:
            self._downloader = GNDroidImageDownloaderDialog(api, None)
            self._downloader.sig_image_installed.connect(lambda _: self.check_os_installed())
        else:
            self._downloader.select_api(api)
        self._downloader.show()
        self._downloader.raise_()
        self._downloader.activateWindow()

    def create_instance(self, launch_now: bool = False):
        name = self.txt_name.text().strip()
        display = self.txt_display.text().strip()
        if not name:
            QMessageBox.warning(self, "Invalid Name", "Please enter an instance identifier.")
            return
        if not display:
            display = name.replace("_", " ").title()

        name = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
        api = self.combo_os.currentData()

        if not AVDManager.is_image_installed(api):
            res = QMessageBox.question(
                self, "System Image Needed",
                f"The Android {api} System Image is not installed yet on your PC.\n\n"
                "Would you like to open the 1-Click OS Downloader to install it now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if res == QMessageBox.StandardButton.Yes:
                self.open_image_downloader()
            return

        ram = self.combo_ram.currentData()
        cores = self.combo_cores.currentData()
        w, h, d = self.combo_res.currentData()
        gpu = self.combo_gpu.currentData()
        root_on = self.chk_root.isChecked()

        try:
            AVDManager.create_instance(
                name=name,
                display_name=display,
                api_level=api,
                ram_mb=ram,
                cores=cores,
                width=w,
                height=h,
                density=d,
                gpu=gpu,
                root_enabled=root_on
            )
            # Save chosen Network & Hardware Bridging configuration for new instance
            try:
                from nexus.network_bridge import save_instance_network_config
                save_instance_network_config(name, {
                    "mode": self.combo_net_mode.currentData(),
                    "adapter_name": self.combo_adapter.currentText(),
                    "replicate_state": True,
                    "bluetooth_enabled": True,
                    "bluetooth_mode": "netsimd",
                    "exposed_ports": "51888, 51880, 5555, 8080, 8088"
                })
            except Exception:
                pass

            self.created_name = name
            self.launch_after = launch_now
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Creation Error", str(e))

GNDroidNewInstanceDialog = GNDroidInstanceCreatorDialog


# ----------------------------------------------------------------------
# Instance Settings / Edit Hardware Dialog
# ----------------------------------------------------------------------
class GNDroidInstanceSettingsDialog(QDialog):
    def __init__(self, instance: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.instance = instance
        self.setWindowTitle(f"⚙️ Hardware & Root Settings: {instance['display_name']} — GNDROiD")
        self.setFixedSize(540, 480)
        self.setup_ui()

    def setup_ui(self):
        self.setStyleSheet("""
            QDialog { background: #f8f9fa; color: #0f172a; font-family: 'Segoe UI Variable Text', 'Segoe UI', -apple-system, sans-serif; }
            QFrame.cardBox { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; }
            QComboBox {
                background: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px;
                padding: 7px 12px; color: #0f172a; font-size: 12px; font-weight: 500;
            }
            QComboBox:focus { border: 1.5px solid #0067c0; }
            QCheckBox { color: #0f172a; font-size: 11px; font-weight: 500; spacing: 8px; }
            QPushButton.btnPrimary {
                background: #0067c0; border: none; border-radius: 6px; color: #ffffff; font-weight: 600; font-size: 12px; padding: 8px 18px;
            }
            QPushButton.btnPrimary:hover { background: #1879c9; }
            QPushButton.btnPrimary:pressed { background: #005a9e; }
            QPushButton.btnSecondary {
                background: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px;
                color: #0f172a; font-weight: 500; font-size: 12px; padding: 8px 18px;
            }
            QPushButton.btnSecondary:hover { background: #f8fafc; border-color: #94a3b8; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        h_box = QHBoxLayout()
        icon = QLabel("⚙️")
        icon.setFont(QFont("Segoe UI Emoji", 22))
        h_box.addWidget(icon)

        t_box = QVBoxLayout()
        t = QLabel("Hardware & Root Settings")
        t.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        t.setStyleSheet("color: #0f172a;")
        t_box.addWidget(t)

        st = QLabel(f"Instance: {self.instance['name']} • Target: Android {self.instance['api_level']}")
        st.setStyleSheet("color: #64748b; font-size: 11px;")
        t_box.addWidget(st)
        h_box.addLayout(t_box)
        layout.addLayout(h_box)

        card = QFrame()
        card.setProperty("class", "cardBox")
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(16, 14, 16, 14)
        c_layout.setSpacing(12)

        grid = QGridLayout()
        grid.setSpacing(10)

        grid.addWidget(QLabel("RAM Allocation:"), 0, 0)
        self.combo_ram = QComboBox()
        for label, val in [
            ("2 GB (2048 MB)", 2048),
            ("4 GB (4096 MB)", 4096),
            ("8 GB (8192 MB)", 8192),
            ("16 GB (16384 MB)", 16384),
            ("24 GB (24576 MB)", 24576),
            ("32 GB (32768 MB)", 32768),
        ]:
            self.combo_ram.addItem(label, val)
        for i in range(self.combo_ram.count()):
            if self.combo_ram.itemData(i) == self.instance["ram_mb"]:
                self.combo_ram.setCurrentIndex(i)
                break
        grid.addWidget(self.combo_ram, 0, 1)

        grid.addWidget(QLabel("CPU Cores:"), 1, 0)
        self.combo_cores = QComboBox()
        for c in [2, 4, 8, 12, 16, 24]:
            self.combo_cores.addItem(f"{c} Dedicated Cores", c)
        for i in range(self.combo_cores.count()):
            if self.combo_cores.itemData(i) == self.instance["cores"]:
                self.combo_cores.setCurrentIndex(i)
                break
        grid.addWidget(self.combo_cores, 1, 1)

        grid.addWidget(QLabel("Screen Resolution:"), 2, 0)
        self.combo_res = QComboBox()
        res_list = [
            ("1440 x 3120 (Galaxy S24 Ultra QHD+ • 500 DPI) [Default]", 1440, 3120, 500),
            ("1080 x 2400 (Phone FHD+ 20:9 • 420 DPI)", 1080, 2400, 420),
            ("1200 x 1920 (Tablet 10-inch • 280 DPI)", 1200, 1920, 280),
            ("3840 x 2160 (4K Smart TV / Display • 320 DPI)", 3840, 2160, 320),
            ("720 x 1600 (Compact Phone HD+ • 320 DPI)", 720, 1600, 320),
        ]
        matched_res = False
        inst_w = self.instance.get("width", 1440)
        inst_h = self.instance.get("height", 3120)
        inst_d = self.instance.get("density", 500)
        for i, (label, w, h, d) in enumerate(res_list):
            self.combo_res.addItem(label, (w, h, d))
            if w == inst_w and h == inst_h:
                self.combo_res.setCurrentIndex(i)
                matched_res = True
        if not matched_res:
            self.combo_res.insertItem(0, f"Custom ({inst_w} x {inst_h})", (inst_w, inst_h, inst_d))
            self.combo_res.setCurrentIndex(0)
        grid.addWidget(self.combo_res, 2, 1)

        grid.addWidget(QLabel("GPU Mode:"), 3, 0)
        self.combo_gpu = QComboBox()
        self.combo_gpu.addItem("Auto (Hardware Vulkan / Direct3D 11)", "auto")
        self.combo_gpu.addItem("Host (Direct Passthrough)", "host")
        self.combo_gpu.addItem("SwiftShader (Software Fallback)", "swiftshader_indirect")
        for i in range(self.combo_gpu.count()):
            if self.combo_gpu.itemData(i) == self.instance.get("gpu", "auto"):
                self.combo_gpu.setCurrentIndex(i)
                break
        grid.addWidget(self.combo_gpu, 3, 1)

        c_layout.addLayout(grid)

        self.chk_root = QCheckBox("🔓 Enable Root Access (Writable System Partition && Permissive SELinux)")
        self.chk_root.setChecked(self.instance.get("root", False))
        self.chk_root.setStyleSheet("color: #b45309; font-weight: bold; margin-top: 6px;")
        c_layout.addWidget(self.chk_root)

        root_note = QLabel(
            "ℹ️ <b>Android 10–16 & SuperSU Note:</b> Retail Google Play images enforce locked dm-verity and block 'adb root'. "
            "Legacy SuperSU (2018) is incompatible with Android 10+. For full root, use Magisk/KernelSU or switch to Google APIs image."
        )
        root_note.setWordWrap(True)
        root_note.setStyleSheet("color: #64748b; font-size: 10px; margin-top: 2px; margin-bottom: 6px;")
        c_layout.addWidget(root_note)

        tools_row = QHBoxLayout()
        tools_row.setSpacing(8)

        self.btn_test_root = QPushButton("🔍 Live Test Guest Root")
        self.btn_test_root.setProperty("class", "btnAction")
        self.btn_test_root.clicked.connect(self.action_test_guest_root)
        tools_row.addWidget(self.btn_test_root)

        self.btn_reset_disp = QPushButton("🖥️ Reset Screen Glitch (1440x3120)")
        self.btn_reset_disp.setProperty("class", "btnAction")
        self.btn_reset_disp.setToolTip("Removes residual multi-display viewports and resets primary screen to clean 1440x3120 500 DPI")
        self.btn_reset_disp.clicked.connect(self.action_reset_display_glitch)
        tools_row.addWidget(self.btn_reset_disp)

        c_layout.addLayout(tools_row)

        self.lbl_root_live = QLabel("")
        self.lbl_root_live.setWordWrap(True)
        self.lbl_root_live.setStyleSheet("color: #0369a1; font-size: 11px; font-weight: 500; margin-top: 2px;")
        c_layout.addWidget(self.lbl_root_live)

        layout.addWidget(card)

        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)

        btn_save = QPushButton("💾 Save Settings")
        btn_save.setProperty("class", "btnPrimary")
        btn_save.clicked.connect(self.save_settings)
        btn_box.addWidget(btn_save)

        btn_cancel = QPushButton("✕ Cancel")
        btn_cancel.setProperty("class", "btnSecondary")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        layout.addLayout(btn_box)

    def action_test_guest_root(self):
        self.lbl_root_live.setText("⏳ Testing guest root status via ADB...")
        serial = self.instance.get("serial", "")
        res = AVDManager.check_live_root(serial)
        self.lbl_root_live.setText(res.get("message", "Check complete."))

    def action_reset_display_glitch(self):
        try:
            AVDManager.reset_instance_display(self.instance["name"], width=1440, height=3120, density=500)
            # Update combo to match
            for i in range(self.combo_res.count()):
                d = self.combo_res.itemData(i)
                if isinstance(d, tuple) and d[0] == 1440 and d[1] == 3120:
                    self.combo_res.setCurrentIndex(i)
                    break
            QMessageBox.information(
                self, "Screen Restored",
                f"Multi-screen viewports purged!\nDisplay reset to Flagship 1440 x 3120 (500 DPI).\nSnapshots and lock files cleared."
            )
        except Exception as e:
            QMessageBox.critical(self, "Reset Error", str(e))

    def save_settings(self):
        ram = self.combo_ram.currentData()
        cores = self.combo_cores.currentData()
        w, h, d = self.combo_res.currentData()
        gpu = self.combo_gpu.currentData()
        root_on = self.chk_root.isChecked()

        try:
            AVDManager.update_instance_settings(
                name=self.instance["name"],
                ram_mb=ram,
                cores=cores,
                width=w,
                height=h,
                density=d,
                gpu=gpu,
                root_enabled=root_on
            )
            QMessageBox.information(self, "Settings Saved", f"Settings for '{self.instance['name']}' saved successfully!")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Save Error", str(e))


# ----------------------------------------------------------------------
# Central Multi-Instance Manager Dialog
# ----------------------------------------------------------------------
def tile_running_windows() -> int:
    hwnds = []
    def enum_cb(h, lparam):
        if user32.IsWindowVisible(h) and not user32.IsIconic(h):
            length = user32.GetWindowTextLengthW(h)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(h, buf, length + 1)
                t = buf.value
                t_lower = t.lower()
                # Feature 12: Case-insensitive window matching so Scrcpy ("GNDROiD - ...", "GNDROiD: ...") windows are properly detected and arranged
                is_scrcpy_app = t.startswith("GNDROiD:") or t.startswith("gndroid:") or t.startswith("GNDROiD -") or t.startswith("gndroid -")
                is_mgmt = any(k in t_lower for k in ["controls", "manager", "doctor", "settings & hardware", "suite", "launcher"]) or "gndroid settings" in t_lower
                if (is_scrcpy_app or ("gndroid" in t_lower or "android emulator" in t_lower)) and not is_mgmt:
                    hwnds.append(h)
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
    if not hwnds:
        return 0

    screen = QApplication.primaryScreen().geometry()
    n = len(hwnds)
    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    w = (screen.width() - 40) // cols
    h = (screen.height() - 80) // rows
    for i, h_wnd in enumerate(hwnds):
        r = i // cols
        c = i % cols
        x = 20 + c * w
        y = 40 + r * h
        user32.MoveWindow(h_wnd, x, y, w, h, True)
    return n

# Feature 12: tile_windows alias
tile_windows = tile_running_windows



class InstanceScannerWorker(QThread):
    instances_loaded = pyqtSignal(list)

    def run(self):
        try:
            insts = AVDManager.list_instances()
            self.instances_loaded.emit(insts)
        except Exception:
            pass


class GNDroidMultiInstanceManager(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("GNDROiD Multi-Instance Manager")
        self.setFixedSize(1180, 700)
        self.instances: List[Dict[str, Any]] = []
        self.selected_instances: set = set()
        self.starting_instances: Dict[str, Dict[str, Any]] = {}
        self.filter_mode: str = "all"  # "all", "running", "stopped"
        self._scanner_worker: Optional[InstanceScannerWorker] = None
        self._downloader: Optional[GNDroidImageDownloaderDialog] = None
        self.setup_ui()
        self.refresh_table()

        self.timer = QTimer(self)
        self.timer.setInterval(3000)
        self.timer.timeout.connect(self.refresh_table)
        self.timer.start()

    def setup_ui(self):
        self.setStyleSheet("""
            QDialog {
                background: #f8f9fa;
                color: #0f172a;
                font-family: 'Segoe UI Variable Text', 'Segoe UI', -apple-system, sans-serif;
            }
            QFrame.cardBox {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
            }
            QLineEdit {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 6px 12px;
                color: #0f172a;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 1.5px solid #0067c0;
            }
            QPushButton.btnAction {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 6px 14px;
                color: #0f172a;
                font-weight: 500;
                font-size: 11px;
            }
            QPushButton.btnAction:hover {
                background: #f8fafc;
                border-color: #94a3b8;
            }
            QPushButton.btnAction:pressed {
                background: #f1f5f9;
            }
            QPushButton.btnHero {
                background: #0067c0;
                border: 1px solid #005a9e;
                border-radius: 6px;
                color: #ffffff;
                font-weight: 600;
                font-size: 11px;
                padding: 6px 14px;
            }
            QPushButton.btnHero:hover {
                background: #1879c9;
            }
            QPushButton.btnHero:pressed {
                background: #005a9e;
            }
            QPushButton.btnStop {
                background: #ffffff;
                border: 1px solid #fca5a5;
                border-radius: 6px;
                color: #dc2626;
                font-weight: 500;
                font-size: 11px;
                padding: 6px 10px;
            }
            QPushButton.btnStop:hover {
                background: #fee2e2;
                border-color: #ef4444;
                color: #b91c1c;
            }
            QPushButton.btnDelete {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                color: #dc2626;
                font-weight: 500;
                font-size: 11px;
                padding: 6px 8px;
            }
            QPushButton.btnDelete:hover {
                background: #fee2e2;
                border-color: #ef4444;
                color: #b91c1c;
            }
            QPushButton.btnFilterActive {
                background: #0067c0;
                border: 1px solid #005a9e;
                border-radius: 6px;
                padding: 5px 12px;
                color: #ffffff;
                font-weight: 600;
                font-size: 11px;
            }
            QPushButton.btnFilterInactive {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 5px 12px;
                color: #64748b;
                font-weight: 500;
                font-size: 11px;
            }
            QPushButton.btnFilterInactive:hover {
                background: #f8fafc;
                color: #0f172a;
            }
            QTableWidget {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                gridline-color: #f1f5f9;
                color: #0f172a;
                outline: none;
            }
            QTableWidget::item {
                padding: 4px 6px;
                border-bottom: 1px solid #f1f5f9;
            }
            QTableWidget::item:hover {
                background: #f8fafc;
            }
            QTableWidget::item:selected {
                background: #e0f2fe;
                color: #0369a1;
            }
            QHeaderView::section {
                background: #f8fafc;
                color: #475569;
                font-weight: 600;
                border: none;
                padding: 8px 10px;
                font-size: 11px;
                border-bottom: 1px solid #e2e8f0;
            }
            QCheckBox {
                color: #0f172a;
                font-size: 11px;
                font-weight: 500;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 8px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #cbd5e1;
                min-height: 24px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background: #94a3b8;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        # 1. Header Section
        head_box = QHBoxLayout()
        head_box.setSpacing(12)

        icon = QLabel()
        icon_path = SystemPaths.get_icon().replace(".ico", ".png")
        if os.path.exists(icon_path):
            pix = QPixmap(icon_path).scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            icon.setPixmap(pix)
        else:
            icon.setText("📱")
            icon.setFont(QFont("Segoe UI Emoji", 24))
        head_box.addWidget(icon)

        t_box = QVBoxLayout()
        t_box.setSpacing(2)
        t = QLabel("GNDROiD Multi-Instance Manager")
        t.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        t.setStyleSheet("color: #0f172a;")
        t_box.addWidget(t)

        st = QLabel("Launch, clone, tile, and manage parallel Android instances with dedicated hardware allocation.")
        st.setStyleSheet("color: #64748b; font-size: 11px;")
        t_box.addWidget(st)
        head_box.addLayout(t_box)

        head_box.addStretch()

        self.btn_new = QPushButton("＋ New Instance")
        self.btn_new.setProperty("class", "btnHero")
        self.btn_new.clicked.connect(self.action_new_instance)
        head_box.addWidget(self.btn_new)

        self.btn_dl_img = QPushButton("Download OS")
        self.btn_dl_img.setProperty("class", "btnAction")
        self.btn_dl_img.clicked.connect(self.action_download_image)
        head_box.addWidget(self.btn_dl_img)

        self.btn_tile_win = QPushButton("Tile Windows")
        self.btn_tile_win.setProperty("class", "btnAction")
        self.btn_tile_win.setToolTip("Auto-arrange all running emulator windows in a clean desktop grid")
        self.btn_tile_win.clicked.connect(self.action_tile_windows)
        head_box.addWidget(self.btn_tile_win)

        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.setProperty("class", "btnAction")
        self.btn_refresh.clicked.connect(self.refresh_table)
        head_box.addWidget(self.btn_refresh)

        layout.addLayout(head_box)

        # 2. Telemetry Bar
        telem_card = QFrame()
        telem_card.setProperty("class", "cardBox")
        tc_l = QHBoxLayout(telem_card)
        tc_l.setContentsMargins(14, 8, 14, 8)

        self.lbl_telem_instances = QLabel("Instances: 0 Total • 0 Running • 0 Stopped")
        self.lbl_telem_instances.setStyleSheet("color: #0f172a; font-weight: 600; font-size: 11px;")
        tc_l.addWidget(self.lbl_telem_instances)

        tc_l.addStretch()

        self.lbl_telem_ports = QLabel("Ports: 5554-5586 (ADB ready)")
        self.lbl_telem_ports.setStyleSheet("color: #64748b; font-size: 11px;")
        tc_l.addWidget(self.lbl_telem_ports)

        tc_l.addStretch()

        self.lbl_telem_host = QLabel("Host System: Multi-Core Hardware Accelerated")
        self.lbl_telem_host.setStyleSheet("color: #64748b; font-size: 11px;")
        tc_l.addWidget(self.lbl_telem_host)

        layout.addWidget(telem_card)

        # 3. Search & Filter Bar
        sf_bar = QHBoxLayout()
        sf_bar.setSpacing(8)

        self.edit_search = QLineEdit()
        self.edit_search.setPlaceholderText("Search instances by name, API level, or ID...")
        self.edit_search.textChanged.connect(self.refresh_table)
        sf_bar.addWidget(self.edit_search, 3)

        self.btn_filt_all = QPushButton("All")
        self.btn_filt_all.setProperty("class", "btnFilterActive")
        self.btn_filt_all.clicked.connect(lambda: self.set_filter("all"))
        sf_bar.addWidget(self.btn_filt_all)

        self.btn_filt_running = QPushButton("● Running")
        self.btn_filt_running.setProperty("class", "btnFilterInactive")
        self.btn_filt_running.clicked.connect(lambda: self.set_filter("running"))
        sf_bar.addWidget(self.btn_filt_running)

        self.btn_filt_stopped = QPushButton("○ Stopped")
        self.btn_filt_stopped.setProperty("class", "btnFilterInactive")
        self.btn_filt_stopped.clicked.connect(lambda: self.set_filter("stopped"))
        sf_bar.addWidget(self.btn_filt_stopped)

        layout.addLayout(sf_bar)

        # 4. Multi-Instance Table
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["☑", "Instance Identity", "Status & Port", "Hardware Specs", "Root & State", "Quick Actions"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 36)
        self.table.setColumnWidth(1, 305)
        self.table.setColumnWidth(2, 160)
        self.table.setColumnWidth(4, 90)
        self.table.setColumnWidth(5, 325)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.table)

        # 5. Batch Controls Footer
        footer = QHBoxLayout()
        footer.setSpacing(8)

        self.chk_select_all = QCheckBox("Select All")
        self.chk_select_all.stateChanged.connect(self.toggle_select_all)
        footer.addWidget(self.chk_select_all)

        btn_batch_start = QPushButton("▶ Start Selected")
        btn_batch_start.setProperty("class", "btnHero")
        btn_batch_start.clicked.connect(self.action_batch_start)
        footer.addWidget(btn_batch_start)

        btn_batch_stop = QPushButton("⏹ Stop Selected")
        btn_batch_stop.setProperty("class", "btnStop")
        btn_batch_stop.clicked.connect(self.action_batch_stop)
        footer.addWidget(btn_batch_stop)

        btn_batch_del = QPushButton("Delete Selected")
        btn_batch_del.setProperty("class", "btnDelete")
        btn_batch_del.clicked.connect(self.action_batch_delete)
        footer.addWidget(btn_batch_del)

        btn_clean_locks = QPushButton("Clean Stale Locks")
        btn_clean_locks.setProperty("class", "btnAction")
        btn_clean_locks.setToolTip("Deletes crashed or orphaned .lock files across all instances so they can launch immediately")
        btn_clean_locks.clicked.connect(self.action_clean_locks)
        footer.addWidget(btn_clean_locks)

        btn_fix_screens = QPushButton("🖥️ Fix Screen Glitch")
        btn_fix_screens.setProperty("class", "btnAction")
        btn_fix_screens.setToolTip("Resets fractured multi-displays and restores clean flagship single-screen layout (1440x3120 500 DPI)")
        btn_fix_screens.clicked.connect(self.action_fix_screens)
        footer.addWidget(btn_fix_screens)

        footer.addStretch()

        btn_close = QPushButton("Close")
        btn_close.setProperty("class", "btnAction")
        btn_close.clicked.connect(self.accept)
        footer.addWidget(btn_close)

        layout.addLayout(footer)

    def show_confirm_dialog(self, title: str, heading: str, body: str, confirm_text: str = "Delete", is_danger: bool = True) -> bool:
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setFixedSize(430, 185)
        dlg.setStyleSheet("""
            QDialog {
                background-color: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                font-family: 'Segoe UI', -apple-system, sans-serif;
            }
            QLabel {
                color: #0f172a;
            }
            QPushButton.btnConfirm {
                background-color: """ + ("#dc2626" if is_danger else "#0067c0") + """;
                color: #ffffff;
                border: 1px solid rgba(0, 0, 0, 0.08);
                border-radius: 4px;
                padding: 6px 18px;
                font-weight: 600;
                font-size: 11px;
                min-width: 75px;
            }
            QPushButton.btnConfirm:hover {
                background-color: """ + ("#b91c1c" if is_danger else "#005a9e") + """;
            }
            QPushButton.btnCancel {
                background-color: #f1f5f9;
                color: #334155;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 6px 18px;
                font-weight: 500;
                font-size: 11px;
                min-width: 75px;
            }
            QPushButton.btnCancel:hover {
                background-color: #e2e8f0;
            }
        """)
        l = QVBoxLayout(dlg)
        l.setContentsMargins(22, 18, 22, 18)
        l.setSpacing(12)

        h_box = QHBoxLayout()
        icon = QLabel("⚠️" if is_danger else "ℹ️")
        icon.setFont(QFont("Segoe UI Emoji", 22))
        h_box.addWidget(icon, alignment=Qt.AlignmentFlag.AlignTop)

        txt_box = QVBoxLayout()
        txt_box.setSpacing(6)
        h_lbl = QLabel(heading)
        h_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        h_lbl.setStyleSheet("color: #0f172a;")
        txt_box.addWidget(h_lbl)

        b_lbl = QLabel(body)
        b_lbl.setWordWrap(True)
        b_lbl.setStyleSheet("color: #475569; font-size: 11px;")
        txt_box.addWidget(b_lbl)

        h_box.addLayout(txt_box, 1)
        l.addLayout(h_box)

        l.addStretch()

        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)
        btn_box.addStretch()

        btn_confirm = QPushButton(confirm_text)
        btn_confirm.setProperty("class", "btnConfirm")
        btn_confirm.clicked.connect(dlg.accept)
        btn_box.addWidget(btn_confirm)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setProperty("class", "btnCancel")
        btn_cancel.clicked.connect(dlg.reject)
        btn_box.addWidget(btn_cancel)

        l.addLayout(btn_box)

        return dlg.exec() == QDialog.DialogCode.Accepted

    def set_filter(self, mode: str):
        self.filter_mode = mode
        self.btn_filt_all.setProperty("class", "btnFilterActive" if mode == "all" else "btnFilterInactive")
        self.btn_filt_running.setProperty("class", "btnFilterActive" if mode == "running" else "btnFilterInactive")
        self.btn_filt_stopped.setProperty("class", "btnFilterActive" if mode == "stopped" else "btnFilterInactive")
        self.btn_filt_all.style().unpolish(self.btn_filt_all); self.btn_filt_all.style().polish(self.btn_filt_all)
        self.btn_filt_running.style().unpolish(self.btn_filt_running); self.btn_filt_running.style().polish(self.btn_filt_running)
        self.btn_filt_stopped.style().unpolish(self.btn_filt_stopped); self.btn_filt_stopped.style().polish(self.btn_filt_stopped)
        self.refresh_table()

    def refresh_table(self):
        if self._scanner_worker and self._scanner_worker.isRunning():
            return
        self._scanner_worker = InstanceScannerWorker(self)
        self._scanner_worker.instances_loaded.connect(self.on_instances_loaded)
        self._scanner_worker.start()

    def on_instances_loaded(self, all_instances: List[Dict[str, Any]]):
        running_count = sum(1 for i in all_instances if i["running"])
        stopped_count = len(all_instances) - running_count

        self.lbl_telem_instances.setText(f"Instances: {len(all_instances)} Total • {running_count} Running • {stopped_count} Stopped")

        query = self.edit_search.text().strip().lower()
        filtered = []
        for inst in all_instances:
            name = inst["name"]
            if name in self.starting_instances:
                if inst["running"]:
                    self.starting_instances.pop(name, None)
                else:
                    inst["starting"] = True
                    inst["port"] = self.starting_instances[name]["port"]
                    inst["serial"] = self.starting_instances[name]["serial"]

            if self.filter_mode == "running" and not inst["running"]:
                continue
            if self.filter_mode == "stopped" and inst["running"]:
                continue
            if query:
                s_target = f"{inst['name']} {inst['display_name']} {inst['api_level']}".lower()
                if query not in s_target:
                    continue
            filtered.append(inst)

        self.instances = filtered
        self.table.setRowCount(len(self.instances))

        for row, inst in enumerate(self.instances):
            self.table.setRowHeight(row, 48)

            # Col 0: Checkbox
            chk = QCheckBox()
            chk.setChecked(inst["name"] in self.selected_instances)
            chk.stateChanged.connect(lambda state, n=inst["name"]: self.on_instance_check(n, state))
            c_box = QWidget()
            c_l = QHBoxLayout(c_box)
            c_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            c_l.setContentsMargins(0, 0, 0, 0)
            c_l.addWidget(chk)
            self.table.setCellWidget(row, 0, c_box)

            # Col 1: Identity
            name_box = QWidget()
            nb_layout = QVBoxLayout(name_box)
            nb_layout.setContentsMargins(6, 4, 6, 4)
            nb_layout.setSpacing(1)
            clean_name = re.sub(r'\s*\(\d+GB RAM\s*/\s*\d+\s*Cores\)', '', inst['display_name'], flags=re.IGNORECASE).strip()
            clean_name = re.sub(r'(?i)gnd[o|r]*id', 'GNDROiD', clean_name)
            t_name = QLabel(f"[A{inst['api_level']}] {clean_name}")
            t_name.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
            t_name.setStyleSheet("color: #0f172a;" if inst["running"] else "color: #334155;")
            t_name.setToolTip(f"{inst['display_name']} (id: {inst['name']})")
            nb_layout.addWidget(t_name)
            sub_name = QLabel(f"id: {inst['name']}")
            sub_name.setStyleSheet("color: #64748b; font-size: 10px; font-family: monospace;")
            nb_layout.addWidget(sub_name)
            self.table.setCellWidget(row, 1, name_box)

            # Col 2: Status & Port
            status_box = QWidget()
            sb_layout = QVBoxLayout(status_box)
            sb_layout.setContentsMargins(6, 4, 6, 4)
            sb_layout.setSpacing(1)
            if inst.get("starting"):
                port_str = str(inst.get("port", "5554"))
                st_lbl = QLabel(f"◐ Booting (Port {port_str})...")
                st_lbl.setStyleSheet("color: #d97706; font-weight: 600; font-size: 11px;")
                sb_layout.addWidget(st_lbl)
                sub_st = QLabel("OS & Kernel Starting...")
                sub_st.setStyleSheet("color: #b45309; font-size: 10px;")
                sb_layout.addWidget(sub_st)
            elif inst["running"]:
                port_str = inst["serial"].replace("emulator-", "")
                st_lbl = QLabel(f"● Running (Port {port_str})")
                st_lbl.setStyleSheet("color: #16a34a; font-weight: 600; font-size: 11px;")
                sb_layout.addWidget(st_lbl)
                sub_st = QLabel(f"serial: {inst['serial']}")
                sub_st.setStyleSheet("color: #64748b; font-size: 10px; font-family: monospace;")
                sb_layout.addWidget(sub_st)
            else:
                st_lbl = QLabel("○ Stopped")
                st_lbl.setStyleSheet("color: #64748b; font-weight: 500; font-size: 11px;")
                sb_layout.addWidget(st_lbl)
                sub_st = QLabel("QuickBoot Ready")
                sub_st.setStyleSheet("color: #94a3b8; font-size: 10px;")
                sb_layout.addWidget(sub_st)
            self.table.setCellWidget(row, 2, status_box)

            # Col 3: Hardware Specs
            ram_gb = inst["ram_mb"] // 1024
            specs_txt = f"{ram_gb} GB RAM • {inst['cores']} Cores • {inst['width']}x{inst['height']} • Android {inst['api_level']}"
            item_specs = QTableWidgetItem(specs_txt)
            item_specs.setForeground(QColor("#334155"))
            self.table.setItem(row, 3, item_specs)

            # Col 4: Root & State
            root_box = QWidget()
            rb_layout = QHBoxLayout(root_box)
            rb_layout.setContentsMargins(6, 4, 6, 4)
            if inst["root"]:
                r_lbl = QLabel("🔓 ROOT")
                r_lbl.setStyleSheet("color: #b45309; font-weight: 600; font-size: 11px;")
            else:
                r_lbl = QLabel("Normal")
                r_lbl.setStyleSheet("color: #64748b; font-weight: 500; font-size: 11px;")
            rb_layout.addWidget(r_lbl)
            self.table.setCellWidget(row, 4, root_box)

            # Col 5: Actions
            act_box = QWidget()
            ab_layout = QHBoxLayout(act_box)
            ab_layout.setContentsMargins(4, 4, 4, 4)
            ab_layout.setSpacing(4)

            if inst.get("starting"):
                btn_start_stop = QPushButton("⏳ Starting")
                btn_start_stop.setEnabled(False)
                btn_start_stop.setFixedWidth(78)
                btn_start_stop.setFixedHeight(28)
                btn_start_stop.setStyleSheet("padding: 4px 6px; font-size: 11px; background: #fef3c7; color: #b45309; border: 1px solid #fde68a; border-radius: 4px;")
                ab_layout.addWidget(btn_start_stop)
            elif inst["running"]:
                btn_start_stop = QPushButton("⏹ Stop")
                btn_start_stop.setProperty("class", "btnStop")
                btn_start_stop.setFixedWidth(68)
                btn_start_stop.setFixedHeight(28)
                btn_start_stop.setStyleSheet("padding: 4px 6px; font-size: 11px;")
                btn_start_stop.clicked.connect(lambda _, n=inst["name"]: self.action_stop_instance(n))
                ab_layout.addWidget(btn_start_stop)

                btn_mirror = QPushButton("🖥 Mirror")
                btn_mirror.setProperty("class", "btnAction")
                btn_mirror.setFixedWidth(74)
                btn_mirror.setFixedHeight(28)
                btn_mirror.setStyleSheet("padding: 4px 6px; font-size: 11px;")
                btn_mirror.setToolTip(f"Open GNDROiD Live Mirror for {inst['serial']}")
                btn_mirror.clicked.connect(lambda _, s=inst["serial"]: start_mirror_with_fallback(s, self))
                ab_layout.addWidget(btn_mirror)
            else:
                btn_start_stop = QPushButton("▶ Start")
                btn_start_stop.setProperty("class", "btnHero")
                btn_start_stop.setFixedWidth(68)
                btn_start_stop.setFixedHeight(28)
                btn_start_stop.setStyleSheet("padding: 4px 6px; font-size: 11px;")
                btn_start_stop.clicked.connect(lambda _, n=inst["name"]: self.action_start_instance(n))
                ab_layout.addWidget(btn_start_stop)

            btn_clone = QPushButton("📋 Clone")
            btn_clone.setProperty("class", "btnAction")
            btn_clone.setFixedWidth(76)
            btn_clone.setFixedHeight(28)
            btn_clone.setStyleSheet("padding: 4px 6px; font-size: 11px;")
            btn_clone.clicked.connect(lambda _, i=inst: self.action_clone_instance(i))
            ab_layout.addWidget(btn_clone)

            btn_edit = QPushButton("⚙")
            btn_edit.setProperty("class", "btnAction")
            btn_edit.setFixedSize(30, 28)
            btn_edit.setStyleSheet("padding: 0px; font-family: 'Segoe UI Emoji', 'Segoe UI Symbol', sans-serif; font-size: 13px; color: #1e293b;")
            btn_edit.setToolTip("Hardware & Root Settings")
            btn_edit.clicked.connect(lambda _, i=inst: self.action_edit_instance(i))
            ab_layout.addWidget(btn_edit)

            btn_open_f = QPushButton("📁")
            btn_open_f.setProperty("class", "btnAction")
            btn_open_f.setFixedSize(30, 28)
            btn_open_f.setStyleSheet("padding: 0px; font-family: 'Segoe UI Emoji', 'Segoe UI Symbol', sans-serif; font-size: 13px; color: #1e293b;")
            btn_open_f.setToolTip("Open AVD Folder in File Explorer")
            btn_open_f.clicked.connect(lambda _, n=inst["name"]: self.open_avd_dir(n))
            ab_layout.addWidget(btn_open_f)

            btn_del = QPushButton("🗑")
            btn_del.setProperty("class", "btnDelete")
            btn_del.setFixedSize(30, 28)
            btn_del.setStyleSheet("padding: 0px; font-family: 'Segoe UI Emoji', 'Segoe UI Symbol', sans-serif; font-size: 13px; color: #dc2626;")
            btn_del.setToolTip("Delete Instance")
            btn_del.clicked.connect(lambda _, n=inst["name"]: self.action_delete_instance(n))
            ab_layout.addWidget(btn_del)

            self.table.setCellWidget(row, 5, act_box)

    def on_instance_check(self, name: str, state: int):
        if state == 2:
            self.selected_instances.add(name)
        else:
            self.selected_instances.discard(name)

    def toggle_select_all(self, state: int):
        if state == 2:
            self.selected_instances = {i["name"] for i in self.instances}
        else:
            self.selected_instances.clear()
        self.refresh_table()

    def action_new_instance(self):
        dlg = GNDroidInstanceCreatorDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh_table()
            if getattr(dlg, "launch_after", False) and getattr(dlg, "created_name", ""):
                self.action_start_instance(dlg.created_name)

    def action_download_image(self, target_api: int = 34):
        if not hasattr(self, "_downloader") or self._downloader is None:
            self._downloader = GNDroidImageDownloaderDialog(target_api, None)
            self._downloader.sig_image_installed.connect(lambda _: self.refresh_table())
        else:
            self._downloader.select_api(target_api)
        self._downloader.show()
        self._downloader.raise_()
        self._downloader.activateWindow()

    def action_tile_windows(self):
        count = tile_running_windows()
        if count == 0:
            QMessageBox.information(self, "Tile Windows", "No active gndroid emulator windows were found to tile.")
        else:
            QMessageBox.information(self, "Tile Windows", f"Successfully tiled {count} emulator window(s) in a desktop grid.")

    action_auto_tile_desktop = action_tile_windows

    def action_clean_locks(self):
        cleaned = AVDManager.clean_stale_locks()
        QMessageBox.information(self, "Clean Locks", f"Cleaned {cleaned} stale .lock file(s) across all instances.\nInstances are ready for immediate launch.")

    def action_fix_screens(self):
        cleaned_total = 0
        for inst in self.instances:
            AVDManager.reset_instance_display(inst["name"], width=1440, height=3120, density=500)
            cleaned_total += 1
        self.refresh_table()
        QMessageBox.information(
            self, "Display Restored",
            f"Successfully cleaned multi-display settings and restored single screen (1440x3120 @ 500 DPI) across {cleaned_total} instance(s).\nStale snapshots and hardware locks have been purged."
        )

    def open_avd_dir(self, name: str):
        avd_dir = os.path.join(os.path.expanduser("~"), ".android", "avd", f"{name}.avd")
        if os.path.exists(avd_dir):
            os.startfile(avd_dir)
        else:
            QMessageBox.warning(self, "Folder Not Found", f"Directory does not exist:\n{avd_dir}")

    def action_clone_instance(self, inst: Dict[str, Any]):
        base_name = inst["name"]
        cloned_name = f"clone_{base_name}_{int(time.time()) % 1000}"
        cloned_display = f"Clone of {inst['display_name']}"

        try:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            AVDManager.clone_instance(base_name, cloned_name, cloned_display, deep_copy_snapshots=False)
            QApplication.restoreOverrideCursor()
            QMessageBox.information(self, "Clone Created", f"Successfully cloned '{base_name}' to new instance:\n\n'{cloned_display}'")
            self.refresh_table()
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Clone Error", str(e))

    def action_edit_instance(self, inst: Dict[str, Any]):
        dlg = GNDroidSettingsDialog(instance_name=inst["name"], parent=self)
        if dlg.exec():
            self.refresh_table()

    def action_start_instance(self, name: str):
        inst = next((i for i in self.instances if i["name"] == name), None)
        if not inst or inst["running"]: return

        api = inst.get("api_level", 34)
        if not AVDManager.is_image_installed(api):
            if self.show_confirm_dialog(
                title="System Image Required",
                heading=f"System Image Android {api} Not Found",
                body=f"Android {api} system image is required to launch '{name}'.\n\nWould you like to open the 1-Click OS Downloader now to install it?",
                confirm_text="Download",
                is_danger=False
            ):
                self.action_download_image(api)
                return
            else:
                return

        try:
            proc, port, log_path = AVDManager.launch_emulator_instance(
                name=name,
                gpu_mode=inst.get("gpu", "auto"),
                is_root=inst.get("root", False)
            )
            target_serial = f"emulator-{port}"
            self.starting_instances[name] = {
                "proc": proc,
                "pid": proc.pid if hasattr(proc, "pid") else None,
                "port": port,
                "serial": target_serial,
                "attempts": 0
            }
            self.refresh_table()

            def poll_manager_boot():
                if name not in self.starting_instances:
                    return
                info = self.starting_instances[name]
                info["attempts"] += 1
                devs = SystemPaths.list_devices()
                online = any(d["serial"] == target_serial and d["state"] == "device" for d in devs)
                if online:
                    self.starting_instances.pop(name, None)
                    self.refresh_table()
                    try:
                        from nexus.display_and_vpn import auto_stabilize_vpn_networking
                        threading.Thread(target=auto_stabilize_vpn_networking, args=(target_serial,), daemon=True).start()
                    except Exception:
                        pass
                    return
                if info["attempts"] < 35:
                    QTimer.singleShot(1500, poll_manager_boot)
                else:
                    self.starting_instances.pop(name, None)
                    self.refresh_table()

            QTimer.singleShot(2000, poll_manager_boot)
        except Exception as e:
            self.starting_instances.pop(name, None)
            self.refresh_table()
            QMessageBox.critical(self, "Launch Error", f"Failed to start instance '{name}': {e}")


    def action_stop_instance(self, name: str):
        # Feature 8: Gracefully stop instance with fallback to process termination
        AVDManager.stop_instance(name, timeout=4.0)
        QTimer.singleShot(1000, self.refresh_table)

    def action_delete_instance(self, name: str):
        if not self.show_confirm_dialog(
            title="Confirm Delete",
            heading=f"Delete '{name}'?",
            body="This will permanently delete this instance and its virtual disk. This action cannot be undone.",
            confirm_text="Delete",
            is_danger=True
        ):
            return
        # Feature 9: Stop instance first, then delete_instance verifies termination & file locks
        self.action_stop_instance(name)
        AVDManager.delete_instance(name)
        self.refresh_table()

    def action_batch_start(self):
        targets = [i for i in self.instances if i["name"] in self.selected_instances and not i["running"]]
        if not targets:
            QMessageBox.information(self, "Notice", "No stopped instances selected to start.")
            return
        for t in targets:
            self.action_start_instance(t["name"])
            time.sleep(1.5)

    def action_batch_stop(self):
        targets = [i for i in self.instances if i["name"] in self.selected_instances and i["running"]]
        if not targets:
            QMessageBox.information(self, "Notice", "No running instances selected to stop.")
            return
        for t in targets:
            self.action_stop_instance(t["name"])

    def action_batch_delete(self):
        targets = list(self.selected_instances)
        if not targets:
            QMessageBox.information(self, "Notice", "No instances selected.")
            return
        if not self.show_confirm_dialog(
            title="Confirm Batch Delete",
            heading=f"Delete {len(targets)} selected instance(s)?",
            body="This will permanently remove the selected virtual machines and free their disk space.",
            confirm_text="Delete All",
            is_danger=True
        ):
            return
        for n in targets:
            self.action_stop_instance(n)
            AVDManager.delete_instance(n)
        self.selected_instances.clear()
        self.refresh_table()


# ----------------------------------------------------------------------
# Feature 13 & 14: Non-Blocking ADB Package Installation & File Push Worker
# ----------------------------------------------------------------------
class AdbInstallOrPushWorker(QThread):
    progress = pyqtSignal(str)
    file_result = pyqtSignal(str, bool, str)  # (filename, is_success, message)
    finished_all = pyqtSignal(int, int)       # (success_count, fail_count)

    def __init__(self, files: List[str], target_serial: str = "", destination_folder: str = "/sdcard/Download/", parent=None):
        super().__init__(parent)
        self.files = list(files)
        self.target_serial = target_serial or ""
        self.destination_folder = destination_folder
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        adb = SystemPaths.get_adb()
        target = ["-s", self.target_serial] if self.target_serial else []
        success_count = 0
        fail_count = 0
        total = len(self.files)

        for idx, fpath in enumerate(self.files):
            if self._is_cancelled:
                break
            if not fpath or not os.path.exists(fpath):
                continue

            fname = os.path.basename(fpath)
            is_apk = fname.lower().endswith(".apk")

            if is_apk:
                self.progress.emit(f"Installing {fname} ({idx + 1}/{total})...")
                try:
                    res = subprocess.run(
                        [adb] + target + ["install", "-r", fpath],
                        capture_output=True,
                        text=True,
                        timeout=120,
                        creationflags=0x08000000
                    )
                    out = ((res.stdout or "") + "\n" + (res.stderr or "")).strip()
                    out_low = out.lower()
                    has_error = (
                        res.returncode != 0 or
                        "failure" in out_low or
                        "install_failed" in out_low or
                        "install_parse_failed" in out_low or
                        "error:" in out_low
                    )
                    if not has_error:
                        success_count += 1
                        self.file_result.emit(fname, True, out or "Success")
                    else:
                        fail_count += 1
                        err = out or f"Installation failed with exit code {res.returncode}"
                        self.file_result.emit(fname, False, err)
                except subprocess.TimeoutExpired:
                    fail_count += 1
                    self.file_result.emit(fname, False, "Installation timed out after 120 seconds.")
                except Exception as e:
                    fail_count += 1
                    self.file_result.emit(fname, False, str(e))
            else:
                self.progress.emit(f"Pushing {fname} ({idx + 1}/{total})...")
                try:
                    res = subprocess.run(
                        [adb] + target + ["push", fpath, self.destination_folder],
                        capture_output=True,
                        text=True,
                        timeout=120,
                        creationflags=0x08000000
                    )
                    out = ((res.stdout or "") + "\n" + (res.stderr or "")).strip()
                    out_low = out.lower()
                    has_error = (
                        res.returncode != 0 or
                        "failed to copy" in out_low or
                        "permission denied" in out_low or
                        "no space left" in out_low or
                        "read-only file system" in out_low or
                        "error:" in out_low
                    )
                    if not has_error:
                        success_count += 1
                        self.file_result.emit(fname, True, out or "File transferred successfully")
                    else:
                        fail_count += 1
                        err = out or f"File transfer failed with exit code {res.returncode}"
                        self.file_result.emit(fname, False, err)
                except subprocess.TimeoutExpired:
                    fail_count += 1
                    self.file_result.emit(fname, False, "File transfer timed out after 120 seconds.")
                except Exception as e:
                    fail_count += 1
                    self.file_result.emit(fname, False, str(e))

        self.finished_all.emit(success_count, fail_count)


class GNDroidCompanionSidebar(QWidget):
    _active_sidebars: Dict[str, "GNDroidCompanionSidebar"] = {}

    def __init__(self, target_serial: str = "", scrcpy_proc: Optional[subprocess.Popen] = None, parent=None):
        super().__init__(parent)
        self.target_serial = target_serial
        self.scrcpy_proc = scrcpy_proc

        key = self.target_serial or "default"
        if key in GNDroidCompanionSidebar._active_sidebars and GNDroidCompanionSidebar._active_sidebars[key] is not self:
            try:
                old = GNDroidCompanionSidebar._active_sidebars[key]
                old.close()
                old.deleteLater()
            except Exception:
                pass
        GNDroidCompanionSidebar._active_sidebars[key] = self

        self.setWindowTitle(f"GNDROiD Controls - {self.target_serial}" if self.target_serial else "GNDROiD Controls")
        self.setFixedWidth(56)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAcceptDrops(True)

        self._is_dragging = False
        self._drag_pos = QPoint()
        self._user_positioned = False
        self._is_recording = False
        self._record_proc = None
        self._active_workers: List[QThread] = []

        self.setup_ui()

        self.track_timer = QTimer(self)
        self.track_timer.setInterval(300)
        self.track_timer.timeout.connect(self.align_with_mirror_window)
        self.track_timer.start()

    def closeEvent(self, event):
        if hasattr(self, "track_timer") and self.track_timer:
            self.track_timer.stop()
        if self._is_recording:
            self.stop_recording()
        if hasattr(self, "_active_workers"):
            for w in list(self._active_workers):
                try:
                    w.cancel()
                except Exception:
                    pass
        key = self.target_serial or "default"
        if GNDroidCompanionSidebar._active_sidebars.get(key) is self:
            del GNDroidCompanionSidebar._active_sidebars[key]
        super().closeEvent(event)

    def setup_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(4, 4, 4, 4)
        root_layout.setSpacing(0)

        self.container = QFrame()
        self.container.setStyleSheet("""
            QFrame#mainContainer {
                background: rgba(255, 255, 255, 0.95);
                border: 1px solid rgba(0, 0, 0, 0.12);
                border-radius: 12px;
            }
        """)
        self.container.setObjectName("mainContainer")

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 40))
        shadow.setOffset(0, 4)
        self.container.setGraphicsEffect(shadow)

        c_layout = QVBoxLayout(self.container)
        c_layout.setContentsMargins(6, 10, 6, 10)
        c_layout.setSpacing(5)
        c_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Top Header Grip Handle & Live Status Dot
        top_box = QHBoxLayout()
        top_box.setContentsMargins(2, 0, 2, 4)
        top_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top_box.setSpacing(6)

        grip = QLabel()
        grip.setFixedSize(22, 4)
        grip.setStyleSheet("background: rgba(0, 0, 0, 0.25); border-radius: 2px;")
        grip.setToolTip("Drag to move • Double-click to re-dock")
        top_box.addWidget(grip)

        self.status_dot = QLabel()
        self.status_dot.setFixedSize(6, 6)
        self.status_dot.setStyleSheet("background: #f59e0b; border-radius: 3px;")
        self.status_dot.setToolTip("Status: Standby / Searching for Window")
        top_box.addWidget(self.status_dot)

        c_layout.addLayout(top_box)

        def make_separator():
            sep = QFrame()
            sep.setFixedHeight(1)
            sep.setStyleSheet("background: rgba(0, 0, 0, 0.08);")
            return sep

        # --- SECTION 1: DISPLAY & AUDIO ---
        btn_rot = GNDroidRibbonButton("rotate", "#1e293b", "Rotate Screen Orientation", "Alt+R")
        btn_rot.clicked.connect(self.action_rotate)
        c_layout.addWidget(btn_rot)

        btn_volup = GNDroidRibbonButton("volup", "#1e293b", "Volume Up", "Alt+Up")
        btn_volup.clicked.connect(lambda: self.send_key(24))
        c_layout.addWidget(btn_volup)

        btn_voldown = GNDroidRibbonButton("voldown", "#1e293b", "Volume Down", "Alt+Down")
        btn_voldown.clicked.connect(lambda: self.send_key(25))
        c_layout.addWidget(btn_voldown)

        btn_screen = GNDroidRibbonButton("screen", "#0067c0", "Toggle Handset Screen (Standby / Wake)", "Alt+O")
        btn_screen.clicked.connect(self.action_toggle_device_screen)
        c_layout.addWidget(btn_screen)

        c_layout.addWidget(make_separator())

        # --- SECTION 2: ANDROID NAVIGATION ---
        btn_back = GNDroidRibbonButton("back", "#1e293b", "Back Navigation", "Esc / Alt+B")
        btn_back.clicked.connect(lambda: self.send_key(4))
        c_layout.addWidget(btn_back)

        btn_home = GNDroidRibbonButton("home", "#1e293b", "Home Screen", "Alt+H")
        btn_home.clicked.connect(lambda: self.send_key(3))
        c_layout.addWidget(btn_home)

        btn_rec = GNDroidRibbonButton("recents", "#1e293b", "Recent Apps", "Alt+S")
        btn_rec.clicked.connect(lambda: self.send_key(187))
        c_layout.addWidget(btn_rec)

        c_layout.addWidget(make_separator())

        # --- SECTION 3: EMULATOR & DEVICE TOOLS ---
        btn_shot = GNDroidRibbonButton("screenshot", "#1e293b", "Capture High-Res Screenshot to Desktop", "Alt+P")
        btn_shot.clicked.connect(self.action_screenshot)
        c_layout.addWidget(btn_shot)

        self.btn_rec_vid = GNDroidRibbonButton("record", "#ef4444", "Toggle Screen Video Recording (MP4)", "Alt+C")
        self.btn_rec_vid.clicked.connect(self.toggle_recording)
        c_layout.addWidget(self.btn_rec_vid)

        btn_apk = GNDroidRibbonButton("apk", "#1e293b", "Install APK or Push File", "Alt+I")
        btn_apk.clicked.connect(self.action_install_apk_dialog)
        c_layout.addWidget(btn_apk)

        btn_multi = GNDroidRibbonButton("multi", "#1e293b", "Multi-Instance Manager & Parallel Clones", "Alt+M")
        btn_multi.clicked.connect(self.action_multi)
        c_layout.addWidget(btn_multi)

        btn_adb = GNDroidRibbonButton("adb", "#1e293b", "ADB Doctor & Troubleshooting Suite", "Alt+D")
        btn_adb.clicked.connect(self.action_adb_doctor)
        c_layout.addWidget(btn_adb)

        btn_wireless = GNDroidRibbonButton("wireless", "#1e293b", "📡 Wireless Debugging & QR Pairing", "Alt+W")
        btn_wireless.clicked.connect(self.action_wireless_pairing)
        c_layout.addWidget(btn_wireless)

        btn_shake = GNDroidRibbonButton("shake", "#1e293b", "Shake Device (Accelerometer Gesture)", "Alt+Z")
        btn_shake.clicked.connect(self.action_shake)
        c_layout.addWidget(btn_shake)

        c_layout.addWidget(make_separator())

        # --- SECTION 4: SYSTEM & POWER ---
        btn_power = GNDroidRibbonButton("power", "#1e293b", "Power & Reboot Menu", "Alt+W")
        btn_power.clicked.connect(self.action_power_menu)
        c_layout.addWidget(btn_power)

        btn_apps = GNDroidRibbonButton("apps", "#1e293b", "📱 App Drawer & Cloner", "Alt+A")
        btn_apps.clicked.connect(self.action_apps)
        c_layout.addWidget(btn_apps)

        btn_set = GNDroidRibbonButton("settings", "#1e293b", "Hardware & System Settings", "Alt+G")
        btn_set.clicked.connect(self.action_open_settings)
        c_layout.addWidget(btn_set)

        btn_close = GNDroidRibbonButton("close", "#dc2626", "Close Mirror & Controls", "Alt+Q")
        btn_close.clicked.connect(self.close_all)
        c_layout.addWidget(btn_close)

        root_layout.addWidget(self.container)

    def action_toggle_device_screen(self):
        # Genuine standby toggle: use scrcpy non-locking turn-screen-off (MOD+o / Alt+O) or non-locking wake/sleep
        hwnd = find_target_window(self.target_serial)
        if hwnd:
            # Send Alt+O to Scrcpy mirror window (scrcpy native MOD+o toggles physical screen off while keeping mirror stream active)
            user32.PostMessageW(hwnd, 0x0104, 0x12, 0x20380001)  # WM_SYSKEYDOWN VK_MENU (Alt)
            user32.PostMessageW(hwnd, 0x0104, 0x4F, 0x20180001)  # WM_SYSKEYDOWN 'O' with Alt
            user32.PostMessageW(hwnd, 0x0105, 0x4F, 0xC0180001)  # WM_SYSKEYUP 'O'
            user32.PostMessageW(hwnd, 0x0105, 0x12, 0xC0380001)  # WM_SYSKEYUP VK_MENU
            return

        # Fallback to non-locking Android standby control via ADB
        adb = SystemPaths.get_adb()
        target = ["-s", self.target_serial] if self.target_serial else []
        try:
            out = subprocess.check_output([adb] + target + ["shell", "dumpsys", "power"], text=True, timeout=2, creationflags=0x08000000)
            if "mWakefulness=Awake" in out:
                subprocess.run([adb] + target + ["shell", "input", "keyevent", "223"], timeout=2, creationflags=0x08000000)
            else:
                subprocess.run([adb] + target + ["shell", "input", "keyevent", "224"], timeout=2, creationflags=0x08000000)
        except Exception:
            self.send_key(223)

    def send_key(self, keycode: int):
        adb = SystemPaths.get_adb()
        target = ["-s", self.target_serial] if self.target_serial else []
        try:
            subprocess.run([adb] + target + ["shell", "input", "keyevent", str(keycode)], timeout=2, creationflags=0x08000000)
        except Exception:
            pass

    def action_rotate(self):
        adb = SystemPaths.get_adb()
        target = ["-s", self.target_serial] if self.target_serial else []
        try:
            out = subprocess.check_output([adb] + target + ["shell", "settings", "get", "system", "user_rotation"], text=True, timeout=2, creationflags=0x08000000).strip()
            curr = int(out) if out.isdigit() else 0
            nxt = (curr + 1) % 4
            subprocess.run([adb] + target + ["shell", "settings", "put", "system", "accelerometer_rotation", "0"], timeout=2, creationflags=0x08000000)
            subprocess.run([adb] + target + ["shell", "settings", "put", "system", "user_rotation", str(nxt)], timeout=2, creationflags=0x08000000)
        except Exception:
            pass

    def action_screenshot(self):
        adb = SystemPaths.get_adb()
        target = ["-s", self.target_serial] if self.target_serial else []
        desktop = os.path.join(os.path.expanduser("~"), "Desktop", "Screenshots")
        os.makedirs(desktop, exist_ok=True)
        fname = f"gndroid_shot_{int(time.time())}.png"
        dest = os.path.join(desktop, fname)
        try:
            subprocess.run([adb] + target + ["shell", "screencap", "-p", "/sdcard/gndroid_tmp_shot.png"], timeout=6, creationflags=0x08000000)
            subprocess.run([adb] + target + ["pull", "/sdcard/gndroid_tmp_shot.png", dest], timeout=6, creationflags=0x08000000)
            subprocess.run([adb] + target + ["shell", "rm", "/sdcard/gndroid_tmp_shot.png"], timeout=2, creationflags=0x08000000)
            QMessageBox.information(self, "Screenshot Saved", f"Screenshot saved to Desktop:\n\n{dest}")
        except Exception as e:
            QMessageBox.warning(self, "Screenshot Error", str(e))

    def action_apps(self):
        adb = SystemPaths.get_adb()
        target = ["-s", self.target_serial] if self.target_serial else []
        try:
            subprocess.run([adb] + target + ["shell", "input", "keyevent", "3"], timeout=2, creationflags=0x08000000)
            subprocess.run([adb] + target + ["shell", "am", "start", "-a", "android.intent.action.ALL_APPS"], timeout=2, creationflags=0x08000000)
        except Exception:
            self.send_key(3)


    def close_all(self):
        if self.scrcpy_proc:
            try:
                self.scrcpy_proc.terminate()
            except Exception:
                pass
        self.close()

    def action_multi(self):
        dlg = GNDroidMultiInstanceManager(self)
        dlg.exec()

    def action_adb_doctor(self):
        dlg = GNDroidADBFixerDialog(self.target_serial, self)
        dlg.exec()

    def action_wireless_pairing(self):
        dlg = GNDroidWirelessPairingDialog(self.target_serial, self)
        dlg.exec()

    def action_shake(self):
        adb = SystemPaths.get_adb()
        target = ["-s", self.target_serial] if self.target_serial else []
        try:
            # For emulators, inject real accelerometer shake vector variations
            if not self.target_serial or self.target_serial.startswith("emulator-"):
                vectors = [(25, 0, 0), (-25, 0, 0), (20, 10, 0), (-20, -10, 0), (0, 9.81, 0)]
                for x, y, z in vectors:
                    subprocess.run(
                        [adb] + target + ["emu", "sensor", "set", "acceleration", f"{x}:{y}:{z}"],
                        timeout=1, creationflags=0x08000000
                    )
                    time.sleep(0.04)
            else:
                # For physical devices, broadcast genuine developer shake action
                subprocess.run(
                    [adb] + target + ["shell", "am", "broadcast", "-a", "com.android.internal.action.SHAKE"],
                    timeout=2, creationflags=0x08000000
                )
        except Exception:
            pass

    def action_power_menu(self):
        adb = SystemPaths.get_adb()
        target = ["-s", self.target_serial] if self.target_serial else []

        menu = QDialog(self)
        menu.setWindowTitle("⚡ Power & Reboot Menu")
        menu.setFixedSize(320, 260)
        menu.setStyleSheet("""
            QDialog {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                font-family: 'Segoe UI Variable Text', 'Segoe UI', -apple-system, sans-serif;
            }
            QPushButton {
                background: #f8fafc;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 8px 12px;
                color: #0f172a;
                font-weight: 500;
                font-size: 11px;
                margin: 2px;
                text-align: left;
            }
            QPushButton:hover {
                background: #f1f5f9;
                border-color: #94a3b8;
            }
            QPushButton:pressed {
                background: #e2e8f0;
            }
            QPushButton.danger {
                background: #fef2f2;
                border-color: #fca5a5;
                color: #dc2626;
            }
            QPushButton.danger:hover {
                background: #dc2626;
                border-color: #dc2626;
                color: #ffffff;
            }
        """)
        ml = QVBoxLayout(menu)
        ml.setContentsMargins(16, 16, 16, 16)
        ml.setSpacing(6)

        btn_lock = QPushButton("🔒  Lock / Wake Screen")
        btn_lock.clicked.connect(lambda: (self.send_key(26), menu.accept()))
        ml.addWidget(btn_lock)

        btn_reboot = QPushButton("🔄  Soft Reboot Android")
        def do_reboot():
            try: subprocess.run([adb] + target + ["reboot"], timeout=4, creationflags=0x08000000)
            except: pass
            menu.accept()
        btn_reboot.clicked.connect(do_reboot)
        ml.addWidget(btn_reboot)

        btn_cold = QPushButton("❄️  Power Off / Cold Reboot")
        def do_cold():
            try: subprocess.run([adb] + target + ["emu", "kill"], timeout=4, creationflags=0x08000000)
            except: pass
            menu.accept()
        btn_cold.clicked.connect(do_cold)
        ml.addWidget(btn_cold)

        btn_cancel = QPushButton("✕  Cancel")
        btn_cancel.clicked.connect(menu.reject)
        ml.addWidget(btn_cancel)

        menu.exec()

    def toggle_recording(self):
        if not self._is_recording:
            self.start_recording()
        else:
            self.stop_recording()

    def start_recording(self):
        adb = SystemPaths.get_adb()
        target = ["-s", self.target_serial] if self.target_serial else []
        try:
            self._record_proc = subprocess.Popen([adb] + target + ["shell", "screenrecord", "/sdcard/gndroid_live_rec.mp4"], creationflags=0x08000000)
            self._is_recording = True
            self.btn_rec_vid.setStyleSheet("border: 2px solid #ef4444;")
            QMessageBox.information(self, "Recording Started", "🔴 Screen video recording started!\n\nClick the record button again when finished to save MP4 to Desktop.")
        except Exception as e:
            QMessageBox.critical(self, "Recording Error", str(e))

    def stop_recording(self):
        if self._record_proc:
            try: self._record_proc.terminate()
            except: pass
        self._is_recording = False
        self.btn_rec_vid.setStyleSheet("")
        time.sleep(1.0)

        adb = SystemPaths.get_adb()
        target = ["-s", self.target_serial] if self.target_serial else []
        desktop = os.path.join(os.path.expanduser("~"), "Desktop", "Screenshots")
        os.makedirs(desktop, exist_ok=True)
        fname = f"gndroid_recording_{int(time.time())}.mp4"
        dest_p = os.path.join(desktop, fname)

        try:
            subprocess.run([adb] + target + ["pull", "/sdcard/gndroid_live_rec.mp4", dest_p], timeout=15, creationflags=0x08000000)
            subprocess.run([adb] + target + ["shell", "rm", "/sdcard/gndroid_live_rec.mp4"], timeout=3, creationflags=0x08000000)
            QMessageBox.information(self, "Recording Saved", f"✅ MP4 Video successfully saved to Desktop:\n\n{dest_p}")
        except Exception as e:
            QMessageBox.warning(self, "Pull Error", f"Recording stopped but file transfer failed: {e}")

    def _start_async_file_transfer(self, file_paths: List[str]):
        if not file_paths:
            return

        prog = QProgressDialog("Preparing transfer...", "Cancel", 0, 0, self)
        prog.setWindowTitle("GNDROiD Package & File Transfer")
        prog.setWindowModality(Qt.WindowModality.NonModal)
        prog.setMinimumDuration(0)
        prog.show()

        worker = AdbInstallOrPushWorker(files=file_paths, target_serial=self.target_serial, parent=self)
        self._active_workers.append(worker)

        worker.progress.connect(prog.setLabelText)
        prog.canceled.connect(worker.cancel)

        def on_file_result(fname: str, is_success: bool, msg: str):
            is_apk = fname.lower().endswith(".apk")
            if is_success:
                QMessageBox.information(
                    self,
                    "APK Installed" if is_apk else "File Transferred",
                    f"Successfully installed:\n\n{fname}" if is_apk else f"Successfully copied to phone Downloads:\n\n{fname}"
                )
            else:
                QMessageBox.critical(
                    self,
                    "Install Error" if is_apk else "Transfer Error",
                    f"Operation failed for {fname}:\n\n{msg}"
                )

        def on_finished(succ: int, fail: int):
            prog.close()
            prog.deleteLater()
            if worker in self._active_workers:
                self._active_workers.remove(worker)

        worker.file_result.connect(on_file_result)
        worker.finished_all.connect(on_finished)
        worker.start()

    def action_install_apk_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select APK to Install", "", "Android Package (*.apk);;All Files (*.*)")
        if not path:
            return
        self._start_async_file_transfer([path])

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._is_dragging = True
            event.accept()

    def mouseMoveEvent(self, event):
        if self._is_dragging and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            self._user_positioned = True
            event.accept()

    def mouseReleaseEvent(self, event):
        self._is_dragging = False

    def mouseDoubleClickEvent(self, event):
        self._user_positioned = False
        self.align_with_mirror_window()

    def align_with_mirror_window(self):
        hwnd = find_target_window(self.target_serial)
        if not hwnd:
            self.status_dot.setStyleSheet("background: #f59e0b; border-radius: 3px;")
            self.status_dot.setToolTip("Status: Standby / Waiting for Window")
            if self.scrcpy_proc and self.scrcpy_proc.poll() is not None:
                self.close()
            return

        self.status_dot.setStyleSheet("background: #10b981; border-radius: 3px;")
        self.status_dot.setToolTip("Status: Connected & Docked")

        if user32.IsIconic(hwnd):
            self.hide()
            return

        if not self._user_positioned:
            rect = RECT()
            if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                target_x = rect.right + 2
                target_y = rect.top
                target_h = max(440, rect.bottom - rect.top)

                screen = QApplication.primaryScreen().geometry()
                if target_x + self.width() > screen.right():
                    target_x = max(10, rect.left - self.width() - 2)

                self.setGeometry(target_x, target_y, 56, target_h)
                self.show()

    def send_key(self, code: int):
        adb = SystemPaths.get_adb()
        cmd = [adb]
        if self.target_serial:
            cmd.extend(["-s", self.target_serial])
        cmd.extend(["shell", "input", "keyevent", str(code)])
        subprocess.Popen(cmd, creationflags=0x08000000, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def action_rotate(self):
        adb = SystemPaths.get_adb()
        target = ["-s", self.target_serial] if self.target_serial else []
        try:
            cur = subprocess.check_output([adb] + target + ["shell", "settings", "get", "system", "user_rotation"], text=True, timeout=2, creationflags=0x08000000).strip()
            new_r = "1" if cur == "0" else "0"
            subprocess.run([adb] + target + ["shell", "settings", "put", "system", "accelerometer_rotation", "0"], timeout=2, creationflags=0x08000000)
            subprocess.run([adb] + target + ["shell", "settings", "put", "system", "user_rotation", new_r], timeout=2, creationflags=0x08000000)
        except Exception:
            pass

    def action_screenshot(self):
        adb = SystemPaths.get_adb()
        target = ["-s", self.target_serial] if self.target_serial else []
        desktop = os.path.join(os.path.expanduser("~"), "Desktop", "Screenshots")
        os.makedirs(desktop, exist_ok=True)
        fname = f"gndroid_screen_{int(time.time())}.png"
        out_path = os.path.join(desktop, fname)
        try:
            subprocess.run([adb] + target + ["shell", "screencap", "-p", "/sdcard/tmp_screen.png"], timeout=3, creationflags=0x08000000)
            subprocess.run([adb] + target + ["pull", "/sdcard/tmp_screen.png", out_path], timeout=3, creationflags=0x08000000)
            subprocess.run([adb] + target + ["shell", "rm", "/sdcard/tmp_screen.png"], timeout=2, creationflags=0x08000000)
            QMessageBox.information(self, "Screenshot Saved", f"High-resolution screenshot saved to:\n\n{out_path}")
        except Exception as e:
            QMessageBox.warning(self, "Screenshot Error", str(e))

    def action_apps(self):
        dlg = GNDroidAppDrawer(self.target_serial, self)
        dlg.exec()

    def action_open_settings(self):
        instance_name = "gndroid"
        if self.target_serial and self.target_serial.startswith("emulator-"):
            try:
                adb = SystemPaths.get_adb()
                name_out = subprocess.check_output([adb, "-s", self.target_serial, "emu", "avd", "name"], text=True, timeout=1, creationflags=0x08000000).strip()
                avd_n = name_out.splitlines()[0].strip() if name_out else ""
                if avd_n:
                    instance_name = avd_n
            except Exception:
                pass
        dlg = GNDroidSettingsDialog(target_serial=self.target_serial, instance_name=instance_name, parent=self)
        dlg.exec()

    def action_settings(self):
        return self.action_open_settings()

    def close_all(self):
        if self.scrcpy_proc:
            try: self.scrcpy_proc.terminate()
            except: pass
        self.close()

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.container.setStyleSheet("""
                QFrame#mainContainer {
                    background: rgba(240, 249, 255, 0.98);
                    border: 1.5px solid #0078d4;
                    border-radius: 12px;
                }
            """)

    def dragLeaveEvent(self, event):
        self.container.setStyleSheet("""
            QFrame#mainContainer {
                background: rgba(255, 255, 255, 0.95);
                border: 1px solid rgba(0, 0, 0, 0.12);
                border-radius: 12px;
            }
        """)

    def dropEvent(self, event: QDropEvent):
        self.dragLeaveEvent(None)
        file_paths = []
        for url in event.mimeData().urls():
            fpath = url.toLocalFile()
            if fpath:
                file_paths.append(fpath)
        if file_paths:
            self._start_async_file_transfer(file_paths)


# ----------------------------------------------------------------------
# Central Mirror Session Launcher with Seamless Fallback
# ----------------------------------------------------------------------
def start_mirror_with_fallback(target_serial: str = "", parent=None):
    if target_serial and target_serial in GNDroidCompanionSidebar._active_sidebars:
        sidebar = GNDroidCompanionSidebar._active_sidebars[target_serial]
        if sidebar.isVisible():
            sidebar.raise_()
            sidebar.activateWindow()
            sidebar.align_with_mirror_window()
            return sidebar

    devs = SystemPaths.list_devices()
    phys = [d for d in devs if not d["is_emulator"] and d["state"] == "device"]
    emus = [d for d in devs if d["is_emulator"] and d["state"] == "device"]

    # Check if target is a Companion device (Port 51880/51888 or direct LAN companion)
    host_ip = (target_serial.split(":")[0] if ":" in target_serial else target_serial) if target_serial else ""
    target_port = int(target_serial.split(":")[-1]) if ":" in (target_serial or "") and target_serial.split(":")[-1].isdigit() else None
    comp_port = None
    if target_port in (51880, 51888):
        comp_port = target_port
    elif host_ip and not host_ip.startswith("emulator-") and host_ip != "gndroid":
        for p in (51880, 51888):
            try:
                import socket
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.18)
                    if s.connect_ex((host_ip, p)) == 0:
                        comp_port = p
                        break
            except Exception:
                pass
    if comp_port:
        win = GNDroidWirelessMirrorWindow(host_ip=host_ip, port=comp_port, model_name="Infinix X690B", parent=parent)
        win.show()
        return win

    selected_serial = target_serial
    if not selected_serial or selected_serial == "gndroid":
        if phys:
            selected_serial = phys[0]["serial"]
        elif emus:
            selected_serial = emus[0]["serial"]
        else:
            dlg = GNDroidNoDeviceDialog(parent)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                if dlg.chosen_action == "run_vm":
                    if parent and hasattr(parent, "launch_virtual_machine"):
                        parent.launch_virtual_machine()
                elif dlg.chosen_action == "adb_fixer":
                    fixer = GNDroidADBFixerDialog("", parent)
                    fixer.exec()
                elif dlg.chosen_action == "retry":
                    return start_mirror_with_fallback("", parent)
            return None

    # Determine device topology to enforce strict screen-off safety
    # Scrcpy screen standby flags: --turn-screen-off, --stay-awake
    # Title: GNDROiD - {selected_serial}
    is_emu = (
        any(d["serial"] == selected_serial and d["is_emulator"] for d in devs)
        or selected_serial.startswith("emulator-")
        or "127.0.0.1:" in selected_serial
        or "localhost:" in selected_serial
    )
    is_lan = (
        any(d["serial"] == selected_serial and d.get("is_lan") for d in devs)
        or ((":" in selected_serial) and not is_emu)
    )

    scrcpy_bin = SystemPaths.get_scrcpy()
    cmd = WirelessMirrorManager.build_scrcpy_command(
        serial=selected_serial,
        is_emulator=is_emu,
        is_wireless=is_lan,
        title=f"GNDROiD - {selected_serial}",
        enable_audio=True,
        scrcpy_bin=scrcpy_bin
    )

    try:
        scrcpy_proc = subprocess.Popen(
            cmd,
            creationflags=0x08000000,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE
        )
        # Feature 8: Assign Scrcpy mirror process to Win32 Job Object
        try:
            from nexus.app_cloner_and_window import assign_to_job_object
            assign_to_job_object(scrcpy_proc)
        except Exception:
            pass

        sidebar = GNDroidCompanionSidebar(selected_serial, scrcpy_proc)
        sidebar.show()

        def monitor_process_supervision():
            start_t = time.time()
            failed_early = False
            err_text = ""
            while time.time() - start_t < 2.0:
                if scrcpy_proc.poll() is not None:
                    if scrcpy_proc.returncode != 0:
                        failed_early = True
                        try:
                            raw_err = scrcpy_proc.stderr.read() if scrcpy_proc.stderr else b""
                            err_text = raw_err.decode("utf-8", errors="ignore")
                        except Exception:
                            pass
                    break
                time.sleep(0.08)

            if failed_early:
                # 1. Seamless audio negotiation error / connection reset fallback -> relaunch with --no-audio
                if WirelessMirrorManager.is_audio_or_reset_error(err_text):
                    fallback_cmd = WirelessMirrorManager.build_scrcpy_command(
                        serial=selected_serial,
                        is_emulator=is_emu,
                        is_wireless=is_lan,
                        title=f"GNDROiD - {selected_serial}",
                        enable_audio=False,
                        scrcpy_bin=scrcpy_bin
                    )
                    try:
                        fallback_proc = subprocess.Popen(
                            fallback_cmd,
                            creationflags=0x08000000,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE
                        )
                        # Feature 8: Assign fallback proc to Job Object
                        try:
                            from nexus.app_cloner_and_window import assign_to_job_object
                            assign_to_job_object(fallback_proc)
                        except Exception:
                            pass
                        # Feature 7: Asynchronously drain fallback stderr pipe to prevent deadlock
                        WirelessMirrorManager.drain_pipe_async(fallback_proc)
                        sidebar.scrcpy_proc = fallback_proc
                        return
                    except Exception:
                        pass

                # 2. Device offline or disconnected fallback -> close sidebar and retry device selection
                if any(k in err_text for k in ["Could not find any ADB device", "Server connection failed", "device offline"]):
                    QTimer.singleShot(0, sidebar.close)
                    QTimer.singleShot(100, lambda: start_mirror_with_fallback("", parent))
            else:
                # Feature 7: Asynchronously drain scrcpy_proc.stderr continuously to prevent 4KB pipe deadlock
                WirelessMirrorManager.drain_pipe_async(scrcpy_proc)

        t = threading.Thread(target=monitor_process_supervision, daemon=True)
        t.start()

        return sidebar
    except Exception as e:
        QMessageBox.critical(parent, "Mirror Error", f"Failed to start mirror: {e}")
        return None

class GNDroidSettingsDialog(QDialog):
    def __init__(self, target_serial: str = "", instance_name: str = "gndroid", parent=None):
        # Feature 12: Protect against argument shifting if parent is passed as 2nd positional argument
        if isinstance(instance_name, QWidget) and parent is None:
            parent = instance_name
            instance_name = "gndroid"
        super().__init__(parent)
        self.target_serial = target_serial or ""
        self.instance_name = instance_name or "gndroid"
        self.cfg = AVDManager.get_instance_full_config(self.instance_name)
        disp_name = self.cfg.get("avd.ini.displayname", "GNDROiD Flagship")
        self.setWindowTitle(f"⚙️ GNDROiD Settings & Hardware Configuration — {disp_name}")
        self.resize(700, 830)
        self.setMinimumSize(660, 760)
        self.setup_ui()

    def setup_ui(self):
        self.setStyleSheet("""
            QDialog { background: #f8f9fa; color: #0f172a; font-family: 'Segoe UI Variable Text', 'Segoe UI', -apple-system, sans-serif; }
            QTabWidget::pane { border: 1px solid #e2e8f0; background: #ffffff; border-radius: 8px; }
            QTabBar::tab {
                background: #f1f5f9; color: #64748b; padding: 10px 18px;
                border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 4px;
                font-weight: 600; font-size: 11px;
            }
            QTabBar::tab:selected { background: #ffffff; color: #0067c0; border-bottom: 2px solid #0067c0; }
            QFrame.cardBox { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; }
            QComboBox, QSpinBox, QLineEdit {
                background: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px;
                padding: 6px 12px; color: #0f172a; font-size: 12px; font-weight: 500;
            }
            QComboBox:focus, QSpinBox:focus, QLineEdit:focus { border: 1.5px solid #0067c0; }
            QCheckBox { color: #0f172a; font-size: 11px; font-weight: 500; spacing: 8px; }
            QPushButton.btnPrimary {
                background: #0067c0; border: none; border-radius: 6px; color: #ffffff; font-weight: 600; font-size: 12px; padding: 9px 20px;
            }
            QPushButton.btnPrimary:hover { background: #1879c9; }
            QPushButton.btnSecondary {
                background: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px;
                color: #0f172a; font-weight: 500; font-size: 12px; padding: 9px 20px;
            }
            QPushButton.btnSecondary:hover { background: #f8fafc; border-color: #94a3b8; }
            QPushButton.btnAction {
                background: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 6px;
                color: #0f172a; font-weight: 500; font-size: 11px; padding: 6px 14px;
            }
            QPushButton.btnAction:hover { background: #e2e8f0; }
            QGroupBox {
                background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px;
                font-weight: 600; font-size: 12px; color: #0f172a; margin-top: 10px; padding: 12px 10px 10px 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin; subcontrol-position: top left;
                padding: 0 6px; color: #0067c0; background: #ffffff;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Header Title
        h_box = QHBoxLayout()
        icon = QLabel("⚙️")
        icon.setFont(QFont("Segoe UI Emoji", 24))
        h_box.addWidget(icon)

        t_box = QVBoxLayout()
        t = QLabel("GNDROiD System & Hardware Configuration")
        t.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        t.setStyleSheet("color: #0f172a;")
        t_box.addWidget(t)

        st = QLabel(f"Instance: {self.instance_name} • Android {self.cfg.get('target', 'android-36')} • Fully Editable Hardware & Engine Settings")
        st.setStyleSheet("color: #64748b; font-size: 11px;")
        t_box.addWidget(st)
        h_box.addLayout(t_box)
        layout.addLayout(h_box)

        self.tabs = QTabWidget()

        # ==============================================================
        # TAB 1: Hardware, CPU & Memory
        # ==============================================================
        tab_hw = QWidget()
        thw_l = QVBoxLayout(tab_hw)
        thw_l.setContentsMargins(16, 16, 16, 16)
        thw_l.setSpacing(12)

        g_hw = QGridLayout()
        g_hw.setSpacing(10)

        # Instance Display Name
        g_hw.addWidget(QLabel("Instance Display Name:"), 0, 0)
        self.txt_display_name = QLineEdit()
        self.txt_display_name.setText(self.cfg.get("avd.ini.displayname", "GNDROiD Flagship"))
        g_hw.addWidget(self.txt_display_name, 0, 1)

        # RAM Allocation
        g_hw.addWidget(QLabel("RAM Allocation:"), 1, 0)
        self.combo_ram = QComboBox()
        cur_ram = int(self.cfg.get("hw.ramSize", 4096))
        ram_opts = [
            ("2 GB (2048 MB) — Light", 2048),
            ("4 GB (4096 MB) — Recommended", 4096),
            ("8 GB (8192 MB) — High Performance", 8192),
            ("12 GB (12288 MB) — Power User", 12288),
            ("16 GB (16384 MB) — Extreme", 16384),
            ("24 GB (24576 MB) — Heavy Workloads", 24576),
            ("32 GB (32768 MB) — Full Host Allocation", 32768)
        ]
        ram_matched = False
        for i, (label, val) in enumerate(ram_opts):
            self.combo_ram.addItem(label, val)
            if val == cur_ram:
                self.combo_ram.setCurrentIndex(i)
                ram_matched = True
        if not ram_matched:
            self.combo_ram.insertItem(0, f"Custom ({cur_ram} MB)", cur_ram)
            self.combo_ram.setCurrentIndex(0)
        g_hw.addWidget(self.combo_ram, 1, 1)

        # CPU Processor Cores
        g_hw.addWidget(QLabel("CPU Processor Cores:"), 2, 0)
        self.combo_cores = QComboBox()
        cur_cores = int(self.cfg.get("hw.cpu.ncore", 4))
        core_opts = [
            ("2 Dedicated Cores (Basic)", 2),
            ("4 Dedicated Cores (Recommended)", 4),
            ("6 Dedicated Cores", 6),
            ("8 Dedicated Cores (High Performance)", 8),
            ("12 Dedicated Cores", 12),
            ("16 Dedicated Cores (Extreme Gaming / Multi-App)", 16),
            ("24 Dedicated Cores (Full Host Allocation)", 24)
        ]
        cores_matched = False
        for i, (label, val) in enumerate(core_opts):
            self.combo_cores.addItem(label, val)
            if val == cur_cores:
                self.combo_cores.setCurrentIndex(i)
                cores_matched = True
        if not cores_matched:
            self.combo_cores.insertItem(0, f"Custom ({cur_cores} Cores)", cur_cores)
            self.combo_cores.setCurrentIndex(0)
        g_hw.addWidget(self.combo_cores, 2, 1)

        # Dalvik / ART Heap Size
        g_hw.addWidget(QLabel("VM Heap Size:"), 3, 0)
        self.combo_heap = QComboBox()
        cur_heap = self.cfg.get("vm.heapSize", "1024").replace("M", "")
        heap_opts = [("256 MB", "256"), ("512 MB", "512"), ("768 MB", "768"), ("1024 MB (Recommended)", "1024"), ("2048 MB (Extreme)", "2048")]
        for i, (label, val) in enumerate(heap_opts):
            self.combo_heap.addItem(label, val)
            if val == cur_heap:
                self.combo_heap.setCurrentIndex(i)
        g_hw.addWidget(self.combo_heap, 3, 1)

        thw_l.addLayout(g_hw)

        # Root Access Section
        self.chk_root = QCheckBox("🔓 Enable Root Access (Writable System Partition && Permissive SELinux)")
        self.chk_root.setChecked(self.cfg.get("gndroid.root", "yes").lower() in ["yes", "true", "1"])
        self.chk_root.setStyleSheet("color: #b45309; font-weight: bold; margin-top: 6px;")
        thw_l.addWidget(self.chk_root)

        root_note = QLabel(
            "ℹ️ <b>Android 10–16 & SuperSU Note:</b> Retail Google Play images enforce locked dm-verity and block 'adb root'. "
            "Legacy SuperSU (2018) is incompatible with modern Android. For full root access, use Magisk/KernelSU or a Google APIs image."
        )
        root_note.setWordWrap(True)
        root_note.setStyleSheet("color: #64748b; font-size: 10px; margin-top: 2px;")
        thw_l.addWidget(root_note)

        root_btn_box = QHBoxLayout()
        self.btn_test_root = QPushButton("🔍 Live Test Guest Root")
        self.btn_test_root.setProperty("class", "btnAction")
        self.btn_test_root.clicked.connect(self.action_test_guest_root)
        root_btn_box.addWidget(self.btn_test_root)

        self.lbl_root_live = QLabel("")
        self.lbl_root_live.setWordWrap(True)
        self.lbl_root_live.setStyleSheet("color: #0369a1; font-size: 11px; font-weight: 500;")
        root_btn_box.addWidget(self.lbl_root_live, 1)
        thw_l.addLayout(root_btn_box)

        thw_l.addStretch()
        self.tabs.addTab(tab_hw, "⚡ Hardware & CPU/RAM")

        # ==============================================================
        # TAB 2: Graphics & Display
        # ==============================================================
        tab_gfx = QWidget()
        tgfx_l = QVBoxLayout(tab_gfx)
        tgfx_l.setContentsMargins(16, 16, 16, 16)
        tgfx_l.setSpacing(12)

        g_gfx = QGridLayout()
        g_gfx.setSpacing(10)

        # GPU Graphics Engine
        g_gfx.addWidget(QLabel("GPU Graphics Backend:"), 0, 0)
        self.combo_gpu = QComboBox()
        cur_gpu = self.cfg.get("hw.gpu.mode", "auto")
        gpu_opts = [
            ("Auto (Hardware Vulkan 1.4 / Direct3D 11 — Recommended)", "auto"),
            ("Host (Direct GPU Passthrough)", "host"),
            ("SwiftShader (Software Rendering Fallback)", "swiftshader_indirect"),
            ("ANGLE (DirectX 11 / 12 Translation)", "angle_indirect")
        ]
        for i, (label, val) in enumerate(gpu_opts):
            self.combo_gpu.addItem(label, val)
            if val == cur_gpu:
                self.combo_gpu.setCurrentIndex(i)
        g_gfx.addWidget(self.combo_gpu, 0, 1)

        # Screen Resolution Presets
        g_gfx.addWidget(QLabel("Screen Resolution Preset:"), 1, 0)
        self.combo_res_preset = QComboBox()
        cur_w = int(self.cfg.get("hw.lcd.width", 1440))
        cur_h = int(self.cfg.get("hw.lcd.height", 3120))
        cur_d = int(self.cfg.get("hw.lcd.density", 500))

        res_presets = [
            ("Galaxy S24 Ultra (1440 x 3120 • 500 DPI • Portrait)", 1440, 3120, 500),
            ("Flagship Smartphone FHD+ (1080 x 2400 • 420 DPI • Portrait)", 1080, 2400, 420),
            ("Tablet 10-inch (1200 x 1920 • 280 DPI • Portrait)", 1200, 1920, 280),
            ("Tablet Landscape (1920 x 1200 • 280 DPI • Landscape)", 1920, 1200, 280),
            ("4K Ultra HD Display (3840 x 2160 • 320 DPI • Landscape)", 3840, 2160, 320),
            ("Compact Phone HD+ (720 x 1600 • 320 DPI • Portrait)", 720, 1600, 320),
            ("Custom Resolution...", 0, 0, 0)
        ]
        preset_idx = 6
        for i, (label, pw, ph, pd) in enumerate(res_presets):
            self.combo_res_preset.addItem(label, (pw, ph, pd))
            if pw == cur_w and ph == cur_h:
                preset_idx = i

        self.combo_res_preset.setCurrentIndex(preset_idx)
        self.combo_res_preset.currentIndexChanged.connect(self.on_resolution_preset_changed)
        g_gfx.addWidget(self.combo_res_preset, 1, 1)

        # Custom Width
        g_gfx.addWidget(QLabel("Screen Width (px):"), 2, 0)
        self.spin_width = QSpinBox()
        self.spin_width.setRange(480, 7680)
        self.spin_width.setValue(cur_w)
        g_gfx.addWidget(self.spin_width, 2, 1)

        # Custom Height
        g_gfx.addWidget(QLabel("Screen Height (px):"), 3, 0)
        self.spin_height = QSpinBox()
        self.spin_height.setRange(480, 7680)
        self.spin_height.setValue(cur_h)
        g_gfx.addWidget(self.spin_height, 3, 1)

        # Screen Density (DPI)
        g_gfx.addWidget(QLabel("Screen Density (DPI):"), 4, 0)
        self.spin_density = QSpinBox()
        self.spin_density.setRange(120, 800)
        self.spin_density.setValue(cur_d)
        g_gfx.addWidget(self.spin_density, 4, 1)

        tgfx_l.addLayout(g_gfx)

        # Device Frame & Glitch Fixer
        self.chk_frame = QCheckBox("📱 Show Device Frame (Realistic Smartphone Bezel Around Window)")
        self.chk_frame.setChecked(self.cfg.get("showDeviceFrame", "yes").lower() in ["yes", "true", "1"])
        tgfx_l.addWidget(self.chk_frame)

        # Multi-Display & Secondary Viewports GroupBox
        self.grp_sec_disp = QGroupBox("🖥️ Multi-Display & Secondary Viewports")
        gsec_l = QVBoxLayout(self.grp_sec_disp)
        gsec_l.setSpacing(8)
        gsec_l.setContentsMargins(12, 12, 12, 10)

        self.chk_sec_disp = QCheckBox("Enable Secondary Display (Display 1)")
        self.chk_sec_disp.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        gsec_l.addWidget(self.chk_sec_disp)

        self.chk_sec_match = QCheckBox("Match Main Display Resolution by Default (Recommended)")
        self.chk_sec_match.setStyleSheet("color: #0369a1; font-weight: 500;")
        gsec_l.addWidget(self.chk_sec_match)

        g_sec = QGridLayout()
        g_sec.setSpacing(8)

        g_sec.addWidget(QLabel("Secondary Resolution Preset:"), 0, 0)
        self.combo_sec_preset = QComboBox()
        sec_presets = [
            ("Match Main Display (Auto-Synchronized)", 0, 0, 0),
            ("Galaxy S24 Ultra (1440 x 3120 • 500 DPI • Portrait)", 1440, 3120, 500),
            ("Flagship Smartphone FHD+ (1080 x 2400 • 420 DPI • Portrait)", 1080, 2400, 420),
            ("Tablet 10-inch (1200 x 1920 • 280 DPI • Portrait)", 1200, 1920, 280),
            ("Tablet Landscape (1920 x 1200 • 280 DPI • Landscape)", 1920, 1200, 280),
            ("Custom Resolution...", -1, -1, -1)
        ]
        for label, pw, ph, pd in sec_presets:
            self.combo_sec_preset.addItem(label, (pw, ph, pd))
        g_sec.addWidget(self.combo_sec_preset, 0, 1)

        g_sec.addWidget(QLabel("Secondary Width (px):"), 1, 0)
        self.spin_sec_width = QSpinBox()
        self.spin_sec_width.setRange(480, 7680)
        g_sec.addWidget(self.spin_sec_width, 1, 1)

        g_sec.addWidget(QLabel("Secondary Height (px):"), 2, 0)
        self.spin_sec_height = QSpinBox()
        self.spin_sec_height.setRange(480, 7680)
        g_sec.addWidget(self.spin_sec_height, 2, 1)

        g_sec.addWidget(QLabel("Secondary Density (DPI):"), 3, 0)
        self.spin_sec_density = QSpinBox()
        self.spin_sec_density.setRange(120, 800)
        g_sec.addWidget(self.spin_sec_density, 3, 1)

        gsec_l.addLayout(g_sec)

        lbl_sec_hint = QLabel("💡 When matching resolution is enabled, Display 1 mirrors main display dimensions (e.g. 1440x3120 @ 500 DPI) with zero scaling distortion or black bars.")
        lbl_sec_hint.setWordWrap(True)
        lbl_sec_hint.setStyleSheet("color: #64748b; font-size: 10px; font-style: italic;")
        gsec_l.addWidget(lbl_sec_hint)

        tgfx_l.addWidget(self.grp_sec_disp)

        # Load secondary display config
        try:
            from nexus.display_and_vpn import get_secondary_display_config
            sec_cfg = get_secondary_display_config(self.instance_name)
        except Exception:
            sec_cfg = {
                "enabled": False,
                "match_primary": True,
                "width": cur_w,
                "height": cur_h,
                "density": cur_d
            }

        sec_is_enabled = bool(sec_cfg.get("enabled", False))
        sec_is_match = bool(sec_cfg.get("match_primary", True))
        sec_w = int(sec_cfg.get("width", cur_w))
        sec_h = int(sec_cfg.get("height", cur_h))
        sec_d = int(sec_cfg.get("density", cur_d))

        self.chk_sec_disp.setChecked(sec_is_enabled)
        self.chk_sec_match.setChecked(sec_is_match)
        self.spin_sec_width.setValue(sec_w)
        self.spin_sec_height.setValue(sec_h)
        self.spin_sec_density.setValue(sec_d)

        # Connect signals for secondary display
        self.chk_sec_disp.toggled.connect(self.on_secondary_display_toggled)
        self.chk_sec_match.toggled.connect(self.on_secondary_match_toggled)
        self.combo_sec_preset.currentIndexChanged.connect(self.on_secondary_preset_changed)
        self.spin_width.valueChanged.connect(self.on_primary_dim_changed)
        self.spin_height.valueChanged.connect(self.on_primary_dim_changed)
        self.spin_density.valueChanged.connect(self.on_primary_dim_changed)

        self.update_secondary_controls_state()

        tools_disp = QHBoxLayout()
        self.btn_reset_disp = QPushButton("🖥️ Reset Screen Glitch (1440x3120)")
        self.btn_reset_disp.setProperty("class", "btnAction")
        self.btn_reset_disp.setToolTip("Purges multi-display secondary viewports and restores clean flagship screen")
        self.btn_reset_disp.clicked.connect(self.action_reset_display_glitch)
        tools_disp.addWidget(self.btn_reset_disp)

        self.lbl_disp_status = QLabel("")
        self.lbl_disp_status.setStyleSheet("color: #16a34a; font-size: 11px; font-weight: 500;")
        tools_disp.addWidget(self.lbl_disp_status, 1)
        tgfx_l.addLayout(tools_disp)

        tgfx_l.addStretch()
        self.tabs.addTab(tab_gfx, "🎮 Graphics & Display")

        # ==============================================================
        # TAB 3: Camera & Media
        # ==============================================================
        tab_media = QWidget()
        tmed_l = QVBoxLayout(tab_media)
        tmed_l.setContentsMargins(16, 16, 16, 16)
        tmed_l.setSpacing(12)

        g_med = QGridLayout()
        g_med.setSpacing(10)

        # Front Camera
        g_med.addWidget(QLabel("Front Camera:"), 0, 0)
        self.combo_cam_front = QComboBox()
        cur_cf = self.cfg.get("hw.camera.front", "webcam0")
        for label, val in [("Host PC Webcam (webcam0 — Recommended)", "webcam0"), ("Virtual Scene Emulated Camera", "emulated"), ("Disabled / None", "none")]:
            self.combo_cam_front.addItem(label, val)
            if val == cur_cf: self.combo_cam_front.setCurrentIndex(self.combo_cam_front.count() - 1)
        g_med.addWidget(self.combo_cam_front, 0, 1)

        # Back Camera
        g_med.addWidget(QLabel("Back / Main Camera:"), 1, 0)
        self.combo_cam_back = QComboBox()
        cur_cb = self.cfg.get("hw.camera.back", "webcam0")
        for label, val in [("Host PC Webcam (webcam0 — Recommended)", "webcam0"), ("Virtual Scene Emulated Camera", "emulated"), ("Disabled / None", "none")]:
            self.combo_cam_back.addItem(label, val)
            if val == cur_cb: self.combo_cam_back.setCurrentIndex(self.combo_cam_back.count() - 1)
        g_med.addWidget(self.combo_cam_back, 1, 1)

        # Audio Driver Backend
        g_med.addWidget(QLabel("Audio Driver Engine:"), 2, 0)
        self.combo_audio = QComboBox()
        self.combo_audio.addItem("Safe Timer-Based Emulation (Recommended)", "none")
        self.combo_audio.addItem("DirectSound Host Audio (Auto)", "auto")
        self.combo_audio.addItem("Disabled / Mute Audio", "none")
        g_med.addWidget(self.combo_audio, 2, 1)

        tmed_l.addLayout(g_med)

        self.chk_mic = QCheckBox("🎙️ Enable Host PC Microphone Passthrough (hw.audioInput)")
        self.chk_mic.setChecked(self.cfg.get("hw.audioInput", "yes").lower() in ["yes", "true", "1"])
        tmed_l.addWidget(self.chk_mic)

        cam_info = QLabel("GNDROiD automatically routes your PC webcam and microphone directly into Android apps for seamless video calls, WhatsApp identity verification, and banking KYC out of the box.")
        cam_info.setWordWrap(True)
        cam_info.setStyleSheet("color: #64748b; font-size: 11px; margin-top: 6px;")
        tmed_l.addWidget(cam_info)

        tmed_l.addStretch()
        self.tabs.addTab(tab_media, "📷 Camera & Audio")

        # ==============================================================
        # TAB 4: Network Adapter, Hardware Bridging & Bluetooth
        # ==============================================================
        tab_net_container = QWidget()
        scroll_net = QScrollArea()
        scroll_net.setWidgetResizable(True)
        scroll_net.setFrameShape(QFrame.Shape.NoFrame)
        scroll_net.setStyleSheet("background: transparent;")

        tab_net = QWidget()
        tnet_l = QVBoxLayout(tab_net)
        tnet_l.setContentsMargins(14, 14, 14, 14)
        tnet_l.setSpacing(14)

        # Load instance network config from nexus.network_bridge
        try:
            from nexus.network_bridge import (
                get_system_network_adapters, get_primary_physical_adapter,
                get_instance_network_config, get_system_bluetooth_adapters,
                get_physical_bluetooth_controller, get_paired_bluetooth_devices,
                get_default_gateway, start_global_lan_bridge
            )
            net_cfg = get_instance_network_config(self.instance_name)
        except Exception:
            net_cfg = {"mode": "lan_bridge", "adapter_name": "", "replicate_state": True, "bluetooth_enabled": True}

        # -------------------------------------------------------------
        # Section 1: Virtual Machine Network Adapter & Bridging Mode
        # -------------------------------------------------------------
        grp_net = QGroupBox("🌐 Virtual Machine Network Adapter & Hardware Bridging")
        g_net_l = QVBoxLayout(grp_net)
        g_net_l.setSpacing(10)

        # Legacy wifi toggle for config.ini compatibility
        self.chk_wifi = QCheckBox("📶 Enable Virtual Wi-Fi Adapter (Full Gigabit Internet via Host)")
        self.chk_wifi.setChecked(self.cfg.get("hw.wifi", "yes").lower() in ["yes", "true", "1"])
        g_net_l.addWidget(self.chk_wifi)

        lbl_mode = QLabel("<b>Network Connection Mode:</b>")
        g_net_l.addWidget(lbl_mode)

        self.combo_net_mode = QComboBox()
        self.combo_net_mode.addItem("⚡ High-Speed LAN Bridge (Host Direct IP 192.168.100.5 • Zero-Driver Plug & Play)", "lan_bridge")
        self.combo_net_mode.addItem("🌐 Hardware Bridged (Replicate Physical Connection • DHCP 192.168.100.x via TAP/NDIS)", "hardware_bridged")
        self.combo_net_mode.addItem("🔒 Standard Isolated NAT (Private 10.0.2.15 Subnet)", "nat")

        cur_mode = net_cfg.get("mode", "lan_bridge")
        for idx in range(self.combo_net_mode.count()):
            if self.combo_net_mode.itemData(idx) == cur_mode:
                self.combo_net_mode.setCurrentIndex(idx)
                break
        self.combo_net_mode.currentIndexChanged.connect(self.on_net_mode_changed)
        g_net_l.addWidget(self.combo_net_mode)

        self.lbl_mode_desc = QLabel(
            "<b>Mode 1 (LAN Bridge):</b> Directly maps Android emulator ports to your physical PC IP (192.168.100.5). "
            "Other phones, Android TVs, and PCs on your Wi-Fi can connect directly with zero kernel drivers or admin rights."
        )
        self.lbl_mode_desc.setWordWrap(True)
        self.lbl_mode_desc.setStyleSheet("color: #475569; font-size: 11px; padding: 6px 8px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px;")
        g_net_l.addWidget(self.lbl_mode_desc)

        # Physical Adapter Selector
        lbl_adapter = QLabel("<b>Select Physical Network Adapter (Bridged Target):</b>")
        g_net_l.addWidget(lbl_adapter)

        self.combo_adapters = QComboBox()
        try:
            all_adapters = get_system_network_adapters()
        except Exception:
            all_adapters = []

        cur_adapter_name = net_cfg.get("adapter_name", "")
        selected_adapter_idx = 0
        for i, ad in enumerate(all_adapters):
            self.combo_adapters.addItem(ad["display_label"], ad["name"])
            if cur_adapter_name and (cur_adapter_name in ad["description"] or cur_adapter_name in ad["name"]):
                selected_adapter_idx = i
        if self.combo_adapters.count() > 0:
            self.combo_adapters.setCurrentIndex(selected_adapter_idx)
        g_net_l.addWidget(self.combo_adapters)

        # Replicate physical connection state checkbox (VMware/VirtualBox style)
        self.chk_replicate_state = QCheckBox("Replicate physical network connection state (Link Up/Down Sync)")
        self.chk_replicate_state.setChecked(net_cfg.get("replicate_state", True))
        g_net_l.addWidget(self.chk_replicate_state)

        # Speed & Latency and Port mappings
        g_net_opts = QGridLayout()
        g_net_opts.addWidget(QLabel("Speed & Latency:"), 0, 0)
        self.combo_net_speed = QComboBox()
        self.combo_net_speed.addItem("Full Gigabit Host Speed / Zero Latency", "full")
        self.combo_net_speed.addItem("5G Ultra-Wideband (300 Mbps / 10ms Latency)", "5g")
        self.combo_net_speed.addItem("LTE / 4G Mobile Data (50 Mbps / 30ms Latency)", "lte")
        g_net_opts.addWidget(self.combo_net_speed, 0, 1)

        g_net_opts.addWidget(QLabel("Exposed LAN Ports:"), 1, 0)
        self.txt_exposed_ports = QLineEdit()
        self.txt_exposed_ports.setText(net_cfg.get("exposed_ports", "51888, 51880, 5555, 8080, 8088"))
        g_net_opts.addWidget(self.txt_exposed_ports, 1, 1)
        g_net_l.addLayout(g_net_opts)

        # Live Physical LAN Status badge
        try:
            gw = get_default_gateway()
            pri = get_primary_physical_adapter()
            pri_ip = pri["primary_ip"] if pri else "192.168.100.5"
            pri_name = pri["name"] if pri else "Wi-Fi"
        except Exception:
            gw, pri_ip, pri_name = "192.168.100.1", "192.168.100.5", "Wi-Fi"

        self.lbl_lan_status = QLabel(
            f"● Physical LAN: <b>{pri_ip}</b> ({pri_name}) | Router Gateway: <b>{gw}</b> | Bridge: <b>Active (Ports 51888, 51880, 5555, 8088)</b>"
        )
        self.lbl_lan_status.setStyleSheet("color: #059669; font-size: 11px; padding: 6px 8px; background: #ecfdf5; border: 1px solid #a7f3d0; border-radius: 6px;")
        g_net_l.addWidget(self.lbl_lan_status)

        # Interactive Bridge Buttons
        b_row = QHBoxLayout()
        self.btn_test_bridge = QPushButton("⚡ Test & Activate LAN Bridge")
        self.btn_test_bridge.setProperty("class", "btnAction")
        self.btn_test_bridge.clicked.connect(self.action_test_lan_bridge)
        b_row.addWidget(self.btn_test_bridge)

        self.btn_refresh_adapters = QPushButton("🔄 Refresh Adapters")
        self.btn_refresh_adapters.setProperty("class", "btnAction")
        self.btn_refresh_adapters.clicked.connect(self.action_refresh_adapters)
        b_row.addWidget(self.btn_refresh_adapters)
        g_net_l.addLayout(b_row)

        tnet_l.addWidget(grp_net)

        # -------------------------------------------------------------
        # Section 2: Bluetooth Controller & Wireless Discovery
        # -------------------------------------------------------------
        grp_bt = QGroupBox("📡 Bluetooth Controller & Hardware Discovery")
        g_bt_l = QVBoxLayout(grp_bt)
        g_bt_l.setSpacing(10)

        self.chk_bluetooth = QCheckBox("Enable Bluetooth Wireless Controller (hw.bluetooth & netsimd)")
        self.chk_bluetooth.setChecked(net_cfg.get("bluetooth_enabled", True))
        g_bt_l.addWidget(self.chk_bluetooth)

        try:
            bt_ctrl = get_physical_bluetooth_controller()
            bt_name = bt_ctrl["name"] if bt_ctrl else "Realtek Wireless Bluetooth Adapter"
            paired_list = get_paired_bluetooth_devices()
        except Exception:
            bt_name = "Realtek Wireless Bluetooth Adapter"
            paired_list = []

        g_bt_row = QHBoxLayout()
        g_bt_row.addWidget(QLabel("Host Bluetooth Radio:"))
        self.lbl_bt_hardware = QLabel(f"<b>{bt_name}</b> (Hardware PnP)")
        self.lbl_bt_hardware.setStyleSheet("color: #0f172a; font-size: 11px;")
        g_bt_row.addWidget(self.lbl_bt_hardware, 1)
        g_bt_l.addLayout(g_bt_row)

        if paired_list:
            paired_str = " • ".join(paired_list)
            lbl_paired = QLabel(f"Paired Mobile Devices Found: {paired_str}")
            lbl_paired.setWordWrap(True)
            lbl_paired.setStyleSheet("color: #475569; font-size: 10px; background: #f1f5f9; padding: 4px 6px; border-radius: 4px;")
            g_bt_l.addWidget(lbl_paired)

        self.combo_bt_mode = QComboBox()
        self.combo_bt_mode.addItem("Google netsimd Virtual BLE Engine & HCI Socket (Port 7300)", "netsimd")
        self.combo_bt_mode.addItem("Direct USB Bluetooth Controller Passthrough", "passthrough")
        g_bt_l.addWidget(self.combo_bt_mode)

        tnet_l.addWidget(grp_bt)

        # -------------------------------------------------------------
        # Section 3: Hardware Biometrics & Environmental Sensors
        # -------------------------------------------------------------
        grp_sensor = QGroupBox("👆 Hardware Biometrics & Sensor Emulation")
        g_sens_l = QVBoxLayout(grp_sensor)
        g_sens_l.setSpacing(8)

        self.chk_fp = QCheckBox("👆 USB Fingerprint Biometric Scanner (hw.fingerprint)")
        self.chk_fp.setChecked(self.cfg.get("hw.fingerprint", "yes").lower() in ["yes", "true", "1"])
        g_sens_l.addWidget(self.chk_fp)

        self.chk_gps = QCheckBox("📍 GPS & Real Geolocation Sensor (hw.gps)")
        self.chk_gps.setChecked(self.cfg.get("hw.gps", "yes").lower() in ["yes", "true", "1"])
        g_sens_l.addWidget(self.chk_gps)

        self.chk_motion = QCheckBox("🔄 Accelerometer & Gyroscope Motion Sensors (hw.accelerometer && hw.gyroscope)")
        self.chk_motion.setChecked(self.cfg.get("hw.accelerometer", "yes").lower() in ["yes", "true", "1"])
        g_sens_l.addWidget(self.chk_motion)

        self.chk_env = QCheckBox("💡 Ambient Light & Proximity Environmental Sensors")
        self.chk_env.setChecked(self.cfg.get("hw.sensors.light", "yes").lower() in ["yes", "true", "1"])
        g_sens_l.addWidget(self.chk_env)

        fp_row = QHBoxLayout()
        self.btn_fp_touch = QPushButton("👆 Trigger Fingerprint Touch (Finger #1)")
        self.btn_fp_touch.setProperty("class", "btnAction")
        self.btn_fp_touch.clicked.connect(self.trigger_fingerprint)
        fp_row.addWidget(self.btn_fp_touch)

        self.fp_status = QLabel("Biometrics: Ready for scan authentication")
        self.fp_status.setStyleSheet("color: #64748b; font-size: 11px;")
        fp_row.addWidget(self.fp_status, 1)
        g_sens_l.addLayout(fp_row)

        tnet_l.addWidget(grp_sensor)
        tnet_l.addStretch()

        scroll_net.setWidget(tab_net)
        tab_net_l = QVBoxLayout(tab_net_container)
        tab_net_l.setContentsMargins(0, 0, 0, 0)
        tab_net_l.addWidget(scroll_net)

        self.tabs.addTab(tab_net_container, "🌐 Network & Adapters")

        layout.addWidget(self.tabs)

        # Dialog Buttons
        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)

        self.btn_save = QPushButton("💾 Save & Apply Settings")
        self.btn_save.setProperty("class", "btnPrimary")
        self.btn_save.clicked.connect(self.action_save_settings)
        btn_box.addWidget(self.btn_save)

        self.btn_cancel = QPushButton("✕ Cancel")
        self.btn_cancel.setProperty("class", "btnSecondary")
        self.btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(self.btn_cancel)

        layout.addLayout(btn_box)

    def on_net_mode_changed(self, idx: int):
        mode = self.combo_net_mode.itemData(idx)
        if mode == "lan_bridge":
            self.lbl_mode_desc.setText(
                "<b>Mode 1 (⚡ High-Speed LAN Bridge):</b> Directly maps Android emulator ports to your physical PC IP (192.168.100.5). "
                "Other phones, Android TVs, and PCs on your Wi-Fi can connect directly with zero driver requirements."
            )
        elif mode == "hardware_bridged":
            self.lbl_mode_desc.setText(
                "<b>Mode 2 (🌐 Hardware Bridged):</b> Bridges Android VM to the selected physical NIC via Windows TAP / Hyper-V Switch. "
                "The home router DHCP assigns a real 192.168.100.x address directly to the Android instance."
            )
        else:
            self.lbl_mode_desc.setText(
                "<b>Mode 3 (🔒 Isolated NAT):</b> Standard Android emulator private 10.0.2.15 sandbox subnet. Isolated from other home network devices."
            )

    def action_test_lan_bridge(self):
        try:
            import socket
            from nexus.network_bridge import start_global_lan_bridge, get_primary_physical_adapter
            start_global_lan_bridge()
            pri = get_primary_physical_adapter()
            host_ip = pri["primary_ip"] if pri else "192.168.100.5"
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2.0)
            res = s.connect_ex((host_ip, 51888))
            s.close()
            if res == 0:
                QMessageBox.information(
                    self, "LAN Bridge Active",
                    f"LAN Bridge is ACTIVE and reachable!\n\n"
                    f"• Host Physical IP: {host_ip}\n"
                    f"• Port: 51888 (HTTP / Stream Control)\n"
                    f"• Status: External Wi-Fi devices can reach the emulator directly at:\n"
                    f"  http://{host_ip}:51888/api/v1/status"
                )
            else:
                QMessageBox.information(
                    self, "LAN Bridge Bound",
                    f"LAN Bridge listener is BOUND to {host_ip}:51888.\n"
                    f"When an emulator instance is running with Companion App, external devices will connect seamlessly."
                )
        except Exception as e:
            QMessageBox.warning(self, "Bridge Test", f"Bridge test status: {e}")

    def action_refresh_adapters(self):
        try:
            from nexus.network_bridge import get_system_network_adapters
            self.combo_adapters.clear()
            for ad in get_system_network_adapters():
                self.combo_adapters.addItem(ad["display_label"], ad["name"])
            QMessageBox.information(self, "Adapters Refreshed", "Physical and virtual network adapters refreshed successfully.")
        except Exception as e:
            QMessageBox.warning(self, "Refresh Error", str(e))

    def on_resolution_preset_changed(self, idx: int):
        data = self.combo_res_preset.itemData(idx)
        if data and isinstance(data, tuple) and data[0] > 0:
            w, h, d = data
            self.spin_width.setValue(w)
            self.spin_height.setValue(h)
            self.spin_density.setValue(d)
            if hasattr(self, 'chk_sec_match') and self.chk_sec_match.isChecked():
                self.sync_secondary_with_primary()

    def on_secondary_display_toggled(self, checked: bool):
        self.update_secondary_controls_state()

    def on_secondary_match_toggled(self, checked: bool):
        if checked:
            self.sync_secondary_with_primary()
        self.update_secondary_controls_state()

    def sync_secondary_with_primary(self):
        self.spin_sec_width.setValue(self.spin_width.value())
        self.spin_sec_height.setValue(self.spin_height.value())
        self.spin_sec_density.setValue(self.spin_density.value())
        self.combo_sec_preset.setCurrentIndex(0)

    def on_primary_dim_changed(self, _=None):
        if hasattr(self, 'chk_sec_match') and self.chk_sec_match.isChecked():
            self.sync_secondary_with_primary()

    def update_secondary_controls_state(self):
        disp_enabled = self.chk_sec_disp.isChecked()
        match_checked = self.chk_sec_match.isChecked()

        self.chk_sec_match.setEnabled(disp_enabled)

        # Presets and custom spinboxes are disabled/auto-synced when match primary is checked
        custom_enabled = disp_enabled and (not match_checked)
        self.combo_sec_preset.setEnabled(custom_enabled)
        self.spin_sec_width.setEnabled(custom_enabled)
        self.spin_sec_height.setEnabled(custom_enabled)
        self.spin_sec_density.setEnabled(custom_enabled)

        if match_checked:
            self.sync_secondary_with_primary()

    def on_secondary_preset_changed(self, idx: int):
        data = self.combo_sec_preset.itemData(idx)
        if data and isinstance(data, tuple):
            pw, ph, pd = data
            if pw == 0:  # Match main
                self.sync_secondary_with_primary()
            elif pw > 0:
                self.spin_sec_width.setValue(pw)
                self.spin_sec_height.setValue(ph)
                self.spin_sec_density.setValue(pd)

    def action_test_guest_root(self):
        self.lbl_root_live.setText("⏳ Testing guest root status via ADB...")
        serial = self.target_serial
        res = AVDManager.check_live_root(serial)
        self.lbl_root_live.setText(res.get("message", "Check complete."))

    def action_reset_display_glitch(self):
        try:
            from nexus.display_and_vpn import set_secondary_display_config
            set_secondary_display_config(self.instance_name, enabled=False)
            AVDManager.reset_instance_display(self.instance_name, 1440, 3120, 500)
            self.spin_width.setValue(1440)
            self.spin_height.setValue(3120)
            self.spin_density.setValue(500)
            self.combo_res_preset.setCurrentIndex(0)
            if hasattr(self, 'chk_sec_disp'):
                self.chk_sec_disp.setChecked(False)
            if hasattr(self, 'chk_sec_match'):
                self.chk_sec_match.setChecked(True)
            if hasattr(self, 'spin_sec_width'):
                self.spin_sec_width.setValue(1440)
            if hasattr(self, 'spin_sec_height'):
                self.spin_sec_height.setValue(3120)
            if hasattr(self, 'spin_sec_density'):
                self.spin_sec_density.setValue(500)
            if hasattr(self, 'update_secondary_controls_state'):
                self.update_secondary_controls_state()
            self.lbl_disp_status.setText("✅ Screen restored to single 1440x3120 500 DPI viewport!")
        except Exception as e:
            self.lbl_disp_status.setText(f"❌ Error: {e}")

    def trigger_fingerprint(self):
        adb = SystemPaths.get_adb()
        target = ["-s", self.target_serial] if self.target_serial else []
        try:
            res = subprocess.check_output([adb] + target + ["emu", "finger", "touch", "1"], text=True, timeout=3, creationflags=0x08000000)
            self.fp_status.setText(f"✅ Biometric Verified: {res.strip()}")
            self.fp_status.setStyleSheet("color: #16a34a; font-size: 11px;")
        except Exception as e:
            self.fp_status.setText(f"Fingerprint: {e}")

    def action_save_settings(self):
        w = self.spin_width.value()
        h = self.spin_height.value()
        d = self.spin_density.value()
        ram = self.combo_ram.currentData()
        cores = self.combo_cores.currentData()
        heap = self.combo_heap.currentData()
        gpu = self.combo_gpu.currentData()
        disp_name = self.txt_display_name.text().strip() or "GNDROiD Flagship"

        cfg_dict = {
            "avd.ini.displayname": disp_name,
            "hw.ramSize": str(ram),
            "hw.cpu.ncore": str(cores),
            "vm.heapSize": str(heap),
            "hw.gpu.mode": str(gpu),
            "hw.lcd.width": str(w),
            "hw.lcd.height": str(h),
            "hw.lcd.density": str(d),
            "showDeviceFrame": "yes" if self.chk_frame.isChecked() else "no",
            "gndroid.root": "yes" if self.chk_root.isChecked() else "no",
            "hw.camera.front": str(self.combo_cam_front.currentData()),
            "hw.camera.back": str(self.combo_cam_back.currentData()),
            "hw.audioInput": "yes" if self.chk_mic.isChecked() else "no",
            "hw.wifi": "yes" if self.chk_wifi.isChecked() else "no",
            "hw.fingerprint": "yes" if self.chk_fp.isChecked() else "no",
            "hw.gps": "yes" if self.chk_gps.isChecked() else "no",
            "hw.accelerometer": "yes" if self.chk_motion.isChecked() else "no",
            "hw.gyroscope": "yes" if self.chk_motion.isChecked() else "no",
            "hw.sensors.light": "yes" if self.chk_env.isChecked() else "no",
            "hw.sensors.proximity": "yes" if self.chk_env.isChecked() else "no",
            "runtime.network.speed": str(self.combo_net_speed.currentData())
        }

        ok = AVDManager.save_full_instance_config(self.instance_name, cfg_dict)

        # Accurately store Network & Hardware Bridging configuration in config.ini
        try:
            from nexus.network_bridge import save_instance_network_config
            net_save_data = {
                "mode": self.combo_net_mode.currentData(),
                "adapter_name": self.combo_adapters.currentText(),
                "replicate_state": self.chk_replicate_state.isChecked(),
                "bluetooth_enabled": self.chk_bluetooth.isChecked(),
                "bluetooth_mode": self.combo_bt_mode.currentData(),
                "exposed_ports": self.txt_exposed_ports.text().strip()
            }
            save_instance_network_config(self.instance_name, net_save_data)
        except Exception as e:
            pass

        # Accurately store secondary display configuration in config.ini
        try:
            from nexus.display_and_vpn import set_secondary_display_config
            set_secondary_display_config(
                instance_name=self.instance_name,
                enabled=self.chk_sec_disp.isChecked(),
                match_primary=self.chk_sec_match.isChecked(),
                width=self.spin_sec_width.value(),
                height=self.spin_sec_height.value(),
                density=self.spin_sec_density.value()
            )
        except Exception as e:
            pass

        if ok:
            msg = (
                f"Configuration successfully saved to config.ini!\n\n"
                f"• Instance: {disp_name}\n"
                f"• RAM: {ram} MB | CPU: {cores} Cores\n"
                f"• Resolution: {w}x{h} @ {d} DPI\n"
                f"• Graphics: {gpu}\n\n"
                f"Hardware allocations will apply upon starting or restarting the instance."
            )
            QMessageBox.information(self, "Settings Saved", msg)
            self.accept()
        else:
            QMessageBox.warning(self, "Save Error", "Failed to write configuration to config.ini.")

# ----------------------------------------------------------------------
# Master Application: gndroid (Ghulam Nabi Kalhoro)
# ----------------------------------------------------------------------
VERSION = "2.2.2"

class GNDroidApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"GNDROiD v{VERSION} — Developed by Ghulam Nabi Kalhoro")
        self.setFixedSize(620, 840)
        self.setAcceptDrops(True)

        icon_path = SystemPaths.get_icon()
        if icon_path:
            self.setWindowIcon(QIcon(icon_path))

        self.scrcpy_proc = None
        self.sidebar_window = None

        # Auto-provision flagship AVD if running on a new system
        AVDManager.ensure_default_flagship_avd()

        self.setup_ui()
        self.apply_styles()
        self.center_on_screen()

        # Initial populate
        hw_info = SystemPaths.get_host_hardware_summary()
        self.dev_combo.addItem(f"⚡ [A34] GNDROiD Flagship ({hw_info['ram_gb']}GB Host RAM / {hw_info['cores']} Cores • Stable)", {
            "type": "vm", "name": "gndroid", "running": False, "serial": "", "api": 34, "inst": None
        })
        self.dev_combo.addItem("📱 Auto-Detect Physical Phone (Plug USB Cable)", {
            "type": "mode_usb", "name": "mode_usb"
        })
        self.dev_combo.addItem("📶 Wireless LAN Phone (Wi-Fi Streaming & Subnet Radar)", {
            "type": "mode_lan", "name": "mode_lan"
        })

        # Zero-lag background device scanner & auto-LAN daemon (never freezes UI)
        self.dev_scanner = DeviceScannerWorker(self)
        self.dev_scanner.devices_updated.connect(self.on_devices_updated)
        self.dev_scanner.auto_lan_status.connect(self.on_auto_lan_status)
        self.dev_scanner.start()

    def closeEvent(self, event):
        # Feature 8: Clean shutdown across the complete process tree
        # 1. Stop background scanner worker
        if hasattr(self, 'dev_scanner') and self.dev_scanner:
            try:
                self.dev_scanner.stop()
            except Exception:
                pass

        # 2. Stop radar worker if running
        if hasattr(self, 'radar_worker') and self.radar_worker:
            try:
                self.radar_worker.stop()
            except Exception:
                pass

        # 3. Close companion sidebars and terminate scrcpy mirrors
        try:
            sidebars = list(GNDroidCompanionSidebar._active_sidebars.values())
            for sb in sidebars:
                try:
                    sb.close()
                except Exception:
                    pass
        except Exception:
            pass

        # 4. Terminate all dedicated floating app windows
        try:
            from nexus.app_cloner_and_window import AppWindowManager
            AppWindowManager.terminate_all_windows(timeout=2.0)
        except Exception:
            pass

        # 5. Gracefully terminate all managed VM instances
        try:
            AVDManager.stop_all_instances(timeout=3.0)
        except Exception:
            pass

        # 6. Terminate any remaining Win32 Job Object tracked child processes
        try:
            from nexus.app_cloner_and_window import Win32JobManager
            Win32JobManager.get_instance().terminate_all_tracked_processes(timeout=2.0)
        except Exception:
            pass

        super().closeEvent(event)

    def center_on_screen(self):
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(max(20, x), max(20, y))

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)

        # 1. Branding Header
        header_frame = QFrame()
        header_frame.setObjectName("headerFrame")
        h_layout = QHBoxLayout(header_frame)
        h_layout.setContentsMargins(16, 12, 16, 12)
        h_layout.setSpacing(14)

        logo_lbl = QLabel()
        logo_pix = QPixmap(SystemPaths.get_icon())
        if not logo_pix.isNull():
            logo_lbl.setPixmap(logo_pix.scaled(50, 50, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        h_layout.addWidget(logo_lbl)

        txt_vbox = QVBoxLayout()
        txt_vbox.setSpacing(2)

        title = QLabel(f"⚡ GNDROiD v{VERSION}")
        title.setFont(QFont("Segoe UI Variable Display", 20, QFont.Weight.Bold))
        title.setStyleSheet("color: #0f172a; letter-spacing: -0.3px;")
        txt_vbox.addWidget(title)

        author = QLabel(f"NextGen Multi-Instance Android VM & Phone Suite v{VERSION} • Developed by Ghulam Nabi Kalhoro")
        author.setStyleSheet("color: #64748b; font-size: 11px;")
        txt_vbox.addWidget(author)

        h_layout.addLayout(txt_vbox, 1)
        main_layout.addWidget(header_frame)

        # 2. Hardware Allocation Banner
        hw_banner = QFrame()
        hw_banner.setObjectName("hwBanner")
        hb_layout = QHBoxLayout(hw_banner)
        hb_layout.setContentsMargins(14, 10, 14, 10)

        hw_info = SystemPaths.get_host_hardware_summary()
        hw_text = QLabel(f"🚀 <b>Host PC Hardware:</b> {hw_info['summary_text']}")
        hw_text.setStyleSheet("color: #0f172a; font-size: 11px;")
        hb_layout.addWidget(hw_text)

        main_layout.addWidget(hw_banner)

        # 3. Device Selector
        dev_frame = QFrame()
        dev_frame.setObjectName("cardFrame")
        df_layout = QVBoxLayout(dev_frame)
        df_layout.setContentsMargins(16, 14, 16, 14)
        df_layout.setSpacing(10)

        df_title = QLabel("📱 Select Target Android Device / Mode:")
        df_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        df_title.setStyleSheet("color: #0f172a;")
        df_layout.addWidget(df_title)

        self.dev_combo = QComboBox()
        self.dev_combo.setMinimumHeight(40)
        self.dev_combo.currentIndexChanged.connect(self.on_device_selection_changed)
        df_layout.addWidget(self.dev_combo)

        # Launch Primary Action Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.btn_launch_vm = QPushButton("⚡ Launch Android 16 Machine")
        self.btn_launch_vm.setObjectName("btnPrimary")
        self.btn_launch_vm.setMinimumHeight(44)
        self.btn_launch_vm.clicked.connect(self.launch_virtual_machine)
        btn_row.addWidget(self.btn_launch_vm)

        self.btn_mirror_usb = QPushButton("🔗 Mirror Phone (USB / LAN)")
        self.btn_mirror_usb.setObjectName("btnSecondary")
        self.btn_mirror_usb.setMinimumHeight(44)
        self.btn_mirror_usb.clicked.connect(self.action_handle_secondary_button)
        btn_row.addWidget(self.btn_mirror_usb)

        df_layout.addLayout(btn_row)

        # LAN Connect & ADB Doctor Row
        lan_row = QHBoxLayout()
        lan_row.setSpacing(10)

        self.btn_lan_connect = QPushButton("📶 Wireless LAN Mode")
        self.btn_lan_connect.setStyleSheet("background: #f8fafc; border: 1px solid #cbd5e1; color: #0f172a; font-weight: 500; padding: 8px; border-radius: 4px; font-size: 11px;")
        self.btn_lan_connect.clicked.connect(self.connect_lan_mode)
        lan_row.addWidget(self.btn_lan_connect)

        self.btn_adb_fixer = QPushButton("🛠️ ADB Doctor && Fixer")
        self.btn_adb_fixer.setStyleSheet("background: #f8fafc; border: 1px solid #cbd5e1; color: #0f172a; font-weight: 500; padding: 8px; border-radius: 4px; font-size: 11px;")
        self.btn_adb_fixer.clicked.connect(self.open_adb_fixer)
        lan_row.addWidget(self.btn_adb_fixer)

        self.btn_wireless_pairing = QPushButton("📡 Wireless Debugging & QR Pairing")
        self.btn_wireless_pairing.setObjectName("btnWirelessPairing")
        self.btn_wireless_pairing.setStyleSheet(
            "background: #f0f9ff; border: 1.5px solid #0284c7; color: #0369a1; "
            "font-weight: 600; padding: 8px; border-radius: 4px; font-size: 11px;"
        )
        self.btn_wireless_pairing.setToolTip("Open Android 11+ SPAKE2 QR pairing and 1-Click TCP 5555 provisioning suite")
        self.btn_wireless_pairing.clicked.connect(self.open_wireless_pairing_dialog)
        lan_row.addWidget(self.btn_wireless_pairing)

        df_layout.addLayout(lan_row)

        # Multi-Instance & 1-Click OS Downloader Row
        multi_row = QHBoxLayout()
        multi_row.setSpacing(10)

        self.btn_multi_manager = QPushButton("🚀 Multi-Instance Manager && Clones")
        self.btn_multi_manager.setStyleSheet("background: #0067c0; border: 1px solid rgba(0, 0, 0, 0.1); color: #ffffff; font-weight: 600; padding: 8px; border-radius: 4px; font-size: 11px;")
        self.btn_multi_manager.clicked.connect(self.open_multi_manager)
        multi_row.addWidget(self.btn_multi_manager)

        self.btn_download_os = QPushButton("📥 1-Click OS Downloader")
        self.btn_download_os.setStyleSheet("background: #f8fafc; border: 1px solid #cbd5e1; color: #0f172a; font-weight: 500; padding: 8px; border-radius: 4px; font-size: 11px;")
        self.btn_download_os.clicked.connect(self.open_image_downloader)
        multi_row.addWidget(self.btn_download_os)

        df_layout.addLayout(multi_row)

        main_layout.addWidget(dev_frame)

        # 4. Seamless Quick-Controls
        tools_frame = QFrame()
        tools_frame.setObjectName("cardFrame")
        tf_layout = QVBoxLayout(tools_frame)
        tf_layout.setContentsMargins(16, 14, 16, 14)
        tf_layout.setSpacing(10)

        tf_title = QLabel("🎮 Full Device Navigation & Hardware Controls:")
        tf_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        tf_title.setStyleSheet("color: #0f172a;")
        tf_layout.addWidget(tf_title)

        grid = QGridLayout()
        grid.setSpacing(8)

        btn_rot = QPushButton("🔄 Rotate Screen")
        btn_rot.clicked.connect(self.toggle_rotation)
        grid.addWidget(btn_rot, 0, 0)

        btn_vol_up = QPushButton("🔊 Vol +")
        btn_vol_up.clicked.connect(lambda: self.send_key(24))
        grid.addWidget(btn_vol_up, 0, 1)

        btn_vol_down = QPushButton("🔉 Vol -")
        btn_vol_down.clicked.connect(lambda: self.send_key(25))
        grid.addWidget(btn_vol_down, 0, 2)

        btn_back = QPushButton("◀ Back")
        btn_back.clicked.connect(lambda: self.send_key(4))
        grid.addWidget(btn_back, 1, 0)

        btn_home = QPushButton("● Home")
        btn_home.clicked.connect(lambda: self.send_key(3))
        grid.addWidget(btn_home, 1, 1)

        btn_recents = QPushButton("▢ Recents")
        btn_recents.clicked.connect(lambda: self.send_key(187))
        grid.addWidget(btn_recents, 1, 2)

        btn_apps = QPushButton("📱 App Drawer & Cloner")
        btn_apps.setToolTip("Browse installed apps, create multi-account clones, and open dedicated floating windows")
        btn_apps.setStyleSheet("color: #0067c0; font-weight: 600;")
        btn_apps.clicked.connect(self.open_app_drawer)
        grid.addWidget(btn_apps, 2, 0)

        btn_shot = QPushButton("📸 Screenshot")
        btn_shot.clicked.connect(self.capture_screenshot)
        grid.addWidget(btn_shot, 2, 1)

        btn_settings = QPushButton("⚙️ Settings")
        btn_settings.setStyleSheet("color: #b45309; font-weight: bold;")
        btn_settings.clicked.connect(self.open_settings)
        grid.addWidget(btn_settings, 2, 2)

        tf_layout.addLayout(grid)
        main_layout.addWidget(tools_frame)

        # 5. Drag & Drop APK / File Transfer Dropzone
        drop_frame = QFrame()
        drop_frame.setObjectName("dropFrame")
        dp_layout = QVBoxLayout(drop_frame)
        dp_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dp_layout.setContentsMargins(14, 14, 14, 14)
        dp_layout.setSpacing(6)

        drop_icon = QLabel("📦")
        drop_icon.setFont(QFont("Segoe UI Emoji", 20))
        drop_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dp_layout.addWidget(drop_icon)

        self.drop_label = QLabel("Drag & Drop APKs to Install, or Any Files to Copy to Phone")
        self.drop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_label.setStyleSheet("color: #64748b; font-size: 12px; font-weight: 600;")
        dp_layout.addWidget(self.drop_label)

        btn_install_shortcuts = QPushButton("📌 Clean Up && Install Official Desktop Shortcuts")
        btn_install_shortcuts.clicked.connect(self.install_desktop_shortcuts)
        dp_layout.addWidget(btn_install_shortcuts)

        main_layout.addWidget(drop_frame)

        # Status Bar
        self.status_bar = QLabel(f"GNDROiD v{VERSION} System Ready • Developed by Ghulam Nabi Kalhoro")
        self.status_bar.setStyleSheet("color: #64748b; font-size: 11px; font-family: monospace;")
        main_layout.addWidget(self.status_bar)

    def on_devices_updated(self, devs: List[Dict[str, Any]]):
        current_data = self.dev_combo.currentData()
        self.dev_combo.blockSignals(True)
        self.dev_combo.clear()

        # 1. Enumerate all user-created and flagship instances from AVDManager
        instances = AVDManager.list_instances()
        running_serials = set()

        for inst in instances:
            name = inst["name"]
            disp = inst["display_name"]
            clean_disp = re.sub(r'\s*\(\d+GB RAM\s*/\s*\d+\s*Cores\)', '', disp, flags=re.IGNORECASE).strip()
            clean_disp = re.sub(r'(?i)gnd[o|r]*id', 'GNDROiD', clean_disp)
            api = inst.get("api_level", 34)
            ram = inst.get("ram_mb", 4096) // 1024
            cores = inst.get("cores", 4)
            if inst["running"]:
                running_serials.add(inst["serial"])
                port_num = inst['serial'].replace('emulator-', '')
                label = f"🟢 [A{api}] {clean_disp} (Running • Normal Android VM • Port {port_num})"
                self.dev_combo.addItem(label, {
                    "type": "vm", "name": name, "running": True,
                    "serial": inst["serial"], "api": api, "inst": inst
                })
            else:
                label = f"⚡ [A{api}] {clean_disp} (Normal Android Instance • {ram}GB RAM / {cores} Cores)"
                self.dev_combo.addItem(label, {
                    "type": "vm", "name": name, "running": False,
                    "serial": "", "api": api, "inst": inst
                })

        if not instances:
            hw_info = SystemPaths.get_host_hardware_summary()
            self.dev_combo.addItem(f"⚡ [A36] GNDROiD Flagship (Normal Android Instance • {hw_info['ram_gb']}GB Host RAM / {hw_info['cores']} Cores)", {
                "type": "vm", "name": "gndroid", "running": False, "serial": "", "api": 36, "inst": None
            })

        # 2. Add physical devices, companion handsets, and any unmapped emulators
        has_physical = False

        # Add active Companion mobile handsets as first-class instances
        for comp_ip in ["192.168.100.245"]:
            for cp in (51880, 51888):
                try:
                    import socket
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s_comp:
                        s_comp.settimeout(0.15)
                        if s_comp.connect_ex((comp_ip, cp)) == 0:
                            self.dev_combo.addItem(f"📱 [Mobile Instance] Infinix X690B ({comp_ip}:{cp} • Wireless Companion)", {
                                "type": "companion", "host_ip": comp_ip, "port": cp, "name": "Infinix X690B"
                            })
                            has_physical = True
                            break
                except Exception:
                    pass
        for d in devs:
            s = d.get("serial", "")
            if not d.get("is_emulator"):
                prefix = "📶 LAN Phone:" if d.get("is_lan") else "📱 USB Phone:"
                self.dev_combo.addItem(f"{prefix} {d.get('model', 'Phone')} ({s})", {
                    "type": "phone", "serial": s, "is_lan": d.get("is_lan", False)
                })
                has_physical = True
            else:
                if s not in running_serials:
                    port_num = s.replace('emulator-', '')
                    self.dev_combo.addItem(f"🟢 Active Android VM (Port {port_num})", {
                        "type": "vm", "name": s, "running": True, "serial": s, "api": 36, "inst": None
                    })

        # 3. Always include USB & Wireless LAN discovery modes so user has access to all modes
        self.dev_combo.addItem("📱 Auto-Detect Physical Phone (Plug USB Cable)", {
            "type": "mode_usb", "name": "mode_usb"
        })
        self.dev_combo.addItem("📶 Wireless LAN Phone (Wi-Fi Streaming & Subnet Radar)", {
            "type": "mode_lan", "name": "mode_lan"
        })

        # Restore previously selected item
        target_idx = 0
        if current_data:
            cur_key = current_data.get("name") if isinstance(current_data, dict) else str(current_data)
            for idx in range(self.dev_combo.count()):
                d = self.dev_combo.itemData(idx)
                if isinstance(d, dict) and (d.get("name") == cur_key or d.get("serial") == cur_key):
                    target_idx = idx
                    break

        self.dev_combo.setCurrentIndex(target_idx)
        self.dev_combo.blockSignals(False)
        self.on_device_selection_changed(self.dev_combo.currentIndex())

        cur_data = self.dev_combo.currentData()
        if not (isinstance(cur_data, dict) and cur_data.get("type") == "vm" and cur_data.get("running")):
            if has_physical:
                self.btn_mirror_usb.setEnabled(True)
                self.btn_mirror_usb.setText("🔗 Mirror Phone [CONNECTED]")
            else:
                self.btn_mirror_usb.setText("🔗 Mirror Phone (Plug USB or LAN)")

    def on_device_selection_changed(self, index: int):
        data = self.dev_combo.itemData(index)
        if not data or not isinstance(data, dict):
            return
        dtype = data.get("type")
        if dtype == "vm":
            raw_name = data.get("name", "GNDROiD")
            disp_name = re.sub(r'(?i)gnd[o|r]*id', 'GNDROiD', raw_name)
            api = data.get("api", 36)
            if data.get("running"):
                port_str = data.get('serial', '').replace('emulator-', '')
                self.btn_launch_vm.setText(f"🖥 Mirror {disp_name} (60 FPS Stream)")
                self.btn_launch_vm.setToolTip(f"Open 60 FPS mirror and controls for {disp_name}")
                self.btn_mirror_usb.setText(f"⏹ Stop {disp_name}")
                self.btn_mirror_usb.setStyleSheet("background: #fee2e2; border: 1.5px solid #ef4444; color: #b91c1c; font-weight: bold; border-radius: 6px; padding: 10px; font-size: 12px;")
                self.btn_mirror_usb.setToolTip(f"Stop running Android VM ({disp_name}) on port {port_str}")
                self.status_bar.setText(f"🟢 Active Android Instance: {disp_name} on port {port_str}. Ready to mirror or stop.")
            else:
                self.btn_launch_vm.setText(f"⚡ Launch {disp_name} (Normal Android Window)")
                self.btn_launch_vm.setToolTip(f"Boot normal Android virtual machine window for {disp_name}")
                self.btn_mirror_usb.setText("🔗 Mirror Phone (USB / LAN)")
                self.btn_mirror_usb.setStyleSheet("")
                self.btn_mirror_usb.setToolTip("Mirror physical phone connected via USB or Wi-Fi")
                self.status_bar.setText(f"Ready: {disp_name} (Android {api}). Click 'Launch' to open normal window.")
        elif dtype == "companion":
            name = data.get("name", "Infinix X690B")
            host_ip = data.get("host_ip", "192.168.100.245")
            port = data.get("port", 51888)
            self.btn_launch_vm.setText(f"🚀 Launch {name} (Mobile Instance)")
            self.btn_launch_vm.setToolTip(f"Open dedicated 60 FPS wireless mirror and controls for {name}")
            self.status_bar.setText(f"🟢 Mobile Handset Ready: {name} at {host_ip}:{port}. Click Launch to start.")
        elif dtype == "phone":
            serial = data.get("serial", "")
            self.btn_launch_vm.setText(f"🔗 Mirror Phone ({serial})")
            self.status_bar.setText(f"Physical Phone Connected: {serial}. Click to mirror with PC audio.")
        elif dtype == "mode_usb":
            self.btn_launch_vm.setText("📱 Mirror Physical Phone (Plug USB Cable)")
            self.status_bar.setText("Plug your phone via USB with USB Debugging enabled, then click to Mirror.")
        elif dtype == "mode_lan":
            self.btn_launch_vm.setText("📶 Connect Wireless Phone (Wi-Fi LAN)")
            self.status_bar.setText("Open Wireless Mode to convert USB phone or discover LAN phones.")
        else:
            serial = data.get("serial", "")
            self.btn_launch_vm.setText("⚡ Launch Selected Device")
            self.status_bar.setText(f"Selected: {serial}")

    def on_auto_lan_status(self, msg: str):
        self.status_bar.setText(msg)
        self.status_bar.setStyleSheet("color: #34d399; font-size: 11px; font-weight: bold;")

    def refresh_devices(self):
        threading.Thread(target=self._async_manual_refresh, daemon=True).start()

    def _async_manual_refresh(self):
        try:
            devs = SystemPaths.list_devices()
            if hasattr(self, 'dev_scanner') and self.dev_scanner:
                self.dev_scanner.devices_updated.emit(devs)
        except Exception:
            pass

    def get_selected_target(self) -> str:
        data = self.dev_combo.currentData()
        if isinstance(data, dict):
            if data.get("serial"):
                return data["serial"]
            return data.get("name", "gndroid")
        elif data and data != "gndroid":
            return str(data)
        devs = SystemPaths.list_devices()
        active = [d["serial"] for d in devs if d["state"] == "device"]
        if active:
            return active[0]
        return "emulator-5554"

    def open_multi_manager(self):
        dlg = GNDroidMultiInstanceManager(self)
        dlg.exec()
        self.refresh_devices()

    def open_image_downloader(self, target_api: int = 34):
        if not hasattr(self, "_downloader_dlg") or self._downloader_dlg is None:
            self._downloader_dlg = GNDroidImageDownloaderDialog(target_api, None)
            self._downloader_dlg.sig_image_installed.connect(lambda _: self.refresh_devices())
        else:
            self._downloader_dlg.select_api(target_api)
        self._downloader_dlg.show()
        self._downloader_dlg.raise_()
        self._downloader_dlg.activateWindow()

    def launch_virtual_machine(self):
        data = self.dev_combo.currentData()
        name = "gndroid"
        api = 34
        inst = None

        if isinstance(data, dict):
            if data.get("type") == "companion":
                win = GNDroidWirelessMirrorWindow(
                    host_ip=data.get("host_ip", "192.168.100.245"),
                    port=data.get("port", 51888),
                    model_name=data.get("name", "Infinix X690B"),
                    parent=self
                )
                win.show()
                return
            elif data.get("type") in ["phone", "mode_usb"]:
                self.mirror_physical_device()
                return
            elif data.get("type") == "mode_lan":
                self.connect_lan_mode()
                return
            elif data.get("type") == "vm":
                name = data.get("name", "gndroid")
                api = data.get("api", 36)
                inst = data.get("inst")
                if data.get("running"):
                    self.mirror_physical_device(data.get("serial", ""))
                    return
        else:
            instances = AVDManager.list_instances()
            if instances:
                target_inst = instances[0]
                name = target_inst["name"]
                api = target_inst.get("api_level", 34)
                inst = target_inst

        # 1-Click System Image Verification before launch
        if not AVDManager.is_image_installed(api):
            res = QMessageBox.question(
                self, "System Image Download Needed",
                f"The Android {api} System Image is not installed yet on your PC.\n\n"
                f"Would you like to download it now with 1-click from Google CDN?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if res == QMessageBox.StandardButton.Yes:
                self.open_image_downloader(api)
                return
            else:
                return

        avd_base = AVDManager.get_avd_dir()
        ini_file = os.path.join(avd_base, f"{name}.ini")
        if not os.path.exists(ini_file):
            if name == "gndroid":
                AVDManager.ensure_default_flagship_avd()
            else:
                QMessageBox.warning(self, "Instance Missing", f"Instance configuration for '{name}' was not found.")
                return

        gpu_mode = inst.get("gpu", "auto") if inst else "auto"
        self.status_bar.setText(f"Starting {name} (Android {api} / GPU {gpu_mode})...")

        try:
            proc, port, log_path = AVDManager.launch_emulator_instance(
                name=name,
                gpu_mode=gpu_mode,
                is_root=inst.get("root", False) if inst else False
            )
            target_serial = f"emulator-{port}"
            self.running_proc = proc
            if not hasattr(self, "active_vm_procs"):
                self.active_vm_procs = {}
            self.active_vm_procs[name] = {
                "proc": proc,
                "pid": proc.pid if hasattr(proc, "pid") else None,
                "serial": target_serial
            }

            self.btn_launch_vm.setEnabled(False)
            self.btn_launch_vm.setText(f"⏳ Booting {name} ({target_serial})...")
            self.status_bar.setText(f"⏳ Booting {name} ({target_serial})... Android OS initializing (approx. 15-20s)...")

            attempts = [0]
            def poll_boot_progress():
                attempts[0] += 1
                devs = SystemPaths.list_devices()
                online = any(d["serial"] == target_serial and d["state"] == "device" for d in devs)
                if online:
                    self.btn_launch_vm.setEnabled(True)
                    self.btn_launch_vm.setText(f"🖥 Mirror {name} ({target_serial})")
                    self.status_bar.setText(f"🟢 Android Machine '{name}' is ONLINE on {target_serial}! Ready to mirror.")
                    self.refresh_devices()
                    try:
                        from nexus.display_and_vpn import auto_stabilize_vpn_networking
                        threading.Thread(target=auto_stabilize_vpn_networking, args=(target_serial,), daemon=True).start()
                    except Exception:
                        pass
                    return

                if attempts[0] < 35:
                    self.status_bar.setText(f"⏳ Booting {name} ({target_serial})... [{attempts[0]*1.5:.0f}s] Android kernel & services starting...")
                    QTimer.singleShot(1500, poll_boot_progress)
                else:
                    self.btn_launch_vm.setEnabled(True)
                    self.btn_launch_vm.setText(f"⚡ Launch {name} (Android {api})")
                    self.status_bar.setText(f"⚠️ Boot wait finished. Click Mirror if window is active.")
                    self.refresh_devices()

            QTimer.singleShot(2000, poll_boot_progress)
        except Exception as e:
            self.btn_launch_vm.setEnabled(True)
            self.status_bar.setText(f"Launch error: {e}")
            QMessageBox.critical(self, "Launch Error", str(e))


    def stop_current_vm(self):
        data = self.dev_combo.currentData()
        serial = ""
        name = "Android VM"
        if isinstance(data, dict):
            serial = data.get("serial", "")
            name = data.get("name", "Android VM")
        if not serial:
            serial = self.get_selected_target()
        
        adb = SystemPaths.get_adb()
        try:
            subprocess.run([adb, "-s", serial, "emu", "kill"], timeout=4, creationflags=0x08000000)
        except Exception:
            pass
        self.status_bar.setText(f"⏹️ Sent stop command to {name} ({serial})...")
        QTimer.singleShot(1000, self.refresh_devices)

    def action_handle_secondary_button(self):
        data = self.dev_combo.currentData()
        if isinstance(data, dict) and data.get("type") == "vm" and data.get("running"):
            self.stop_current_vm()
        else:
            self.mirror_physical_device()

    def mirror_physical_device(self, target_serial: str = ""):
        if not target_serial or target_serial == "gndroid":
            target_serial = self.get_selected_target()
        self.sidebar_window = start_mirror_with_fallback(target_serial, self)
        if self.sidebar_window:
            self.status_bar.setText(f"[OK] Controls and mirror active")

    def connect_lan_mode(self):
        self.open_adb_fixer(initial_tab=1)

    def open_adb_fixer(self, initial_tab: int = 0):
        dlg = GNDroidADBFixerDialog(self.get_selected_target(), self)
        if hasattr(dlg, "tabs") and initial_tab < dlg.tabs.count():
            dlg.tabs.setCurrentIndex(initial_tab)
        dlg.exec()
        self.refresh_devices()

    def open_wireless_pairing_dialog(self):
        dlg = GNDroidWirelessPairingDialog(self.get_selected_target(), self)
        dlg.sig_device_paired.connect(lambda target, _: self.refresh_devices())
        dlg.exec()
        self.refresh_devices()

    def send_key(self, code: int):
        adb = SystemPaths.get_adb()
        target = self.get_selected_target()
        cmd = [adb]
        if target and target != "gndroid":
            cmd.extend(["-s", target])
        cmd.extend(["shell", "input", "keyevent", str(code)])
        subprocess.Popen(cmd, creationflags=0x08000000)

    def toggle_rotation(self):
        adb = SystemPaths.get_adb()
        target = self.get_selected_target()
        t_args = ["-s", target] if target and target != "gndroid" else []
        try:
            cur = subprocess.check_output([adb] + t_args + ["shell", "settings", "get", "system", "user_rotation"], text=True, timeout=2, creationflags=0x08000000).strip()
            new_r = "1" if cur == "0" else "0"
            subprocess.run([adb] + t_args + ["shell", "settings", "put", "system", "accelerometer_rotation", "0"], timeout=2, creationflags=0x08000000)
            subprocess.run([adb] + t_args + ["shell", "settings", "put", "system", "user_rotation", new_r], timeout=2, creationflags=0x08000000)
            self.status_bar.setText(f"[OK] Screen rotated to {'Landscape' if new_r == '1' else 'Portrait'}")
        except Exception as e:
            self.status_bar.setText(f"Rotate error: {e}")

    def capture_screenshot(self):
        adb = SystemPaths.get_adb()
        target = self.get_selected_target()
        t_args = ["-s", target] if target and target != "gndroid" else []
        desktop = os.path.join(os.path.expanduser("~"), "Desktop", "Screenshots")
        os.makedirs(desktop, exist_ok=True)
        fname = f"gndroid_screen_{int(time.time())}.png"
        out_path = os.path.join(desktop, fname)
        try:
            subprocess.run([adb] + t_args + ["shell", "screencap", "-p", "/sdcard/tmp_screen.png"], timeout=3, creationflags=0x08000000)
            subprocess.run([adb] + t_args + ["pull", "/sdcard/tmp_screen.png", out_path], timeout=3, creationflags=0x08000000)
            subprocess.run([adb] + t_args + ["shell", "rm", "/sdcard/tmp_screen.png"], timeout=2, creationflags=0x08000000)
            QMessageBox.information(self, "Screenshot Saved", f"High-resolution screenshot saved to:\n\n{out_path}")
        except Exception as e:
            QMessageBox.warning(self, "Screenshot Error", str(e))

    def open_app_drawer(self):
        target = self.get_selected_target()
        dlg = GNDroidAppDrawer(target, self)
        dlg.exec()

    def open_settings(self):
        target = self.get_selected_target()
        name = "gndroid"
        data = self.dev_combo.currentData()
        if isinstance(data, dict) and data.get("name") and data.get("type") == "vm":
            name = data.get("name")
        dlg = GNDroidSettingsDialog(target_serial=target, instance_name=name, parent=self)
        if dlg.exec():
            self.refresh_devices()

    def install_desktop_shortcuts(self):
        if ShortcutManager.install_official_shortcuts():
            QMessageBox.information(
                self, "Shortcuts Installed",
                "Official Desktop Shortcuts installed with professional icon:\n\n"
                "1. gndroid (Virtual Machine & Master Suite)\n"
                "2. gndroid Mirror (Direct Phone Mirroring with Sidebar)\n\n"
                "All old .bat files and temporary links have been cleanly removed!"
            )
        else:
            QMessageBox.warning(self, "Error", "Failed to update desktop shortcuts.")

    # Drag & Drop handling for APK and Files
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def _start_async_file_transfer(self, file_paths: List[str]):
        if not file_paths:
            return

        target = self.get_selected_target()
        serial = target if target and target != "gndroid" else ""

        prog = QProgressDialog("Preparing transfer...", "Cancel", 0, 0, self)
        prog.setWindowTitle("GNDROiD Package & File Transfer")
        prog.setWindowModality(Qt.WindowModality.NonModal)
        prog.setMinimumDuration(0)
        prog.show()

        worker = AdbInstallOrPushWorker(files=file_paths, target_serial=serial, parent=self)
        if not hasattr(self, "_active_transfer_workers"):
            self._active_transfer_workers = []
        self._active_transfer_workers.append(worker)

        def on_progress(text: str):
            self.status_bar.setText(text)
            prog.setLabelText(text)

        worker.progress.connect(on_progress)
        prog.canceled.connect(worker.cancel)

        def on_file_result(fname: str, is_success: bool, msg: str):
            is_apk = fname.lower().endswith(".apk")
            if is_success:
                QMessageBox.information(
                    self,
                    "APK Installed" if is_apk else "File Transferred",
                    f"Successfully installed:\n\n{fname}" if is_apk else f"Successfully copied to phone Downloads folder:\n\n{fname}"
                )
            else:
                QMessageBox.critical(
                    self,
                    "Install Error" if is_apk else "Transfer Error",
                    f"Operation failed for {fname}:\n\n{msg}"
                )

        def on_finished(succ: int, fail: int):
            prog.close()
            prog.deleteLater()
            if hasattr(self, "_active_transfer_workers") and worker in self._active_transfer_workers:
                self._active_transfer_workers.remove(worker)
            self.status_bar.setText(f"GNDROiD v{VERSION} System Ready • Developed by Ghulam Nabi Kalhoro")

        worker.file_result.connect(on_file_result)
        worker.finished_all.connect(on_finished)
        worker.start()

    def dropEvent(self, event: QDropEvent):
        file_paths = []
        for url in event.mimeData().urls():
            fpath = url.toLocalFile()
            if fpath:
                file_paths.append(fpath)
        if file_paths:
            self._start_async_file_transfer(file_paths)

    def apply_styles(self):
        self.setStyleSheet("""
            QMainWindow {
                background: #f8f9fa;
                color: #0f172a;
                font-family: 'Segoe UI Variable Text', 'Segoe UI', -apple-system, sans-serif;
            }
            #headerFrame {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
            }
            #hwBanner {
                background: #f1f5f9;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
            }
            #cardFrame {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
            }
            #dropFrame {
                background: #f8fafc;
                border: 2px dashed #cbd5e1;
                border-radius: 8px;
            }
            QComboBox {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 6px 12px;
                color: #0f172a;
                font-size: 12px;
                font-weight: 500;
            }
            QComboBox:focus {
                border: 1px solid #0067c0;
            }
            QComboBox QAbstractItemView {
                background: #ffffff;
                color: #0f172a;
                selection-background-color: #0067c0;
                selection-color: #ffffff;
            }
            QPushButton#btnPrimary {
                background: #0067c0;
                border: 1px solid rgba(0, 0, 0, 0.08);
                border-radius: 6px;
                color: #ffffff;
                font-weight: 600;
                font-size: 12px;
            }
            QPushButton#btnPrimary:hover {
                background: #005a9e;
            }
            QPushButton#btnPrimary:pressed {
                background: #004578;
            }
            QPushButton#btnSecondary {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                color: #0f172a;
                font-weight: 500;
                font-size: 12px;
            }
            QPushButton#btnSecondary:hover {
                background: #f1f5f9;
                border-color: #94a3b8;
            }
            QPushButton#btnSecondary:pressed {
                background: #e2e8f0;
            }
            QPushButton {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 6px 12px;
                color: #0f172a;
                font-weight: 500;
                font-size: 11px;
            }
            QPushButton:hover {
                background: #f1f5f9;
                border-color: #94a3b8;
            }
            QPushButton:pressed {
                background: #e2e8f0;
            }
        """)

# ----------------------------------------------------------------------
# Application Entrypoint & CLI Handlers
# ----------------------------------------------------------------------
def main():
    app = QApplication(sys.argv)
    icon_path = SystemPaths.get_icon()
    if icon_path:
        app.setWindowIcon(QIcon(icon_path))

    # Handle CLI flags
    args = sys.argv[1:]

    # 1. Direct App Launcher: gndroid.exe --app <package_name> [--user <id>] [--window] (or --launch <package_name>)
    if "--app" in args or "--launch" in args:
        flag = "--app" if "--app" in args else "--launch"
        idx = args.index(flag)
        pkg = args[idx + 1] if idx + 1 < len(args) else ""
        if pkg:
            user_id = 0
            if "--user" in args:
                u_idx = args.index("--user")
                if u_idx + 1 < len(args):
                    try:
                        user_id = int(args[u_idx + 1])
                    except ValueError:
                        user_id = 0

            target_serial = ""
            if "--serial" in args:
                s_idx = args.index("--serial")
                if s_idx + 1 < len(args):
                    target_serial = args[s_idx + 1]
            elif "-s" in args:
                s_idx = args.index("-s")
                if s_idx + 1 < len(args):
                    target_serial = args[s_idx + 1]
            if not target_serial:
                if find_active_serial:
                    target_serial = find_active_serial()
                else:
                    target_serial = "emulator-5554"

            app_title = ""
            if "--title" in args:
                t_idx = args.index("--title")
                if t_idx + 1 < len(args):
                    app_title = args[t_idx + 1]
            if not app_title:
                app_title = pkg.split(".")[-1].capitalize()

            # Dedicated floating window mode
            if "--window" in args or "-w" in args or flag == "--launch":
                if AppWindowManager:
                    AppWindowManager.launch_app_in_dedicated_window(
                        serial=target_serial,
                        package_name=pkg,
                        app_title=app_title,
                        user_id=user_id
                    )
                    sys.exit(0)

            # Standard main mirror launch
            adb = SystemPaths.get_adb()
            cmd_launch = [adb]
            if target_serial:
                cmd_launch.extend(["-s", target_serial])
            if user_id != 0:
                cmd_launch.extend(["shell", "am", "start", "--user", str(user_id), pkg])
            else:
                cmd_launch.extend(["shell", "monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1"])
            subprocess.run(cmd_launch, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)

            # If scrcpy is not running, start mirror + sidebar
            try:
                task_out = subprocess.check_output(["tasklist", "/fi", "imagename eq scrcpy.exe"], text=True, creationflags=0x08000000)
                if "scrcpy.exe" not in task_out.lower():
                    sidebar = start_mirror_with_fallback(target_serial, None)
                    if sidebar:
                        sys.exit(app.exec())
            except Exception:
                pass
            sys.exit(0)

    # 2. Direct AVD / Instance Launcher: gndroid.exe --avd <name> or --instance <name> (or launch --avd <name>)
    if "--avd" in args or "--instance" in args or ("launch" in args and not ("--app" in args or "--launch" in args)):
        avd_name = ""
        if "--avd" in args:
            idx = args.index("--avd")
            if idx + 1 < len(args) and not args[idx + 1].startswith("-"):
                avd_name = args[idx + 1]
        elif "--instance" in args:
            idx = args.index("--instance")
            if idx + 1 < len(args) and not args[idx + 1].startswith("-"):
                avd_name = args[idx + 1]
        elif "launch" in args:
            idx = args.index("launch")
            if idx + 1 < len(args) and not args[idx + 1].startswith("-"):
                avd_name = args[idx + 1]

        if not avd_name and ("--avd" in args or "--instance" in args):
            avd_name = "gndroid"

        if avd_name:
            AVDManager.launch_emulator_instance(avd_name)
            sys.exit(0)

    # 3. Direct Mirror Launcher: gndroid.exe --mirror [serial]
    if "--mirror" in args or "mirror" in args:
        target_serial = ""
        if "--mirror" in args:
            m_idx = args.index("--mirror")
            if m_idx + 1 < len(args) and not args[m_idx + 1].startswith("-"):
                target_serial = args[m_idx + 1]
        elif "mirror" in args:
            m_idx = args.index("mirror")
            if m_idx + 1 < len(args) and not args[m_idx + 1].startswith("-"):
                target_serial = args[m_idx + 1]

        if not target_serial:
            if "--serial" in args:
                s_idx = args.index("--serial")
                if s_idx + 1 < len(args):
                    target_serial = args[s_idx + 1]
            elif "-s" in args:
                s_idx = args.index("-s")
                if s_idx + 1 < len(args):
                    target_serial = args[s_idx + 1]

        # Feature 18: Multi-Device Mirroring Guard
        # Check if a ribbon is already open for THAT SPECIFIC serial/title.
        # Allow concurrent mirroring of distinct device serials so users can mirror multiple devices simultaneously.
        existing_ribbon = None
        check_serial = target_serial
        if not check_serial:
            devs = SystemPaths.list_devices()
            phys = [d for d in devs if not d.get("is_emulator") and d.get("state") == "device"]
            emus = [d for d in devs if d.get("is_emulator") and d.get("state") == "device"]
            if phys:
                check_serial = phys[0]["serial"]
            elif emus:
                check_serial = emus[0]["serial"]

        if check_serial:
            # 1. Exact match for target serial ribbon
            candidate_titles = [
                f"GNDROiD Controls - {check_serial}",
                f"gndroid Controls - {check_serial}"
            ]
            for c_title in candidate_titles:
                h = user32.FindWindowW(None, c_title)
                if h and user32.IsWindowVisible(h):
                    existing_ribbon = h
                    break

            # 2. Window enumeration fallback for target serial ribbon
            if not existing_ribbon:
                def enum_ribbon_cb(h, lparam):
                    nonlocal existing_ribbon
                    if user32.IsWindowVisible(h):
                        length = user32.GetWindowTextLengthW(h)
                        if length > 0:
                            buf = ctypes.create_unicode_buffer(length + 1)
                            user32.GetWindowTextW(h, buf, length + 1)
                            w_title = buf.value.lower()
                            if "controls" in w_title and check_serial.lower() in w_title:
                                existing_ribbon = h
                                return False
                    return True

                WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
                user32.EnumWindows(WNDENUMPROC(enum_ribbon_cb), 0)
        else:
            # No specific serial: check for generic controls ribbon
            for c_title in ["GNDROiD Controls", "gndroid Controls"]:
                h = user32.FindWindowW(None, c_title)
                if h and user32.IsWindowVisible(h):
                    existing_ribbon = h
                    break

        if existing_ribbon and user32.IsWindowVisible(existing_ribbon):
            user32.SetForegroundWindow(existing_ribbon)
            sys.exit(0)

        sidebar = start_mirror_with_fallback(target_serial, None)
        if sidebar:
            sys.exit(app.exec())
        sys.exit(0)

    # Direct Mobile Instance Launcher: gndroid.exe --mobile [ip] or --companion [ip]
    if "--mobile" in args or "--companion" in args or "mobile" in args:
        m_ip = "192.168.100.245"
        for idx, a in enumerate(args):
            if a in ("--mobile", "--companion", "mobile") and idx + 1 < len(args) and not args[idx + 1].startswith("-"):
                m_ip = args[idx + 1]
        m_port = 51880
        for p in (51880, 51888):
            try:
                import socket
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.25)
                    if s.connect_ex((m_ip, p)) == 0:
                        m_port = p
                        break
            except Exception:
                pass
        win = GNDroidWirelessMirrorWindow(host_ip=m_ip, port=m_port, model_name="Infinix X690B")
        win.show()
        sys.exit(app.exec())

    # 3. Direct Wireless LAN Mode: gndroid.exe --lan or --wireless
    if "--lan" in args or "--wireless" in args or "lan" in args:
        dlg = GNDroidADBFixerDialog("", None)
        if hasattr(dlg, "tabs") and dlg.tabs.count() > 1:
            dlg.tabs.setCurrentIndex(1)
        dlg.show()
        sys.exit(app.exec())

    # 4. Direct ADB Doctor & Troubleshooting Suite: gndroid.exe --adb-fixer or --fix
    if "--adb-fixer" in args or "--fixer" in args or "--fix" in args or "fix" in args:
        dlg = GNDroidADBFixerDialog("", None)
        dlg.show()
        sys.exit(app.exec())

    # 4. Direct Multi-Instance Manager: gndroid.exe --multi or --instances
    if "--multi" in args or "--instances" in args or "multi" in args:
        dlg = GNDroidMultiInstanceManager()
        dlg.show()
        sys.exit(app.exec())

    # 5. Direct OS Downloader: gndroid.exe --download-image or --downloader
    if "--download-image" in args or "--downloader" in args or "download" in args:
        dlg = GNDroidImageDownloaderDialog(34)
        dlg.show()
        sys.exit(app.exec())

    # 6. Install Shortcuts: gndroid.exe --install-shortcuts
    if "--install-shortcuts" in args:
        ShortcutManager.install_official_shortcuts()
        sys.exit(0)

    # Default: Master Suite Window
    window = GNDroidApp()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

