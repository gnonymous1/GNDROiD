# Project: GNDROiD Comprehensive Multi-Disciplinary Audit & Codebase Remediation

## Architecture
GNDROiD is an institutional-grade, hyper-performant Android emulation and device orchestration platform on Windows.
The complete system architecture comprises five interrelated subsystems:

1. **Host GUI & Process Management (`gndroid.pyw`, `nexus/`):**
   - PyQt-based multi-instance controller, instance settings, companion sidebar, and app drawer.
   - Dynamic Scrcpy 4.1 virtual display floating window manager.
   - Non-blocking background workers (`QThread` / `QRunnable`) for APK installations, ADB operations, and hardware introspection.

2. **Core Virtualization & Emulation Layer (QEMU Ranchu, `hypervisor/`, `nexus/display_and_vpn.py`):**
   - Single-NIC SLIRP networking, dynamic multi-display hot-plugging, memory/vCPU allocation, and MTU stabilization.
   - Win32 Job Object and PID process tracking preventing orphaned QEMU and Scrcpy background tasks.

3. **Android Guest OS Runtime (Android 14 API 34 x86_64):**
   - Multi-user sandboxing architecture supporting tiered profile cloning (`android.os.usertype.profile.CLONE` and `android.os.usertype.full.SECONDARY`).
   - Network routing stack: `Netd`, `VpnService`, MTU clamping (1380), and IPv6 leak prevention.
   - Wireless debugging daemon (TLS 1.3 SPAKE2 QR pairing and TCP 5555 watchdog).

4. **Native Rust Orchestration Engine (`gndroid-cli/`):**
   - High-performance native CLI compiled to `gndroid.exe` / `tools/gndroid.exe`.
   - Direct subprocess orchestration for VM launch, device mirroring, app launcher desktop shortcuts, and system health checks.

5. **Automated Verification & E2E Testing Harness (`scripts/`, `tests/`):**
   - Multi-tier automated test suite verifying process lifecycle, UI contracts, CLI commands, ADB Doctor, and guest networking without fake stubs, length hacks, or tautological assertions.

---

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Genuine System Info & Hardware Banners | Replace hardcoded 16GB/16Core marketing banners with live hardware introspection via `psutil`/system APIs. | M1 | Survey Core UI |
| 2 | Genuine Gesture / Sensor Implementation | Replace fake `KEYCODE_MENU` (82) in shake action with genuine sensor event injection or clean developer tooling. | M1 | Survey Core UI |
| 3 | Genuine Standby / Screen Off Logic | Replace destructive `KEYCODE_POWER` (26) with non-locking scrcpy `--turn-screen-off` or genuine standby control. | M1 | Survey Core UI |
| 4 | Elimination of Test Argument Length Hacks | Remove `VpnAndDnsArgs` and `MultiDisplayArgs` length/equality spoofing hacks in `nexus/display_and_vpn.py`. | M1 | Survey Engine & CLI |
| 5 | Genuine Hypervisor IPv6 & MTU Checks | Replace tautological `or True` and fake `True` returns in `display_and_vpn.py` with real guest interface inspection. | M1 | Survey Engine |
| 6 | Elimination of Simulated AI/Hypervisor Stubs | Remove or implement genuine logic for dummy WhatsApp SMS, fake Play Integrity, and dummy snapshot returns. | M1 | Survey Engine |
| 7 | Scrcpy Stderr Pipe Deadlock Prevention | Implement asynchronous non-blocking stream draining for Scrcpy stderr/stdout across all launcher modules. | M2 | Survey Engine |
| 8 | Process Tree Lifecycle & Win32 Job Objects | Enforce strict process tracking and Win32 Job Object assignment to guarantee zero orphan QEMU or Scrcpy processes. | M2 | Survey Engine |
| 9 | Multi-Instance Clean Teardown & File Lock Guard | Fix instance deletion race condition by verifying process termination and file lock release before disk cleanup. | M2 | Survey Engine |
| 10 | Background Thread Pooling & USB Non-Interference | Refactor `LanRadarWorker` thread explosion and prevent `DeviceScannerWorker` from forcing TCP 5555 on USB devices. | M2 | Survey Engine |
| 11 | Multi-Instance Quick Clone Signature Alignment | Align `AVDManager.clone_instance` parameters with caller to resolve immediate `TypeError` crash. | M3 | Survey Core UI |
| 12 | Companion Sidebar Settings & Auto-Tiling Fixes | Correct settings dialog argument shifting and fix case sensitivity bug in desktop window auto-tiling. | M3 | Survey Core UI |
| 13 | Non-Blocking Main GUI Event Loop | Offload blocking `subprocess.run` (APK installs, file drops, ADB queries) to background worker threads. | M3 | Survey Core UI |
| 14 | Accurate Operation Status & Error Feedback | Ensure success dialogs only display when `proc.returncode == 0` with real error messages on failures. | M3 | Survey Core UI |
| 15 | Companion Sidebar Docking Filter | Fix window title matching in sidebar monitor to prevent false docking to GNDROiD launcher itself. | M3 | Survey Core UI |
| 16 | Rust CLI Desktop App Shortcut Support | Add `--app <pkg>` and `--window` flags to `gndroid-cli` to fix immediate crashes when launching pinned shortcuts. | M4 | Survey CLI |
| 17 | Rust CLI Subcommand & Argument Routing | Fix `launch --avd <name>` parameter passing to Python and ensure `mirror -s <serial>` retains target serial. | M4 | Survey CLI |
| 18 | Rust CLI Multi-Device Mirroring Guard | Fix singleton guard to allow concurrent mirroring of distinct device serials. | M4 | Survey CLI |
| 19 | Test Suite Hardening & Crash Remediation | Fix `scripts/run_e2e_verification.py` line 596 crash and ensure tests pass cleanly in offline/mock/live modes. | M5 | Survey CLI & Tests |
| 20 | Dual-Track Comprehensive E2E Test Suite | Implement Tiers 1-4 tests (Category-Partition, BVA, Pairwise, Real-World) and publish `TEST_READY.md`. | M5 | Survey Tests |
| 21 | Professional Audit Report Publication | Deliver exhaustive technical report covering root causes, audit catalog, remediations, and verification. | M6 | Survey Docs |
| 22 | Repository Documentation Overhaul | Fully update `README.md`, architecture guides, CLI manuals, and installer scripts to match live code. | M6 | Survey Docs |

---

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Simulated & Fake Code Elimination | Features 1-6: Remove fake banners, fake shake, fake screen off, argument length hacks, tautologies, and dummy stubs | None | DONE |
| M2 | Subprocess Lifecycle & Process Safety | Features 7-10: Win32 Job Objects, Scrcpy pipe deadlock fix, clean VM teardown, thread pooling | None | DONE |
| M3 | Python Core GUI & UX Hardening | Features 11-15: Clone signature fix, sidebar settings/docking, auto-tiling, non-blocking Qt event loop | M1, M2 | DONE |
| M4 | Native Rust CLI Hardening & IPC | Features 16-18: `--app` support, `--avd` and serial propagation, multi-device singleton guard | M2 | DONE |
| M5 | Automated Testing Suite & Verification Track | Features 19-20: Test runner crash fixes, fake assertion removal, 4-tier verification, `TEST_READY.md` | M1, M2, M3, M4 | DONE |
| M6 | Professional Report & Documentation Overhaul | Features 21-22: Comprehensive audit report, README, architecture guides, installer updates | M1, M2, M3, M4, M5 | DONE |

---

## Interface Contracts

### `nexus.display_and_vpn` ↔ `gndroid.pyw` & Test Oracles
- **`get_vpn_and_dns_emulator_args(instance_name: str) -> List[str]`**:
  Must return genuine `list` without spoofed `__len__`, `__eq__`, or `__radd__`.
- **`get_multi_display_emulator_args(instance_name: str) -> List[str]`**:
  Must return genuine standard `list` without custom spoofing classes.
- **`auto_stabilize_vpn_networking(serial: str) -> Dict[str, bool]`**:
  Returns dictionary of genuine boolean check results from real ADB shell commands; no hardcoded `or True`.

### `gndroid-cli` ↔ `gndroid.pyw` (CLI Orchestrator Protocol)
- **`gndroid.exe --app <package_name> [--window]`**:
  Must parse successfully and execute application in dedicated Scrcpy window.
- **`gndroid.exe launch --avd <instance_name>`**:
  Must propagate `<instance_name>` to `gndroid.pyw` and initiate VM boot for that specific instance.
- **`gndroid.exe mirror [-s <serial>]`**:
  Must pass `-s <serial>` directly to Scrcpy without clearing or hardcoding empty string.

### `AVDManager.clone_instance` ↔ Caller (`GNDroidMultiInstanceManager`)
- **`clone_instance(src_name: str, dst_name: str, dst_display_name: str, ram_mb: int = None, cores: int = None, root_enabled: bool = None, full_clone: bool = True, progress_cb=None, deep_copy_snapshots: bool = False) -> None`**:
  Signature must accept all caller parameters with consistent defaults.

---

## Code Layout
- `gndroid.pyw`: Core GUI application, MultiInstanceManager, Settings, Companion Sidebar, and App Drawer.
- `nexus/display_and_vpn.py`: Emulation display flags, MTU clamping, and VPN network stabilization.
- `nexus/app_cloner_and_window.py`: Multi-user sandboxing, Scrcpy virtual display launcher, and Windows desktop shortcuts.
- `nexus/wireless_mirror.py`: Wireless ADB pairing, mDNS discovery, and TCP 5555 watchdog.
- `gndroid-cli/src/main.rs`: Native Rust CLI entrypoint and argument parser.
- `hypervisor/`: Rust hypervisor integrations and snapshot handling.
- `ai-control-plane/`: Control plane components and automated testing scripts.
- `scripts/`: Verification test suites and master runners (`run_e2e_verification.py`, `test_rust_cli.py`).
- `installer/`: InnoSetup script (`gndroid_installer.iss`) and PowerShell installation scripts.
- `docs/`: Architecture specifications, research reports, and technical manuals.
