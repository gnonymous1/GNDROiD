# Project: GNDROiD Core Enhancements & Networking Architecture

## Architecture
GNDROiD is an institutional-grade, hyper-performant Android emulation platform on Windows. The system architecture spans three primary tiers:
1. **Host GUI & Management Layer (`gndroid.pyw`, `nexus/`):**
   - PyQt-based multi-instance controller, instance settings, QR modals, companion sidebar, and app drawer.
   - Shortcut & window manager orchestrating floating Windows desktop application viewports via hardware-accelerated Scrcpy 4.1 virtual display pipelines.
2. **Emulation & Virtualization Layer (`AVDManager`, QEMU Ranchu, `hypervisor/`):**
   - Launch flag generation, dynamic display hot-plugging (`-multidisplay`, `-hotplug-multi-display`), and memory/CPU resource allocation.
   - Networking subsystem bridging host networking to the guest VM via QEMU SLIRP and kernel-level TAP/Wintun adapters.
3. **Android Guest OS Runtime (Android 14 API 34 x86_64):**
   - Multi-user sandboxing architecture supporting tiered profile cloning (`android.os.usertype.profile.CLONE` and `android.os.usertype.full.SECONDARY`).
   - Network routing stack: `Netd`, `VpnService`, fwmark policy routing, MTU clamping, and IPv6 leak prevention.
   - Developer options and adbd: Wireless debugging daemon, TLS 1.3 SPAKE2 authentication, and mDNS service advertisement.

```
+-----------------------------------------------------------------------------------+
|                              GNDROiD Host Desktop (Windows)                       |
|                                                                                   |
|  +--------------------+   +---------------------+   +--------------------------+  |
|  | Main Control Window|   | Screen-Fitted QR    |   | App Drawer & Cloner      |  |
|  | & Instance Settings|   | Dialog (1:1 Ratio)  |   | (Multi-Account / Filters)|  |
|  +--------------------+   +---------------------+   +--------------------------+  |
|            │                         │                           │                |
|            │ (Presets & Flags)       │ (WIFI:T:ADB / APK URL)    │ (Launch Window)|
|            ▼                         ▼                           ▼                |
|  +-----------------------------------------------------------------------------+  |
|  |                Scrcpy 4.1 Virtual Display Manager (`--new-display`)         |  |
|  |                Floating Windows Viewports (60 FPS, Touch/Input/Resize)      |  |
|  +-----------------------------------------------------------------------------+  |
|            │                                                                      |
|            ▼ (ADB & Multi-Display HAL Hotplug)                                    |
|  +-----------------------------------------------------------------------------+  |
|  |                    QEMU / Hypervisor Emulation Layer                        |  |
|  |  - Single-NIC SLIRP (-dns-server 8.8.8.8)                                   |  |
|  |  - Multidisplay flags (-multidisplay 1,1440,3120,500,0)                    |  |
|  +-----------------------------------------------------------------------------+  |
|            │                                                                      |
|            ▼ (Virtual Hardware Bus)                                               |
|  +-----------------------------------------------------------------------------+  |
|  |                       Android 14 Guest OS (API 34)                          |  |
|  |  - Tiered Users: User 0 (Master), Profile 10 (Clone), User 11..N (Secondary)|  |
|  |  - Policy Routing: VpnService, MTU=1380, Disable IPv6, No Captive Trap     |  |
|  |  - Wireless adbd: TLS 1.3 / SPAKE2 QR Pairing + TCP 5555 Watchdog          |  |
|  +-----------------------------------------------------------------------------+  |
+-----------------------------------------------------------------------------------+
```

---

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Secondary Display Presets | Secondary display exposes presets matching primary display resolution (1440x3120 @ 500 DPI) by default and is fully configurable. | M1 | R1 |
| 2 | Anti-Letterbox Multi-Display Launch | Emulator launch flags pass `-multidisplay` and `-hotplug-multi-display`, preventing primary portrait display shrinking and black bars. | M1 | R1 |
| 3 | Instance Settings Key Preservation | `AVDManager.update_instance_settings` preserves `hw.display1.*` keys during saves, preventing configuration erasure. | M1 | R1 |
| 4 | Undistorted 1:1 QR Code Modal | Mobile download QR code modal removes invalid QSS `margin: 0 auto;`, restoring perfect 1:1 aspect ratio with intact finder patterns. | M1 | R4 |
| 5 | Screen-Fitted Modal Sizing & Controls | QR dialog expands to dynamic height (min 490px), ensuring the "Done" button and controls are 100% visible and clickable on all DPI scalings. | M1 | R4 |
| 6 | Tiered AOSP Profile Sandboxing | App cloning engine supports Clone Profile #1 + Secondary Users #2..N with `fw.max_users 32`, bypassing AOSP's 1-clone limit. | M2 | R2 |
| 7 | Dedicated Floating Windows | Each cloned app launches into its own independent floating Windows desktop window via Scrcpy 4.1 virtual display (`--new-display`). | M2 | R2 |
| 8 | Multi-Account App Drawer UI | GNDROiD App Drawer displays clone tags (`[Master]`, `[Clone #ID]`), clone action buttons, and Windows desktop `.lnk` pinning. | M2 | R2 |
| 9 | VPN Failure Root-Cause Analysis | Authoritative technical RCA documenting the 5 SLIRP/Android 14 VpnService failure mechanisms and architectural resolutions. | M3 | R3 |
| 10 | QEMU Network Flags & SLIRP Hardening | Hardened QEMU flags (`-dns-server 8.8.8.8,1.1.1.1`, `-netdelay none`, single-NIC VirtioWifi avoidance) to ensure stable tunnel egress. | M3 | R3 |
| 11 | Guest Netd & MTU Stabilization | Guest-side network stabilization: clamp MTU to 1380, disable IPv6 leak bypass, disable captive portal probe trap, grant `ACTIVATE_VPN`. | M3 | R3 |
| 12 | Commercial VPN Verification | Verification that WireGuard, OpenVPN, and ProtonVPN connect cleanly and external IP lookups reflect the VPN endpoint. | M3 | R3 |
| 13 | Wireless Debugging Comparative Report | Deep technical research report comparing AOSP Wireless Debugging, SPAKE2 TLS, Shizuku IPC, LADB, and TCP 5555. | M4 | R5 |
| 14 | Integrated Wireless ADB Provisioning | Dual-engine wireless provisioning: Android 11+ Zero-Cable QR code pairing + 1-Click TCP 5555 fallback with auto-reconnection watchdog. | M4 | R5 |
| 15 | Automated Verification Suite | Independent automated test suite validating display presets, app cloning & floating windows, VPN IP switching, QR rendering, and ADB auth. | M5 | R6 |

---

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | UI & Display Subsystem | R1 Secondary Display Presets & Letterbox Fix, R4 Screen-Fitted 1:1 QR Code Modal | None | DONE |
| M2 | App Cloning & Floating Windows | R2 Tiered AOSP Sandboxing & Scrcpy 4.1 Virtual Display Floating Windows | None | DONE |
| M3 | Emulator VPN Architecture & IP Routing | R3 Root-Cause Analysis, QEMU SLIRP Hardening, Guest Netd/MTU Clamp, Public IP Verification | None | DONE |
| M4 | Wireless Debugging Research & Provisioning | R5 Comparative Research Report, SPAKE2 QR Pairing Engine, TCP 5555 Fallback | None | DONE |
| M5 | E2E Integration & Verification Track | R6 Independent Automated Verification Test Suite (Tiers 1-4), Forensic Audit & Hardening | M1, M2, M3, M4 | IN_PROGRESS (Hardening) |

---

## Interface Contracts

### `nexus.display_and_vpn` ↔ `gndroid.pyw` (AVDManager)
- **`get_multi_display_emulator_args(instance_name: str) -> List[str]`**:
  Returns `["-multidisplay", f"1,{w},{h},{d},{flag}", "-hotplug-multi-display"]` when secondary display is enabled.
- **`sanitize_multi_display_config(cfg_path: str) -> bool`**:
  Sanitizes `config.ini`, ensuring secondary display dimensions match primary display aspect ratio and resolution (1440x3120 @ 500 DPI).
- **`auto_stabilize_vpn_networking(serial: str) -> Dict[str, bool]`**:
  Clamps MTU to 1380 on all guest interfaces, disables IPv6 (`disable_ipv6=1`), disables captive portal probe (`captive_portal_mode 0`), and sets Private DNS.

### `nexus.app_cloner_and_window` ↔ `gndroid.pyw` (AppDrawer & CLI)
- **`AppCloneManager.create_clone_user(serial: str, name: str) -> int`**:
  Creates Clone profile #1 (`android.os.usertype.profile.CLONE`), or falls back to Secondary User (`android.os.usertype.full.SECONDARY`) with `fw.max_users 32`. Returns allocated `user_id`.
- **`AppCloneManager.clone_app_to_user(serial: str, package_name: str, user_id: int) -> bool`**:
  Zero-copy installation via `pm install-existing --user <user_id> <package_name>`.
- **`AppWindowManager.launch_app_in_dedicated_window(serial: str, package_name: str, app_title: str, user_id: int, width: int, height: int, density: int)`**:
  Spawns Scrcpy 4.1 process with `--new-display`, `--start-app`, `--window-title`, and `-x, --flex-display`.

### `nexus.wireless_mirror` ↔ `gndroid.pyw` (Sidebar & Modals)
- **`QRPairingWorker.generate_qr_payload(service_name: str, pin: str) -> str`**:
  Generates standard AOSP pairing string `WIFI:T:ADB;S:<service_name>;P:<pin>;;`.
- **`QRPairingWorker.pair_and_connect(serial: str, ip: str, port: int, pin: str) -> bool`**:
  Performs `adb pair <ip>:<pairing_port> <pin>` and resolves connect port via mDNS or fallback.

---

## Code Layout
- `gndroid.pyw`: Main application window, AVDManager, GNDroidAppDrawer, GNDroidSettingsDialog, QR download dialog.
- `nexus/display_and_vpn.py`: Secondary display configuration, presets, sanitization, and guest-side VPN networking doctor.
- `nexus/app_cloner_and_window.py`: Multi-user profile management, zero-copy cloning, Scrcpy virtual display launcher, and Windows shortcut manager.
- `nexus/wireless_mirror.py`: Wireless ADB pairing worker, mDNS discovery, and TCP 5555 watchdog.
- `docs/VPN_NETWORKING_ARCHITECTURE_ROOT_CAUSE.md`: Root-cause technical analysis for R3.
- `docs/WIRELESS_DEBUGGING_RESEARCH_REPORT.md`: Comprehensive technical research report for R5.
- `scripts/verify_secondary_display.py`: Automated verification for R1.
- `scripts/test_app_cloner_and_window.py`: Automated verification for R2.
- `scripts/verify_vpn_routing.py`: Automated verification for R3.
- `scripts/verify_qr_dialog.py`: Automated verification for R4.
- `scripts/verify_wireless_debugging.py`: Automated verification for R5.
- `scripts/run_e2e_verification.py`: Full test runner executing all verification suites.
