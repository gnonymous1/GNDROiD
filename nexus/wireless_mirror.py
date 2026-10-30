"""
nexus/wireless_mirror.py — Wireless Debugging & Resilient Mirroring Engine for GNDROiD
=====================================================================================
Developed by Ghulam Nabi Kalhoro (gnkalhoro)

Provides institutional-grade hardening for Android wireless debugging, LAN phone mirroring,
and ADB diagnostics:
  1. Safe scrcpy command construction avoiding black screen lockouts:
     --turn-screen-off is STRICTLY restricted to physical USB-connected devices.
     It is NEVER appended for emulators or wireless devices.
  2. Ultra-low-latency 60 FPS performance (--video-codec=h264, --max-fps=60, --stay-awake).
  3. Audio resilience (--audio-codec=opus with seamless automatic fallback to --no-audio).
  4. Fast (<1.5s) pre-flight TCP verification for Wi-Fi endpoints.
  5. Comprehensive ADB Doctor LAN diagnostic reporting (port 5555, Wi-Fi subnet, and mDNS).
"""

import os
import sys
import re
import time
import socket
import shutil
import io
import secrets
import random
import threading
import subprocess
from typing import Optional, List, Dict, Any, Callable, Tuple

try:
    import qrcode
except ImportError:
    qrcode = None

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    from PyQt6.QtGui import QPixmap, QImage
except ImportError:
    QPixmap = None
    QImage = None


# -----------------------------------------------------------------------------
# Binary Resolution Helpers
# -----------------------------------------------------------------------------
def find_scrcpy_binary() -> str:
    """Locates scrcpy executable across workspace, bundled dist, or system PATH."""
    cwd = os.getcwd()
    module_dir = os.path.dirname(os.path.abspath(__file__))
    workspace_root = os.path.dirname(module_dir)

    search_roots = [cwd, workspace_root, module_dir]
    for root in search_roots:
        candidates = [
            os.path.join(root, "scrcpy.exe"),
            os.path.join(root, "scrcpy", "scrcpy.exe"),
            os.path.join(root, "dist", "gndroid", "scrcpy.exe"),
            os.path.join(root, "dist", "AndroidMobilePlayer", "scrcpy.exe"),
        ]
        for cand in candidates:
            if os.path.isfile(cand):
                return os.path.abspath(cand)

    which = shutil.which("scrcpy")
    if which:
        return which
    return "scrcpy"


def find_adb_binary() -> str:
    """Locates adb executable across workspace, bundled dist, or system PATH."""
    cwd = os.getcwd()
    module_dir = os.path.dirname(os.path.abspath(__file__))
    workspace_root = os.path.dirname(module_dir)

    search_roots = [cwd, workspace_root, module_dir]
    for root in search_roots:
        candidates = [
            os.path.join(root, "adb.exe"),
            os.path.join(root, "scrcpy", "adb.exe"),
            os.path.join(root, "dist", "gndroid", "adb.exe"),
            os.path.join(root, "dist", "AndroidMobilePlayer", "adb.exe"),
        ]
        for cand in candidates:
            if os.path.isfile(cand):
                return os.path.abspath(cand)

    which = shutil.which("adb")
    if which:
        return which
    return "adb"


# -----------------------------------------------------------------------------
# Wireless Mirror Manager
# -----------------------------------------------------------------------------
class WirelessMirrorManager:
    """
    High-performance manager for resilient Android screen mirroring over
    USB, Wi-Fi LAN, and virtual emulator instances.
    """

    def __init__(self, scrcpy_bin: Optional[str] = None, adb_bin: Optional[str] = None):
        self.scrcpy_bin = scrcpy_bin or find_scrcpy_binary()
        self.adb_bin = adb_bin or find_adb_binary()
        self.last_process: Optional[subprocess.Popen] = None
        self.last_command: List[str] = []
        self.fallback_occurred: bool = False

    @staticmethod
    def build_scrcpy_command(
        serial: str = "",
        is_emulator: bool = False,
        is_wireless: bool = False,
        title: str = "",
        enable_audio: bool = True,
        scrcpy_bin: Optional[str] = None
    ) -> List[str]:
        """
        Constructs hardened scrcpy arguments according to strict safety rules:
        - Key rule: --turn-screen-off must ONLY be included for physical USB-connected devices.
          It must NEVER be included if is_emulator is True or is_wireless is True
          (to avoid black screen lockouts).
        - Audio safety: includes --audio-codec=opus if enable_audio is True, or --no-audio if False.
        - Performance: includes --max-fps=60, --video-codec=h264, --stay-awake.
        - Title: custom title or 'GNDROiD - {serial}'.
        """
        bin_path = scrcpy_bin or find_scrcpy_binary()
        clean_serial = serial.strip() if serial else ""

        # Auto-detect flags from serial pattern if flags were left at default False
        detected_is_emulator = is_emulator or (
            clean_serial.startswith("emulator-")
            or "127.0.0.1:" in clean_serial
            or "localhost:" in clean_serial
        )
        detected_is_wireless = is_wireless or (
            (":" in clean_serial) and not detected_is_emulator
        )

        cmd: List[str] = [bin_path]

        # Serial specification
        if clean_serial:
            cmd.extend(["-s", clean_serial])

        # Window title specification
        if title:
            window_title = title
        elif clean_serial:
            window_title = f"GNDROiD - {clean_serial}"
        else:
            window_title = "GNDROiD"
        cmd.append(f"--window-title={window_title}")

        # Low-latency 60 FPS performance flags
        cmd.append("--video-codec=h264")
        cmd.append("--max-fps=60")

        # Audio safety
        if enable_audio:
            cmd.append("--audio-codec=opus")
        else:
            cmd.append("--no-audio")

        # CRITICAL SAFETY RULE:
        # --turn-screen-off must ONLY be included for physical USB devices.
        # NEVER include for emulators or wireless Wi-Fi devices.
        is_physical_usb = (
            not is_emulator
            and not is_wireless
            and not detected_is_emulator
            and not detected_is_wireless
        )
        if is_physical_usb:
            cmd.append("--turn-screen-off")

        # Keep device awake during active session
        cmd.append("--stay-awake")

        return cmd

    @staticmethod
    def validate_wireless_connection(ip_port: str, timeout: float = 1.5) -> bool:
        """
        Checks TCP connectivity to the IP and port (e.g. 5555 or paired port)
        within 1.5s before attempting mirror.
        """
        if not ip_port or not isinstance(ip_port, str):
            return False

        target = ip_port.strip()
        if not target:
            return False

        if ":" in target:
            parts = target.split(":")
            host = parts[0].strip()
            try:
                port = int(parts[1].strip())
            except (ValueError, IndexError):
                return False
        else:
            host = target
            port = 5555

        if not host or not (1 <= port <= 65535):
            return False

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(timeout)
                return sock.connect_ex((host, port)) == 0
        except Exception:
            return False

    @staticmethod
    def is_audio_or_reset_error(stderr_text: str) -> bool:
        """
        Determines whether the given stderr output indicates an audio recording/playback failure
        or a connection reset.
        """
        if not stderr_text:
            return True

        lower = stderr_text.lower()
        error_indicators = [
            "audio",
            "opus",
            "demuxer",
            "could not record audio",
            "audio initialization failed",
            "failed to start audio",
            "audiorecord",
            "audio disabled",
            "sound",
            "playback",
            "connection reset",
            "reset by peer",
            "wsaeconnreset",
            "connection refused",
            "broken pipe",
            "device disconnected",
            "server connection failed",
        ]
        return any(indicator in lower for indicator in error_indicators)

    def _spawn_scrcpy(self, cmd: List[str], creation_flags: int) -> subprocess.Popen:
        """Internal helper to spawn scrcpy process."""
        return subprocess.Popen(
            cmd,
            creationflags=creation_flags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE
        )

    def launch_resilient_mirror(
        self,
        serial: str = "",
        parent: Any = None,
        enable_audio: bool = True,
        title: str = "",
        scrcpy_bin: Optional[str] = None,
        sync_probe: Optional[bool] = None,
        probe_timeout: float = 2.0,
        on_fallback: Optional[Callable[[List[str]], None]] = None
    ) -> Optional[subprocess.Popen]:
        """
        Launches scrcpy with the appropriate flags.
        If the process terminates in under 2 seconds with an audio error or connection reset,
        automatically restarts with --no-audio as a seamless fallback.

        Parameters:
        - serial: Target ADB serial (USB serial, emulator ID, or IP:Port).
        - parent: Optional parent Qt widget or sidebar reference.
        - enable_audio: Whether to initially request Opus audio stream.
        - title: Optional custom window title.
        - scrcpy_bin: Optional custom scrcpy binary path.
        - sync_probe: If True, waits up to probe_timeout for early exit.
                      If None, defaults to True when parent is None (headless/CLI/test),
                      or False when parent is provided (GUI responsive thread).
        - probe_timeout: Detection window for early exit (default 2.0s).
        - on_fallback: Optional callback receiving the fallback command list.
        """
        bin_path = scrcpy_bin or self.scrcpy_bin or find_scrcpy_binary()
        clean_serial = serial.strip() if serial else ""

        # Infer connection topology
        is_emu = (
            clean_serial.startswith("emulator-")
            or "127.0.0.1:" in clean_serial
            or "localhost:" in clean_serial
        )
        is_lan = (":" in clean_serial) and not is_emu

        # Pre-connect wireless device via ADB if needed
        if is_lan and clean_serial:
            try:
                adb = self.adb_bin or find_adb_binary()
                # Run fast non-blocking connect check
                subprocess.run(
                    [adb, "connect", clean_serial],
                    capture_output=True,
                    timeout=2.0,
                    creationflags=0x08000000 if sys.platform == "win32" else 0
                )
            except Exception:
                pass

        # Build primary command with initial audio preference
        primary_cmd = self.build_scrcpy_command(
            serial=clean_serial,
            is_emulator=is_emu,
            is_wireless=is_lan,
            title=title,
            enable_audio=enable_audio,
            scrcpy_bin=bin_path
        )
        self.last_command = primary_cmd
        self.fallback_occurred = False

        creation_flags = 0x08000000 if sys.platform == "win32" else 0

        try:
            proc = self._spawn_scrcpy(primary_cmd, creation_flags)
            self.last_process = proc
        except Exception as e:
            print(f"[WirelessMirror] Failed to spawn scrcpy: {e}", file=sys.stderr)
            return None

        # Determine probing mode
        should_sync = (parent is None) if (sync_probe is None) else sync_probe

        if should_sync:
            # Synchronous probe: poll for early exit up to probe_timeout
            start_time = time.time()
            failed_early = False
            stderr_captured = ""

            while time.time() - start_time < probe_timeout:
                if proc.poll() is not None:
                    failed_early = True
                    try:
                        raw_err = proc.stderr.read() if proc.stderr else b""
                        stderr_captured = raw_err.decode("utf-8", errors="ignore")
                    except Exception:
                        pass
                    break
                time.sleep(0.05)

            if failed_early and proc.returncode != 0:
                if self.is_audio_or_reset_error(stderr_captured) and enable_audio:
                    print(
                        f"[WirelessMirror] scrcpy exited in <{probe_timeout}s with audio/reset error. "
                        "Seamlessly restarting with --no-audio fallback...",
                        file=sys.stderr
                    )
                    self.fallback_occurred = True
                    fallback_cmd = self.build_scrcpy_command(
                        serial=clean_serial,
                        is_emulator=is_emu,
                        is_wireless=is_lan,
                        title=title,
                        enable_audio=False,
                        scrcpy_bin=bin_path
                    )
                    self.last_command = fallback_cmd
                    if on_fallback:
                        try:
                            on_fallback(fallback_cmd)
                        except Exception:
                            pass

                    try:
                        fallback_proc = self._spawn_scrcpy(fallback_cmd, creation_flags)
                        self.last_process = fallback_proc
                        return fallback_proc
                    except Exception as e:
                        print(f"[WirelessMirror] Fallback spawn failed: {e}", file=sys.stderr)
                        return None
            return proc

        else:
            # Asynchronous background monitor for interactive Qt UI
            def _async_monitor():
                time.sleep(probe_timeout)
                if proc.poll() is not None and proc.returncode != 0:
                    raw_err = b""
                    try:
                        if proc.stderr:
                            raw_err = proc.stderr.read()
                    except Exception:
                        pass
                    stderr_txt = raw_err.decode("utf-8", errors="ignore")

                    if self.is_audio_or_reset_error(stderr_txt) and enable_audio:
                        print(
                            f"[WirelessMirror] Early termination detected. Auto-relaunching with --no-audio...",
                            file=sys.stderr
                        )
                        self.fallback_occurred = True
                        fallback_cmd = self.build_scrcpy_command(
                            serial=clean_serial,
                            is_emulator=is_emu,
                            is_wireless=is_lan,
                            title=title,
                            enable_audio=False,
                            scrcpy_bin=bin_path
                        )
                        self.last_command = fallback_cmd
                        if on_fallback:
                            try:
                                on_fallback(fallback_cmd)
                            except Exception:
                                pass

                        try:
                            fallback_proc = self._spawn_scrcpy(fallback_cmd, creation_flags)
                            self.last_process = fallback_proc
                            if parent and hasattr(parent, "scrcpy_proc"):
                                parent.scrcpy_proc = fallback_proc
                        except Exception:
                            pass

            monitor_thread = threading.Thread(target=_async_monitor, daemon=True)
            monitor_thread.start()
            return proc


# -----------------------------------------------------------------------------
# ADB Doctor & LAN Diagnostic Helper
# -----------------------------------------------------------------------------
def get_lan_diagnostic_info(adb_bin: Optional[str] = None) -> Dict[str, Any]:
    """
    Comprehensive ADB Doctor LAN diagnostic reporting helper:
    - Checks port 5555 (listening status, conflicting processes, connected ADB devices).
    - Checks Wi-Fi / LAN subnet IP (local host IP, subnet CIDR prefix, connected phone IP).
    - Checks mDNS pairing state (daemon availability, pairing/connect services discovered).
    """
    adb = adb_bin or find_adb_binary()
    creation_flags = 0x08000000 if sys.platform == "win32" else 0

    # 1. Port 5555 Inspection
    port_5555_listening = False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.35)
            port_5555_listening = (s.connect_ex(("127.0.0.1", 5555)) == 0)
    except Exception:
        pass

    port_5555_conflicts: List[Dict[str, str]] = []
    try:
        netstat_out = subprocess.check_output(
            ["netstat", "-ano"],
            text=True,
            timeout=3.0,
            creationflags=creation_flags
        )
        for line in netstat_out.splitlines():
            if ":5555 " in line and "LISTENING" in line:
                parts = line.split()
                pid = parts[-1] if parts else "Unknown"
                port_5555_conflicts.append({"raw": line.strip(), "pid": pid})
    except Exception:
        pass

    port_5555_devices: List[str] = []
    try:
        dev_out = subprocess.check_output(
            [adb, "devices"],
            text=True,
            timeout=3.0,
            creationflags=creation_flags
        )
        for line in dev_out.splitlines()[1:]:
            line = line.strip()
            if ":5555" in line:
                port_5555_devices.append(line.split()[0])
    except Exception:
        pass

    # 2. Host and Subnet IP Discovery
    host_ip = "127.0.0.1"
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            host_ip = s.getsockname()[0]
    except Exception:
        try:
            host_ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            pass

    if host_ip and host_ip != "127.0.0.1":
        subnet_prefix = ".".join(host_ip.split(".")[:3]) + "."
    else:
        subnet_prefix = "192.168.1."

    phone_lan_ip: Optional[str] = None
    try:
        dev_lines = subprocess.check_output(
            [adb, "devices"],
            text=True,
            timeout=3.0,
            creationflags=creation_flags
        ).splitlines()[1:]

        for line in dev_lines:
            parts = line.strip().split()
            if len(parts) >= 2 and parts[1] == "device":
                d_serial = parts[0]
                if ":" in d_serial:
                    phone_lan_ip = d_serial.split(":")[0]
                    break
                else:
                    # Query wlan0 interface
                    try:
                        ip_out = subprocess.check_output(
                            [adb, "-s", d_serial, "shell", "ip -f inet addr show wlan0"],
                            text=True,
                            timeout=2.0,
                            creationflags=creation_flags
                        )
                        m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", ip_out)
                        if m:
                            phone_lan_ip = m.group(1)
                            break
                    except Exception:
                        pass
    except Exception:
        pass

    # 3. mDNS Service & Pairing State Inspection
    mdns_supported = False
    mdns_check_text = ""
    try:
        check_out = subprocess.check_output(
            [adb, "mdns", "check"],
            text=True,
            timeout=3.0,
            creationflags=creation_flags
        ).strip()
        mdns_check_text = check_out
        if "mdns daemon version" in check_out.lower() or "adb discovery" in check_out.lower():
            mdns_supported = True
    except Exception:
        pass

    mdns_services: List[Dict[str, Any]] = []
    mdns_pairing_active = False
    try:
        svc_out = subprocess.check_output(
            [adb, "mdns", "services"],
            text=True,
            timeout=3.0,
            creationflags=creation_flags
        )
        for line in svc_out.splitlines():
            line = line.strip()
            if not line or "List of discovered" in line:
                continue
            parts = line.split()
            if len(parts) >= 3:
                name = parts[0]
                svc_type = parts[1]
                addr = parts[2]
                is_pairing = ("pairing" in svc_type.lower() or "pairing" in name.lower())
                if is_pairing:
                    mdns_pairing_active = True
                mdns_services.append({
                    "name": name,
                    "service_type": svc_type,
                    "address": addr,
                    "is_pairing": is_pairing
                })
    except Exception:
        pass

    # Generate institutional summary string
    port_status = "In Use (Listening)" if port_5555_listening else "Available / Unbound"
    mdns_status = (
        f"Available ({len(mdns_services)} services, pairing={'Active' if mdns_pairing_active else 'Idle'})"
        if mdns_supported else "Unavailable"
    )
    summary = (
        f"Subnet: {subnet_prefix}0/24 | Host IP: {host_ip} | "
        f"Port 5555: {port_status} | mDNS: {mdns_status}"
    )

    return {
        # High-level summary
        "summary": summary,
        "ready_for_wireless": (host_ip != "127.0.0.1"),

        # Top-level direct keys for convenience
        "port_5555_listening": port_5555_listening,
        "port_5555_conflicts": port_5555_conflicts,
        "port_5555_devices": port_5555_devices,
        "host_ip": host_ip,
        "subnet_prefix": subnet_prefix,
        "phone_lan_ip": phone_lan_ip,
        "mdns_supported": mdns_supported,
        "mdns_pairing_active": mdns_pairing_active,
        "mdns_services": mdns_services,
        "mdns_check_text": mdns_check_text,

        # Structured namespaces
        "port_5555": {
            "listening": port_5555_listening,
            "conflicts": port_5555_conflicts,
            "connected_devices": port_5555_devices,
            "status": port_status
        },
        "wifi_subnet": {
            "host_ip": host_ip,
            "subnet_prefix": subnet_prefix,
            "phone_lan_ip": phone_lan_ip,
            "has_local_ip": (host_ip != "127.0.0.1")
        },
        "mdns": {
            "supported": mdns_supported,
            "pairing_active": mdns_pairing_active,
            "services": mdns_services,
            "check_output": mdns_check_text
        }
    }


# Attach helper to class for both static and module-level invocation
WirelessMirrorManager.get_lan_diagnostic_info = staticmethod(get_lan_diagnostic_info)


# -----------------------------------------------------------------------------
# Wireless Pairing Engine (Android 11+ SPAKE2 QR & 1-Click TCP 5555)
# -----------------------------------------------------------------------------
class WirelessPairingEngine:
    """
    Dual-engine wireless debugging pairing and provisioning engine for GNDROiD:
    1. AOSP Android 11+ SPAKE2 QR Code Zero-Cable Pairing Engine with mDNS service discovery
       (_adb-tls-pairing._tcp and _adb-tls-connect._tcp).
    2. 1-Click TCP 5555 Provisioning Engine with automatic LAN IP discovery and mode switching.
    """

    @staticmethod
    def generate_pairing_credentials(
        service_name: Optional[str] = None,
        password: Optional[str] = None
    ) -> Tuple[str, str, str]:
        """
        Generates standard Android 11+ pairing credentials and AOSP QR payload schema:
        WIFI:T:ADB;S:<service_name>;P:<password>;;
        """
        if not service_name:
            rand_id = secrets.token_hex(2).upper()
            service_name = f"GNDROiD-{rand_id}"

        if not password:
            password = f"{secrets.randbelow(900000) + 100000}"

        payload = f"WIFI:T:ADB;S:{service_name};P:{password};;"
        return service_name, password, payload

    @staticmethod
    def generate_qr_payload(service_name: str, pin: str) -> str:
        """Adheres to the interface contract specified in PROJECT.md."""
        return f"WIFI:T:ADB;S:{service_name.strip()};P:{pin.strip()};;"

    @staticmethod
    def generate_qr_image(payload: str, box_size: int = 5, border: int = 2):
        """Generates a PIL Image of the QR code with 1:1 aspect ratio."""
        if qrcode is None:
            raise RuntimeError("The 'qrcode' package is required for QR code image generation.")
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=box_size,
            border=border,
        )
        qr.add_data(payload)
        qr.make(fit=True)
        return qr.make_image(fill_color="#0f172a", back_color="#ffffff")

    @staticmethod
    def generate_qr_png_bytes(payload: str, box_size: int = 5, border: int = 2) -> bytes:
        """Returns raw PNG bytes of the generated QR code."""
        img = WirelessPairingEngine.generate_qr_image(payload, box_size, border)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    @staticmethod
    def generate_qr_pixmap(payload: str, box_size: int = 5, border: int = 2):
        """Generates a QPixmap for PyQt6 GUI components."""
        raw_bytes = WirelessPairingEngine.generate_qr_png_bytes(payload, box_size, border)
        if QPixmap is not None:
            pix = QPixmap()
            pix.loadFromData(raw_bytes)
            return pix
        return None

    @staticmethod
    def discover_mdns_services(
        adb_bin: Optional[str] = None,
        timeout: float = 2.5
    ) -> List[Dict[str, Any]]:
        """
        Queries ADB daemon for discovered mDNS services (_adb-tls-pairing and _adb-tls-connect).
        """
        adb = adb_bin or find_adb_binary()
        creation_flags = 0x08000000 if sys.platform == "win32" else 0
        services: List[Dict[str, Any]] = []

        try:
            out = subprocess.check_output(
                [adb, "mdns", "services"],
                text=True,
                timeout=timeout,
                creationflags=creation_flags
            )
            for line in out.splitlines():
                line = line.strip()
                if not line or "List of discovered" in line:
                    continue
                parts = line.split()
                if len(parts) >= 3:
                    name = parts[0]
                    svc_type = parts[1]
                    addr = parts[2]
                    host = addr.split(":")[0] if ":" in addr else addr
                    port = int(addr.split(":")[1]) if ":" in addr and addr.split(":")[1].isdigit() else 0
                    is_pair = ("pairing" in svc_type.lower() or "pairing" in name.lower())
                    is_conn = ("connect" in svc_type.lower() or "connect" in name.lower())
                    services.append({
                        "name": name,
                        "service_type": svc_type,
                        "address": addr,
                        "host": host,
                        "port": port,
                        "is_pairing": is_pair,
                        "is_connect": is_conn,
                    })
        except Exception:
            pass

        return services

    @classmethod
    def discover_pairing_service(
        cls,
        target_service_name: Optional[str] = None,
        adb_bin: Optional[str] = None,
        timeout: float = 2.5
    ) -> Optional[Dict[str, Any]]:
        """Discovers the active _adb-tls-pairing service on the local network."""
        services = cls.discover_mdns_services(adb_bin=adb_bin, timeout=timeout)
        for svc in services:
            if svc.get("is_pairing"):
                if target_service_name:
                    if target_service_name.lower() in svc["name"].lower():
                        return svc
                else:
                    return svc
        return None

    @classmethod
    def discover_connect_service(
        cls,
        ip_filter: Optional[str] = None,
        adb_bin: Optional[str] = None,
        timeout: float = 2.5
    ) -> Optional[Dict[str, Any]]:
        """Discovers the active _adb-tls-connect service matching an IP address."""
        services = cls.discover_mdns_services(adb_bin=adb_bin, timeout=timeout)
        for svc in services:
            if svc.get("is_connect"):
                if ip_filter:
                    if ip_filter in svc["address"]:
                        return svc
                else:
                    return svc
        return None

    @staticmethod
    def pair_device(
        host_port: str,
        password: str,
        adb_bin: Optional[str] = None,
        timeout: float = 6.0
    ) -> Tuple[bool, str]:
        """
        Executes 'adb pair <host_port> <password>'.
        Returns (success: bool, output_message: str).
        """
        adb = adb_bin or find_adb_binary()
        creation_flags = 0x08000000 if sys.platform == "win32" else 0
        clean_target = host_port.strip()
        clean_pwd = password.strip()

        try:
            proc = subprocess.run(
                [adb, "pair", clean_target, clean_pwd],
                capture_output=True,
                text=True,
                timeout=timeout,
                creationflags=creation_flags
            )
            output = (proc.stdout or "") + (proc.stderr or "")
            success = "successfully paired" in output.lower() or "paired" in output.lower()
            return success, output.strip()
        except subprocess.TimeoutExpired:
            return False, f"Pairing timed out after {timeout}s."
        except Exception as e:
            return False, f"Pairing execution failed: {e}"

    @staticmethod
    def connect_device(
        host_port: str,
        adb_bin: Optional[str] = None,
        timeout: float = 6.0
    ) -> Tuple[bool, str]:
        """
        Executes 'adb connect <host_port>'.
        Returns (success: bool, output_message: str).
        """
        adb = adb_bin or find_adb_binary()
        creation_flags = 0x08000000 if sys.platform == "win32" else 0
        clean_target = host_port.strip()

        try:
            proc = subprocess.run(
                [adb, "connect", clean_target],
                capture_output=True,
                text=True,
                timeout=timeout,
                creationflags=creation_flags
            )
            output = (proc.stdout or "") + (proc.stderr or "")
            success = "connected to" in output.lower() or "already connected" in output.lower()
            return success, output.strip()
        except subprocess.TimeoutExpired:
            return False, f"Connection timed out after {timeout}s."
        except Exception as e:
            return False, f"Connection execution failed: {e}"

    @classmethod
    def pair_and_connect(
        cls,
        pairing_host_port: str,
        password: str,
        connect_host_port: Optional[str] = None,
        adb_bin: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Full AOSP pairing & connection workflow:
        1. Executes adb pair <pairing_host_port> <password>.
        2. Resolves connection endpoint via mDNS _adb-tls-connect or supplied host_port.
        3. Executes adb connect <connect_target>.
        """
        paired, p_msg = cls.pair_device(pairing_host_port, password, adb_bin=adb_bin)
        if not paired:
            return False, f"Pairing failed: {p_msg}"

        time.sleep(0.5)

        target_ip = pairing_host_port.split(":")[0] if ":" in pairing_host_port else pairing_host_port
        target_connect = connect_host_port

        if not target_connect:
            connect_svc = cls.discover_connect_service(ip_filter=target_ip, adb_bin=adb_bin)
            if connect_svc:
                target_connect = connect_svc["address"]
            else:
                target_connect = f"{target_ip}:5555"

        connected, c_msg = cls.connect_device(target_connect, adb_bin=adb_bin)
        if connected:
            return True, f"Successfully paired with {pairing_host_port} and connected to {target_connect}."
        return False, f"Paired with {pairing_host_port}, but connect to {target_connect} failed: {c_msg}"

    @staticmethod
    def query_device_lan_ip(serial: str, adb_bin: Optional[str] = None) -> Optional[str]:
        """
        Queries connected device LAN IP address via wlan0, ip route, or dhcp properties.
        """
        adb = adb_bin or find_adb_binary()
        creation_flags = 0x08000000 if sys.platform == "win32" else 0
        clean_serial = serial.strip()
        cmd_prefix = [adb]
        if clean_serial:
            cmd_prefix.extend(["-s", clean_serial])

        # Method 1: ip -f inet addr show wlan0
        try:
            out = subprocess.check_output(
                cmd_prefix + ["shell", "ip -f inet addr show wlan0"],
                text=True,
                timeout=2.0,
                creationflags=creation_flags
            )
            m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", out)
            if m:
                ip = m.group(1)
                if ip and not ip.startswith("127."):
                    return ip
        except Exception:
            pass

        # Method 2: ip route get 8.8.8.8
        try:
            out = subprocess.check_output(
                cmd_prefix + ["shell", "ip route get 8.8.8.8"],
                text=True,
                timeout=2.0,
                creationflags=creation_flags
            )
            m = re.search(r"src (\d+\.\d+\.\d+\.\d+)", out)
            if m:
                ip = m.group(1)
                if ip and not ip.startswith("127."):
                    return ip
        except Exception:
            pass

        # Method 3: getprop dhcp.wlan0.ipaddress
        try:
            out = subprocess.check_output(
                cmd_prefix + ["shell", "getprop dhcp.wlan0.ipaddress"],
                text=True,
                timeout=2.0,
                creationflags=creation_flags
            ).strip()
            if out and re.match(r"^\d+\.\d+\.\d+\.\d+$", out) and not out.startswith("127."):
                return out
        except Exception:
            pass

        return None

    @staticmethod
    def enable_tcpip_mode(
        serial: str,
        port: int = 5555,
        adb_bin: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Switches connected device to TCP/IP listening mode on specified port.
        """
        adb = adb_bin or find_adb_binary()
        creation_flags = 0x08000000 if sys.platform == "win32" else 0
        clean_serial = serial.strip()
        cmd = [adb]
        if clean_serial:
            cmd.extend(["-s", clean_serial])
        cmd.extend(["tcpip", str(port)])

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5.0,
                creationflags=creation_flags
            )
            out = (proc.stdout or "") + (proc.stderr or "")
            success = "restarting in tcp mode" in out.lower() or proc.returncode == 0
            return success, out.strip()
        except Exception as e:
            return False, f"Failed to execute tcpip: {e}"

    @classmethod
    def provision_tcp_5555(
        cls,
        serial: str,
        port: int = 5555,
        adb_bin: Optional[str] = None
    ) -> Tuple[bool, str, Optional[str]]:
        """
        1-Click TCP 5555 Provisioning pipeline:
        1. Detects device wlan0 / LAN IP.
        2. Issues 'adb -s <serial> tcpip <port>'.
        3. Waits for daemon restart and executes 'adb connect <ip>:<port>'.
        Returns (success: bool, status_message: str, connect_target: Optional[str]).
        """
        ip = cls.query_device_lan_ip(serial, adb_bin=adb_bin)
        if not ip:
            return False, f"Could not determine Wi-Fi LAN IP address for '{serial}'. Verify device is on Wi-Fi.", None

        ok, msg = cls.enable_tcpip_mode(serial, port=port, adb_bin=adb_bin)
        if not ok:
            return False, f"Failed to switch device to TCP mode: {msg}", None

        time.sleep(1.2)  # Allow adbd daemon to restart in TCP socket mode

        target = f"{ip}:{port}"
        conn_ok, conn_msg = cls.connect_device(target, adb_bin=adb_bin)
        if conn_ok:
            return True, f"Successfully provisioned wireless ADB: connected to {target}.", target
        return False, f"Device switched to TCP mode on {target}, but initial connect returned: {conn_msg}", target


# -----------------------------------------------------------------------------
# Wireless Reconnection Watchdog
# -----------------------------------------------------------------------------
class WirelessReconnectionWatchdog:
    """
    Resilient background watchdog thread that monitors active wireless ADB connections,
    detects Wi-Fi network drops or AP roaming, and automatically re-establishes
    dropped connections with backoff.
    """

    def __init__(
        self,
        targets: Optional[List[str]] = None,
        check_interval: float = 3.0,
        adb_bin: Optional[str] = None,
        on_status_change: Optional[Callable[[str, bool, str], None]] = None
    ):
        self.targets = set(t.strip() for t in targets) if targets else set()
        self.check_interval = max(1.0, check_interval)
        self.adb_bin = adb_bin or find_adb_binary()
        self.on_status_change = on_status_change
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._target_states: Dict[str, bool] = {}
        self._lock = threading.Lock()
        self._retry_counts: Dict[str, int] = {}

    def add_target(self, target: str):
        """Adds a target endpoint (e.g., '192.168.1.150:5555') to the watchdog."""
        with self._lock:
            self.targets.add(target.strip())
            self._retry_counts[target.strip()] = 0

    def remove_target(self, target: str):
        """Removes a target endpoint from monitoring."""
        with self._lock:
            self.targets.discard(target.strip())
            if target.strip() in self._target_states:
                del self._target_states[target.strip()]
            if target.strip() in self._retry_counts:
                del self._retry_counts[target.strip()]

    def is_target_alive(self, target: str) -> bool:
        """Lightweight TCP ping probe followed by ADB state verification."""
        if ":" in target:
            parts = target.split(":")
            host = parts[0]
            try:
                port = int(parts[1])
            except ValueError:
                port = 5555
        else:
            host = target
            port = 5555

        # Phase 1: Fast TCP socket probe (<350ms)
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.35)
                if s.connect_ex((host, port)) != 0:
                    return False
        except Exception:
            return False

        # Phase 2: Check adb get-state
        adb = self.adb_bin
        creation_flags = 0x08000000 if sys.platform == "win32" else 0
        try:
            proc = subprocess.run(
                [adb, "-s", target, "get-state"],
                capture_output=True,
                text=True,
                timeout=1.5,
                creationflags=creation_flags
            )
            return proc.returncode == 0 and "device" in proc.stdout.lower()
        except Exception:
            return False

    def reconnect_target(self, target: str) -> bool:
        """Attempts to reconnect a dropped wireless target via 'adb connect <target>'."""
        adb = self.adb_bin
        creation_flags = 0x08000000 if sys.platform == "win32" else 0
        try:
            proc = subprocess.run(
                [adb, "connect", target],
                capture_output=True,
                text=True,
                timeout=3.0,
                creationflags=creation_flags
            )
            out = (proc.stdout or "") + (proc.stderr or "")
            return "connected to" in out.lower() or "already connected" in out.lower()
        except Exception:
            return False

    def start(self):
        """Starts the background monitoring watchdog thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="WirelessReconnectionWatchdog"
        )
        self._thread.start()

    def stop(self, timeout: float = 2.0):
        """Stops the background watchdog thread cleanly."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def is_alive(self) -> bool:
        """Returns True if watchdog thread is actively running."""
        return self._running and self._thread is not None and self._thread.is_alive()

    def _run_loop(self):
        while self._running:
            with self._lock:
                current_targets = list(self.targets)

            for target in current_targets:
                if not self._running:
                    break

                was_alive = self._target_states.get(target, True)
                is_alive = self.is_target_alive(target)

                if is_alive:
                    self._retry_counts[target] = 0
                    if not was_alive:
                        self._target_states[target] = True
                        if self.on_status_change:
                            try:
                                self.on_status_change(target, True, f"Target {target} restored connection.")
                            except Exception:
                                pass
                else:
                    self._target_states[target] = False
                    retries = self._retry_counts.get(target, 0) + 1
                    self._retry_counts[target] = retries

                    reconnected = self.reconnect_target(target)
                    if reconnected:
                        self._target_states[target] = True
                        self._retry_counts[target] = 0
                        if self.on_status_change:
                            try:
                                self.on_status_change(target, True, f"Target {target} automatically reconnected.")
                            except Exception:
                                pass
                    else:
                        if was_alive or (retries % 5 == 1):
                            if self.on_status_change:
                                try:
                                    self.on_status_change(
                                        target,
                                        False,
                                        f"Target {target} unreachable. Reconnection attempt #{retries} failed."
                                    )
                                except Exception:
                                    pass

            slices = int(self.check_interval * 10)
            for _ in range(slices):
                if not self._running:
                    break
                time.sleep(0.1)


__all__ = [
    "WirelessMirrorManager",
    "get_lan_diagnostic_info",
    "WirelessPairingEngine",
    "WirelessReconnectionWatchdog",
    "find_adb_binary",
    "find_scrcpy_binary",
]
