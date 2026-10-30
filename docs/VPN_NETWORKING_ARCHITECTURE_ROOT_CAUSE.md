# Android Emulator VPN & Networking Architecture: Root-Cause Analysis & Resolution Blueprint

**Document Reference:** GNDROiD-ARCH-R3-NET  
**Target Milestone:** M3 (Emulator VPN Architecture & IP Routing)  
**Requirement ID:** R3 (Android Emulator VPN Architecture Investigation and Resolution)  
**Status:** Approved Technical Architecture  
**Author:** GNDROiD Systems & Networking Architecture Group  
**Date:** 2026-10-30  

---

## Executive Summary

Commercial Android VPN applications—including WireGuard, OpenVPN, ProtonVPN, NordVPN, and Cloudflare WARP—routinely fail inside standard Android Virtual Devices (AVDs). When executed within default Google Android Studio / QEMU Ranchu emulators running Android 14 (API 34 x86_64), VPN clients encounter one of three critical failure states:
1. **Connection Failure / Handshake Timeout:** The tunnel handshake fails to reach the remote endpoint, leaving the client in an infinite "Connecting..." or "Reconnecting..." loop.
2. **Path MTU Silent Black Hole:** The tunnel reports active establishment (`tun0` created), but subsequent TCP/UDP traffic freezes completely; web browsers hang indefinitely and speed tests fail with zero throughput.
3. **Public IP & DNS Leakage:** Despite an active VPN tunnel interface, external IP verification services (e.g., `ipify.org`, `icanhazip.com`, `dnsleaktest.com`) report the host machine's physical ISP public IP address rather than the VPN server endpoint, accompanied by unencrypted DNS resolution through local host resolvers.

This document presents a comprehensive, forensic investigation into the 5 interacting failure mechanisms across the virtualization boundary, guest Linux kernel, Android 14 `Netd` policy routing engine, and host Windows networking stack. It delivers the definitive 3-tier architectural resolution implemented in GNDROiD.

---

## Architectural Context: The Virtualization Boundary

```
+----------------------------------------------------------------------------------------------------+
|                                      WINDOWS HOST ENVIRONMENT                                      |
|                                                                                                    |
|  Physical Network Adapter (Ethernet / Wi-Fi)  <===> Host Winsock TCP/IP Stack (MTU <= 1500)       |
|                                    ▲                                                               |
|                                    │ (Non-privileged user-mode sockets: sendto/recvfrom)           |
|                                    ▼                                                               |
|  +-----------------------------------------------------------------------------------------------+ |
|  |                           QEMU RANCHU VIRTUALIZATION CORE (emulator.exe)                      | |
|  |                                                                                               | |
|  |   +-----------------------------------------------------------------------------------------+ | |
|  |   |                           SLIRP User-Mode Network Stack (libslirp)                     | | |
|  |   |   - Virtual Gateway:   10.0.2.2      - Virtual DNS Proxy: 10.0.2.3                          | | |
|  |   |   - Virtual Alias IPv4: 10.0.2.15    - Virtual Wi-Fi IPv4: 10.0.2.16                         | | |
|  |   |   - Site-Local IPv6:   fec0::/64     - Stateless UDP/TCP NAT Table (No Protocol 50 ESP) | | |
|  |   +-----------------------------------------------------------------------------------------+ | |
|  |                                    │                           │                              | |
|  |                       Virtual NIC 1│ (Virtio-Net)  Virtual NIC 2│ (Virtio-Wifi / mac80211_hwsim)| |
|  +------------------------------------┼---------------------------┼------------------------------+ |
+---------------------------------------┼---------------------------┼--------------------------------+
                                        │                           │
========================================│===========================│=================================
                                        ▼                           ▼
+----------------------------------------------------------------------------------------------------+
|                                    GUEST ANDROID 14 OS (API 34)                                    |
|                                                                                                    |
|   +-----------------------------+               +----------------------------------------------+   |
|   |   Linux Interface: eth0     |               |   Linux Interface: wlan0 (Default Route)     |   |
|   |   IP: 10.0.2.15 / MTU: 1500 |               |   IP: 10.0.2.16 / MTU: 1500                  |   |
|   |   IPv6: fec0::5054:...      |               |   IPv6: fec0::6fe4:...                       |   |
|   +-----------------------------+               +----------------------------------------------+   |
|                                  ▲             ▲                                                   |
|                                  │             │ [VpnService.protect() mark]                       |
|   +------------------------------┴-------------┴-----------------------------------------------+   |
|   |                          Android 14 Netd & fwmark Policy Routing Engine                     |   |
|   |   - Table 99: Local network          - Table 1015: eth0 (via 10.0.2.2)                     |   |
|   |   - Table 98: VPN internal route     - Table 1016: wlan0 (via 10.0.2.2)                    |   |
|   |   - NetworkMonitor: connectivitycheck.gstatic.com/generate_204 HTTP 204 Probe Trap         |   |
|   +-------------------------------------------------------------------------------------------+   |
|                                                ▲                                                   |
|                                                │ Enforced Tunnel Routing                           |
|   +--------------------------------------------┴----------------------------------------------+   |
|   |                                Virtual Network Interface: tun0                            |   |
|   |   Created by VpnService.Builder() via /dev/tun (Ownership system:vpn 0660)                 |   |
|   |   Assigned IP: 10.x.x.x (IPv4-only tunnel) / Default MTU: 1280 - 1420 bytes               |   |
|   +-------------------------------------------------------------------------------------------+   |
|                                                ▲                                                   |
|                                                │ Tunneled App Payloads                             |
|   +--------------------------------------------┴----------------------------------------------+   |
|   |                                Commercial VPN Client Application                           |   |
|   |                    (WireGuard, OpenVPN Core, ProtonVPN, NordVPN, Tailscale)                |   |
|   +-------------------------------------------------------------------------------------------+   |
+----------------------------------------------------------------------------------------------------+
```

---

## The 5 Root-Cause Failure Mechanisms

### Mechanism 1: QEMU SLIRP User-Mode NAT Limitations
Standard Android SDK emulators use **SLIRP** (`-netdev user`), a user-mode software network emulator originally derived from 1990s BSD dial-up software and embedded into QEMU.

1. **Winsock Proxy Architecture, Not Raw Bridging:**
   SLIRP does not inject raw Ethernet frames into the host physical adapter. Instead, it reassembles guest IP frames inside the host user-space process (`emulator.exe`) and maps guest TCP/UDP connections to unprivileged Windows Winsock API calls (`sendto`, `recvfrom`, `connect`).
2. **Zero Protocol 50 (ESP) & Raw Protocol Support:**
   IPsec / IKEv2 protocols rely directly on IP Protocol 50 (Encapsulating Security Payload). Because user-mode Winsock sockets on Windows cannot bind raw IP protocols without elevated Administrator privileges and custom NDIS drivers, SLIRP silently drops all Protocol 50 packets. IPsec-based commercial VPNs fail instantly.
3. **Aggressive UDP NAT State Table Timeouts:**
   WireGuard and OpenVPN over UDP maintain persistent tunnels through UDP keepalive handshakes. SLIRP's internal `udp_attach` session table tracks active NAT translations. If packet jitter or host CPU scheduling delays exceed SLIRP's strict inactivity timer, the session mapping is purged. Subsequent incoming packets from the VPN server cannot be mapped back to guest port `51820` and are silently discarded, disconnecting the tunnel.

### Mechanism 2: `virtiowifi` Multi-Homing Conflict & Asymmetric Routing
Modern Android 14 emulators instantiate two simultaneous virtual network adapters:
- `eth0`: Virtual Virtio-Net Ethernet interface (allocated IP `10.0.2.15/8`).
- `wlan0`: Virtual Wi-Fi adapter simulated by `mac80211_hwsim` (allocated IP `10.0.2.16/24`).

Both interfaces reside on the same QEMU virtual switch and share the exact same default gateway: `10.0.2.2`.

```
Guest Interface eth0:  10.0.2.15/8  --> Gateway: 10.0.2.2 (Table 1015)
Guest Interface wlan0: 10.0.2.16/24 --> Gateway: 10.0.2.2 (Table 1016)
```

Android 14 treats `wlan0` as the primary Wi-Fi interface and routes un-marked traffic through `table 1016`. However:
1. When a VPN application invokes `VpnService.protect(socketFd)`, the underlying socket is assigned an `SO_MARK` fwmark binding it to a specific physical network interface.
2. If Android's `Netd` binds the protected socket to `wlan0`, but host-side QEMU emits the outer UDP tunnel packet with `eth0` source MAC/IP attributes (or vice-versa), an asymmetric routing collision occurs.
3. The remote VPN server receives outer packets originating from `10.0.2.15` and transmits response packets to that endpoint, but guest Android's routing tables expect return traffic on `10.0.2.16`. The handshake reply is dropped by the guest kernel as an invalid reverse-path forwarding (RPF) frame.

### Mechanism 3: Android 14 `NetworkMonitor` Captive Portal Trap
Android 14 enforces strict network validation via `com.android.server.connectivity.NetworkMonitor`.

```
[wlan0 Link Up] ──> NetworkMonitor Probes: http://connectivitycheck.gstatic.com/generate_204
                           │
                           ├── Latency > 8000ms or SLIRP DNS drop
                           ▼
                  [Probe Times Out]
                           │
                           ▼
              [wlan0 Marked "NO_INTERNET / UNVALIDATED"]
                           │
                           ▼
     [VpnService.protect() Protected Sockets Stall / Blocked]
                           │
                           ▼
               [VPN Handshake Packet Never Leaves Guest]
```

1. Upon interface link detection, `NetworkMonitor` dispatches HTTP GET probes to Google endpoints (`connectivitycheck.gstatic.com/generate_204` and `www.google.com/gen_204`).
2. Due to SLIRP DNS translation latency and initial Winsock buffer delays, these probe requests frequently time out.
3. Android flags the physical network as **Unvalidated** ("Wi-Fi has no internet access").
4. Under Android 14's strict security architecture, `VpnService.protect()` cannot route outer encapsulation sockets across an unvalidated underlying network. The VPN client's outer handshake UDP packets are blocked internally by Netd before ever reaching `10.0.2.2`.

### Mechanism 4: Path MTU Black Hole
Path MTU (PMTU) black holes represent the single most insidious emulator VPN failure, causing established tunnels to freeze.

1. **The Math of Packet Encapsulation Overhead:**
   - Standard host physical Ethernet / Wi-Fi MTU: `1500 bytes` (often `1492` over PPPoE or `1420` over cellular).
   - Guest `eth0` and `wlan0` default MTU: `1500 bytes`.
   - Guest `tun0` interface default MTU: `1420 bytes` (WireGuard) or `1500 bytes` (OpenVPN default).
   - Encapsulation overhead:
     * Inner Payload: `1420 bytes`
     * Outer IPv4 Header: `20 bytes`
     * Outer UDP Header: `8 bytes`
     * WireGuard Header: `32 bytes`
     * Total Frame Size = `1420 + 20 + 8 + 32 = 1480 bytes` (near the threshold).
     * If OpenVPN or IPsec with AES-256-GCM is used with a 1500-byte inner MTU: `1500 + 20 + 8 + 72 = 1600 bytes`!
2. **Absence of ICMP Type 3 Code 4 Synthesis:**
   When an application sends a maximum-size TCP packet with the `DF` (Don't Fragment) bit set, the encapsulated frame exceeds the host's physical MTU.
   In a physical router, the router drops the oversized packet and generates an ICMP `Fragmentation Needed and DF set` (Type 3, Code 4) error back to the sender.
   **QEMU SLIRP does not synthesize ICMP Type 3 Code 4 errors back to the guest.**
3. **The Result:** The host Winsock socket silently drops the frame. Small packets (TCP SYN, handshakes, ping) pass through, but as soon as a bulk data transfer begins (TLS Client Hello, HTTP GET response), traffic halts completely.

### Mechanism 5: IPv6 Dual-Stack Bypass & DNS Hijacking
When a VPN tunnel is established inside Android, external IP lookups often continue revealing the host machine's physical ISP address due to IPv6 and DNS misrouting:

```
[App requests https://api64.ipify.org]
                  │
                  ▼
   1. DNS Query for A (IPv4) and AAAA (IPv6)
      ├── SLIRP intercepts Port 53 -> Forwards to Host ISP DNS (10.0.2.3)
      └── DNS Leak: Queries unencrypted via Host ISP Resolver!
                  │
                  ▼
   2. RFC 6724 / Happy Eyeballs Address Sorting
      ├── tun0 has IPv4 route: 0.0.0.0/0
      ├── eth0/wlan0 retain site-local IPv6 default: fec0::/64
      └── Happy Eyeballs prioritizes IPv6 AAAA destination!
                  │
                  ▼
   3. Egress Traffic Routing Decision
      ├── IPv6 packet matches default route on eth0/wlan0 (NOT tun0!)
      └── Outer Packet bypasses VPN tunnel entirely ──> EXPOSES HOST PUBLIC IP!
```

1. **IPv6 Bypass:** Commercial VPN apps frequently default to IPv4-only virtual addressing inside mobile clients (`0.0.0.0/0`). However, QEMU SLIRP assigns guest interfaces site-local IPv6 addresses (`fec0::5054:...`). Android 14's RFC 6724 address selection algorithm prioritizes IPv6. Connections to dual-stack web endpoints bypass `tun0` entirely, routing unencrypted over `eth0`/`wlan0`.
2. **Virtual DNS Interception (10.0.2.3):** SLIRP sets guest DNS to `10.0.2.3`. When the guest issues a DNS query to `10.0.2.3:53`, SLIRP forwards the request to the host Windows machine's primary DNS adapter—typically the host ISP's DNS. This causes severe DNS leaks and circumvents the VPN tunnel's secure DNS servers.

---

## 3-Tier Architectural Resolution

GNDROiD resolves these failure mechanisms through a coordinated, multi-layered architecture:

```
+====================================================================================================+
|                                  GNDROiD 3-TIER RESOLUTION ENGINE                                  |
+====================================================================================================+
|                                                                                                    |
|  [ TIER 1: QEMU LAUNCH FLAGS & SLIRP HARDENING (`gndroid.pyw`) ]                                   |
|  ├── -dns-server 8.8.8.8,1.1.1.1       Direct upstream public DNS; eliminates SLIRP 10.0.2.3 host  |
|  │                                     ISP redirection and DNS query dropouts.                     |
|  ├── -netdelay none -netspeed full     Removes artificial QEMU latency emulation; prevents         |
|  │                                     NetworkMonitor HTTP 204 probe timeout false positives.     |
|  └── -netfast                          Optimizes user-mode buffer throughput and TCP/UDP handling.  |
|                                                                                                    |
|  [ TIER 2: GUEST NETD & MTU STABILIZATION (`nexus/display_and_vpn.py`) ]                           |
|  ├── 1. Path MTU Clamping:                                                                         |
|  │      ip link set dev eth0 mtu 1380  Guarantees encapsulated outer packets stay <= 1460 B,       |
|  │      ip link set dev wlan0 mtu 1380 preventing Path MTU black hole silent packet drops.         |
|  ├── 2. IPv6 Leak Cutoff:                                                                          |
|  │      sysctl -w net.ipv6.conf.all.disable_ipv6=1     Eliminates dual-stack bypass; forces       |
|  │      sysctl -w net.ipv6.conf.eth0.disable_ipv6=1    100% of guest traffic through IPv4         |
|  │      sysctl -w net.ipv6.conf.wlan0.disable_ipv6=1   tun0 interface.                            |
|  ├── 3. Captive Portal Bypass:                                                                     |
|  │      settings put global captive_portal_mode 0              Prevents physical interface from    |
|  │      settings put global captive_portal_detection_enabled 0 being marked "unvalidated".        |
|  ├── 4. VpnService AppOps Auto-Grant:                                                              |
|  │      appops set <pkg> ACTIVATE_VPN allow    Eliminates modal popup blocking tunnel launch.      |
|  └── 5. Private DNS Enforcement:                                                                   |
|         settings put global private_dns_mode hostname                                              |
|         settings put global private_dns_specifier dns.google   TLS 1.3 encrypted DNS routing.      |
|                                                                                                    |
|  [ TIER 3: MICRO-VM LAYER-2 TAP BRIDGING (`hypervisor/src/vmm.rs`) ]                               |
|  └── Windows Wintun / TAP-Windows6 Driver with WinNAT                                              |
|      Full kernel-level Layer-2/Layer-3 packet forwarding:                                          |
|      - Native support for IP Protocol 50 (ESP), IKEv2, WireGuard, and OpenVPN.                     |
|      - True Path MTU Discovery (PMTUD) with synthesized ICMP Type 3 Code 4.                        |
|      - Zero SLIRP session table state loss during idle periods.                                    |
+====================================================================================================+
```

---

## Technical Specifications: Implementation Details

### Tier 1: QEMU Launch Flag Hardening

In `gndroid.pyw` (`AVDManager.launch_emulator_instance`), the emulator CLI command is constructed with strict networking parameters:

```python
cmd = [
    emu,
    "-avd", name,
    "-port", str(port),
    "-gpu", gpu_mode,
    "-netfast",
    "-netdelay", "none",
    "-netspeed", "full",
    "-no-snapshot-load",
    "-crash-report-mode", "never",
    "-dns-server", "8.8.8.8,1.1.1.1"
]
```

- **`-dns-server 8.8.8.8,1.1.1.1`**: Instructs QEMU SLIRP to proxy DNS queries directly to Google Public DNS (`8.8.8.8`) and Cloudflare DNS (`1.1.1.1`) rather than inspecting the host Windows adapter's registry to find local ISP resolvers.
- **`-netdelay none -netspeed full`**: Disables network simulation throttling. Standard AVDs default to latency characteristics that cause Android 14 `NetworkMonitor` HTTP 204 probes to exceed timeout limits during boot.

### Tier 2: Guest Netd & Kernel Stabilization Engine

In `nexus/display_and_vpn.py`, the core function `auto_stabilize_vpn_networking(serial: str) -> Dict[str, bool]` executes immediately upon guest boot detection.

#### Interface Contract & Execution Logic
```python
def auto_stabilize_vpn_networking(serial: str = "emulator-5554") -> Dict[str, bool]:
    """
    Executes guest-side network stabilization:
    1. Clamps MTU to 1380 on all physical network interfaces (eth0, wlan0).
    2. Disables IPv6 across all interfaces to eliminate dual-stack bypass leaks.
    3. Disables captive portal detection to keep physical networks validated.
    4. Grants ACTIVATE_VPN AppOps permissions to VPN client applications.
    5. Configures Private DNS (dns.google in hostname mode).
    """
```

#### Detailed Operations Table

| Stage | Command / Parameter | Architectural Purpose |
|---|---|---|
| **MTU Clamping** | `ip link set dev eth0 mtu 1380`<br>`ip link set dev wlan0 mtu 1380` | Clamps the MTU below host path limits (`1420-1492 B`), preventing fragmentation black holes for encrypted packets. |
| **IPv6 Leak Cutoff** | `sysctl -w net.ipv6.conf.all.disable_ipv6=1`<br>`sysctl -w net.ipv6.conf.default.disable_ipv6=1`<br>`sysctl -w net.ipv6.conf.eth0.disable_ipv6=1`<br>`sysctl -w net.ipv6.conf.wlan0.disable_ipv6=1` | Shuts down `fec0::/64` site-local routing in the guest kernel, guaranteeing that Android's Happy Eyeballs algorithm cannot bypass IPv4 `tun0`. |
| **Captive Portal Bypass** | `settings put global captive_portal_mode 0`<br>`settings put global captive_portal_detection_enabled 0` | Informs Android 14's `ConnectivityService` that network interfaces are pre-validated, ensuring `VpnService.protect()` sockets route without stalling. |
| **VPN AppOps Authorization** | `appops set <pkg> ACTIVATE_VPN allow` | Authorizes the target VPN application to create `tun0` without requiring user interaction with the system confirmation dialog. |
| **Private DNS Security** | `settings put global private_dns_mode hostname`<br>`settings put global private_dns_specifier dns.google` | Routes guest DNS queries through DNS-over-TLS (DoT) via `dns.google`, bypassing SLIRP DNS proxy interception. |

### Tier 3: Next-Gen Micro-VM Layer-2 TAP / Wintun Architecture

For next-generation workloads using the GNDROiD Rust micro-VM (`hypervisor/src/vmm.rs`), the architecture bypasses QEMU SLIRP entirely:

1. **Wintun High-Performance TUN Driver:**
   - Deploys WireGuard's ultra-fast `Wintun.dll` driver on Windows, operating entirely in kernel mode.
2. **Layer-2/Layer-3 Tap Bridging:**
   - The micro-VM exposes a Virtio-Net device backed by the Wintun adapter (`192.168.150.1/24`).
   - Guest packets traverse directly into Windows kernel NDIS processing.
   - Full support for IP Protocol 50 (ESP) enables hardware-accelerated IPsec and IKEv2.
3. **Kernel-Level WinNAT Routing:**
   - Host PowerShell script provisions an isolated WinNAT prefix:
     `New-NetNat -Name "GNDROiD-NAT" -InternalIPInterfaceAddressPrefix "192.168.150.0/24"`
   - Complete ICMP Type 3 Code 4 generation ensures proper Path MTU Discovery across external links.

---

## Verification & Traffic Analysis Matrix

| Requirement | Test Method | Expected Behavior | Validation Tool |
|---|---|---|---|
| **MTU Sizing** | `adb shell ip link show eth0` | `mtu 1380` on both `eth0` and `wlan0` | `scripts/verify_vpn_routing.py` |
| **IPv6 Leak Cutoff** | `adb shell cat /proc/sys/net/ipv6/conf/all/disable_ipv6` | Returns `1`; no active `fec0::` global/site addresses | `scripts/verify_vpn_routing.py` |
| **Captive Portal** | `adb shell settings get global captive_portal_mode` | Returns `0`; physical network marked validated immediately | `scripts/verify_vpn_routing.py` |
| **VpnService AppOps** | `adb shell appops get <pkg> ACTIVATE_VPN` | Returns `ACTIVATE_VPN: allow` | `scripts/verify_vpn_routing.py` |
| **Tunnel Egress** | `curl -s https://api64.ipify.org` inside guest | Returns public IP of remote VPN endpoint, NOT host ISP IP | `scripts/verify_vpn_routing.py` |
| **DNS Leak Prevention** | `adb shell nslookup myip.opendns.com 208.67.222.222` | Resolves cleanly through encrypted tunnel without timeouts | `scripts/verify_vpn_routing.py` |

---

## Conclusion

Standard Android emulator networking fails with commercial VPN applications not because of a single bug, but due to an unfortunate confluence of virtualization design trade-offs (QEMU SLIRP user-mode NAT) and Android 14 security mechanisms (Netd fwmark policy routing, captive portal probes, Happy Eyeballs IPv6 preference).

By enforcing hardened QEMU launch flags (`-dns-server 8.8.8.8,1.1.1.1`, `-netdelay none -netspeed full`), stabilizing guest kernel routing via `auto_stabilize_vpn_networking` (MTU clamping to 1380, IPv6 disabling, captive portal bypass, and AppOps permissions), and establishing a path to micro-VM Layer-2 TAP bridging, GNDROiD guarantees robust, leak-free commercial VPN operation across all Android 14 instances.
