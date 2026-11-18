# Security Policy & Secret Management — GNDROiD

The **GNDROiD** project adheres to institutional-grade security standards for Android virtualization, hardware bridging, and companion device communications.

---

## 1. Reporting a Vulnerability

If you discover a security vulnerability or sensitive information exposure within GNDROiD, **please do not disclose it publicly via GitHub Issues.**

Instead, report it directly to the lead architect:
- **Lead Maintainer:** Ghulam Nabi Kalhoro
- **Email:** `ghulamnabi.kalhoro@outlook.com` (or submit a private security advisory via GitHub Security tab)
- **Response SLA:** Within 48 hours with an initial assessment and mitigation timeline.

---

## 2. Secrets & Cryptographic Key Management

To ensure project integrity and prevent unauthorized impersonation or malicious modifications:
1. **Zero-Secret Repository Policy:**
   - No private Android signing keys (`*.keystore`, `*.jks`), TLS private certificates (`*.pem`, `*.key`), or production API secrets are stored within version control.
   - All `.env`, local configuration overrides, and personal authentication tokens are excluded via `.gitignore`.
2. **GitHub Actions Secrets:**
   - Automated CI/CD builds, release signing, and package deployment inject cryptographic material dynamically from encrypted **GitHub Repository Secrets**:
     - `GNDROID_KEYSTORE_BASE64`: Encrypted base64 payload of the official release signing keystore.
     - `GNDROID_KEYSTORE_PASS`: Production signing password.
     - `GNDROID_KEY_ALIAS`: Canonical signing alias.
     - `GH_TOKEN`: Scoped GitHub token for immutable release asset uploads.
3. **Local Development Hygiene:**
   - Developers should copy `.env.example` to `.env` for local configuration.
   - Any debug keystore generated locally remains uncommitted and untracked.

---

## 3. Sandboxing & Memory Safety

- **Win32 Job Object Isolation:**
  Every child process (`qemu-system-x86_64.exe`, `adb.exe`, `scrcpy.exe`) is assigned to a Win32 Job Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE (0x00002000)` to prevent lingering zombie processes or unauthorized background persistence.
- **AOSP Multi-User Boundary Enforcement:**
  Cloned app profiles strictly isolate user data directories (`/data/user/<id>/`) preventing token leakage or inter-process snooping between concurrent accounts.
- **IPv6 Leak Protection:**
  Virtual guests disable global IPv6 routing (`net.ipv6.conf.all.disable_ipv6=1`) to eliminate IPv6 bypass of active corporate or VPN tunnels.

---

## 4. Intellectual Property & Anti-Plagiarism

- All proprietary core modules, hardware bridging architectures, and interface branding are the protected intellectual property of **Ghulam Nabi Kalhoro**.
- Unauthorized redistribution, closed-source cloning, or trademark infringement is prohibited under the terms of the project [LICENSE](LICENSE).
