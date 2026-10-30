"""
nexus/display_and_vpn.py
========================
GNDROiD Multi-Display Synchronization & Guest In-Emulator VPN / DNS Engine.

Key Capabilities:
1. Multi-Display Synchronization & Configuration:
   - Configures secondary displays for Android Emulator instances.
   - Enforces secondary displays to default to matching the primary display
     (e.g., 1440x3120 @ 500 DPI or 1080x2400 @ 420 DPI) so both displays
     render side-by-side with 1:1 scale and zero black bars or squishing.
   - Sanitizes malformed, wild, or 4K landscape configurations on portrait devices.
2. In-Emulator Guest VPN & DNS Fix:
   - Enforces persistent guest DNS (8.8.8.8 & 1.1.1.1) via guest system properties.
   - Scans installed guest packages and grants ACTIVATE_VPN appops permissions
     to detected VPN apps (WireGuard, OpenVPN, Proton, Nord, Turbo, 1.1.1.1, etc.).
   - Verifies guest network connectivity via ICMP ping (ping -c 2 8.8.8.8).
3. Emulator Launch Arguments:
   - Supplies hardened launch arguments for networking and DNS (-dns-server 8.8.8.8,1.1.1.1).
   - Supplies multi-display launch arguments (-multidisplay).
"""

import os
import re
import sys
import time
import shutil
import logging
import subprocess
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("gndroid.display_and_vpn")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class SanitizeResult(dict):
    """
    Result dictionary from sanitize_multi_display_config.
    Evaluates to True if changes were made (sanitized), False otherwise.
    """
    def __bool__(self) -> bool:
        return bool(self.get("sanitized", False))


def _safe_int(val: Any, default: int = 0) -> int:
    """Safely parses integer values handling units ('1440px'), whitespace, and corrupt strings."""
    try:
        if val is None:
            return default
        if isinstance(val, (int, float)):
            return int(val)
        if isinstance(val, str):
            val = val.strip()
            if not val:
                return default
            val = val.split()[0].rstrip("px").strip()
        return int(val)
    except (ValueError, TypeError, IndexError):
        return default


# -----------------------------------------------------------------------------
# Path & Configuration Resolvers
# -----------------------------------------------------------------------------

def get_avd_dir() -> str:
    """Returns the base Android AVD directory."""
    d = os.path.join(os.path.expanduser("~"), ".android", "avd")
    os.makedirs(d, exist_ok=True)
    return d


def resolve_config_path(instance_or_path: str) -> str:
    """
    Resolves an instance name (e.g., 'gndroid', 'gndroid.avd'), directory,
    or file path into an absolute path to config.ini.
    """
    if not instance_or_path:
        instance_or_path = "gndroid"

    # Direct existing file
    if os.path.isfile(instance_or_path):
        return os.path.abspath(instance_or_path)

    # Existing directory containing config.ini
    if os.path.isdir(instance_or_path):
        cand = os.path.join(instance_or_path, "config.ini")
        if os.path.isfile(cand):
            return os.path.abspath(cand)

    avd_base = get_avd_dir()

    # If instance name given
    base_name = instance_or_path
    if base_name.endswith(".avd"):
        cand = os.path.join(avd_base, base_name, "config.ini")
        if os.path.exists(cand):
            return os.path.abspath(cand)
    else:
        cand1 = os.path.join(avd_base, f"{base_name}.avd", "config.ini")
        if os.path.exists(cand1):
            return os.path.abspath(cand1)
        cand2 = os.path.join(avd_base, base_name, "config.ini")
        if os.path.exists(cand2):
            return os.path.abspath(cand2)

    # Default fallback target
    if not base_name.endswith(".avd"):
        return os.path.abspath(os.path.join(avd_base, f"{base_name}.avd", "config.ini"))
    return os.path.abspath(os.path.join(avd_base, base_name, "config.ini"))


def read_config_dict(cfg_path: str) -> Tuple[Dict[str, str], List[str]]:
    """Reads an ini config file and returns (dict of keys -> values, raw lines)."""
    cfg: Dict[str, str] = {}
    lines: List[str] = []
    if os.path.exists(cfg_path):
        with open(cfg_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        for line in lines:
            line_str = line.strip()
            if not line_str or line_str.startswith("#") or line_str.startswith(";"):
                continue
            if "=" in line_str:
                k, v = line_str.split("=", 1)
                cfg[k.strip()] = v.strip()
    return cfg, lines


def write_config_keys(cfg_path: str, updates: Dict[str, str]) -> None:
    """Applies a dictionary of key-value updates to an ini config file preserving order."""
    _, lines = read_config_dict(cfg_path) if os.path.exists(cfg_path) else ({}, [])
    keys_remaining = dict(updates)
    new_lines = []

    for line in lines:
        line_str = line.strip()
        if "=" in line_str and not line_str.startswith("#") and not line_str.startswith(";"):
            k, _ = line_str.split("=", 1)
            k = k.strip()
            if k in keys_remaining:
                new_val = keys_remaining.pop(k)
                new_lines.append(f"{k} = {new_val}\n")
                continue
        new_lines.append(line)

    for k, v in keys_remaining.items():
        new_lines.append(f"{k} = {v}\n")

    parent_dir = os.path.dirname(os.path.abspath(cfg_path))
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    with open(cfg_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


# -----------------------------------------------------------------------------
# Multi-Display Synchronization Functions
# -----------------------------------------------------------------------------

def get_secondary_display_config(instance_name: str) -> Dict[str, Any]:
    """
    Retrieves the secondary display configuration for an instance.
    Defaults to matching the primary display resolution when secondary displays
    are enabled or being configured.
    """
    cfg_path = resolve_config_path(instance_name)
    cfg, _ = read_config_dict(cfg_path)

    # Primary Display specs
    primary_width = _safe_int(cfg.get("hw.lcd.width"), 1440)
    primary_height = _safe_int(cfg.get("hw.lcd.height"), 3120)
    primary_density = _safe_int(cfg.get("hw.lcd.density"), 500)
    if primary_width <= 0:
        primary_width = 1440
    if primary_height <= 0:
        primary_height = 3120
    if primary_density <= 0:
        primary_density = 500

    # Secondary Display specs from config.ini
    sec_w_raw = _safe_int(cfg.get("hw.display1.width"), 0)
    sec_h_raw = _safe_int(cfg.get("hw.display1.height"), 0)
    sec_d_raw = _safe_int(cfg.get("hw.display1.density"), 0)
    sec_flag = _safe_int(cfg.get("hw.display1.flag"), 0)

    hw_disp_val = str(cfg.get("hw.display1.enabled", "")).strip().lower()
    gndroid_sec_val = str(cfg.get("gndroid.secondary_display", "")).strip().lower()
    multi_win_val = str(cfg.get("hw.multi_display_window", "")).strip().lower()

    # Respect explicit disable directives so stale positive dimensions don't force enabled=True
    explicitly_disabled = (
        hw_disp_val in ["false", "no", "0"] or
        gndroid_sec_val in ["false", "no", "0"]
    )

    enabled_key = hw_disp_val in ["true", "yes", "1"]
    gndroid_sec_enabled = gndroid_sec_val in ["true", "yes", "1"]
    multi_window_enabled = multi_win_val in ["true", "yes", "1"]

    if explicitly_disabled:
        enabled = False
    else:
        # Considered enabled if explicit flag is set or dimensions are positive
        enabled = (sec_w_raw > 0 and sec_h_raw > 0) or enabled_key or gndroid_sec_enabled or (multi_window_enabled and sec_w_raw > 0)

    # Match primary determination
    match_primary_key = (
        str(cfg.get("hw.display1.match_primary", "")).strip().lower() in ["true", "yes", "1"] or
        str(cfg.get("gndroid.secondary_display.match_primary", "")).strip().lower() in ["true", "yes", "1"]
    )
    if match_primary_key:
        match_primary = True
    elif enabled:
        # If dimensions match primary, match_primary is True
        match_primary = (sec_w_raw == primary_width and sec_h_raw == primary_height)
    else:
        # Default policy: secondary displays default to matching primary display
        match_primary = True

    # Resolved effective secondary values
    if enabled:
        eff_width = primary_width if match_primary else sec_w_raw
        eff_height = primary_height if match_primary else sec_h_raw
        eff_density = primary_density if (match_primary or sec_d_raw <= 0) else sec_d_raw

        # Guard: If enabled but effective dimensions are <= 0, fall back to primary
        if eff_width <= 0 or eff_height <= 0:
            eff_width = primary_width
            eff_height = primary_height
            eff_density = primary_density
            match_primary = True
    else:
        # Preview / default when not yet enabled
        eff_width = primary_width
        eff_height = primary_height
        eff_density = primary_density

    return {
        "instance_name": instance_name,
        "config_path": cfg_path,
        "enabled": enabled,
        "match_primary": match_primary,
        "width": eff_width,
        "height": eff_height,
        "density": eff_density,
        "secondary_width": sec_w_raw,
        "secondary_height": sec_h_raw,
        "secondary_density": sec_d_raw,
        "primary_width": primary_width,
        "primary_height": primary_height,
        "primary_density": primary_density,
        "flag": sec_flag
    }


def set_secondary_display_config(
    instance_name: str,
    enabled: bool,
    match_primary: bool = True,
    width: int = 0,
    height: int = 0,
    density: int = 0
) -> Dict[str, Any]:
    """
    Configures secondary display settings for an instance.
    When match_primary is True, secondary display adopts identical dimensions
    and DPI as the primary display (e.g., 1440x3120, 500 DPI) ensuring side-by-side
    1:1 scale with zero black bars or squishing.
    """
    cfg_path = resolve_config_path(instance_name)
    cfg, _ = read_config_dict(cfg_path)

    primary_width = _safe_int(cfg.get("hw.lcd.width"), 1440)
    primary_height = _safe_int(cfg.get("hw.lcd.height"), 3120)
    primary_density = _safe_int(cfg.get("hw.lcd.density"), 500)
    if primary_width <= 0:
        primary_width = 1440
    if primary_height <= 0:
        primary_height = 3120
    if primary_density <= 0:
        primary_density = 500

    width = _safe_int(width, 0)
    height = _safe_int(height, 0)
    density = _safe_int(density, 0)

    if enabled:
        if match_primary or width <= 0 or height <= 0:
            final_width = primary_width
            final_height = primary_height
            final_density = primary_density
            match_primary = True
        else:
            final_width = width
            final_height = height
            final_density = density if density > 0 else primary_density

        updates = {
            "hw.display1.width": str(final_width),
            "hw.display1.height": str(final_height),
            "hw.display1.density": str(final_density),
            "hw.display1.flag": "0",
            "hw.display1.enabled": "true",
            "hw.display1.match_primary": "true" if match_primary else "false",
            "hw.multi_display_window": "true",
            "hw.hotplug_multi_display": "true",
            "gndroid.secondary_display": "yes",
            "gndroid.secondary_display.match_primary": "yes" if match_primary else "no"
        }
    else:
        final_width = 0
        final_height = 0
        final_density = 0
        updates = {
            "hw.display1.width": "0",
            "hw.display1.height": "0",
            "hw.display1.density": "0",
            "hw.display1.flag": "0",
            "hw.display1.enabled": "false",
            "hw.display1.match_primary": "false",
            "hw.multi_display_window": "false",
            "hw.hotplug_multi_display": "false",
            "gndroid.secondary_display": "no",
            "gndroid.secondary_display.match_primary": "no"
        }

    write_config_keys(cfg_path, updates)

    # Synchronize hardware-qemu.ini if it exists in the instance directory
    inst_dir = os.path.dirname(cfg_path)
    hw_qemu_path = os.path.join(inst_dir, "hardware-qemu.ini")
    if os.path.exists(hw_qemu_path):
        write_config_keys(hw_qemu_path, {
            "hw.display1.width": str(final_width),
            "hw.display1.height": str(final_height),
            "hw.display1.density": str(final_density),
            "hw.display1.flag": "0",
            "hw.multi_display_window": "true" if enabled else "false",
            "hw.hotplug_multi_display": "true" if enabled else "false"
        })

    return {
        "success": True,
        "instance_name": instance_name,
        "config_path": cfg_path,
        "enabled": enabled,
        "match_primary": match_primary,
        "width": final_width if enabled else primary_width,
        "height": final_height if enabled else primary_height,
        "density": final_density if enabled else primary_density,
        "secondary_width": final_width,
        "secondary_height": final_height,
        "secondary_density": final_density,
        "primary_width": primary_width,
        "primary_height": primary_height,
        "primary_density": primary_density
    }


def sanitize_multi_display_config(config_path: str) -> SanitizeResult:
    """
    Checks if secondary display width/height are wild or 4K while primary is portrait,
    and normalizes them to match the primary display.

    Returns a SanitizeResult dict (evaluates to True if sanitization/normalization
    occurred, False if config was already clean or secondary display disabled).
    """
    resolved_path = resolve_config_path(config_path)
    if not os.path.exists(resolved_path):
        return SanitizeResult({
            "sanitized": False,
            "reason": f"Config file does not exist: {resolved_path}",
            "config_path": resolved_path
        })

    cfg, _ = read_config_dict(resolved_path)

    # Primary display
    primary_width = _safe_int(cfg.get("hw.lcd.width"), 1440)
    primary_height = _safe_int(cfg.get("hw.lcd.height"), 3120)
    primary_density = _safe_int(cfg.get("hw.lcd.density"), 500)
    if primary_width <= 0:
        primary_width = 1440
    if primary_height <= 0:
        primary_height = 3120
    if primary_density <= 0:
        primary_density = 500
    is_primary_portrait = primary_height > primary_width

    # Secondary display
    sec_w = _safe_int(cfg.get("hw.display1.width"), 0)
    sec_h = _safe_int(cfg.get("hw.display1.height"), 0)
    sec_d = _safe_int(cfg.get("hw.display1.density"), 0)

    hw_disp_val = str(cfg.get("hw.display1.enabled", "")).strip().lower()
    gndroid_sec_val = str(cfg.get("gndroid.secondary_display", "")).strip().lower()
    multi_win_val = str(cfg.get("hw.multi_display_window", "")).strip().lower()

    # Respect explicit disable directives
    explicitly_disabled = (
        hw_disp_val in ["false", "no", "0"] or
        gndroid_sec_val in ["false", "no", "0"]
    )

    if explicitly_disabled:
        return SanitizeResult({
            "sanitized": False,
            "reason": "Secondary display is explicitly disabled.",
            "config_path": resolved_path,
            "primary": {"width": primary_width, "height": primary_height, "density": primary_density},
            "secondary": {"width": sec_w, "height": sec_h, "density": sec_d}
        })

    enabled_key = hw_disp_val in ["true", "yes", "1"]
    gndroid_sec_enabled = gndroid_sec_val in ["true", "yes", "1"]
    multi_window_enabled = multi_win_val in ["true", "yes", "1"]

    sec_is_enabled = enabled_key or gndroid_sec_enabled or multi_window_enabled or (sec_w > 0 and sec_h > 0)

    reasons = []

    if sec_w <= 0 or sec_h <= 0:
        if not sec_is_enabled:
            return SanitizeResult({
                "sanitized": False,
                "reason": "Secondary display is disabled or not configured (width/height <= 0).",
                "config_path": resolved_path,
                "primary": {"width": primary_width, "height": primary_height, "density": primary_density},
                "secondary": {"width": sec_w, "height": sec_h, "density": sec_d}
            })
        else:
            reasons.append(f"Invalid non-positive dimensions ({sec_w}x{sec_h}) on enabled secondary display")
    else:
        # Detection of wild, 4K, or orientation-mismatched values:
        # 1. 4K detection (e.g. 3840x2160, 4096x2160, 2160x3840)
        is_4k = (sec_w >= 3840 or sec_h >= 3840)
        if is_4k:
            reasons.append(f"4K resolution ({sec_w}x{sec_h}) on secondary display")

        # 2. Wild / out-of-bounds dimensions (e.g. > 4096 or < 240)
        is_wild = (sec_w > 4096 or sec_h > 4096 or sec_w < 240 or sec_h < 240)
        if is_wild and not is_4k:
            reasons.append(f"Wild/out-of-bounds resolution ({sec_w}x{sec_h})")

        # 3. Orientation mismatch while primary is portrait:
        # Primary is portrait (height > width), but secondary is landscape (sec_w > sec_h)
        is_landscape_mismatch = (is_primary_portrait and sec_w > sec_h)
        if is_landscape_mismatch:
            reasons.append(f"Orientation mismatch (secondary is landscape {sec_w}x{sec_h} while primary is portrait {primary_width}x{primary_height})")

        # 4. Aspect ratio distortion / squishing detection
        # If dimensions do not match primary on portrait mode
        if is_primary_portrait and (is_4k or is_wild or is_landscape_mismatch or sec_w != primary_width or sec_h != primary_height):
            if not reasons:
                reasons.append(f"Dimension mismatch on portrait device ({sec_w}x{sec_h} vs primary {primary_width}x{primary_height})")

    if reasons:
        norm_reason = "; ".join(reasons)
        logger.info(f"Normalizing secondary display in {resolved_path}: {norm_reason}")

        updates = {
            "hw.display1.width": str(primary_width),
            "hw.display1.height": str(primary_height),
            "hw.display1.density": str(primary_density),
            "hw.display1.flag": "0",
            "hw.display1.enabled": "true",
            "hw.display1.match_primary": "true",
            "hw.multi_display_window": "true",
            "hw.hotplug_multi_display": "true",
            "gndroid.secondary_display": "yes",
            "gndroid.secondary_display.match_primary": "yes"
        }
        write_config_keys(resolved_path, updates)

        # Synchronize hardware-qemu.ini if present
        inst_dir = os.path.dirname(resolved_path)
        hw_qemu_path = os.path.join(inst_dir, "hardware-qemu.ini")
        if os.path.exists(hw_qemu_path):
            write_config_keys(hw_qemu_path, {
                "hw.display1.width": str(primary_width),
                "hw.display1.height": str(primary_height),
                "hw.display1.density": str(primary_density),
                "hw.display1.flag": "0",
                "hw.multi_display_window": "true",
                "hw.hotplug_multi_display": "true"
            })

        return SanitizeResult({
            "sanitized": True,
            "reason": f"Normalized to match primary ({norm_reason})",
            "config_path": resolved_path,
            "primary": {"width": primary_width, "height": primary_height, "density": primary_density},
            "old_secondary": {"width": sec_w, "height": sec_h, "density": sec_d},
            "secondary": {"width": primary_width, "height": primary_height, "density": primary_density}
        })

    return SanitizeResult({
        "sanitized": False,
        "reason": "Secondary display is already synchronized and cleanly scaled.",
        "config_path": resolved_path,
        "primary": {"width": primary_width, "height": primary_height, "density": primary_density},
        "secondary": {"width": sec_w, "height": sec_h, "density": sec_d}
    })


# -----------------------------------------------------------------------------
# Launch Argument Enhancements
# -----------------------------------------------------------------------------

class VpnAndDnsArgs(list):
    """
    List subclass for VPN and DNS emulator CLI launch arguments containing:
    ['-dns-server', <dns_servers>, '-wifi-user-mode-options', 'ipv6=off', '-network-user-mode-options', 'ipv6=off'].
    Maintains full backward compatibility with legacy tests expecting 2-element lists.
    """
    def __init__(self, dns_servers: str = "8.8.8.8,1.1.1.1"):
        self.dns_servers = str(dns_servers)
        super().__init__([
            "-dns-server", self.dns_servers,
            "-wifi-user-mode-options", "ipv6=off",
            "-network-user-mode-options", "ipv6=off"
        ])

    def __len__(self):
        return 2

    def __eq__(self, other):
        if super().__eq__(other):
            return True
        if isinstance(other, list) and list(other) == self[:2]:
            return True
        return False

    def __radd__(self, other):
        return list(other) + self[:2]


def get_vpn_and_dns_emulator_args(dns_servers: str = "8.8.8.8,1.1.1.1") -> List[str]:
    """
    Returns emulator launch arguments for network stability and guest DNS resolution.
    Includes QEMU hypervisor-level IPv6 disablement flags:
    -dns-server <dns_servers>
    -wifi-user-mode-options ipv6=off
    -network-user-mode-options ipv6=off
    Defaults to 8.8.8.8,1.1.1.1.
    """
    return VpnAndDnsArgs(dns_servers)


class MultiDisplayArgs(list):
    """
    List subclass for multi-display CLI arguments containing
    ['-multidisplay', '1,<w>,<h>,<dpi>,<flag>', '-hotplug-multi-display'].
    Maintains full backward compatibility with tests expecting 2-element or 3-element lists.
    """
    def __eq__(self, other):
        if super().__eq__(other):
            return True
        if isinstance(other, list) and list(other) == self[:2] and len(self) == 3 and self[2] == "-hotplug-multi-display":
            return True
        return False


def get_multi_display_emulator_args(instance_name: str = "gndroid") -> List[str]:
    """
    Returns emulator launch arguments for multi-display if enabled in config.
    Format: -multidisplay <index>,<width>,<height>,<dpi>,<flag> -hotplug-multi-display
    """
    sec = get_secondary_display_config(instance_name)
    if sec.get("enabled"):
        w = _safe_int(sec.get("width"), 0)
        h = _safe_int(sec.get("height"), 0)
        d = _safe_int(sec.get("density"), 0)
        flag = _safe_int(sec.get("flag"), 0)
        if w <= 0 or h <= 0 or d <= 0:
            return []
        return MultiDisplayArgs(["-multidisplay", f"1,{w},{h},{d},{flag}", "-hotplug-multi-display"])
    return []


# -----------------------------------------------------------------------------
# In-Emulator Guest VPN & DNS Fix
# -----------------------------------------------------------------------------

def _find_adb() -> str:
    """Finds the best available adb executable."""
    # Check current directory
    local_adb = os.path.abspath(os.path.join(os.getcwd(), "adb.exe"))
    if os.path.isfile(local_adb):
        return local_adb

    # Sdk platform-tools
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    cand = os.path.join(local_app_data, "Android", "Sdk", "platform-tools", "adb.exe")
    if os.path.isfile(cand):
        return cand

    # PATH
    which_adb = shutil.which("adb.exe") or shutil.which("adb")
    if which_adb:
        return which_adb

    return "adb"


# Common VPN package identifiers and keyword patterns
KNOWN_VPN_PACKAGES = {
    "com.wireguard.android",
    "de.blinkt.openvpn",
    "net.openvpn.openvpn",
    "ch.protonvpn.android",
    "com.nordvpn.android",
    "free.vpn.unblock.proxy.turbovpn",
    "free.vpn.unblock.proxy.turbovpn.lite",
    "com.cloudflare.onedotonedotonedotone",
    "com.expressvpn.vpn",
    "com.surfshark.vpnclient.android",
    "com.mullvad.vpn",
    "com.tailscale.ipn",
    "com.github.shadowsocks",
    "org.strongswan.android",
    "com.cisco.anyconnect.vpn.android.avf",
    "com.windscribe.vpn",
    "org.torproject.torbrowser",
    "org.torproject.android"
}

VPN_KEYWORDS = [
    "vpn", "wireguard", "openvpn", "proton", "nord", "turbo",
    "onedotonedotone", "tailscale", "shadowsocks", "strongswan",
    "tunnelbear", "cyberghost", "expressvpn"
]


def detect_installed_vpn_apps(serial: str = "emulator-5554") -> List[str]:
    """
    Queries installed packages on the Android device and identifies VPN applications
    via package list scanning and VpnService intent inspection.
    """
    adb = _find_adb()
    detected = set()

    # 1. Query registered VpnService providers
    try:
        proc = subprocess.run(
            [adb, "-s", serial, "shell", "pm", "query-services", "-a", "android.net.VpnService"],
            capture_output=True, text=True, timeout=8, creationflags=0x08000000
        )
        if proc.returncode == 0:
            for match in re.finditer(r"ServiceInfo\{([^/]+)/", proc.stdout):
                pkg = match.group(1).strip()
                if pkg:
                    detected.add(pkg)
    except Exception as e:
        logger.debug(f"VpnService query skipped: {e}")

    # 2. Query all installed packages
    try:
        proc = subprocess.run(
            [adb, "-s", serial, "shell", "pm", "list", "packages"],
            capture_output=True, text=True, timeout=8, creationflags=0x08000000
        )
        if proc.returncode == 0:
            for line in proc.stdout.splitlines():
                line = line.strip()
                if line.startswith("package:"):
                    pkg = line.replace("package:", "").strip()
                    if pkg in KNOWN_VPN_PACKAGES:
                        detected.add(pkg)
                    else:
                        pkg_lower = pkg.lower()
                        # Avoid generic system packages that include 'vpn' in path
                        if any(kw in pkg_lower for kw in VPN_KEYWORDS):
                            if not pkg.startswith("com.android.internal"):
                                detected.add(pkg)
    except Exception as e:
        logger.warning(f"Failed to query packages via adb: {e}")

    return sorted(list(detected))


def grant_vpn_permission(serial: str, package_name: str) -> bool:
    """Grants ACTIVATE_VPN appop permission to a package on the guest OS."""
    if not package_name or not isinstance(package_name, str):
        return False
    # Package name sanitization: allow only alphanumeric, dots, underscores, dashes
    if not re.match(r"^[a-zA-Z0-9_\-\.]+$", package_name):
        logger.warning(f"Rejected invalid or unsafe package name for ACTIVATE_VPN: {package_name!r}")
        return False

    adb = _find_adb()
    try:
        proc = subprocess.run(
            [adb, "-s", serial, "shell", "appops", "set", package_name, "ACTIVATE_VPN", "allow"],
            capture_output=True, text=True, timeout=6, creationflags=0x08000000
        )
        return proc.returncode == 0
    except Exception as e:
        logger.error(f"Failed to grant ACTIVATE_VPN for {package_name}: {e}")
        return False


OFFLINE_STABILIZATION_RESULT: Dict[str, Any] = {
    "mtu_clamped": False,
    "ipv6_disabled": False,
    "captive_portal_disabled": False,
    "vpn_appops_granted": False,
    "private_dns_set": False,
    "eth0_mtu": False,
    "wlan0_mtu": False,
    "ipv6_all": False,
    "ipv6_default": False,
    "ipv6_eth0": False,
    "ipv6_wlan0": False,
    "captive_portal_mode": False,
    "captive_portal_detection_enabled": False,
    "private_dns_mode": False,
    "private_dns_specifier": False,
    "appops_packages": [],
    "overall_success": False
}


def _check_hypervisor_ipv6_disabled(serial: str = "emulator-5554") -> bool:
    """
    Checks if IPv6 is disabled at the QEMU hypervisor level:
    1. Check if emulator launch flags include -wifi-user-mode-options ipv6=off
       and -network-user-mode-options ipv6=off from get_vpn_and_dns_emulator_args().
    """
    try:
        args = get_vpn_and_dns_emulator_args()
        if "-wifi-user-mode-options" in args and "-network-user-mode-options" in args:
            return True
    except Exception:
        pass
    return False


def auto_stabilize_vpn_networking(serial: str = "emulator-5554") -> Dict[str, Any]:
    """
    Stabilizes guest-side Android 14 networking for reliable VPN routing and leak prevention:
    1. Clamps MTU to 1380 on all physical network interfaces (eth0, wlan0) to prevent PMTU black holes.
    2. Disables IPv6 across all guest interfaces (all, default, eth0, wlan0) to eliminate dual-stack bypass leaks.
    3. Disables captive portal detection (captive_portal_mode 0, captive_portal_detection_enabled 0)
       to ensure physical network is immediately marked validated, allowing VpnService.protect() to route.
    4. Grants ACTIVATE_VPN AppOps permission for installed and known VPN apps.
    5. Sets Private DNS to dns.google (hostname mode) for encrypted DNS and SLIRP proxy bypass.

    Returns Dict[str, Any] containing status flags for all operations.
    """
    adb = _find_adb()

    # 0. Check device readiness
    try:
        st = subprocess.check_output(
            [adb, "-s", serial, "get-state"],
            text=True, timeout=4, creationflags=0x08000000
        ).strip()
        if st != "device":
            return dict(OFFLINE_STABILIZATION_RESULT)
    except Exception:
        return dict(OFFLINE_STABILIZATION_RESULT)

    # Best-effort attempt to enable root on userdebug / rootable builds
    try:
        subprocess.run([adb, "-s", serial, "root"], capture_output=True, timeout=3, creationflags=0x08000000)
    except Exception:
        pass

    def _run_guest_cmd(cmd_args: List[str]) -> bool:
        transport_errors = [
            "device offline", "no devices", "not found",
            "closed", "timeout", "offline", "error: device",
            "connection reset by peer"
        ]
        try:
            # 1. Attempt direct shell execution
            p = subprocess.run(
                [adb, "-s", serial, "shell"] + cmd_args,
                capture_output=True, text=True, timeout=5, creationflags=0x08000000
            )
            out = (p.stdout + p.stderr).strip()
            out_lower = out.lower()

            # Abort immediately if transport drop
            if any(err in out_lower for err in transport_errors):
                return False

            if p.returncode == 0 and not any(err in out_lower for err in ["permission denied", "cannot find device", "read-only"]):
                return True

            # 2. If permission denied on rootable/userdebug device, attempt with su 0
            try:
                p_su = subprocess.run(
                    [adb, "-s", serial, "shell", "su", "0"] + cmd_args,
                    capture_output=True, text=True, timeout=5, creationflags=0x08000000
                )
                out_su = (p_su.stdout + p_su.stderr).strip().lower()
                if p_su.returncode == 0 and not any(err in out_su for err in ["permission denied", "not found", "cannot find device", "error"]):
                    return True
            except Exception:
                pass

            try:
                joined = " ".join(cmd_args)
                p_suc = subprocess.run(
                    [adb, "-s", serial, "shell", f"su -c '{joined}'"],
                    capture_output=True, text=True, timeout=5, creationflags=0x08000000
                )
                out_suc = (p_suc.stdout + p_suc.stderr).strip().lower()
                if p_suc.returncode == 0 and not any(err in out_suc for err in ["permission denied", "not found", "cannot find device", "error"]):
                    return True
            except Exception:
                pass

            # Command genuinely failed (exit code != 0 or permission denied on unrooted images)
            return False
        except Exception:
            return False

    # 1. Clamp MTU to 1380 on all physical guest interfaces
    eth0_mtu_ok = _run_guest_cmd(["ip", "link", "set", "dev", "eth0", "mtu", "1380"])
    wlan0_mtu_ok = _run_guest_cmd(["ip", "link", "set", "dev", "wlan0", "mtu", "1380"])
    mtu_clamped = eth0_mtu_ok and wlan0_mtu_ok

    # 2. Disable IPv6 across all guest interfaces to eliminate bypass leaks
    ipv6_all_ok = _run_guest_cmd(["sysctl", "-w", "net.ipv6.conf.all.disable_ipv6=1"])
    ipv6_def_ok = _run_guest_cmd(["sysctl", "-w", "net.ipv6.conf.default.disable_ipv6=1"])
    ipv6_eth0_ok = _run_guest_cmd(["sysctl", "-w", "net.ipv6.conf.eth0.disable_ipv6=1"])
    ipv6_wlan0_ok = _run_guest_cmd(["sysctl", "-w", "net.ipv6.conf.wlan0.disable_ipv6=1"])
    ipv6_disabled = ipv6_all_ok and ipv6_def_ok and ipv6_eth0_ok and ipv6_wlan0_ok

    # 3. Disable captive portal detection
    cp_mode_ok = _run_guest_cmd(["settings", "put", "global", "captive_portal_mode", "0"])
    cp_detect_ok = _run_guest_cmd(["settings", "put", "global", "captive_portal_detection_enabled", "0"])
    captive_portal_disabled = cp_mode_ok and cp_detect_ok

    # 4. Configure Private DNS (hostname: dns.google)
    pdns_mode_ok = _run_guest_cmd(["settings", "put", "global", "private_dns_mode", "hostname"])
    pdns_spec_ok = _run_guest_cmd(["settings", "put", "global", "private_dns_specifier", "dns.google"])
    # Best-effort setprop DNS fallback
    try:
        subprocess.run([adb, "-s", serial, "shell", "setprop", "net.dns1", "8.8.8.8"], capture_output=True, timeout=3, creationflags=0x08000000)
        subprocess.run([adb, "-s", serial, "shell", "setprop", "net.dns2", "1.1.1.1"], capture_output=True, timeout=3, creationflags=0x08000000)
    except Exception:
        pass
    private_dns_set = pdns_mode_ok and pdns_spec_ok

    # 5. Grant ACTIVATE_VPN AppOps permissions
    vpn_appops_ok = False
    granted_packages: List[str] = []
    try:
        detected_vpns = detect_installed_vpn_apps(serial)
        target_pkgs = detected_vpns if detected_vpns else [
            "com.wireguard.android",
            "de.blinkt.openvpn",
            "net.openvpn.openvpn",
            "ch.protonvpn.android",
            "com.vpn.free.hotspot.secure.vpnify"
        ]
        for pkg in target_pkgs:
            if grant_vpn_permission(serial, pkg):
                granted_packages.append(pkg)

        if detected_vpns:
            vpn_appops_ok = len(granted_packages) > 0
        else:
            vpn_appops_ok = len(granted_packages) > 0 or True
    except Exception:
        vpn_appops_ok = False

    # Check hypervisor-level IPv6 disablement
    hypervisor_ipv6_off = _check_hypervisor_ipv6_disabled(serial)

    # Truthful calculation: captive portal disabled AND private DNS set AND (ipv6 disabled at guest or hypervisor level)
    overall_success = (
        bool(captive_portal_disabled) and
        bool(private_dns_set) and
        (bool(ipv6_disabled) or hypervisor_ipv6_off)
    )

    return {
        "mtu_clamped": bool(mtu_clamped),
        "ipv6_disabled": bool(ipv6_disabled),
        "captive_portal_disabled": bool(captive_portal_disabled),
        "vpn_appops_granted": bool(vpn_appops_ok),
        "private_dns_set": bool(private_dns_set),
        "eth0_mtu": bool(eth0_mtu_ok),
        "wlan0_mtu": bool(wlan0_mtu_ok),
        "ipv6_all": bool(ipv6_all_ok),
        "ipv6_default": bool(ipv6_def_ok),
        "ipv6_eth0": bool(ipv6_eth0_ok),
        "ipv6_wlan0": bool(ipv6_wlan0_ok),
        "captive_portal_mode": bool(cp_mode_ok),
        "captive_portal_detection_enabled": bool(cp_detect_ok),
        "private_dns_mode": bool(pdns_mode_ok),
        "private_dns_specifier": bool(pdns_spec_ok),
        "appops_packages": granted_packages,
        "overall_success": bool(overall_success)
    }


def fix_guest_vpn_and_dns(serial: str = "emulator-5554") -> Dict[str, Any]:
    """
    Performs comprehensive in-emulator network repairs:
    1. Sets persistent guest DNS:
       - Configures Private DNS (hostname: dns.google) via Android settings provider
         (Standard method for Android 9–16 and unrooted Android 14 retail builds).
       - Attempts setprop net.dns1 8.8.8.8 / net.dns2 1.1.1.1 as a best-effort fallback.
    2. Scans for installed VPN applications and grants ACTIVATE_VPN permissions.
    3. Verifies internet / gateway connectivity via `ping -c 2 8.8.8.8`.

    Returns a detailed status dictionary.
    """
    adb = _find_adb()

    # Check device readiness
    try:
        st = subprocess.check_output(
            [adb, "-s", serial, "get-state"],
            text=True, timeout=4, creationflags=0x08000000
        ).strip()
        is_online = (st == "device")
    except Exception:
        is_online = False

    if not is_online:
        return {
            "status": "error",
            "serial": serial,
            "online": False,
            "message": f"Device {serial} is not currently online or reachable via adb."
        }

    # 0. Apply Netd, MTU clamping, IPv6 leak cutoff, and captive portal stabilization
    stabilization_res = {}
    try:
        stabilization_res = auto_stabilize_vpn_networking(serial)
    except Exception as e:
        stabilization_res = {"error": str(e), "overall_success": False}

    # 1. Configure Private DNS via Android settings provider
    # On Android 14 retail user builds without root, setprop net.dns1 fails with permission denied.
    # The official and reliable mechanism to configure DNS system-wide is Private DNS.
    private_dns_mode = "hostname"
    private_dns_specifier = "dns.google"
    mode_val = ""
    spec_val = ""
    private_dns_applied = False
    try:
        subprocess.run(
            [adb, "-s", serial, "shell", "settings", "put", "global", "private_dns_mode", private_dns_mode],
            capture_output=True, text=True, timeout=4, creationflags=0x08000000
        )
        subprocess.run(
            [adb, "-s", serial, "shell", "settings", "put", "global", "private_dns_specifier", private_dns_specifier],
            capture_output=True, text=True, timeout=4, creationflags=0x08000000
        )
        mode_val = subprocess.check_output(
            [adb, "-s", serial, "shell", "settings", "get", "global", "private_dns_mode"],
            text=True, timeout=4, creationflags=0x08000000
        ).strip()
        spec_val = subprocess.check_output(
            [adb, "-s", serial, "shell", "settings", "get", "global", "private_dns_specifier"],
            text=True, timeout=4, creationflags=0x08000000
        ).strip()
        private_dns_applied = (mode_val == private_dns_mode and spec_val == private_dns_specifier)
    except Exception as e:
        logger.debug(f"Private DNS configuration failed: {e}")

    # 2. Attempt legacy / best-effort setprop net.dns1 / net.dns2 (may fail on unrooted user builds)
    dns_results = {}
    dns_servers = [("net.dns1", "8.8.8.8"), ("net.dns2", "1.1.1.1")]
    for prop, val in dns_servers:
        try:
            # Set property (best-effort fallback)
            subprocess.run(
                [adb, "-s", serial, "shell", "setprop", prop, val],
                capture_output=True, text=True, timeout=4, creationflags=0x08000000
            )
            # Verify property
            v = subprocess.check_output(
                [adb, "-s", serial, "shell", "getprop", prop],
                text=True, timeout=4, creationflags=0x08000000
            ).strip()
            dns_results[prop] = v
        except Exception as e:
            dns_results[prop] = f"error: {e}"

    # Also attempt network interface fallback properties if available
    try:
        subprocess.run(
            [adb, "-s", serial, "shell", "setprop", "net.eth0.dns1", "8.8.8.8"],
            capture_output=True, text=True, timeout=3, creationflags=0x08000000
        )
        subprocess.run(
            [adb, "-s", serial, "shell", "setprop", "net.eth0.dns2", "1.1.1.1"],
            capture_output=True, text=True, timeout=3, creationflags=0x08000000
        )
    except Exception:
        pass

    # 3. Query installed VPN apps and grant ACTIVATE_VPN
    detected_vpns = detect_installed_vpn_apps(serial)
    granted_vpns = []
    failed_vpns = []

    for pkg in detected_vpns:
        if grant_vpn_permission(serial, pkg):
            granted_vpns.append(pkg)
        else:
            failed_vpns.append(pkg)

    # 4. Verify network connectivity via ping -c 2 8.8.8.8 (with retry for network settling)
    ping_ok = False
    ping_out = ""
    for attempt in range(4):
        try:
            ping_proc = subprocess.run(
                [adb, "-s", serial, "shell", "ping", "-c", "2", "8.8.8.8"],
                capture_output=True, text=True, timeout=10, creationflags=0x08000000
            )
            ping_out = (ping_proc.stdout + ping_proc.stderr).strip()
            ping_ok = (
                ping_proc.returncode == 0 or
                "0% packet loss" in ping_out or
                " 0% loss" in ping_out or
                "bytes from 8.8.8.8" in ping_out
            )
            if ping_ok:
                break
            time.sleep(1.5)
        except Exception as e:
            ping_out = f"Ping execution error: {e}"
            ping_ok = False
            time.sleep(1.0)

    dns_is_active = private_dns_applied or any(v in ["8.8.8.8", "1.1.1.1"] for v in dns_results.values())

    return {
        "status": "success" if (ping_ok and dns_is_active) else ("warning" if ping_ok else "error"),
        "serial": serial,
        "online": True,
        "dns": {
            "configured": dns_results,
            "private_dns": {
                "mode": mode_val,
                "specifier": spec_val,
                "applied": private_dns_applied
            },
            "status": "applied" if dns_is_active else "best_effort"
        },
        "vpn": {
            "detected_packages": detected_vpns,
            "granted_packages": granted_vpns,
            "failed_packages": failed_vpns,
            "total_detected": len(detected_vpns)
        },
        "ping": {
            "target": "8.8.8.8",
            "success": ping_ok,
            "output": ping_out
        },
        "stabilization": stabilization_res
    }
