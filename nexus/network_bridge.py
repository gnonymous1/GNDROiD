"""
nexus/network_bridge.py
=======================
GNDROiD Network Adapter & Hardware Bridging Configuration Engine.

Architectural Capabilities:
1. Physical & Virtual Network Adapter Discovery:
   - Queries Windows NDIS stack via PowerShell Get-NetAdapter & psutil.
   - Identifies physical NICs (Wi-Fi 6, Realtek PCIe GbE) vs Virtual Switches (Hyper-V, VMware, VirtualBox).
   - Detects active IP addresses (192.168.100.x), MAC addresses, link speeds, and default gateway.

2. Physical Bluetooth Controller & Paired Device Discovery:
   - Queries Windows PnP Bluetooth class devices.
   - Detects Realtek Wireless Bluetooth Adapter and internal USB HCI controllers.
   - Identifies real paired physical devices (smartphones, tablets, audio headsets).

3. Tri-Mode Virtual Machine Networking:
   - Mode 1: High-Speed LAN Bridge (Host Direct Socket Bridge / Zero-Driver Mode):
     Transparently exposes the emulator's services (ports 51888, 51880, 5555, 8080, 8088)
     directly on the PC's physical LAN IP (e.g., 192.168.100.5), allowing any Android TV,
     smartphone, or PC on the home Wi-Fi to communicate directly with the emulator.
   - Mode 2: Hardware Bridged Adapter (Real DHCP 192.168.100.x via TAP/Hyper-V Switch):
     Passes QEMU hardware bridge tap flags so the home router assigns an independent IP directly.
   - Mode 3: Standard Isolated NAT (10.0.2.15).

4. Bluetooth & Netsimd Integration:
   - Controls Google netsimd virtual BLE engine (port 7300) and HCI controller bindings.
"""

import os
import sys
import json
import socket
import select
import logging
import threading
import subprocess
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("gndroid.network_bridge")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class NetworkAdapterInfo:
    def __init__(self, name: str, description: str, status: str, mac: str,
                 link_speed: str, ips: List[str], is_physical: bool, is_wifi: bool):
        self.name = name
        self.description = description
        self.status = status
        self.mac = mac
        self.link_speed = link_speed
        self.ips = ips or []
        self.is_physical = is_physical
        self.is_wifi = is_wifi

    def to_dict(self) -> Dict[str, Any]:
        tag = "[Physical Wi-Fi]" if (self.is_physical and self.is_wifi) else \
              "[Physical LAN]" if self.is_physical else \
              "[Hyper-V]" if "hyper-v" in self.description.lower() else \
              "[VMware]" if "vmware" in self.description.lower() else \
              "[VirtualBox]" if "virtualbox" in self.description.lower() else "[Virtual]"
        
        ip_str = f" ({self.ips[0]})" if self.ips else " (Disconnected)"
        display_label = f"{tag} {self.description}{ip_str}"

        return {
            "name": self.name,
            "description": self.description,
            "display_label": display_label,
            "status": self.status,
            "mac": self.mac,
            "link_speed": self.link_speed,
            "ips": self.ips,
            "is_physical": self.is_physical,
            "is_wifi": self.is_wifi,
            "primary_ip": self.ips[0] if self.ips else ""
        }


def get_system_network_adapters() -> List[Dict[str, Any]]:
    """
    Discovers all physical and virtual network adapters on the Windows host.
    Returns structured list with physical classification, IPs, and MACs.
    """
    adapters: List[Dict[str, Any]] = []

    # 1. Query PowerShell Get-NetAdapter
    ps_cmd = (
        "Get-NetAdapter | Select-Object Name, InterfaceDescription, Status, MacAddress, LinkSpeed "
        "| ConvertTo-Json -Compress"
    )
    raw_ps_data = []
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=8
        )
        if res.returncode == 0 and res.stdout.strip():
            parsed = json.loads(res.stdout.strip())
            raw_ps_data = parsed if isinstance(parsed, list) else [parsed]
    except Exception as e:
        logger.warning(f"PowerShell Get-NetAdapter query failed: {e}")

    # 2. Query IP addresses via psutil
    ip_map: Dict[str, List[str]] = {}
    try:
        import psutil
        for iface_name, snic_list in psutil.net_if_addrs().items():
            ip_map[iface_name] = [
                snic.address for snic in snic_list
                if snic.family == socket.AF_INET and not snic.address.startswith("127.")
            ]
    except Exception:
        pass

    # 3. Process adapters
    if raw_ps_data:
        for item in raw_ps_data:
            name = item.get("Name", "")
            desc = item.get("InterfaceDescription", "")
            status = item.get("Status", "Unknown")
            mac = item.get("MacAddress", "")
            speed = item.get("LinkSpeed", "")
            ips = ip_map.get(name, [])

            d_lower = desc.lower()
            is_virtual = any(k in d_lower for k in [
                "virtual", "hyper-v", "vmware", "host-only", "loopback", "direct virtual", "wsl", "tap"
            ])
            is_physical = not is_virtual
            is_wifi = "wi-fi" in name.lower() or "wireless" in d_lower or "802.11" in d_lower

            adapter = NetworkAdapterInfo(
                name=name, description=desc, status=status, mac=mac,
                link_speed=speed, ips=ips, is_physical=is_physical, is_wifi=is_wifi
            )
            adapters.append(adapter.to_dict())
    else:
        for name, ips in ip_map.items():
            adapter = NetworkAdapterInfo(
                name=name, description=name, status="Up", mac="",
                link_speed="N/A", ips=ips, is_physical=True, is_wifi="wi-fi" in name.lower()
            )
            adapters.append(adapter.to_dict())

    # Sort so active physical adapters appear first
    adapters.sort(key=lambda a: (
        0 if (a["is_physical"] and a["status"] == "Up" and a["ips"]) else
        1 if (a["status"] == "Up" and a["ips"]) else
        2 if a["is_physical"] else 3
    ))

    return adapters


def get_primary_physical_adapter() -> Optional[Dict[str, Any]]:
    """Returns the primary active physical adapter (e.g., Wi-Fi with 192.168.100.5)."""
    adapters = get_system_network_adapters()
    for a in adapters:
        if a["is_physical"] and a["status"] == "Up" and a["ips"]:
            return a
    for a in adapters:
        if a["status"] == "Up" and a["ips"]:
            return a
    return adapters[0] if adapters else None


def get_system_bluetooth_adapters() -> List[Dict[str, Any]]:
    """Discovers physical and virtual Bluetooth controllers and devices on Windows."""
    devices: List[Dict[str, Any]] = []
    ps_cmd = (
        "Get-PnpDevice -Class Bluetooth | Select-Object FriendlyName, Status, InstanceId "
        "| ConvertTo-Json -Compress"
    )
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=8
        )
        if res.returncode == 0 and res.stdout.strip():
            parsed = json.loads(res.stdout.strip())
            items = parsed if isinstance(parsed, list) else [parsed]
            for it in items:
                fn = it.get("FriendlyName", "")
                st = it.get("Status", "Unknown")
                iid = it.get("InstanceId", "")
                if not fn: continue

                fn_lower = fn.lower()
                is_physical = any(w in fn_lower for w in ["adapter", "realtek", "intel", "qualcomm", "broadcom"]) and "enumerator" not in fn_lower
                devices.append({
                    "name": fn,
                    "status": st,
                    "instance_id": iid,
                    "is_physical": is_physical
                })
    except Exception as e:
        logger.warning(f"PowerShell Bluetooth query failed: {e}")

    devices.sort(key=lambda d: 0 if d["is_physical"] else 1)
    return devices


def get_physical_bluetooth_controller() -> Optional[Dict[str, Any]]:
    """Returns the primary hardware Bluetooth controller (e.g., Realtek Wireless Bluetooth Adapter)."""
    for d in get_system_bluetooth_adapters():
        if d.get("is_physical"):
            return d
    return None


def get_paired_bluetooth_devices() -> List[str]:
    """Returns a list of clean, distinct paired mobile devices and accessories."""
    all_devs = get_system_bluetooth_adapters()
    ignored = {"service", "enumerator", "transport", "protocol", "pse", "nap", "gateway", "push"}
    clean_names = set()
    for d in all_devs:
        if d.get("is_physical"): continue
        name = d.get("name", "").strip()
        words = set(name.lower().split())
        if not words.intersection(ignored) and len(name) > 2:
            clean_names.add(name)
    return sorted(list(clean_names))


def get_default_gateway() -> str:
    """Finds the default gateway IP (e.g., 192.168.100.1)."""
    try:
        cmd = ["powershell", "-NoProfile", "-Command", "(Get-NetRoute -DestinationPrefix '0.0.0.0/0' | Select-Object -First 1).NextHop"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass
    return "192.168.100.1"


# ======================================================================
# High-Speed Multi-Port Socket Relay Daemon
# ======================================================================
class SocketRelayHub:
    """
    Multi-port high-performance socket bridge.
    Binds to 0.0.0.0 (or specified host IP) on ports like 51888, 51880, 5555, 8080, 8088,
    and transparently pipes traffic to 127.0.0.1 with TCP_NODELAY.
    """
    def __init__(self, host_bind: str = "0.0.0.0", port_map: Optional[Dict[int, int]] = None):
        self.host_bind = host_bind
        self.port_map = port_map or {51888: 51888, 51880: 51880, 5555: 5555, 8088: 8088, 8080: 8080}
        self.servers: Dict[int, socket.socket] = {}
        self.running = False
        self._threads: List[threading.Thread] = []
        self.lock = threading.Lock()

    def start(self):
        with self.lock:
            if self.running: return
            self.running = True
            for ext_port, target_port in self.port_map.items():
                t = threading.Thread(
                    target=self._run_port_listener,
                    args=(ext_port, target_port),
                    daemon=True,
                    name=f"Bridge-{ext_port}->{target_port}"
                )
                t.start()
                self._threads.append(t)

    def stop(self):
        with self.lock:
            self.running = False
            for p, s in list(self.servers.items()):
                try:
                    s.close()
                except Exception:
                    pass
            self.servers.clear()

    def _run_port_listener(self, ext_port: int, target_port: int):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind((self.host_bind, ext_port))
            server.listen(128)
            server.settimeout(1.0)
            with self.lock:
                self.servers[ext_port] = server
            logger.info(f"[Bridge] Listening on {self.host_bind}:{ext_port} -> 127.0.0.1:{target_port}")
        except Exception as e:
            logger.warning(f"[Bridge] Cannot bind port {ext_port} on {self.host_bind}: {e}")
            return

        while self.running:
            try:
                client_sock, client_addr = server.accept()
                threading.Thread(
                    target=self._pipe_connection,
                    args=(client_sock, target_port),
                    daemon=True
                ).start()
            except socket.timeout:
                continue
            except Exception:
                break

    def _pipe_connection(self, client_sock: socket.socket, target_port: int):
        try:
            target_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            target_sock.settimeout(5.0)
            target_sock.connect(("127.0.0.1", target_port))
            target_sock.settimeout(None)
            client_sock.settimeout(None)

            for s in [client_sock, target_sock]:
                try:
                    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                except Exception:
                    pass

            def forward(src, dst):
                try:
                    while self.running:
                        data = src.recv(65536)
                        if not data: break
                        dst.sendall(data)
                except Exception:
                    pass
                finally:
                    try: dst.shutdown(socket.SHUT_WR)
                    except Exception: pass

            t1 = threading.Thread(target=forward, args=(client_sock, target_sock), daemon=True)
            t2 = threading.Thread(target=forward, args=(target_sock, client_sock), daemon=True)
            t1.start()
            t2.start()
            t1.join()
            t2.join()
        except Exception:
            pass
        finally:
            try: client_sock.close()
            except Exception: pass


_global_relay_hub: Optional[SocketRelayHub] = None

def start_global_lan_bridge(host_bind: str = "0.0.0.0") -> SocketRelayHub:
    global _global_relay_hub
    if _global_relay_hub is None or not _global_relay_hub.running:
        _global_relay_hub = SocketRelayHub(host_bind=host_bind)
        _global_relay_hub.start()
    return _global_relay_hub


# ======================================================================
# Instance Network & Bridging Configuration Helpers
# ======================================================================
def get_instance_network_config(instance_name: str, avd_dir: Optional[str] = None) -> Dict[str, Any]:
    """Reads network configuration for an instance from config.ini."""
    if avd_dir is None:
        home = os.path.expanduser("~")
        avd_dir = os.path.join(home, ".android", "avd")

    cfg_file = os.path.join(avd_dir, f"{instance_name}.avd", "config.ini")
    config: Dict[str, Any] = {
        "mode": "lan_bridge",  # lan_bridge | hardware_bridged | nat
        "adapter_name": "",
        "replicate_state": True,
        "bluetooth_enabled": True,
        "bluetooth_mode": "netsimd",  # netsimd | passthrough
        "exposed_ports": "51888, 51880, 5555, 8080, 8088"
    }

    if os.path.isfile(cfg_file):
        try:
            with open(cfg_file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip()
                        if k == "gndroid.net.mode": config["mode"] = v
                        elif k == "gndroid.net.adapter": config["adapter_name"] = v
                        elif k == "gndroid.net.replicate_state": config["replicate_state"] = (v.lower() in ["yes", "true", "1"])
                        elif k == "gndroid.net.bluetooth.enabled": config["bluetooth_enabled"] = (v.lower() in ["yes", "true", "1"])
                        elif k == "gndroid.net.bluetooth.mode": config["bluetooth_mode"] = v
                        elif k == "gndroid.net.exposed_ports": config["exposed_ports"] = v
        except Exception as e:
            logger.warning(f"Failed to read network config from {cfg_file}: {e}")

    # Default adapter if empty
    if not config["adapter_name"]:
        primary = get_primary_physical_adapter()
        if primary:
            config["adapter_name"] = primary["description"]

    return config


def save_instance_network_config(instance_name: str, net_cfg: Dict[str, Any], avd_dir: Optional[str] = None) -> bool:
    """Saves network configuration into config.ini for the instance."""
    if avd_dir is None:
        home = os.path.expanduser("~")
        avd_dir = os.path.join(home, ".android", "avd")

    cfg_file = os.path.join(avd_dir, f"{instance_name}.avd", "config.ini")
    if not os.path.isfile(cfg_file):
        return False

    keys_to_write = {
        "gndroid.net.mode": str(net_cfg.get("mode", "lan_bridge")),
        "gndroid.net.adapter": str(net_cfg.get("adapter_name", "")),
        "gndroid.net.replicate_state": "yes" if net_cfg.get("replicate_state", True) else "no",
        "gndroid.net.bluetooth.enabled": "yes" if net_cfg.get("bluetooth_enabled", True) else "no",
        "gndroid.net.bluetooth.mode": str(net_cfg.get("bluetooth_mode", "netsimd")),
        "gndroid.net.exposed_ports": str(net_cfg.get("exposed_ports", "51888, 51880, 5555, 8080, 8088"))
    }

    try:
        lines: List[str] = []
        with open(cfg_file, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        new_lines: List[str] = []
        found_keys = set()
        for line in lines:
            line_str = line.strip()
            if "=" in line_str and not line_str.startswith("#"):
                k, _ = line_str.split("=", 1)
                k = k.strip()
                if k in keys_to_write:
                    new_lines.append(f"{k} = {keys_to_write[k]}\n")
                    found_keys.add(k)
                    continue
            new_lines.append(line)

        for k, v in keys_to_write.items():
            if k not in found_keys:
                new_lines.append(f"{k} = {v}\n")

        with open(cfg_file, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        return True
    except Exception as e:
        logger.error(f"Failed to write network config to {cfg_file}: {e}")
        return False


def get_emulator_network_args(instance_name: str) -> List[str]:
    """Generates launch arguments for emulator.exe according to network configuration."""
    cfg = get_instance_network_config(instance_name)
    mode = cfg.get("mode", "lan_bridge")
    args: List[str] = []

    # Mode 2: Hardware Bridged Adapter (TAP / Hyper-V Switch)
    if mode == "hardware_bridged":
        adapter = cfg.get("adapter_name", "")
        args.extend([
            "-qemu",
            "-net", "nic,model=virtio",
            "-net", f"tap,ifname={adapter or 'OpenVPN TAP-Windows6'}"
        ])

    # Bluetooth netsimd / HCI
    if cfg.get("bluetooth_enabled", True):
        args.extend(["-grpc", "7300"])

    return args
