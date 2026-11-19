# Project: GNDROiD Next-Gen Capabilities & LDPlayer-Grade Gaming Mode

## Architecture

GNDROiD is a Windows x86_64 native Android emulation platform leveraging QEMU 2026, Scrcpy 4.1, and a modular Python backend (`nexus/`). The Next-Gen capabilities introduce enterprise regional cloaking, authenticated proxy interception, high-density multi-instance synchronization, resource optimization, LDPlayer-grade gaming controls, and unified GUI integration.

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                       GNDROiD GUI                                           │
│  gndroid.pyw: GNDroidApp (Main), GNDroidSettingsDialog (Tab 5), Multi-Instance, Companion   │
└──────────────┬──────────────────────────────┬───────────────────────────────┬───────────────┘
               │                              │                               │
┌──────────────▼──────────────┐┌──────────────▼──────────────┐┌───────────────▼───────────────┐
│     Installer & Region      ││        Proxy Engine         ││     Multi-Instance & Sensors  │
│  nexus/package_installer.py ││   nexus/proxy_manager.py    ││   nexus/sync_multiplexer.py   │
│  nexus/region_controller.py ││                             ││   nexus/eco_throttler.py      │
│                             ││  - Local Auth Proxy (8990)  ││   nexus/memory_trimmer.py     │
│  - Split-APK Session Stream ││  - Tun2Socks Interceptor    ││   nexus/sensor_console.py     │
│  - Hardware Polyfill (S24U) ││  - DNS-over-Proxy           ││                               │
│  - 4-Tier Persona Switcher  ││  - Egress Kill-Switch       ││  - Scrcpy Binary Multiplex    │
│  - Play Store Token Engine  ││                             ││  - 1-5 FPS Win32 Background   │
└─────────────────────────────┘└─────────────────────────────┘│  - 4-Tier Memory Purge       │
                                                              │  - QEMU Telnet Sensors & GPX  │
                                                              └───────────────┬───────────────┘
                                                                              │
┌─────────────────────────────────────────────────────────────────────────────▼───────────────┐
│                           Precision Controls & Gaming Mode Profile                          │
│  nexus/keymapper.py: PC Keyboard/Mouse/Gamepad mapping, WASD, crosshair aim, MOBA presets   │
│  nexus/macro_engine.py: Action sequence recorder, variable speed replay, automated loops    │
│  nexus/gaming_profile.py: 120Hz refresh, direct CPU P-core pinning, low-latency Scrcpy UHID │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Multi-Format Split-APK Unpacker | Pure-Python archive parsing for `.xapk` (manifest.json), `.apkm` (info.json), `.apks` (toc.pb), and raw AAB bundles. | M1 | R1, Survey 1 |
| 2 | Native Split Session Installer | Android PackageInstaller session streaming via `pm install-create` and `adb exec-in pm install-write` (bypassing Windows PTY/CRLF corruption) with `-i com.android.vending`. | M1 | R1, Survey 1 |
| 3 | Automated OBB Deployment | Automatic extraction and deployment of game `.obb` expansion files to `/sdcard/Android/obb/<package_name>/`. | M1 | R1, Survey 1 |
| 4 | Anonymous GMS Token Dispatcher | Anonymous Google Play frontend dispatcher querying `/fdfe/delivery` for direct Google CDN APK downloads across country codes. | M1 | R1, Survey 1 |
| 5 | Certified Hardware Polyfill | Galaxy S24 Ultra (`SM-S928B`, `pineapple`) & Pixel 9 Pro (`komodo`) device build fingerprints and telephony/camera capability XML injection. | M1 | R1, Survey 1 |
| 6 | 4-Tier Region Changer: Telephony | Tier 1: MCC/MNC, SIM ISO country, SPN, CarrierConfig overrides, and Radio HAL vsock bridge. | M1 | R2, Survey 1 |
| 7 | 4-Tier Region Changer: System OS | Tier 2: System locale (`en-AE`, `ar-SA`), timezone (`Asia/Dubai`, `Asia/Riyadh`), and NTP clock offset synchronization. | M1 | R2, Survey 1 |
| 8 | 4-Tier Region Changer: Hardware | Tier 3: QEMU Telnet port 5554 `geo fix <lon> <lat>` and mock cell tower ID injection. | M1 | R2, Survey 1 |
| 9 | 4-Tier Region Changer: Network | Tier 4: Egress IP verification via `ip-api.com`, MTU 1380 clamping, IPv6 cutoff, and DNS leak prevention. | M1 | R2, Survey 1 |
| 10 | Fast Auth-Stripping Local Proxy | Host-side HTTP/HTTPS/SOCKS5 daemon on `127.0.0.1:8990` (`10.0.2.2:8990` in guest) injecting upstream Basic/Digest auth and stripping auth headers towards guest. | M2 | R3, Survey 2 |
| 11 | Transparent Tun2Socks Interceptor | Full guest TCP/UDP traffic capture forcing Wi-Fi proxy bypass apps (Flutter, Telegram, gRPC) through upstream proxy. | M2 | R3, Survey 2 |
| 12 | DNS-over-Proxy & Egress Kill-Switch | Remote DNS resolution through proxy and immediate fail-closed firewall kill-switch (`iptables -I OUTPUT 1 -j DROP`) upon proxy drop. | M2 | R3, Survey 2 |
| 13 | Multi-Instance Input Synchronizer | Real-time binary Scrcpy control socket multiplexer (`>BBQIIHHHHII` touch, `>BBIII` key) broadcasting normalized inputs from master to slaves (<2ms latency). | M3 | R4, Survey 2 |
| 14 | Eco Mode & Dynamic Background Throttling | Win32 foreground window monitor dynamically throttling unfocused instances to 1–5 FPS, demoting to `IDLE_PRIORITY_CLASS`, and pinning to E-cores. | M3 | R4, Survey 2 |
| 15 | 1-Click Memory Trimmer & Compactor | 4-tier memory purge: ART `am trim-memory RUNNING_CRITICAL`, Linux `drop_caches=3` + `compact_memory=1`, and Win32 `K32EmptyWorkingSet()`. | M3 | R4, Survey 2 |
| 16 | Extended Sensors & GPX Route Player | Authenticated QEMU Telnet console client streaming accelerometer, gyro, orientation, and GPX route playback with Haversine speed interpolation. | M3 | R4, Survey 2 |
| 17 | Precision Keymapping & Gamepad Engine | PC-level keyboard/mouse mapping (WASD, crosshair aim, MOBA smart casting) and gamepad presets with Scrcpy UHID integration. | M4 | R5, Survey 3 |
| 18 | Script Automation & Macro Engine | Touch, key, and delay recorder with variable-speed replay, repeat loops, and JSON persistence. | M4 | R5, Survey 3 |
| 19 | Gaming Mode Launch Profile | Performance profile configuring QEMU flags, 120Hz display refresh properties, host P-core affinity, and low-latency Scrcpy streaming flags. | M4 | R5, Survey 3 |
| 20 | GUI: Universal Region & Proxy Tab | Dedicated Tab 5 in `GNDroidSettingsDialog` with 1-click region selector, proxy mode switch, credentials inputs, and live egress verification badge. | M5 | R6, Survey 3 |
| 21 | GUI: Split-APK Sideload Integration | Integration with drag-and-drop dropzone, file picker dialog, and companion sidebar action for `.xapk`/`.apkm`/`.apks`/`.aab` installs. | M5 | R6, Survey 3 |
| 22 | GUI: Multi-Instance Toolbar & Actions | Input Synchronizer toggle bar, Eco Mode switch, 1-Click Memory Cleaner button, and Macro Manager dialog launcher in `GNDroidMultiInstanceManager`. | M5 | R6, Survey 3 |
| 23 | GUI: Keymapping HUD Overlay & Gaming Toggle | Visual floating HUD overlay (`GNDroidKeymapOverlay`) and 1-click Gaming Mode profile selector on main launcher and companion sidebar. | M5 | R6, Survey 3 |
| 24 | E2E Automated Verification & Hardening | Complete 5-tier test suite covering split-APK installation, proxy authentication, 4-tier region sync, input multiplexing, macro replay, and adversarial testing. | M6 | Acceptance, All |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Core Packaging, Polyfill & Region Controller | Features 1–9 (`nexus/package_installer.py`, `nexus/region_controller.py`) | none | DONE (Verified: split-APK sessions, S24U/P9P polyfills, token engine, 4-tier persona sync) |
| M2 | Enterprise Authenticated Transparent Proxy Engine | Features 10–12 (`nexus/proxy_manager.py`) | none | DONE (Verified: 127.0.0.1:8990 auth-stripping loopback, Tun2Socks interceptor, DNS-over-Proxy, egress killswitch) |
| M3 | Multi-Instance Subsystems & Extended Sensors | Features 13–16 (`nexus/sync_multiplexer.py`, `nexus/eco_throttler.py`, `nexus/memory_trimmer.py`, `nexus/sensor_console.py`) | none | DONE (Verified: sub-ms Scrcpy binary sync, 1–5 FPS background eco throttling, 4-tier RAM purge, QEMU Telnet/GPX) |
| M4 | Precision Controls, Macro Engine & Gaming Mode | Features 17–19 (`nexus/keymapper.py`, `nexus/macro_engine.py`, `nexus/gaming_profile.py`) | none | DONE (Verified: WASD/mouse delta/smart cast/gamepad, macro record/playback, 120Hz P-core profile) |
| M5 | Complete GUI Integration & Settings Controls | Features 20–23 (`gndroid.pyw`) | M1, M2, M3, M4 | DONE (Verified: Tab 5 Region & Proxy in Settings, Multi-Instance sync/eco/trim toolbar, Macro Dialog, Gaming Mode toggle, Split-bundle file pickers) |
| M6 | Final E2E Test Suite Pass & Adversarial Hardening | Feature 24 (215/215 tests passing across 14 test suites, zero regressions, py_compile verified) | M5, TEST_READY.md | DONE (100% Passed: 215/215 tests pass in 13.12s) |


## Interface Contracts

### `nexus/package_installer.py`
```python
def install_split_apk_bundle(
    serial: str,
    bundle_path: str,
    adb_path: str = "adb",
    install_as_vending: bool = True,
    progress_callback: Optional[Callable[[str, int], None]] = None
) -> Tuple[bool, str]:
    """
    Unpacks .xapk, .apkm, .apks, or .aab, validates manifests, deploys OBBs,
    creates PackageInstaller session via pm install-create, streams splits via
    adb exec-in pm install-write, commits session.
    Returns (success: bool, message: str).
    """

def apply_hardware_polyfill(
    serial: str,
    profile_name: str = "samsung_s24_ultra",
    adb_path: str = "adb"
) -> Tuple[bool, str]:
    """
    Applies certified device build properties and injects camera/telephony
    feature XMLs into guest /system/etc/permissions/ or /product/etc/permissions/.
    """

def fetch_apk_via_anonymous_gms(
    package_name: str,
    country_code: str = "AE",
    output_dir: str = "./downloads"
) -> Tuple[bool, str, List[str]]:
    """
    Queries Google Play Frontend API anonymously for direct CDN download links
    for the specified country. Returns (success, main_or_bundle_path, split_paths).
    """
```

### `nexus/region_controller.py`
```python
class UniversalRegionController:
    REGIONS: Dict[str, RegionProfile]  # AE, SA, US, GB, PK, DE, JP

    def switch_region(
        self,
        serial: str,
        region_code: str,
        adb_path: str = "adb",
        console_port: int = 5554,
        auth_token: Optional[str] = None
    ) -> RegionSwitchResult:
        """
        Atomically synchronizes:
        - Tier 1: Telephony (MCC/MNC, SIM ISO, SPN, CarrierConfig)
        - Tier 2: System OS (Locale, Timezone, NTP clock offset)
        - Tier 3: Hardware (QEMU Telnet geo fix, cell tower ID)
        - Tier 4: Network (MTU 1380, IPv6 cutoff, DNS leak prevention, egress verification)
        """

    def verify_egress(self, serial: str, expected_country: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Executes guest-side curl to ip-api.com and verifies egress IP, country, and DNS.
        """
```

### `nexus/proxy_manager.py`
```python
class EnterpriseProxyManager:
    def start_auth_proxy(
        self,
        upstream_url: str,  # http://user:pass@host:port or socks5://user:pass@host:port
        local_port: int = 8990
    ) -> int:
        """Starts host auth-stripping daemon on 127.0.0.1:local_port."""

    def attach_instance_proxy(
        self,
        serial: str,
        mode: str,  # 'local_auth' or 'tun2socks'
        upstream_config: Dict[str, Any],
        enable_kill_switch: bool = True
    ) -> bool:
        """Configures guest proxy settings and egress kill-switch."""

    def detach_instance_proxy(self, serial: str) -> bool:
        """Restores guest network settings and removes kill-switch rules."""
```

### `nexus/sync_multiplexer.py`
```python
class InputSyncMultiplexer:
    def register_master(self, serial: str, width: int, height: int, control_socket: socket.socket): ...
    def add_slave(self, serial: str, width: int, height: int, control_socket: socket.socket): ...
    def remove_slave(self, serial: str): ...
    def broadcast_event(self, packet_bytes: bytes, event_type: str): ...
```

### `nexus/eco_throttler.py` & `nexus/memory_trimmer.py`
```python
class EcoThrottler:
    def enable_eco_mode(self, instance_pids: Dict[str, int], target_fps: int = 5): ...
    def disable_eco_mode(self): ...

class MemoryTrimmer:
    @staticmethod
    def trim_instance(serial: str, host_pid: Optional[int] = None) -> Tuple[bool, int]:
        """
        Executes 4-tier purge:
        1. am trim-memory RUNNING_CRITICAL
        2. drop_caches = 3 & compact_memory = 1
        3. Win32 K32EmptyWorkingSet on host PID
        Returns (success: bool, estimated_freed_mb: int).
        """
```

### `nexus/keymapper.py` & `nexus/macro_engine.py` & `nexus/gaming_profile.py`
```python
class Keymapper:
    def load_preset(self, game_id: str) -> KeymapConfig: ...
    def handle_host_key_event(self, key: int, is_down: bool) -> List[AndroidInputEvent]: ...
    def handle_host_mouse_event(self, x: int, y: int, buttons: int) -> List[AndroidInputEvent]: ...

class MacroEngine:
    def start_recording(self): ...
    def stop_recording(self) -> MacroScript: ...
    def play_macro(self, serial: str, script: MacroScript, speed: float = 1.0, loop_count: int = 1): ...

class GamingProfileManager:
    @staticmethod
    def get_gaming_launch_args(name: str, base_args: List[str]) -> List[str]: ...
    @staticmethod
    def apply_runtime_gaming_optimizations(serial: str, host_pid: int): ...
```

## Code Layout
- `nexus/` (Exclusive write ownership per milestone worker):
  - `nexus/package_installer.py` — Owned by Milestone M1 Worker
  - `nexus/region_controller.py` — Owned by Milestone M1 Worker
  - `nexus/proxy_manager.py` — Owned by Milestone M2 Worker
  - `nexus/sync_multiplexer.py` — Owned by Milestone M3 Worker
  - `nexus/eco_throttler.py` — Owned by Milestone M3 Worker
  - `nexus/memory_trimmer.py` — Owned by Milestone M3 Worker
  - `nexus/sensor_console.py` — Owned by Milestone M3 Worker
  - `nexus/keymapper.py` — Owned by Milestone M4 Worker
  - `nexus/macro_engine.py` — Owned by Milestone M4 Worker
  - `nexus/gaming_profile.py` — Owned by Milestone M4 Worker
- `gndroid.pyw` — Owned exclusively by Milestone M5 Worker
- `tests/` — Owned exclusively by E2E Testing Track Orchestrator and Test Writers
  - `tests/test_package_installer.py`
  - `tests/test_region_controller.py`
  - `tests/test_proxy_manager.py`
  - `tests/test_sync_multiplexer.py`
  - `tests/test_eco_and_memory.py`
  - `tests/test_sensor_console.py`
  - `tests/test_keymapper_and_macro.py`
  - `tests/test_gaming_profile.py`
  - `tests/test_gui_integration.py`
  - `tests/run_all_e2e_tests.py`
