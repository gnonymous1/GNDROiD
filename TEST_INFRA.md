# E2E Test Infra: GNDROiD Core Enhancements & Networking Architecture

## Test Philosophy
- Opaque-box, requirement-driven verification derived directly from `ORIGINAL_REQUEST.md`.
- Systematic 4-tier methodology:
  - **Tier 1 - Feature Coverage**: Isolated happy-path verification of each feature (≥5 test cases per feature).
  - **Tier 2 - Boundary & Corner Cases**: Stress-testing edge cases, DPI bounds, AOSP limits, and MTU thresholds (≥5 test cases per feature).
  - **Tier 3 - Cross-Feature Combinations**: Pairwise testing of interacting subsystems (e.g., VPN routing active while app clone launches in dedicated floating window; secondary display active during wireless ADB pairing).
  - **Tier 4 - Real-World Application Scenarios**: Realistic end-to-end user workflows (e.g. multi-account messaging apps on separate floating viewports under active commercial VPN tunnel).

---

## Feature Inventory & Test Coverage Matrix
| # | Feature | Source | Tier 1 | Tier 2 | Tier 3 | Tier 4 |
|---|---------|--------|:------:|:------:|:------:|:------:|
| 1 | Secondary Display Presets | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ | ✓ |
| 2 | Anti-Letterbox Multi-Display Launch | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ | ✓ |
| 3 | Instance Settings Key Preservation | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ | ✓ |
| 4 | Undistorted 1:1 QR Code Modal | ORIGINAL_REQUEST §R4 | 5 | 5 | ✓ | ✓ |
| 5 | Screen-Fitted Modal Sizing & Controls | ORIGINAL_REQUEST §R4 | 5 | 5 | ✓ | ✓ |
| 6 | Tiered AOSP Profile Sandboxing | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ | ✓ |
| 7 | Dedicated Floating Windows | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ | ✓ |
| 8 | Multi-Account App Drawer UI | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ | ✓ |
| 9 | VPN Failure Root-Cause Analysis | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ | ✓ |
| 10 | QEMU Network Flags & SLIRP Hardening | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ | ✓ |
| 11 | Guest Netd & MTU Stabilization | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ | ✓ |
| 12 | Commercial VPN Verification | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ | ✓ |
| 13 | Wireless Debugging Comparative Report | ORIGINAL_REQUEST §R5 | 5 | 5 | ✓ | ✓ |
| 14 | Integrated Wireless ADB Provisioning | ORIGINAL_REQUEST §R5 | 5 | 5 | ✓ | ✓ |

---

## Test Architecture
- **Master Test Runner**: `python scripts/run_e2e_verification.py`
  - Exit code `0` indicates 100% test pass.
  - Generates machine-readable JSON results and Markdown summary table.
- **Subsystem Test Harnesses**:
  - `scripts/verify_secondary_display.py`: Validates display preset consistency, `config.ini` keys, and QEMU multi-display launch args.
  - `scripts/verify_qr_dialog.py`: Validates pixel aspect ratio (width == height == 200px), finder pattern completeness, dialog bounds, and Done button visibility.
  - `scripts/test_app_cloner_and_window.py`: Validates Clone profile #1, Secondary User #2..N allocation, zero-copy package cloning, and Scrcpy 4.1 `--new-display` process arguments.
  - `scripts/verify_vpn_routing.py`: Validates MTU clamping (1380), IPv6 disablement, captive portal bypass, tun0 route table binding, and public IP changes via curl/urllib against ipify/ifconfig.me.
  - `scripts/verify_wireless_debugging.py`: Validates AOSP QR payload parsing, `adb pair` simulation, TCP 5555 fallback, and auto-reconnection watchdog.

---

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Target Workflow |
|---|----------|--------------------|-----------------|
| 1 | Multi-Account Floating Workflow | F6, F7, F8, F1 | Launch WhatsApp Master on primary display (1440x3120), clone account into dedicated floating window on virtual display 1, verify simultaneous independent operation. |
| 2 | Secure Geo-Restricted Browsing | F9, F10, F11, F12 | Launch commercial VPN client in guest VM, verify WireGuard handshake, confirm public IP switches to VPN endpoint, and confirm DNS resolves without ISP leaks. |
| 3 | Zero-Cable Wireless Development | F4, F13, F14 | Connect phone via AOSP Wireless Debugging QR code, verify SPAKE2 handshake, disconnect USB, verify continuous ADB access via background watchdog. |
| 4 | Dual-Display Power User Setup | F1, F2, F3 | Enable secondary display matching Galaxy S24 Ultra (1440x3120), verify primary display retains full height with 0 black letterbox pixels. |
| 5 | Cross-Subsystem Stress Test | F1, F6, F7, F11, F12 | Run 2 app clones in floating windows while active WireGuard tunnel routes all guest traffic through external VPN server. |
