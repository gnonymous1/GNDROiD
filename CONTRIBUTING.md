# Contributing to GNDROiD

Welcome to the **GNDROiD** open-source contributor community! Thank you for your interest in making GNDROiD the fastest, most reliable, and most developer-friendly Android virtualization and physical device mirroring engine on Windows.

GNDROiD is architected and maintained by **Ghulam Nabi Kalhoro** ([@gnkalhoro](https://github.com/gnkalhoro) / [@gnonymous1](https://github.com/gnonymous1)). We warmly invite developers, systems engineers, UI/UX designers, Android enthusiasts, and reverse engineers from around the globe to participate in this early access release.

---

## 🧭 Code of Conduct

By participating in this project, you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md). We are committed to fostering a welcoming, respectful, and harassment-free community.

---

## 🎯 High-Priority Contribution Areas

We actively welcome contributions in the following domains:

1. **Hardware Acceleration & Virtualization Engine**
   - Optimization for Windows Hypervisor Platform (WHPX), Intel HAXM, and Nested KVM.
   - GPU rendering pipeline improvements: Vulkan 1.3, ANGLE Direct3D 11/12, SwiftShader software fallbacks.
   - Dynamic memory ballooning and CPU scheduling for multi-core processors (up to 24 cores).

2. **Network Bridging & Packet Routing**
   - TAP / NDIS Layer 2 physical bridging drivers.
   - Automatic router DHCP lease management (`192.168.100.x` or user home subnets).
   - High-performance packet forwarding, MTU 1380 optimization, and direct static IP / custom DNS bindings.
   - Isolated MAC address synthesis for parallel multi-instance clones.

3. **Physical Hardware & Sensor Emulation**
   - Bluetooth HCI socket emulation via Google `netsimd` (Port 7300).
   - Biometric fingerprint scanner hardware passthrough.
   - Real-time GPS, accelerometer, gyroscope, and ambient light simulation.

4. **Wireless Companion & Android TV Receiver**
   - Enhancements to `GNDROiD Link` APK (Kotlin / Jetpack Compose).
   - Ultra-low latency H.264 / H.265 / AV1 wireless screen casting over LAN (Port 51880).
   - Android TV big-screen receiver and peer-to-peer display rendering.

5. **Modern Desktop UI & Multi-Instance Manager**
   - Modern dark/light UI improvements with PyQt6.
   - Grid, tile, and cascade auto-arrangement for multi-instance gaming and testing setups.
   - Single-app borderless floating window streaming.

6. **Packaging, Cross-Platform Portability & CI/CD**
   - Inno Setup script automation and automated GitHub Actions builds.
   - Linux KVM / macOS Apple Silicon port exploration.

---

## 🛠️ Local Development Environment

### 1. Prerequisites
- **Operating System:** Windows 10 (21H2+) or Windows 11 (64-bit).
- **Python:** Python 3.10, 3.11, or 3.12 (64-bit).
- **Git:** Git for Windows.
- **Android SDK:** Command-line tools or full Android Studio (optional, bundled tools provided).
- **Hypervisor:** Windows Hypervisor Platform (`WHPX`) enabled in Windows Features.

### 2. Getting the Source Code
```powershell
# Clone the repository
git clone https://github.com/gnonymous1/GNDROiD.git
cd GNDROiD

# Create a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install required dependencies
pip install -r requirements.txt
```

### 3. Setting Up Environment Secrets
Never hardcode or commit keys or credentials. Copy the template:
```powershell
Copy-Item .env.example .env
```
Populate `.env` with your local test configuration. `.env` is ignored by Git.

### 4. Running GNDROiD from Source
```powershell
# Launch the main GUI Master Suite
python gndroid.pyw

# Or launch specific modules
python gndroid.pyw --mirror        # Physical Phone Mirror
python gndroid.pyw --multi         # Multi-Instance Manager
python gndroid.pyw --lan           # Wireless LAN Radar
python gndroid.pyw --fix           # ADB Doctor
```

---

## 🔒 Security & Intellectual Property Guidelines

1. **Never Commit Secrets or Private Keys:**
   - Keystores (`*.keystore`, `*.jks`, `*.p12`), signing keys, `.env` files, and personal device credentials must **never** be committed.
   - Check `.gitignore` before staging files. Run `git status` carefully.
   - Review our [Security Policy](SECURITY.md) for vulnerability disclosure procedures.

2. **Licensing & Copyright:**
   - All contributions become part of GNDROiD under the terms of the [Apache License 2.0](LICENSE) with trademark reservations for the **GNDROiD** name and branding by Ghulam Nabi Kalhoro.
   - Ensure that code you submit does not infringe third-party patents or proprietary licenses.

---

## 🌿 Contribution Workflow

### Step 1: Find or Open an Issue
Before starting significant work, please check existing [GitHub Issues](https://github.com/gnonymous1/GNDROiD/issues) or open a new one to discuss your proposal with the maintainer.

### Step 2: Create a Feature Branch
```powershell
git checkout -b feat/my-awesome-feature
# or for bug fixes:
git checkout -b fix/issue-123-network-dhcp
```

### Step 3: Write Clean, Documented Code
- Follow PEP 8 guidelines for Python code.
- Ensure all subprocess calls use non-blocking background execution or the Win32 Job Object isolation system (`CREATE_NO_WINDOW = 0x08000000`).
- Test your changes thoroughly on Windows with real physical phones or virtual instances.

### Step 4: Commit Your Changes
Use conventional commit prefixes:
- `feat:` for new capabilities
- `fix:` for bug fixes
- `perf:` for latency or memory improvements
- `docs:` for documentation updates
- `refactor:` for code restructuring

Example:
```powershell
git commit -m "feat(network): support custom subnet gateway configuration in bridged mode"
```

### Step 5: Open a Pull Request
1. Push your branch: `git push origin feat/my-awesome-feature`
2. Open a Pull Request on GitHub against `origin/master`.
3. Complete the [Pull Request Template](.github/PULL_REQUEST_TEMPLATE.md).
4. Maintainers will review your PR, provide constructive feedback, and merge upon validation.

---

## 🏆 Contributor Recognition

All merged contributors are proudly acknowledged in:
- The GitHub Release Notes
- The `CONTRIBUTORS.md` hall of fame
- The desktop software's "About & Credits" dialog

Thank you for contributing to the future of Android emulation on Windows! 🚀
