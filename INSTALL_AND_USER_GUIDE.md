# GNDROiD v2.5.0 — Complete Installation & User Guide
**Architect & Maintainer:** Ghulam Nabi Kalhoro  
**System Target:** Windows 10 & 11 (64-bit) | AMD-V / Intel VT-x | WHPX / Hyper-V  
**Documentation Version:** 2.5.0-Release  

---

## Table of Contents
1. [Overview & Architectural Highlights](#1-overview--architectural-highlights)
2. [Prerequisites & System Requirements](#2-prerequisites--system-requirements)
3. [Installation Methods](#3-installation-methods)
   - [Method A: 1-Click Turnkey PowerShell Installer (Recommended)](#method-a-1-click-turnkey-powershell-installer-recommended)
   - [Method B: Inno Setup GUI Wizard Installer](#method-b-inno-setup-gui-wizard-installer)
   - [Method C: Portable Standalone Deployment](#method-c-portable-standalone-deployment)
4. [First Launch & Core GUI Walkthrough](#4-first-launch--core-gui-walkthrough)
5. [Hardware Allocation & Settings Engine](#5-hardware-allocation--settings-engine)
6. [Tri-Mode Virtual Machine Networking](#6-tri-mode-virtual-machine-networking)
   - [Mode 1: High-Speed LAN Bridge](#mode-1-high-speed-lan-bridge-host-ip)
   - [Mode 2: Hardware Bridged Adapter (Router DHCP 192.168.100.x)](#mode-2-hardware-bridged-adapter-router-dhcp-192168100x)
   - [Mode 3: Isolated NAT Subnet](#mode-3-isolated-nat-subnet)
   - [Direct Static IP & Custom DNS Configuration](#direct-static-ip--custom-dns-configuration)
7. [Multi-Instance Manager & Parallel Workloads](#7-multi-instance-manager--parallel-workloads)
8. [Physical Phone Mirroring & Single-App Floating Windows](#8-physical-phone-mirroring--single-app-floating-windows)
9. [GNDROiD Link: Wireless Companion & Android TV Mode](#9-gndroid-link-wireless-companion--android-tv-mode)
10. [ADB Doctor & 1-Click Auto-Repair Suite](#10-adb-doctor--1-click-auto-repair-suite)
11. [Keyboard Shortcuts & Navigation Quick Reference](#11-keyboard-shortcuts--navigation-quick-reference)
12. [Frequently Asked Questions & Troubleshooting](#12-frequently-asked-questions--troubleshooting)

---

## 1. Overview & Architectural Highlights

**GNDROiD** is an institutional-grade, hyper-performant Android virtualization, hardware passthrough, and physical device orchestration suite engineered for Windows.

- **Zero-Console Operation:** Instantaneous Win32 Registry and native psutil hardware inspection eliminates flashing command prompt/PowerShell windows.
- **Hardware Bridging & Router DHCP:** Directly bridges virtual Android instances to your home or office router, granting each instance an independent physical LAN IP (`192.168.100.x`) and a unique virtual MAC address.
- **Process Safety:** OS-level Win32 Job Object containment (`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`) guarantees zero orphaned QEMU, Scrcpy, or ADB zombie processes.
- **Dedicated Floating App Windows:** Stream sandboxed apps or clone profiles into individual borderless desktop windows powered by Scrcpy 4.1 virtual display pipelines.
- **Universal Companion Receiver:** Turn any physical Android phone or Android TV into an active remote screen and input receiver via the built-in `GNDROiD_Companion.apk`.

---

## 2. Prerequisites & System Requirements

| Specification | Minimum Requirement | Recommended (Institutional / Multi-Instance) |
|---|---|---|
| **Operating System** | Windows 10 (Build 19041+) 64-bit | Windows 11 (64-bit, 23H2 or newer) |
| **Processor** | Intel Core i5 (4-Core) / AMD Ryzen 3 | Intel Core i7/i9 (8+ Cores) / AMD Ryzen 7/9 |
| **Virtualization** | Intel VT-x or AMD-V enabled in BIOS | WHPX (Windows Hypervisor Platform) active |
| **System Memory** | 8 GB DDR4 | 16 GB to 32 GB DDR4/DDR5 |
| **Free Storage** | 10 GB SSD | 50 GB+ NVMe SSD |
| **Graphics** | DirectX 11 / OpenGL 3.3 capable GPU | Vulkan 1.3 / Direct3D 12 Discrete GPU |
| **Android SDK** | Android Platform-Tools (ADB) | Android SDK Build-Tools 34+ (Auto-detected) |

> **Pro-Tip: Enabling Virtualization in Windows**  
> Ensure **Windows Hypervisor Platform** and **Virtual Machine Platform** are enabled in Windows Features:  
> Run in PowerShell (Admin):  
> `Enable-WindowsOptionalFeature -Online -FeatureName HypervisorPlatform -All`

---

## 3. Installation Methods

### Method A: 1-Click Turnkey PowerShell Installer (Recommended)

1. Download the latest release archive (`GNDROiD-v2.5.0-Early-Access-Windows-x64.zip`) from [GitHub Releases](https://github.com/gnonymous1/GNDROiD/releases).
2. Extract the folder to your preferred location (e.g. `C:\Users\<User>\Desktop\GNDROiD`).
3. Right-click `setup.ps1` and select **Run with PowerShell** (or open PowerShell in the directory and run `./setup.ps1`).
4. The installer automatically:
   - Validates system requirements and virtualization flags.
   - Installs runtime dependencies into `C:\Users\<User>\AppData\Local\Programs\GNDROiD\`.
   - Generates official Desktop and Start Menu shortcuts.
   - Cleans up stale socket locks and verifies ADB daemon readiness.

### Method B: Inno Setup GUI Wizard Installer

1. Run `installer\GNDROiD-Setup-v2.5.0-Full.exe`.
2. Follow the modern setup wizard:
   - Review and accept the license and usage terms.
   - Choose your installation directory (`Program Files` for all users, or `AppData\Local\Programs` for single user).
   - Select installation components (Core VM Engine, Mirroring Suite, Vector Controls Ribbon).
   - Check desired desktop shortcuts and `.apk` file associations.
3. Click **Install**. The wizard deploys all pre-compiled assets and launches the suite.

### Method C: Portable Standalone Deployment

GNDROiD is fully portable:
- You can run `gndroid.exe` directly from any directory without administrative privileges.
- All configurations are saved cleanly into standard `.android/avd/` and user configuration profiles.

---

## 4. First Launch & Core GUI Walkthrough

When you start GNDROiD (`gndroid.exe` or `gndroid.pyw`), the Windows 11 Fluent Light interface appears:

1. **Host PC Telemetry Banner:** Shows real-time host RAM, available CPU cores, and GPU backend.
2. **Device / Mode Selector (`dev_combo`):**
   - ⚡ **GNDROiD Flagship:** Your default high-performance Android instance.
   - 📱 **Physical Phone (USB):** Plug a phone via USB to immediately enable 60 FPS screen mirroring.
   - 📶 **Wireless LAN Phone:** Auto-discover phones on your local Wi-Fi subnet.
   - 🚀 **Mobile Companion Handsets:** Live status of linked Android TV and companion devices.
3. **Primary Action Buttons:**
   - **Launch Android Machine:** Boots the virtual machine in a realistic device frame.
   - **Mirror Phone:** Initiates high-speed USB/Wi-Fi screen mirroring.
4. **Hardware Controls Ribbon:**
   - 🔄 Screen Rotation (Portrait / Landscape toggle)
   - 🔊 Volume Up / 🔉 Volume Down
   - ◀ Back, ● Home, ▢ Recents
   - 📱 App Drawer & Cloner
   - 📸 Screenshot (Saves crisp PNG to Desktop\Screenshots)
   - ⚙️ **Settings & Hardware Configuration**

---

## 5. Hardware Allocation & Settings Engine

Access via the **⚙️ Settings** button on the main window:

### Tab 1: ⚡ Hardware & CPU/RAM
- **Display Name:** Customize your instance's system label.
- **RAM Allocation:** Choose between 2 GB, 4 GB, 8 GB, 16 GB, up to 32 GB.
- **CPU Cores:** Allocate 2, 4, 6, 8, 12, 16, or 24 dedicated virtual cores.
- **VM Heap Size:** 256 MB to 2048 MB Dalvik/ART runtime memory.
- **Root Access:** Toggle writable system partition (`-writable-system`) and permissive SELinux.

### Tab 2: 🎮 Graphics & Display
- **GPU Backend:** Auto (Vulkan 1.4 / Direct3D 11 hardware passthrough), Host Passthrough, or Software SwiftShader fallback.
- **Screen Resolution Presets:**
  - Galaxy S24 Ultra (1440 x 3120 • 500 DPI • Portrait)
  - Flagship FHD+ (1080 x 2400 • 420 DPI • Portrait)
  - 10-inch Tablet (1200 x 1920 • 280 DPI)
  - 4K Ultra HD Display (3840 x 2160 • 320 DPI • Landscape)
  - Custom Width, Height, and DPI spinboxes.
- **Multi-Display & Secondary Viewports:** Enable secondary display mirroring with zero letterbox distortion.

### Tab 3: 📷 Camera & Audio
- **Front & Back Cameras:** Map physical host PC webcams (`webcam0`) directly into Android apps for instant WhatsApp video calls, KYC verification, and barcode scanning.
- **Microphone Passthrough:** High-fidelity host microphone routing.

---

## 6. Tri-Mode Virtual Machine Networking

GNDROiD includes an industry-first **Tri-Mode Network Architecture** found under Settings → **🌐 Network & Adapters**:

```
                       ┌────────────────────────────┐
                       │    Home / Office Router    │
                       │     (192.168.100.1 GW)     │
                       └──────────────┬─────────────┘
                                      │
            ┌─────────────────────────┴─────────────────────────┐
            │                                                   │
  Physical PC Host                                    Android Guest Instance
  Realtek Wi-Fi / GbE                                (Hardware Bridged Mode)
  IP: 192.168.100.5                                   IP: 192.168.100.155 (Router DHCP)
  MAC: e4:5f:01:8a:b2:99                              MAC: 52:54:00:1a:2b:01 (Unique)
```

### Mode 1: High-Speed LAN Bridge (Host IP)
- Maps emulator services (ports `51888`, `51880`, `5555`, `8080`, `8088`) directly to your PC's physical LAN IP (e.g., `192.168.100.5`).
- External phones, Android TVs, and other PCs on your Wi-Fi can reach the emulator with zero drivers needed.

### Mode 2: Hardware Bridged Adapter (Router DHCP 192.168.100.x) — [Default]
- Bridges the Android VM directly to your physical network adapter (Realtek Wi-Fi 6, Intel Ethernet, etc.).
- Your router's DHCP server assigns a real, independent `192.168.100.x` address directly to the Android instance.
- Features **Link State Replication** (synchronizes Wi-Fi connect/disconnect state).

### Mode 3: Isolated NAT Subnet
- Standard isolated sandbox on the `10.0.2.15` subnet. Useful for secure malware analysis and testing.

### Direct Static IP & Custom DNS Configuration
- Under **🎯 Direct Static IP & Custom DNS Server Assignment**:
  - Switch from **Automatic DHCP** to **Static Manual IP**.
  - Specify Static IPv4 (e.g. `192.168.100.155`), Subnet Mask (`255.255.255.0`), and Gateway (`192.168.100.1`).
  - Select DNS Presets: Google DNS (`8.8.8.8 / 8.8.4.4`), Cloudflare (`1.1.1.1`), or Quad9 (`9.9.9.9`).
  - Click **⚡ Apply IP & DNS to Running Emulator Now** to inject live via ADB with zero reboots required.

---

## 7. Multi-Instance Manager & Parallel Workloads

Click **🚀 Multi-Instance Manager & Clones** on the main window:
- **Parallel Instances:** Launch multiple independent Android instances concurrently.
- **Deterministic MAC & Router IPs:** Every newly created instance automatically receives a unique virtual MAC address and a dedicated sequential router IP (e.g. Instance 1: `.151`, Instance 2: `.152`, Instance 3: `.153`).
- **1-Click Cloning:** Clone any instance with all installed applications, user accounts, and saved states preserved.
- **Auto-Tile Desktop:** Automatically arrange all running emulator windows in a clean, non-overlapping grid across your monitors.

---

## 8. Physical Phone Mirroring & Single-App Floating Windows

### USB Mirroring
1. Enable **Developer Options** on your physical phone (Settings → About Phone → Tap 'Build Number' 7 times).
2. Turn ON **USB Debugging**.
3. Plug your phone into your PC via USB cable.
4. On your phone screen, tap **Always allow from this computer**.
5. Select your phone from GNDROiD's dropdown and click **🔗 Mirror Phone**.

### Wireless Debugging (Android 11+)
1. Click **📡 Wireless Debugging & QR Pairing**.
2. On your phone, go to *Settings → Developer Options → Wireless Debugging*.
3. Tap *Pair device with QR code* and scan the QR code displayed by GNDROiD.
4. GNDROiD pairs and establishes a 60 FPS wireless stream over Wi-Fi without cables!

### Single-App Dedicated Windows (App Cloner)
1. Click **📱 App Drawer & Cloner**.
2. Select any installed app (e.g. WhatsApp, Telegram, YouTube).
3. Click **Launch Dedicated Window**.
4. The app opens in its own borderless desktop window with independent focus and taskbar integration.

---

## 9. GNDROiD Link: Wireless Companion & Android TV Mode

The companion APK (`tools\GNDROiD_Companion.apk`) extends your emulation to mobile devices:

1. **Install on Phone or Android TV:**
   - Install via GNDROiD: Settings → ADB Fixer → Install Nexus APK, or sideload via flash drive to your Android TV.
2. **Android TV Leanback Launcher:**
   - Full D-Pad remote control support.
   - Screen Cast Engine: Wirelessly cast your Android TV screen to your PC monitor at 60 FPS.
3. **Local Wi-Fi Radar Beacon:**
   - Automatically announces the handset on port `51880` / `51888`.
   - Your PC auto-discovers the phone and adds it to the target device selector.

---

## 10. ADB Doctor & 1-Click Auto-Repair Suite

Encountering connection issues? Click **🛠️ ADB Doctor & Fixer**:
- **⚡ 1-Click Auto-Repair All:** Terminates rogue zombie processes, clears port `5037`, restarts the ADB daemon, and reconnects all devices.
- **🛡️ Fix VPN & DNS Routing:** Clamps Netd MTU to 1380 to eliminate VPN black holes, disables IPv6 leaks, and sets persistent DNS.
- **🔑 Reset RSA Auth Keys:** Regenerates corrupted authentication keys to re-trigger authorization prompts.
- **Clean Stale Locks:** Purges crashed `.lock` files from virtual machines so they can boot instantly.

---

## 11. Keyboard Shortcuts & Navigation Quick Reference

| Shortcut | Action | Description |
|---|---|---|
| `Ctrl + F` | Fullscreen Toggle | Toggle borderless fullscreen mirror |
| `Ctrl + R` | Rotate Display | Rotate screen between Portrait and Landscape |
| `Alt + O` | Screen Standby | Turn physical phone display OFF while mirroring to PC |
| `Alt + P` | Power Button | Emulates physical device Power key |
| `Alt + Up / Down` | Volume Control | Hardware Volume Up / Volume Down |
| `Alt + H` | Home Key | Navigate to Android Home Screen |
| `Alt + B` | Back Key | Android Back button navigation |
| `Alt + S` | App Switcher | Android Recents / App Overview |
| `Ctrl + V` | Paste Clipboard | Paste text from PC clipboard into Android |

---

## 12. Frequently Asked Questions & Troubleshooting

#### Q: "Emulator exited during boot (code 1)"
- **A:** Ensure Windows Hypervisor Platform is enabled. Open Settings → 🎮 Graphics & Display and verify GPU Backend is set to **Auto** or **Host**. If running on AMD CPU, make sure SVM (Secure Virtual Machine) is enabled in BIOS.

#### Q: "Why does the instance show 10.0.2.15 instead of my router IP?"
- **A:** Open Settings → **🌐 Network & Adapters**. Verify **Network Connection Mode** is set to **Mode 2: Hardware Bridged** and that your physical Wi-Fi or Ethernet adapter is selected. Click **Test & Activate LAN Bridge**.

#### Q: "How can other computers on my Wi-Fi access the emulator?"
- **A:** With **Mode 2 (Hardware Bridged)**, the emulator has its own router IP (e.g. `192.168.100.155`). Any device on the same Wi-Fi can ping, connect via ADB (`adb connect 192.168.100.155:5555`), or open local servers running inside the emulator.

---

**GNDROiD Systems Architecture & Engineering Group**  
*Lead Developer & Architect: Ghulam Nabi Kalhoro*  
*Repository:* [https://github.com/gnonymous1/GNDROiD](https://github.com/gnonymous1/GNDROiD)
