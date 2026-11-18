# GNDROiD v2.5.0 Early Access — Institutional Android Virtualization & Device Orchestrator

[![Early Access](https://img.shields.io/badge/Release-v2.5.0%20Early%20Access-brightgreen.svg?style=flat-square)](https://github.com/gnonymous1/GNDROiD/releases/tag/v2.5.0)
[![License](https://img.shields.io/badge/License-Apache%202.0%20w%2F%20Trademark-blue.svg?style=flat-square)](LICENSE)
[![Contributions Welcome](https://img.shields.io/badge/Contributions-Welcome-orange.svg?style=flat-square)](CONTRIBUTING.md)
[![Verification](https://img.shields.io/badge/Verification%20Suite-207%2F207%20Passed%20(100%25)-brightgreen.svg?style=flat-square)](TEST_READY.md)
[![Platform](https://img.shields.io/badge/Platform-Windows%2011%20%7C%20WHPX%20%7C%20x86__64-blue.svg?style=flat-square)]()
[![Streaming](https://img.shields.io/badge/Streaming-Scrcpy%204.1%20Virtual%20Displays-orange.svg?style=flat-square)]()
[![Networking](https://img.shields.io/badge/Network-Hardware%20Bridged%20%2F%20Router%20DHCP-success.svg?style=flat-square)]()

---

> ### 🌟 **Public Early Access Release & Call for Open-Source Contributions**
> Welcome to **GNDROiD v2.5.0 Early Access**! GNDROiD is an institutional-grade, hyper-performant Android virtualization, sandboxing, and physical device orchestration engine architected for Windows 10 & 11 by **Ghulam Nabi Kalhoro**.
>
> We are officially inviting the open-source community—developers, kernel hackers, UI designers, testers, and emulation enthusiasts—to contribute, test, and shape the next generation of Windows-native Android virtualization.
>
> 🚀 **Quick Navigation:**
> - 📖 **[Complete Installation & User Guide (12 Sections)](INSTALL_AND_USER_GUIDE.md)**
> - 🤝 **[Community Contribution Guidelines & Dev Roadmap](CONTRIBUTING.md)**
> - 🔒 **[Security Policy & Secret Protection Guide](SECURITY.md)**
> - 📜 **[Apache 2.0 License & Trademark Reservation](LICENSE)**
> - 🐛 **[Report a Bug](https://github.com/gnonymous1/GNDROiD/issues/new?template=bug_report.md)** | 💡 **[Request a Feature](https://github.com/gnonymous1/GNDROiD/issues/new?template=feature_request.md)**

---

**GNDROiD** combines native Windows ergonomics with direct hardware virtualization, allowing operators to run multi-account sandboxes, assign independent physical router IP addresses to parallel Android instances, stream physical and virtual devices at 60–120 FPS, and automate end-to-end user journeys with zero process orphaning.

---

## What's New in v2.5.0 Early Access

1. 🌐 **Mode 2 Hardware Bridged Networking (Router DHCP):**
   - Connects the Android VM directly to your physical network adapter (Realtek Wi-Fi / Ethernet) via TAP/NDIS.
   - Your home or office router assigns Android a real `192.168.100.x` address directly, making it an independent physical node on your LAN.
   - Direct Static IP and custom DNS (Google `8.8.8.8`, Cloudflare `1.1.1.1`) configuration straight from the UI.
2. 👥 **Multi-Instance Parallel Execution with Independent Router IPs:**
   - Run 3 to 4+ Android instances simultaneously, each acquiring its own unique MAC address and distinct router DHCP lease (`.100.155`, `.100.156`, `.100.157`).
3. ⚡ **Silent Zero-Flicker Background Architecture:**
   - All internal shell processes (QEMU hardware probing, netsimd, scrcpy, adb, Bluetooth detection) execute silently with Win32 `CREATE_NO_WINDOW (0x08000000)`, eliminating terminal popups and UI lag.
4. 📡 **Google `netsimd` Bluetooth HCI Controller & Sensor Passthrough:**
   - Google `netsimd` virtual BLE engine on Port 7300 paired with host Bluetooth radio discovery.
   - Hardware biometrics (USB Fingerprint Scanner simulation), GPS real geolocation, accelerometer, gyroscope, and ambient light sensors.
5. 📱 **`GNDROiD Link` Wireless Companion & Android TV Mode:**
   - Zero-cable wireless LAN screen mirroring (Port 51880) and Android TV big-screen receiver mode.
6. 📦 **Turnkey Windows Packaging & User Manual:**
   - Inno Setup Wizard installer and native PowerShell automated system deployer with Start Menu manual integration.

---

## Key System Capabilities

### 1. Tiered App Cloning & AOSP Multi-User Sandboxing
- **Zero-Copy Package Cloning:** Instantly provision isolated app sandboxes utilizing Android's native multi-user architecture (`android.os.usertype.profile.CLONE` and `full.SECONDARY`).
- **Complete Inode & Storage Segregation:** Each clone profile maintains fully isolated private data in `/data/user/<id>/`, allowing concurrent logins for WhatsApp, Telegram, banking portals, and social platforms without account crosstalk or token collision.
- **Dynamic Profile Quotas:** Automated profile lifecycle management with clean teardown, quota auditing, and unprivileged execution.

### 2. Scrcpy 4.1 Dedicated Floating App Windows
- **Single-App Virtual Displays:** Launch individual sandboxed applications into dedicated, borderless floating desktop windows via `--new-display=<WxH>/<DPI> --start-app=+<package>`.
- **Docked Companion Sidebar:** Each mirrored device or floating app window features an auto-docking controls ribbon providing 1-click volume, navigation, rotate, gesture shake, and screen-off controls.
- **Non-Locking Screen Standby (`Alt+O`):** Save device power and keep physical phone screens dark while streaming video and routing audio directly to host PC speakers.

### 3. Zero-Cable Wireless ADB Pairing & Monitoring
- **TLS 1.3 SPAKE2 QR Pairing:** 1-click pairing modal generating undistorted 1:1 square QR codes for instantaneous Android 11+ wireless debugging pairing.
- **Persistent Reconnection Watchdog:** Background thread continuously monitors ADB connection state, automatically reconnecting dropped Wi-Fi sessions without cable re-plugging.
- **Automatic LAN Conversion:** Convert connected USB debugging sessions into permanent wireless LAN endpoints on port 5555.

### 4. Hardened SLIRP Networking & Netd MTU Clamping
- **Elimination of MTU Black Holes:** Automatically clamps virtual network interface (`eth0`, `wlan0`) MTU to 1380 bytes, eliminating fragmentation and packet drop across WireGuard, OpenVPN, and corporate VPN tunnels.
- **Dual-Stack IPv6 Leak Prevention:** Guest sysctl hardening (`net.ipv6.conf.all.disable_ipv6=1`) and verified `/proc/net/if_inet6` inspection prevent public ISP IP and DNS leaks.
- **Automated AppOps Authorization:** Automatically grants `ACTIVATE_VPN` AppOps permissions to detected VPN packages.

### 5. Native Rust CLI Orchestrator (`gndroid.exe`)
- **Zero-Dependency Native Binary:** High-performance PE32+ executable compiled with Rust toolchain, replacing legacy batch files with zero console flashing.
- **Desktop App Shortcut Dispatcher:** Native parsing and forwarding for desktop shortcut invocations (`--app <pkg> --window --user <id>`).
- **Multi-Device Parallel Mirroring:** Dynamic per-device singleton guards allow concurrent parallel mirroring of distinct physical phones and VMs.

### 6. Win32 Job Object Process Safety & Teardown
- **Zero Zombie Processes:** Every QEMU emulator instance, Scrcpy streaming process, and ADB worker is bound to an OS-level Win32 Job Object configured with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE (0x00002000)`.
- **Asynchronous Pipe Draining (`drain_pipe_async`):** Continuous background draining of Scrcpy stderr prevents 4 KB anonymous pipe buffer deadlocks.
- **Verified File Lock Teardown:** Pre-deletion file accessibility inspection via `kernel32.CreateFileW` (`FILE_SHARE_NONE`) and progressive backoff ensures zero directory corruption on instance deletion.

---

## Tri-Mode Operating Matrix & Next-Gen Micro-VM

Beyond standard QEMU Ranchu emulation, GNDROiD incorporates a next-generation **VirtIO-first micro-VM architecture** (crosvm / Cuttlefish / Treble GSI) supporting three operational modes:

| Mode | Target Platform | Display & Resolution | Hardware Connectivity & Passthrough |
|---|---|---|---|
| **Mode 1** | **Flagship Android Smartphone** | 9:20 / 9:19.5 Portrait (1080x2400 / 1440x3120) | Rutabaga/gfxstream Vulkan 1.3 host GPU, 5G USB modem / SIM bank over vsock, KernelSU stealth root. |
| **Mode 2** | **Android TV 4K** | 16:9 Landscape (3840x2160 / 1920x1080) | Google TV Leanback UI, tactile virtual TV remote (D-Pad, Netflix/YouTube hotkeys), HDMI-CEC over vsock. |
| **Mode 3** | **Physical Phone Cloner** | Matches Native Physical Device | Clones connected phone identity and data; live USB hardware passthrough for real SIM, 50MP camera, and IMU sensors. |

*For complete hardware setup, network bridging, and operational guides, see [`INSTALL_AND_USER_GUIDE.md`](INSTALL_AND_USER_GUIDE.md).*

---

## System Requirements & Prerequisites

- **Host Operating System:** Microsoft Windows 10 (Build 19041+) or Windows 11 (x86_64).
- **Hypervisor Acceleration:** Windows Hypervisor Platform (WHPX) or Hyper-V enabled.
- **Python Runtime:** Python 3.10, 3.11, or 3.12 (with `PyQt6`, `psutil`, `pywin32`).
- **Android SDK:** Android SDK Platform-Tools (`adb.exe`), Command-Line Tools, and Android Emulator (`emulator.exe`).
- **Video Mirroring Core:** Scrcpy v4.1 or higher (bundled in `dist/gndroid/` and `tools/`).
- **Rust Toolchain (Optional for source development):** Rust 1.75+ (Cargo) for compiling `gndroid-cli`.

---

## Installation & Setup

GNDROiD provides a modern, automated installation workflow. **All legacy `.bat` scripts have been completely excised from the repository.**

### Quick Deployment via PowerShell
Execute the turnkey setup script from an elevated PowerShell terminal:

```powershell
# Run the automated deployment script
powershell.exe -ExecutionPolicy Bypass -File .\setup.ps1
```

`setup.ps1` automatically detects standalone Inno Setup packages (`installer/GNDROiD-Setup-v2.5.0-Full.exe`) or executes the automated PowerShell system deployer (`installer/install_system.ps1`), registering native desktop shortcuts and configuring system paths.

---

## Native Rust CLI Usage Manual

The native orchestrator `gndroid.exe` (and its mirrored companion `tools/gndroid.exe`) provides unified command-line control:

```
Usage: gndroid.exe [OPTIONS] [COMMAND]

Commands:
  gui        Launch GNDROiD Master Control Suite (Fluent Light UI)
  launch     Launch an Android Virtual Device (AVD) instance
  mirror     Launch Scrcpy phone mirroring with docked companion sidebar
  multi      Open Multi-Instance Manager for parallel clones and batch runs
  fix        Launch ADB Doctor, USB diagnostics, and wireless subnet radar
  lan        Convert connected USB devices to wireless LAN mode (port 5555)
  download   Open 1-Click Online Android System Image Downloader
  devices    Display terminal radar table of connected devices
  clean      Kill zombie port 5037 blockers and restart ADB server cleanly
  shortcuts  Re-install Windows desktop shortcuts

Options:
  --app <PACKAGE>      Package name to launch directly in a dedicated window
  -w, --window         Launch app in a dedicated Scrcpy floating window
  -u, --user <USER>    Target Android User Profile ID (e.g. 0 for main, 10 for clone)
  -t, --title <TITLE>  Custom window title for the floating application window
  -s, --serial <SERIAL> Target device serial number
  -h, --help           Print help
  -V, --version        Print version (gndroid 2.5.0)
```

### CLI Command Examples

```powershell
# 1. Launch Master Fluent Light GUI
.\gndroid.exe

# 2. Launch a specific AVD instance in background
.\gndroid.exe launch --avd gndroid

# 3. Mirror a specific physical phone or VM by serial
.\gndroid.exe mirror -s emulator-5554

# 4. Launch a cloned app into a dedicated floating window
.\gndroid.exe --app com.whatsapp --user 10 --window --title "WhatsApp (Work Account)"

# 5. Display live device radar table
.\gndroid.exe devices

# 6. Clean port conflicts and restart ADB
.\gndroid.exe clean
```

---

## Automated Testing & Verification Suite

GNDROiD is validated through a 4-tier opaque-box automated test harness covering all functional requirements, security boundaries, and process lifecycles with **zero facades, zero tautologies, and zero fake mocks**.

### Running the Test Suites

All test suites run in both live and stateful mock modes with exit code 0:

```powershell
# 1. Master E2E 4-Tier Verification Suite (160 tests: Feature, Boundary, Pairwise, Workload)
python scripts/run_e2e_verification.py

# 2. Native Rust CLI & Zero-Batch Verification (7 tests)
python scripts/test_rust_cli.py

# 3. Guest Netd & VPN Routing Stabilization (6 tests)
python scripts/verify_vpn_routing.py

# 4. Milestone 4 Native CLI IPC & Shortcuts (9 tests)
python scripts/test_milestone_4_cli_ipc.py

# 5. Milestone 3 GUI UX & Event Loop Hardening (14 tests)
python scripts/test_milestone_3_gui_ux.py

# 6. Milestone 2 Process Safety & Win32 Job Objects (11 tests)
python scripts/test_milestone_2_process_safety.py
```

### Master Verification Results Summary

```
================================================================================
  COMPLETE GNDROiD SYSTEM VERIFICATION SUITE — SUMMARY RESULTS
================================================================================
  Master E2E 4-Tier Suite (run_e2e_verification.py):      160 / 160 PASS ✅
  Rust CLI & Zero-Batch Suite (test_rust_cli.py):           7 /   7 PASS ✅
  VPN Routing Architecture Suite (verify_vpn_routing.py):    6 /   6 PASS ✅
  CLI IPC & Shortcut Suite (test_milestone_4_cli_ipc.py):   9 /   9 PASS ✅
  GUI UX & Event Loop Suite (test_milestone_3_gui_ux.py):   14 /  14 PASS ✅
  Process Safety & Job Objects (test_milestone_2_...):      11 /  11 PASS ✅
--------------------------------------------------------------------------------
  AGGREGATE TOTAL:                                        207 / 207 PASS (100.0%)
================================================================================
```

*All 207 automated E2E, networking, process safety, and GUI verification checks pass 100% prior to release packaging.*

---

## Repository Structure & Public Assets

```
GNDROiD/
├── INSTALL_AND_USER_GUIDE.md   # Master 12-Section Installation & Operational Guide
├── README.md                   # System Architecture & Public Release Overview
├── setup.ps1                   # Modern Turnkey PowerShell Deployer
├── LICENSE                     # Apache 2.0 License w/ Trademark Reservation
├── NOTICE                      # Copyright & Attribution Notice (Ghulam Nabi Kalhoro)
├── SECURITY.md                 # Vulnerability Disclosure & Secret Policy
├── CONTRIBUTING.md              # Contributor Guidelines & Development Tracks
├── CODE_OF_CONDUCT.md          # Contributor Covenant v2.1
├── .env.example                # Configuration & Secret Template
├── .github/                    # Community Issue & Pull Request Templates
├── companion-app/              # Android Companion & Universal Receiver
│   ├── GNDROiD_Companion.apk   # Direct Android Companion APK (Wireless Mirror & TV Receiver)
│   └── README.md               # Companion App Setup & Wireless Mirroring Manual
└── installer/                  # Windows Setup & Installer Automation
    ├── install_system.ps1      # Native PowerShell System Installer & PATH Configurator
    ├── uninstall_system.ps1    # Clean Registry & Shortcut Uninstaller
    ├── gndroid_installer.iss   # Professional Inno Setup 6 Wizard Script
    └── GNDROiD_User_Guide.txt  # Plain-Text User Manual (Packaged with Installer)
```

> **📦 Download Full Portable Suite:** The compiled 64-bit Windows binary package (including ADB, Scrcpy, FFmpeg/SDL3 DLLs, and GUI launcher) is available via **[GitHub Releases](https://github.com/gnonymous1/GNDROiD/releases/tag/v2.5.0)** (`GNDROiD-v2.5.0-Early-Access-Windows-x64.zip`).

---

## Technical Audit & Certification

GNDROiD has completed an exhaustive, forensic engineering audit resolving all 21 cataloged bugs, race conditions, pipe deadlocks, and simulated stubs across Milestones M1 through M5. The platform is certified for high-concurrency enterprise automation, multi-account operations, and low-latency device streaming.

---

## ⭐ Support & Share GNDROiD

If you find **GNDROiD** useful, please **Star ⭐ this repository**, share it with your developer and gaming communities, and join us in building the future of Windows-native Android virtualization!

### 🔍 Topics & Viral Discovery Hashtags

`#GNDROiD` `#AndroidEmulator` `#WindowsAndroidEmulator` `#AndroidOnWindows` `#Windows11` `#Scrcpy` `#ADB` `#AndroidVirtualMachine` `#WHPX` `#QEMU` `#Vulkan` `#HardwareBridging` `#RouterDHCP` `#BridgedNetworking` `#MultiInstance` `#AndroidMultiInstance` `#AppCloner` `#WirelessMirroring` `#PhoneMirroring` `#ScreenMirroring` `#AndroidTV` `#AndroidGaming` `#MobileGamingOnPC` `#OpenSource` `#GitHubTrending` `#DevTools` `#Virtualization` `#HyperV` `#AndroidDev` `#TechInnovation`

---

**Developed & Engineered by Ghulam Nabi Kalhoro**  
*GNDROiD Systems Architecture & Engineering Group*
