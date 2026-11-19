#!/usr/bin/env python3
"""
nexus/sensor_console.py - QEMU Telnet Console Client & GPX Route Simulation
==========================================================================

Provides authenticated interactive control over QEMU Android emulator hardware
sensors, telephony states, battery emulation, network conditions, and automated
GPX trajectory playback with Haversine velocity and bearing interpolation.

Capabilities:
- QemuTelnetConsole:
    Connects to QEMU Telnet port (default 5554)
    Authenticates via ~/.emulator_console_auth_token
    Commands:
        geo fix <lon> <lat> [<alt> [<satellites>]]
        sensor set <type> <values>
        network delay <delay> / speed <speed>
        power capacity <pct> / ac <on|off> / status <status>
        gsm signal <1-4> / voice <state>
        finger touch <id>
- GpxRoutePlayer:
    Parses GPX XML schemas (trkpt, rtept, wpt) with elevation and timestamps
    Calculates Haversine spherical geodesic distance and initial azimuth bearing
    Smooth linear spatial and temporal interpolation along track segments
    Multi-threaded background playback with speed multipliers (1x–50x), loop
    support, pause/resume, and real-time telemetry callbacks
"""

import datetime
import logging
import math
import os
import re
import socket
import threading
import time
import xml.etree.ElementTree as ET
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

logger = logging.getLogger("nexus.sensor_console")

EARTH_RADIUS_METERS = 6371000.0


# ---------------------------------------------------------------------------
# Geodesic Math Utilities
# ---------------------------------------------------------------------------
def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Computes great-circle distance between two GPS coordinates in meters.
    Formula:
        a = sin^2(dlat/2) + cos(lat1)*cos(lat2)*sin^2(dlon/2)
        d = 2 * R * atan2(sqrt(a), sqrt(1-a))
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * (math.sin(dlambda / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    return EARTH_RADIUS_METERS * c


def haversine_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Computes initial forward azimuth bearing from coordinate 1 to coordinate 2
    in decimal degrees [0.0, 360.0).
    Formula:
        y = sin(dlon) * cos(lat2)
        x = cos(lat1)*sin(lat2) - sin(lat1)*cos(lat2)*cos(dlon)
        bearing = atan2(y, x)
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)

    y = math.sin(dlambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - (math.sin(phi1) * math.cos(phi2) * math.cos(dlambda))

    initial_bearing = math.degrees(math.atan2(y, x))
    return (initial_bearing + 360.0) % 360.0


# ---------------------------------------------------------------------------
# QemuTelnetConsole
# ---------------------------------------------------------------------------
class QemuTelnetConsole:
    """
    Client for the QEMU Android Emulator Telnet Console (e.g. 127.0.0.1:5554).
    Handles authentication and sensor / network / power / geo commands.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 5554,
        auth_token_path: Optional[str] = None,
        timeout: float = 5.0,
    ) -> None:
        self.host = host
        self.port = port
        self.auth_token_path = auth_token_path
        self.timeout = timeout
        self.sock: Optional[socket.socket] = None
        self._lock = threading.RLock()
        self._authenticated = False

    @property
    def is_connected(self) -> bool:
        """Returns True if the socket is open."""
        with self._lock:
            return self.sock is not None

    @property
    def is_authenticated(self) -> bool:
        """Returns True if authenticated."""
        with self._lock:
            return self._authenticated

    def connect(self) -> bool:
        """
        Connects to QEMU Telnet port, reads the initial greeting banner,
        and automatically attempts authentication.
        """
        with self._lock:
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(self.timeout)
                self.sock.connect((self.host, self.port))

                # Read initial banner until prompt or timeout
                banner = self._read_until(["OK", "Android Console", "\n"])
                logger.debug(f"QEMU Console initial banner: {banner.strip()}")

                # Authenticate if prompt requests or token is available
                auth_success = self.authenticate()
                return auth_success
            except Exception as exc:
                logger.error(f"Failed to connect to QEMU Telnet at {self.host}:{self.port}: {exc}")
                self.close()
                return False

    def authenticate(self, token: Optional[str] = None) -> bool:
        """
        Authenticates with QEMU console using the auth token.
        If token is not provided, reads from token file.
        """
        with self._lock:
            if not self.sock:
                return False

            if not token:
                token = self._resolve_auth_token()

            if not token:
                logger.warning("No QEMU emulator auth token found.")
                return False

            response = self.send_command(f"auth {token.strip()}")
            if "OK" in response:
                self._authenticated = True
                logger.info(f"QEMU console authenticated successfully on port {self.port}.")
                return True
            else:
                logger.error(f"QEMU console authentication failed: {response}")
                self._authenticated = False
                return False

    def _resolve_auth_token(self) -> Optional[str]:
        """Resolves token from specified path or standard user home paths."""
        candidates = []
        if self.auth_token_path:
            candidates.append(self.auth_token_path)

        user_home = os.path.expanduser("~")
        candidates.append(os.path.join(user_home, ".emulator_console_auth_token"))
        candidates.append(r"C:\Users\Reader-Branch\.emulator_console_auth_token")

        for path in candidates:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        token = f.read().strip()
                        if token:
                            return token
                except Exception as exc:
                    logger.debug(f"Error reading auth token from {path}: {exc}")
        return None

    def send_command(self, cmd: str) -> str:
        """
        Sends a command string to QEMU Telnet console and awaits response.
        Returns the command output.
        """
        with self._lock:
            if not self.sock:
                return "KO: not connected"

            try:
                line = cmd.strip() + "\r\n"
                self.sock.sendall(line.encode("utf-8"))
                response = self._read_until(["OK", "KO"])
                return response
            except Exception as exc:
                logger.error(f"Error executing command '{cmd}': {exc}")
                return f"KO: {exc}"

    def _read_until(self, terminators: List[str], max_bytes: int = 4096) -> str:
        """Reads from socket until one of the terminators is encountered or timeout."""
        buf = bytearray()
        start = time.time()
        while time.time() - start < self.timeout:
            try:
                chunk = self.sock.recv(512)
                if not chunk:
                    break
                buf.extend(chunk)
                text = buf.decode("utf-8", errors="replace")
                for term in terminators:
                    if term in text:
                        return text
            except socket.timeout:
                break
            except Exception:
                break
        return buf.decode("utf-8", errors="replace")

    def set_geo(
        self,
        longitude: float,
        latitude: float,
        altitude: float = 0.0,
        satellites: int = 10
    ) -> bool:
        """
        Injects GPS coordinates into the Android Radio/GPS HAL via:
        `geo fix <lon> <lat> [<alt> [<satellites>]]`
        """
        cmd = f"geo fix {longitude:.6f} {latitude:.6f} {altitude:.1f} {satellites}"
        res = self.send_command(cmd)
        return "OK" in res

    def set_sensor(
        self,
        sensor_type: str,
        values: Union[Tuple[float, ...], List[float], str]
    ) -> bool:
        """
        Sets values for simulated hardware sensors.
        Types: 'acceleration', 'magnetic-field', 'orientation', 'temperature',
               'proximity', 'light', 'pressure', 'humidity'
        """
        if isinstance(values, (tuple, list)):
            val_str = ":".join(f"{v:.4f}" for v in values)
        else:
            val_str = str(values)
        cmd = f"sensor set {sensor_type} {val_str}"
        res = self.send_command(cmd)
        return "OK" in res

    def set_network_delay(self, delay: str) -> bool:
        """Configures network latency: 'none', 'gprs', 'edge', 'umts', 'lte'."""
        res = self.send_command(f"network delay {delay}")
        return "OK" in res

    def set_network_speed(self, speed: str) -> bool:
        """Configures network bandwidth: 'full', 'gsm', 'edge', 'umts', 'hsdpa', 'lte'."""
        res = self.send_command(f"network speed {speed}")
        return "OK" in res

    def set_power_capacity(self, percentage: int) -> bool:
        """Configures simulated battery level (0 to 100)."""
        pct = max(0, min(100, int(percentage)))
        res = self.send_command(f"power capacity {pct}")
        return "OK" in res

    def set_power_ac(self, ac_on: bool) -> bool:
        """Configures AC charger connection: 'on' or 'off'."""
        val = "on" if ac_on else "off"
        res = self.send_command(f"power ac {val}")
        return "OK" in res

    def set_power_status(self, status: str) -> bool:
        """Configures battery state: 'charging', 'discharging', 'not-charging', 'full'."""
        res = self.send_command(f"power status {status}")
        return "OK" in res

    def set_gsm_signal(self, signal: int) -> bool:
        """Configures cellular signal strength (0 to 4)."""
        res = self.send_command(f"gsm signal {max(0, min(4, signal))}")
        return "OK" in res

    def set_gsm_voice(self, state: str) -> bool:
        """Configures cellular voice state: 'home', 'roaming', 'searching', 'denied'."""
        res = self.send_command(f"gsm voice {state}")
        return "OK" in res

    def finger_touch(self, touch_id: int) -> bool:
        """Simulates fingerprint touch sensor event."""
        res = self.send_command(f"finger touch {touch_id}")
        return "OK" in res

    def close(self) -> None:
        """Closes the Telnet session."""
        with self._lock:
            if self.sock:
                try:
                    self.sock.sendall(b"quit\r\n")
                except Exception:
                    pass
                try:
                    self.sock.close()
                except Exception:
                    pass
                self.sock = None
                self._authenticated = False


# ---------------------------------------------------------------------------
# GpxRoutePlayer
# ---------------------------------------------------------------------------
class GpxRoutePlayer:
    """
    Parses GPX XML routes and streams dynamic coordinates to QemuTelnetConsole.
    Features:
    - Haversine distance, speed, and heading calculations
    - High-fidelity linear spatial interpolation between waypoints
    - Playback speed multiplier, loop mode, pause, and progress callbacks
    """

    def __init__(self, console: QemuTelnetConsole) -> None:
        self.console = console
        self._raw_points: List[Dict[str, Any]] = []
        self._interpolated_points: List[Dict[str, Any]] = []
        self._total_distance_m = 0.0

        # State tracking
        self._is_playing = False
        self._is_paused = False
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()  # Set means not paused
        self._worker_thread: Optional[threading.Thread] = None
        self._current_index = 0
        self._lock = threading.RLock()

    @property
    def is_playing(self) -> bool:
        with self._lock:
            return self._is_playing

    @property
    def is_paused(self) -> bool:
        with self._lock:
            return self._is_paused

    @property
    def total_distance_m(self) -> float:
        with self._lock:
            return self._total_distance_m

    @property
    def point_count(self) -> int:
        with self._lock:
            return len(self._interpolated_points) or len(self._raw_points)

    @staticmethod
    def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Static reference to haversine_distance."""
        return haversine_distance(lat1, lon1, lat2, lon2)

    @staticmethod
    def haversine_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Static reference to haversine_bearing."""
        return haversine_bearing(lat1, lon1, lat2, lon2)

    def load_gpx_content(self, gpx_xml: str) -> List[Dict[str, Any]]:
        """Parses GPX XML string containing trackpoints, routepoints, or waypoints."""
        with self._lock:
            root = ET.fromstring(gpx_xml)
            points: List[Dict[str, Any]] = []

            # Strip namespaces for unified querying
            for elem in root.iter():
                if "}" in elem.tag:
                    elem.tag = elem.tag.split("}", 1)[1]

            # Look for trkpt, rtept, or wpt
            found_nodes = root.findall(".//trkpt")
            if not found_nodes:
                found_nodes = root.findall(".//rtept")
            if not found_nodes:
                found_nodes = root.findall(".//wpt")

            for node in found_nodes:
                lat = float(node.attrib.get("lat", 0.0))
                lon = float(node.attrib.get("lon", 0.0))

                ele_elem = node.find("ele")
                ele = float(ele_elem.text) if ele_elem is not None and ele_elem.text else 0.0

                time_elem = node.find("time")
                timestamp_str = time_elem.text if time_elem is not None and time_elem.text else ""

                points.append({
                    "lat": lat,
                    "lon": lon,
                    "ele": ele,
                    "time": timestamp_str,
                })

            self._raw_points = points
            self._compute_route_metrics()
            return list(self._raw_points)

    def load_gpx_file(self, filepath: str) -> List[Dict[str, Any]]:
        """Reads a GPX file from disk and parses its waypoints."""
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        return self.load_gpx_content(content)

    def _compute_route_metrics(self) -> None:
        """Computes distances, bearings, and default interpolations across loaded points."""
        if not self._raw_points:
            self._total_distance_m = 0.0
            self._interpolated_points = []
            return

        total_d = 0.0
        for i in range(len(self._raw_points) - 1):
            p1 = self._raw_points[i]
            p2 = self._raw_points[i + 1]
            seg_dist = haversine_distance(p1["lat"], p1["lon"], p2["lat"], p2["lon"])
            bearing = haversine_bearing(p1["lat"], p1["lon"], p2["lat"], p2["lon"])
            p1["seg_dist"] = seg_dist
            p1["bearing"] = bearing
            total_d += seg_dist

        if self._raw_points:
            self._raw_points[-1]["seg_dist"] = 0.0
            self._raw_points[-1]["bearing"] = (
                self._raw_points[-2]["bearing"] if len(self._raw_points) > 1 else 0.0
            )

        self._total_distance_m = total_d
        # By default, interpolated points equal raw points unless interpolated
        self._interpolated_points = list(self._raw_points)

    def interpolate_route(self, interval_meters: float = 10.0) -> List[Dict[str, Any]]:
        """
        Generates smoothly interpolated intermediate waypoints along the route
        at the specified distance step (in meters).
        """
        with self._lock:
            if len(self._raw_points) < 2:
                return list(self._raw_points)

            interpolated: List[Dict[str, Any]] = []

            for i in range(len(self._raw_points) - 1):
                p1 = self._raw_points[i]
                p2 = self._raw_points[i + 1]
                dist = haversine_distance(p1["lat"], p1["lon"], p2["lat"], p2["lon"])
                bearing = haversine_bearing(p1["lat"], p1["lon"], p2["lat"], p2["lon"])

                steps = max(1, int(dist / max(1.0, interval_meters)))
                for s in range(steps):
                    frac = float(s) / float(steps)
                    ilat = p1["lat"] + (p2["lat"] - p1["lat"]) * frac
                    ilon = p1["lon"] + (p2["lon"] - p1["lon"]) * frac
                    iele = p1["ele"] + (p2["ele"] - p1["ele"]) * frac
                    interpolated.append({
                        "lat": ilat,
                        "lon": ilon,
                        "ele": iele,
                        "bearing": bearing,
                        "seg_dist": dist / steps,
                    })

            # Append final point
            interpolated.append(self._raw_points[-1])
            self._interpolated_points = interpolated
            return list(self._interpolated_points)

    def start_playback(
        self,
        speed_multiplier: float = 1.0,
        loop: bool = False,
        tick_interval: float = 0.2,
        callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> None:
        """
        Starts GPX route streaming on a dedicated background worker thread.

        Args:
            speed_multiplier: Playback speed acceleration factor (1.0 = normal, 2.0 = 2x)
            loop: Whether to loop the route continuously upon reaching destination
            tick_interval: Interval between GPS coordinate updates in seconds
            callback: Progress notification callback receiving telemetry status dict
        """
        with self._lock:
            if self._is_playing:
                logger.warning("GPX playback is already running.")
                return

            points = self._interpolated_points or self._raw_points
            if not points:
                logger.error("Cannot start playback: no route points loaded.")
                return

            self._is_playing = True
            self._is_paused = False
            self._stop_event.clear()
            self._pause_event.set()
            self._current_index = 0

            self._worker_thread = threading.Thread(
                target=self._playback_loop,
                args=(points, speed_multiplier, loop, tick_interval, callback),
                name="GNDROiD_GpxPlayer",
                daemon=True,
            )
            self._worker_thread.start()
            logger.info(
                f"GPX playback started: {len(points)} points, total={self._total_distance_m:.1f}m, speed={speed_multiplier}x, loop={loop}"
            )

    def _playback_loop(
        self,
        points: List[Dict[str, Any]],
        speed_multiplier: float,
        loop: bool,
        tick_interval: float,
        callback: Optional[Callable[[Dict[str, Any]], None]]
    ) -> None:
        """Internal worker loop streaming waypoints to QEMU console."""
        total_pts = len(points)
        effective_delay = max(0.01, tick_interval / max(0.1, speed_multiplier))
        dist_traveled = 0.0

        while not self._stop_event.is_set():
            idx = self._current_index
            if idx >= total_pts:
                if loop and not self._stop_event.is_set():
                    self._current_index = 0
                    dist_traveled = 0.0
                    continue
                else:
                    break

            # Handle pause
            self._pause_event.wait()
            if self._stop_event.is_set():
                break

            pt = points[idx]
            lat = pt["lat"]
            lon = pt["lon"]
            ele = pt.get("ele", 0.0)
            bearing = pt.get("bearing", 0.0)
            seg_dist = pt.get("seg_dist", 0.0)
            dist_traveled += seg_dist

            # Calculate simulated speed in km/h
            speed_mps = (seg_dist / max(0.01, effective_delay)) * speed_multiplier
            speed_kmh = speed_mps * 3.6

            # Send geo fix to QEMU console
            try:
                self.console.set_geo(longitude=lon, latitude=lat, altitude=ele)
            except Exception as exc:
                logger.debug(f"Error sending geo fix: {exc}")

            # Notify callback if provided
            if callback:
                telemetry = {
                    "lat": lat,
                    "lon": lon,
                    "ele": ele,
                    "bearing": bearing,
                    "speed_kmh": round(speed_kmh, 1),
                    "distance_traveled_m": round(dist_traveled, 1),
                    "total_distance_m": round(self._total_distance_m, 1),
                    "point_index": idx,
                    "total_points": total_pts,
                    "progress_percent": round((float(idx) / float(max(1, total_pts - 1))) * 100.0, 1),
                }
                try:
                    callback(telemetry)
                except Exception as exc:
                    logger.debug(f"Progress callback error: {exc}")

            self._current_index += 1
            time.sleep(effective_delay)

        with self._lock:
            self._is_playing = False
            self._is_paused = False

        logger.info("GPX playback loop ended.")

    def pause_playback(self) -> None:
        """Pauses route playback without resetting current waypoint index."""
        with self._lock:
            if self._is_playing and not self._is_paused:
                self._is_paused = True
                self._pause_event.clear()
                logger.info("GPX playback paused.")

    def resume_playback(self) -> None:
        """Resumes paused route playback."""
        with self._lock:
            if self._is_playing and self._is_paused:
                self._is_paused = False
                self._pause_event.set()
                logger.info("GPX playback resumed.")

    def stop_playback(self) -> None:
        """Halts route playback and waits for worker thread termination."""
        with self._lock:
            self._stop_event.set()
            self._pause_event.set()
            self._is_playing = False
            self._is_paused = False

        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=1.0)
            self._worker_thread = None
        logger.info("GPX playback stopped.")
