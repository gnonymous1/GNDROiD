"""
Nexus Wireless Mirroring, Packaging, Region, Proxy, Multi-Instance & Gaming Suite for GNDROiD.
Developed for high-performance, resilient low-latency Android device virtualization and control.
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
    SanitizeResult,
)
from .package_installer import (
    install_split_apk_bundle,
    apply_hardware_polyfill,
    fetch_apk_via_anonymous_gms,
    NativeSplitApkInstaller,
    HardwarePolyfill,
    AnonymousGmsDispatcher,
    SplitBundleManifest,
)
from .region_controller import (
    UniversalRegionController,
    RegionProfile,
    RegionPersona,
    RegionSwitchResult,
)
from .proxy_manager import (
    EnterpriseProxyManager,
    UpstreamConfig,
    LocalProxyDaemon,
    TransparentTun2SocksInterceptor,
    EgressKillSwitch,
    ProxyMode,
    ProxyProtocol,
)
from .sync_multiplexer import (
    InputSyncMultiplexer,
    InstanceNode,
    encode_touch_packet,
    decode_touch_packet,
    encode_key_packet,
    decode_key_packet,
    scale_coordinate,
)
from .eco_throttler import (
    EcoThrottler,
    Win32ProcessApi,
    InstanceInfo,
)
from .memory_trimmer import (
    MemoryTrimmer,
    TrimResult,
)
from .sensor_console import (
    QemuTelnetConsole,
    GpxRoutePlayer,
    haversine_distance,
    haversine_bearing,
)
from .keymapper import (
    Keymapper,
    PrecisionKeymapper,
    KeymapConfig,
    KeymapNode,
    AndroidInputEvent,
)
from .macro_engine import (
    MacroEngine,
    MacroScript,
    MacroStep,
)
from .gaming_profile import (
    GamingModeProfile,
    GamingProfileManager,
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
    "install_split_apk_bundle",
    "apply_hardware_polyfill",
    "fetch_apk_via_anonymous_gms",
    "NativeSplitApkInstaller",
    "HardwarePolyfill",
    "AnonymousGmsDispatcher",
    "SplitBundleManifest",
    "UniversalRegionController",
    "RegionProfile",
    "RegionPersona",
    "RegionSwitchResult",
    "EnterpriseProxyManager",
    "UpstreamConfig",
    "LocalProxyDaemon",
    "TransparentTun2SocksInterceptor",
    "EgressKillSwitch",
    "ProxyMode",
    "ProxyProtocol",
    "InputSyncMultiplexer",
    "InstanceNode",
    "encode_touch_packet",
    "decode_touch_packet",
    "encode_key_packet",
    "decode_key_packet",
    "scale_coordinate",
    "EcoThrottler",
    "Win32ProcessApi",
    "InstanceInfo",
    "MemoryTrimmer",
    "TrimResult",
    "QemuTelnetConsole",
    "GpxRoutePlayer",
    "haversine_distance",
    "haversine_bearing",
    "Keymapper",
    "PrecisionKeymapper",
    "KeymapConfig",
    "KeymapNode",
    "AndroidInputEvent",
    "MacroEngine",
    "MacroScript",
    "MacroStep",
    "GamingModeProfile",
    "GamingProfileManager",
]
