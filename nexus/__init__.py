"""
Nexus Wireless Mirroring & Remote ADB Control Suite for GNDROiD.
Developed for high-performance, resilient low-latency Android device streaming.
"""

from .wireless_mirror import (
    WirelessMirrorManager,
    get_lan_diagnostic_info,
    WirelessPairingEngine,
    WirelessReconnectionWatchdog,
)
from .gndroid_companion_client import (
    GNDroidCompanionClient,
    GNDroidSubnetRadar,
    GNDroidConnectionWatchdog,
)
from .display_and_vpn import (
    get_secondary_display_config,
    set_secondary_display_config,
    sanitize_multi_display_config,
    auto_stabilize_vpn_networking,
    fix_guest_vpn_and_dns,
    get_vpn_and_dns_emulator_args,
    get_multi_display_emulator_args,
    detect_installed_vpn_apps,
    grant_vpn_permission,
    SanitizeResult
)

__all__ = [
    "WirelessMirrorManager",
    "get_lan_diagnostic_info",
    "WirelessPairingEngine",
    "WirelessReconnectionWatchdog",
    "get_secondary_display_config",
    "set_secondary_display_config",
    "sanitize_multi_display_config",
    "auto_stabilize_vpn_networking",
    "fix_guest_vpn_and_dns",
    "get_vpn_and_dns_emulator_args",
    "get_multi_display_emulator_args",
    "detect_installed_vpn_apps",
    "grant_vpn_permission",
    "SanitizeResult",
    "GNDroidCompanionClient",
    "GNDroidSubnetRadar",
    "GNDroidConnectionWatchdog",
]
