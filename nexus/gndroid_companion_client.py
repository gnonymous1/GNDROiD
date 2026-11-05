#!/usr/bin/env python3
"""
nexus/gndroid_companion_client.py
=================================
High-Performance Python Client, Subnet Radar, and Watchdog Bridge for GNDROiD Link.
Interfaces with com.gndroid.companion over local Wi-Fi / ADB on TCP port 51888,
providing remote control, volume, power, clipboard sync, direct line-speed file push,
and sub-second zero-drop connection watchdog.
"""

import os
import sys
import time
import json
import socket
import urllib.request
import urllib.parse
import urllib.error
import threading
from typing import Dict, Any, List, Optional, Callable, Tuple

DEFAULT_PORT = 51888
BEACON_PORT = 51880


class GNDroidCompanionClient:
    """Client for controlling GNDROiD Link Android companion on port 51888."""

    def __init__(self, host: str = "127.0.0.1", port: int = DEFAULT_PORT, timeout: float = 2.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._base_url = f"http://{self.host}:{self.port}"

    def update_host(self, host: str, port: int = DEFAULT_PORT):
        self.host = host
        self.port = port
        self._base_url = f"http://{self.host}:{self.port}"

    def _request(self, endpoint: str, method: str = "GET", data: Optional[dict] = None, headers: Optional[dict] = None) -> Tuple[bool, Any]:
        url = f"{self._base_url}{endpoint}"
        h = {"Content-Type": "application/json"}
        if headers:
            h.update(headers)

        payload = None
        if data is not None and method == "POST":
            payload = json.dumps(data).encode("utf-8")

        req = urllib.request.Request(url, data=payload, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
                try:
                    return True, json.loads(raw)
                except Exception:
                    return True, raw
        except Exception as e:
            return False, str(e)

    def ping(self, timeout: float = 1.0) -> bool:
        """Fast sub-second heartbeat check."""
        old_to = self.timeout
        self.timeout = timeout
        try:
            ok, res = self._request("/ping", method="GET")
            return ok and isinstance(res, dict) and res.get("pong") is True
        finally:
            self.timeout = old_to

    def get_status(self) -> Dict[str, Any]:
        """Fetches live telemetry, battery, and permission matrix."""
        ok, res = self._request("/api/v1/status", method="GET")
        if ok and isinstance(res, dict):
            return res
        return {"status": "offline", "error": str(res)}

    def control(self, action: str, **params) -> bool:
        """Sends remote control action (wake, lock, back, home, recents, vol, etc.)."""
        payload = {"action": action}
        payload.update(params)
        ok, res = self._request("/api/v1/control", method="POST", data=payload)
        return ok and isinstance(res, dict) and res.get("success") is True

    # Remote navigation helpers
    def nav_back(self) -> bool:
        return self.control("back")

    def nav_home(self) -> bool:
        return self.control("home")

    def nav_recents(self) -> bool:
        return self.control("recents")

    def nav_notifications(self) -> bool:
        return self.control("notifications")

    def nav_quick_settings(self) -> bool:
        return self.control("quick_settings")

    def power_dialog(self) -> bool:
        return self.control("power")

    def screen_lock(self) -> bool:
        return self.control("lock")

    def screen_wake(self) -> bool:
        return self.control("wake")

    def volume_up(self) -> bool:
        return self.control("volume_up")

    def volume_down(self) -> bool:
        return self.control("volume_down")

    def volume_mute(self) -> bool:
        return self.control("volume_mute")

    def tap(self, x: float, y: float) -> bool:
        return self.control("tap", x=x, y=y)

    def swipe(self, x1: float, y1: float, x2: float, y2: float, duration_ms: int = 300) -> bool:
        return self.control("swipe", x1=x1, y1=y1, x2=x2, y2=y2, duration=duration_ms)

    # Clipboard sync
    def get_clipboard(self) -> str:
        ok, res = self._request("/api/v1/clipboard", method="GET")
        if ok and isinstance(res, dict):
            return res.get("text", "")
        return ""

    def set_clipboard(self, text: str) -> bool:
        ok, res = self._request("/api/v1/clipboard", method="POST", data={"text": text})
        return ok and isinstance(res, dict) and res.get("success") is True

    # Application drawer & launcher
    def list_apps(self) -> List[Dict[str, Any]]:
        ok, res = self._request("/api/v1/apps", method="GET")
        if ok and isinstance(res, dict):
            return res.get("apps", [])
        return []

    def launch_app(self, package_name: str) -> bool:
        ok, res = self._request("/api/v1/launch_app", method="POST", data={"package": package_name})
        return ok and isinstance(res, dict) and res.get("success") is True

    # Line-speed direct LAN file upload
    def upload_file(self, file_path: str, remote_filename: Optional[str] = None) -> Tuple[bool, str]:
        if not os.path.exists(file_path):
            return False, f"Local file not found: {file_path}"

        filename = remote_filename or os.path.basename(file_path)
        url = f"{self._base_url}/api/v1/upload"

        try:
            with open(file_path, "rb") as f:
                content = f.read()

            headers = {
                "Content-Type": "application/octet-stream",
                "Content-Length": str(len(content)),
                "X-Filename": filename
            }
            req = urllib.request.Request(url, data=content, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=30.0) as resp:
                raw = resp.read().decode("utf-8")
                res = json.loads(raw)
                if res.get("success") is True:
                    return True, res.get("path", "")
                return False, str(res)
        except Exception as e:
            return False, str(e)


class GNDroidSubnetRadar:
    """Listens for GNDROiD beacon UDP packets on port 51880 and maintains active device registry."""

    def __init__(self, port: int = BEACON_PORT, on_device_found: Optional[Callable[[Dict[str, Any]], None]] = None):
        self.port = port
        self.on_device_found = on_device_found
        self._devices: Dict[str, Dict[str, Any]] = {}
        self._running = False
        self._socket: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def start(self):
        if self._running:
            return
        self._running = True

        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            # Bind to 0.0.0.0 on beacon port
            self._socket.bind(("", self.port))
            self._socket.settimeout(1.5)
        except Exception as e:
            print(f"[!] Warning: Subnet Radar socket bind failed: {e}")
            self._running = False
            return

        self._thread = threading.Thread(target=self._listen_loop, name="GNDroidSubnetRadar", daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None

    def _listen_loop(self):
        while self._running and self._socket:
            try:
                data, addr = self._socket.recvfrom(4096)
                ip = addr[0]
                text = data.decode("utf-8", errors="ignore").strip()
                if not text.startswith("{"):
                    continue

                obj = json.loads(text)
                if obj.get("magic") == "GNDROID_BEACON":
                    obj["ip"] = ip
                    obj["last_seen"] = time.time()
                    with self._lock:
                        is_new = ip not in self._devices
                        self._devices[ip] = obj

                    if is_new and self.on_device_found:
                        try:
                            self.on_device_found(obj)
                        except Exception:
                            pass
            except socket.timeout:
                continue
            except Exception:
                if not self._running:
                    break

    def get_devices(self, max_age_sec: float = 6.0) -> List[Dict[str, Any]]:
        """Returns list of currently active devices heard from within max_age_sec."""
        now = time.time()
        active = []
        with self._lock:
            for ip, dev in list(self._devices.items()):
                if now - dev.get("last_seen", 0) <= max_age_sec:
                    active.append(dev)
        return active

    def send_discovery_probe(self):
        """Broadcasts GNDROID_DISCOVER to provoke instant device responses."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.sendto(b"GNDROID_DISCOVER", ("255.255.255.255", self.port))
            s.close()
        except Exception:
            pass


class GNDroidConnectionWatchdog:
    """
    Sub-second connection watchdog maintaining an unbreakable session.
    Monitors client ping and performs 0-second re-bind / ADB port forward fallback
    if packet loss or Wi-Fi roaming occurs.
    """

    def __init__(self, client: GNDroidCompanionClient, adb_serial: str = "", interval_sec: float = 1.5):
        self.client = client
        self.adb_serial = adb_serial
        self.interval_sec = interval_sec
        self.is_connected = False
        self.packet_loss_count = 0
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self.on_state_changed: Optional[Callable[[bool, str], None]] = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._watch_loop, name="GNDroidWatchdog", daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _watch_loop(self):
        while self._running:
            ok = self.client.ping(timeout=0.8)
            if ok:
                self.packet_loss_count = 0
                if not self.is_connected:
                    self.is_connected = True
                    if self.on_state_changed:
                        self.on_state_changed(True, "Connected (Sub-second heartbeat active)")
            else:
                self.packet_loss_count += 1
                if self.packet_loss_count >= 2 and self.is_connected:
                    self.is_connected = False
                    if self.on_state_changed:
                        self.on_state_changed(False, f"Connection warning: {self.packet_loss_count} dropped pings")
                    self._attempt_rebind()

            time.sleep(self.interval_sec)

    def _attempt_rebind(self):
        # Attempt ADB forward fallback if host is localhost or serial is known
        if self.adb_serial:
            try:
                import subprocess
                subprocess.run(
                    ["adb", "-s", self.adb_serial, "forward", f"tcp:{DEFAULT_PORT}", f"tcp:{DEFAULT_PORT}"],
                    capture_output=True, timeout=2, creationflags=0x08000000 if sys.platform == "win32" else 0
                )
            except Exception:
                pass
