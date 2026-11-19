# TEST_INFRA.md: GNDROiD Next-Gen E2E Test Infrastructure & Synthetic Fixtures Specification

**Version:** 3.0.0  
**Status:** Canonical Test Infrastructure Architecture & Quality Standard  
**Integrity Mode:** Opaque-Box, Zero-Hardware CI/CD Emulation  
**Target Platform:** Windows x86_64, Python 3.10+, PowerShell / Bash  
**Scope:** Features 1 through 23, Cross-Feature Pairwise (Tier 3), Real-World Scenarios (Tier 4), and Adversarial Hardening (Tier 5)

---

## 1. Test Philosophy & Engineering Principles

The GNDROiD Next-Gen E2E testing framework is engineered around strict, non-negotiable principles:

1. **Opaque-Box Requirement-Driven Verification:**
   - Tests are derived directly from user requirements (`ORIGINAL_REQUEST.md` R1–R6) and architectural interfaces (`PROJECT.md`).
   - Testing exercises public interfaces, subprocess invocations, network sockets, and file contracts rather than private class internals.

2. **Zero Physical Hardware Dependency:**
   - The test suite executes deterministically in continuous integration (CI) environments without physical Android handsets, physical USB connections, or active GPU display monitors.
   - High-fidelity synthetic fixtures emulate ADB, QEMU console, upstream proxy servers, and Scrcpy control sockets in-memory.

3. **Strict Ban on Tautological Assertions:**
   - Zero tolerance for simulated assertions, hardcoded `pass_5 = True`, tautologies (`or True`), dummy mock length checks, or mock return values designed solely to mask failures.
   - Every assertion tests verifiable state transitions: binary packet structures, socket byte streams, property mutations, or process life cycles.

4. **Ephemeral Port & Socket Isolation:**
   - All network services (mock QEMU Telnet, mock HTTP/SOCKS5 proxy, mock Scrcpy control socket) bind to `127.0.0.1:0` (dynamic OS port allocation) to prevent port collisions during parallel test runs.

5. **Resource Containment & Guaranteed Cleanup:**
   - Every fixture must implement context managers (`__enter__` / `__exit__`) and strict `try ... finally` blocks to terminate threads, close sockets, and purge temporary file artifacts.

---

## 2. Multi-Tier Testing Methodology

The test suite is structured into five rigorous verification tiers:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          TIER 5: ADVERSARIAL HARDENING                      │
│        Chaos injection: sudden socket drop, zip-slip, memory exhaustion    │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                      TIER 4: REAL-WORLD APPLICATION SCENARIOS               │
│       15+ end-to-end workflows: Gaming Mode, Multi-Instance, Banking Sideload │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                  TIER 3: PAIRWISE CROSS-FEATURE INTEGRATION                 │
│      25+ combinatorial tests: Proxy + Region, Split-APK + Polyfill, etc.    │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
         ┌─────────────────────────────┴─────────────────────────────┐
         ▼                                                           ▼
┌─────────────────────────────────┐         ┌─────────────────────────────────┐
│   TIER 1: FEATURE COVERAGE      │         │ TIER 2: BOUNDARY & CORNER CASES │
│   Happy Path Verification       │         │ Nulls, extremes, network drops  │
│   >=5 test cases per feature    │         │ >=5 test cases per feature      │
│   (115 test cases total)        │         │ (115 test cases total)          │
└─────────────────────────────────┘         └─────────────────────────────────┘
```

### Tier 1: Feature Coverage (Category-Partition)
- **Objective:** Verify nominal functionality for each of the 23 discrete features.
- **Quota:** Minimum 5 distinct test cases per feature ($23 \times 5 = 115$ test cases).
- **Focus:** Valid inputs, correct state transitions, standard protocol negotiations.

### Tier 2: Boundary Value Analysis & Corner Cases
- **Objective:** Verify error handling, input validation, and boundary conditions.
- **Quota:** Minimum 5 distinct test cases per feature ($23 \times 5 = 115$ test cases).
- **Focus:** Corrupted archives, missing splits, network dropouts, 407 proxy challenges, rapid toggling, zero-dimension viewports, out-of-bounds coordinates, non-root fallback.

### Tier 3: Pairwise Combinations & Cross-Feature Integration
- **Objective:** Verify interactions between coupled subsystems.
- **Quota:** Minimum 25 pairwise integration test cases.
- **Focus:** Matrix combinations such as Region Changer + Authenticated Proxy, Split-APK Installer + Hardware Polyfill, Input Synchronizer + Eco Mode Throttler.

### Tier 4: Real-World Application Scenarios
- **Objective:** Validate end-to-end user journeys mirroring production workflows.
- **Quota:** Minimum 15 comprehensive scenario tests.
- **Focus:** Full game launch under Gaming Mode, multi-instance synchronized farming, foreign banking app installation under 4-tier cloaking, GPX route navigation under network constraints.

### Tier 5: Adversarial Hardening
- **Objective:** Stress testing under adverse operating conditions.
- **Focus:** Malformed ZIP archives (Zip Slip attempts), high-frequency Scrcpy packet bursts (1000+ packets/sec), immediate proxy failover to kill-switch, memory compaction under load.

---

## 3. Complete 23-Feature Inventory Test Mapping

| # | Feature Name | Source | Milestone | Test Suite Location | Tier 1 Target | Tier 2 Target | Tier 3 Cross-Link | Tier 4 Scenario |
|---|--------------|:------:|:---------:|---------------------|:-------------:|:-------------:|:-----------------:|:---------------:|
| 1 | Multi-Format Split-APK Unpacker | R1 | M1 | `tests/test_package_installer.py` | 5 | 5 | Feat 1 + Feat 5 | Scenario 3 |
| 2 | Native Split Session Installer | R1 | M1 | `tests/test_package_installer.py` | 5 | 5 | Feat 2 + Feat 4 | Scenario 3 |
| 3 | Automated OBB Deployment | R1 | M1 | `tests/test_package_installer.py` | 5 | 5 | Feat 3 + Feat 1 | Scenario 1 |
| 4 | Anonymous GMS Token Dispatcher | R1 | M1 | `tests/test_package_installer.py` | 5 | 5 | Feat 4 + Feat 2 | Scenario 3 |
| 5 | Certified Hardware Polyfill | R1 | M1 | `tests/test_package_installer.py` | 5 | 5 | Feat 5 + Feat 6 | Scenario 3 |
| 6 | 4-Tier Region Changer: Telephony | R2 | M1 | `tests/test_region_controller.py` | 5 | 5 | Feat 6 + Feat 10 | Scenario 3 |
| 7 | 4-Tier Region Changer: System OS | R2 | M1 | `tests/test_region_controller.py` | 5 | 5 | Feat 7 + Feat 8 | Scenario 3 |
| 8 | 4-Tier Region Changer: Hardware | R2 | M1 | `tests/test_region_controller.py` | 5 | 5 | Feat 8 + Feat 16 | Scenario 4 |
| 9 | 4-Tier Region Changer: Network | R2 | M1 | `tests/test_region_controller.py` | 5 | 5 | Feat 9 + Feat 12 | Scenario 3 |
| 10 | Fast Auth-Stripping Local Proxy | R3 | M2 | `tests/test_proxy_manager.py` | 5 | 5 | Feat 10 + Feat 6 | Scenario 3 |
| 11 | Transparent Tun2Socks Interceptor | R3 | M2 | `tests/test_proxy_manager.py` | 5 | 5 | Feat 11 + Feat 12 | Scenario 3 |
| 12 | DNS-over-Proxy & Egress Kill-Switch | R3 | M2 | `tests/test_proxy_manager.py` | 5 | 5 | Feat 12 + Feat 9 | Scenario 3 |
| 13 | Multi-Instance Input Synchronizer | R4 | M3 | `tests/test_sync_multiplexer.py` | 5 | 5 | Feat 13 + Feat 14 | Scenario 2 |
| 14 | Eco Mode Dynamic Background Throttling | R4 | M3 | `tests/test_eco_and_memory.py` | 5 | 5 | Feat 14 + Feat 15 | Scenario 2 |
| 15 | 1-Click Memory Trimmer & Compactor | R4 | M3 | `tests/test_eco_and_memory.py` | 5 | 5 | Feat 15 + Feat 14 | Scenario 2 |
| 16 | Extended Sensors & GPX Route Player | R4 | M3 | `tests/test_sensor_console.py` | 5 | 5 | Feat 16 + Feat 8 | Scenario 4 |
| 17 | Precision Keymapping & Gamepad Engine | R5 | M4 | `tests/test_keymapper_and_macro.py` | 5 | 5 | Feat 17 + Feat 19 | Scenario 1 |
| 18 | Script Automation & Macro Engine | R5 | M4 | `tests/test_keymapper_and_macro.py` | 5 | 5 | Feat 18 + Feat 13 | Scenario 2 |
| 19 | Gaming Mode Launch Profile | R5 | M4 | `tests/test_gaming_profile.py` | 5 | 5 | Feat 19 + Feat 17 | Scenario 1 |
| 20 | GUI: Universal Region & Proxy Tab | R6 | M5 | `tests/test_gui_integration.py` | 5 | 5 | Feat 20 + Feat 6/10 | Scenario 3 |
| 21 | GUI: Split-APK Sideload Integration | R6 | M5 | `tests/test_gui_integration.py` | 5 | 5 | Feat 21 + Feat 1/2 | Scenario 3 |
| 22 | GUI: Multi-Instance Toolbar & Actions | R6 | M5 | `tests/test_gui_integration.py` | 5 | 5 | Feat 22 + Feat 13/14 | Scenario 2 |
| 23 | GUI: Keymapping HUD Overlay & Gaming Toggle | R6 | M5 | `tests/test_gui_integration.py` | 5 | 5 | Feat 23 + Feat 17/19 | Scenario 1 |
| - | **Total Required Test Cases** | | | | **115** | **115** | **>=25** | **>=15** |

---

## 4. Synthetic High-Fidelity Fixtures Architecture

All synthetic fixtures reside under `tests/fixtures/` and are importable across test modules.

```
tests/fixtures/
├── __init__.py
├── mock_adb.py           # Subprocess interceptor & state machine for ADB
├── mock_qemu.py          # In-memory Telnet console server (port 5554 / dynamic)
├── mock_proxy.py         # Dual HTTP/HTTPS and SOCKS5 proxy server with auth
├── mock_scrcpy.py        # Binary Scrcpy control socket server & packet decoder
└── bundle_generator.py   # Pure-Python generator for .xapk, .apkm, .apks, .aab
```

### 4.1 `tests/fixtures/mock_adb.py`

#### Purpose & Architecture
Intercepts Python standard library calls to `subprocess.run`, `subprocess.Popen`, and `subprocess.check_output` targeting `adb.exe`. Maintains an in-memory virtual Android state machine tracking installed packages, PackageInstaller sessions, system properties, settings, network device MTUs, sysctl parameters, iptables rules, and virtual filesystem paths.

#### Detailed Wire Command Specifications
1. **PackageInstaller Session Management:**
   - `shell pm install-create -r -t -d -g -i com.android.vending --install-location 0 -S <bytes>`
     - Validates pre-allocation size.
     - Allocates unique numeric session ID (e.g. `10842918`).
     - Returns stdout: `Success: [10842918]\n` with return code 0.
   - `exec-in pm install-write -S <size> <sessionId> <splitName>`
     - Reads binary data directly from `kwargs.get("stdin")` or input stream.
     - Verifies stream length matches `<size>`.
     - Appends split payload to active session.
     - Returns stdout: `Success: streamed <size> bytes\n` with return code 0.
     - If session missing: returns stderr `Failure [INSTALL_FAILED_INVALID_SESSION]\n` with return code 1.
   - `shell pm install-commit <sessionId>`
     - Validates all splits present.
     - Moves package from staged session to `user_packages[0]`.
     - Returns stdout: `Success\n` with return code 0.
   - `shell pm install-abandon <sessionId>`
     - Clears staged splits and deletes session.
     - Returns stdout: `Success\n` with return code 0.

2. **System Properties (`setprop` / `getprop`):**
   - Telephony: `gsm.sim.operator.numeric`, `gsm.sim.operator.alpha`, `gsm.sim.operator.iso-country`, `gsm.operator.numeric`, `gsm.operator.alpha`, `gsm.operator.iso-country`, `gsm.sim.state`.
   - System OS: `persist.sys.locale`, `persist.sys.timezone`.
   - Hardware Polyfill: `ro.product.model`, `ro.product.brand`, `ro.build.fingerprint`, `ro.board.platform`.
   - SurfaceFlinger / Gaming: `ro.surface_flinger.has_wide_color_display`, `ro.surface_flinger.has_HDR_display`, `ro.surface_flinger.max_frame_buffer_acquired_buffers`, `ro.sf.lcd_density`.
   - DNS: `net.dns1`, `net.dns2`.

3. **Android Settings (`settings put` / `settings get`):**
   - Tables: `global`, `system`, `secure`.
   - Keys: `http_proxy`, `global_http_proxy_host`, `global_http_proxy_port`, `private_dns_mode`, `auto_time_zone`, `peak_refresh_rate`, `min_refresh_rate`.

4. **Network & System Controls:**
   - `ip link set dev <dev> mtu <mtu>`: Updates interface MTU map (e.g. `eth0` -> 1380).
   - `echo <val> > <path>`:
     - `/proc/sys/net/ipv6/conf/all/disable_ipv6`: Sets IPv6 status.
     - `/proc/sys/vm/drop_caches`: Triggers kernel cache drop.
     - `/proc/sys/vm/compact_memory`: Triggers memory compaction.
   - `iptables -I OUTPUT 1 -j DROP` / `iptables -D OUTPUT 1`: Manages kill-switch rules.
   - `am trim-memory <target> <level>`: Validates trim level (`RUNNING_CRITICAL`, `COMPLETE`).
   - `curl -s --max-time 4 http://ip-api.com/json`: Returns mock JSON payload reflecting current simulated egress country.
   - `push <src> <dest>`: Copies file into in-memory virtual filesystem map.

#### Key Code Contract
```python
class MockAdbSession:
    def __init__(self, initial_state: Optional[MockAdbState] = None): ...
    def __enter__(self) -> "MockAdbSession": ...
    def __exit__(self, exc_type, exc_val, exc_tb): ...

class MockAdbState:
    def __init__(self):
        self.properties: Dict[str, str] = {}
        self.settings: Dict[str, Dict[str, str]] = {}
        self.sessions: Dict[str, StagedInstallSession] = {}
        self.installed_packages: Set[str] = set()
        self.virtual_fs: Dict[str, bytes] = {}
        self.iptables_rules: List[str] = []
        self.command_log: List[List[str]] = []
        self.simulated_egress: Dict[str, Any] = {"countryCode": "AE", "query": "195.229.241.50"}
```

---

### 4.2 `tests/fixtures/mock_qemu.py`

#### Purpose & Architecture
An in-memory TCP Telnet console server binding to `127.0.0.1:0` (or standard port 5554). Emulates QEMU console control protocols, requiring authentication against a token file or configured secret string, and handling GPS coordinate updates, network conditioning, battery parameters, and virtual sensors.

#### Protocol Wire Sequence
1. **Connection Greeting:**
   Upon client connection, transmits:
   ```
   Android Console: Authentication required
   Android Console: type 'auth <auth_token>' to authenticate
   Android Console: you can find your auth token in
   'C:\Users\...\.emulator_console_auth_token'
   OK
   ```
2. **Authentication Command:**
   - Client sends: `auth <token>\r\n`
   - If token matches: replies `OK\r\n` and sets session state `authenticated = True`.
   - If token mismatches: replies `KO: authentication failed\r\n`.
3. **Control Commands:**
   - `geo fix <lon> <lat> [<alt> [<satellites>]]`:
     - Parses floating point values; validates $-180 \le \text{lon} \le 180$, $-90 \le \text{lat} \le 90$.
     - Records entry in `server.geo_history` with monotonic timestamp.
     - Replies `OK\r\n`.
   - `network delay <delay>` / `network speed <speed>`:
     - Validates speed/delay parameters (`none`, `gprs`, `edge`, `umts`, `lte`, `full`).
     - Updates `server.network_state`.
     - Replies `OK\r\n`.
   - `power capacity <0-100>`, `power ac <on|off>`, `power status <state>`:
     - Updates `server.power_state`.
     - Replies `OK\r\n`.
   - `sensor set acceleration <x>:<y>:<z>`, `sensor set orientation <azimuth>:<pitch>:<roll>`:
     - Parses sensor vector triplets; updates `server.sensor_state`.
     - Replies `OK\r\n`.
   - `quit` / `exit`:
     - Closes client socket.

#### Key Code Contract
```python
class MockQemuConsoleServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 0, auth_token: str = "secret_qemu_token", require_auth: bool = True):
        self.host = host
        self.requested_port = port
        self.port = 0
        self.auth_token = auth_token
        self.require_auth = require_auth
        self.geo_history: List[Tuple[float, float, float, float]] = []
        self.command_log: List[str] = []
        self.network_state = {"delay": "none", "speed": "full"}
        self.power_state = {"capacity": 100, "ac": "on", "status": "charging"}
        self.sensor_state: Dict[str, str] = {}
        
    def start(self): ...
    def stop(self): ...
    def __enter__(self) -> "MockQemuConsoleServer": ...
    def __exit__(self, exc_type, exc_val, exc_tb): ...
```

---

### 4.3 `tests/fixtures/mock_proxy.py`

#### Purpose & Architecture
An in-memory dual-protocol proxy server supporting HTTP/HTTPS CONNECT tunneling and SOCKS5 (RFC 1928 / RFC 1929) with user/password authentication. Used to test local auth-stripping proxy injection, Tun2Socks routing, DNS-over-Proxy resolution, and egress kill-switch fail-closed activation.

#### Protocol Wire Sequence
1. **HTTP/HTTPS Proxy (CONNECT & GET/POST):**
   - **Authentication Challenge:**
     - Client connects and sends `CONNECT target.com:443 HTTP/1.1\r\n...`.
     - If `Proxy-Authorization: Basic <base64>` is missing or invalid:
       Replies `HTTP/1.1 407 Proxy Authentication Required\r\nProxy-Authenticate: Basic realm="MockProxy"\r\nContent-Length: 0\r\n\r\n`.
       Increments `server.auth_failures`.
     - If valid:
       Replies `HTTP/1.1 200 Connection Established\r\n\r\n`.
       Increments `server.auth_successes`.
       Enters bidirectional transparent byte-tunneling mode.
   - **Plain HTTP Request:**
     - Verifies `Proxy-Authorization` header; strips or validates; returns HTTP 200 response with simulated upstream payload.

2. **SOCKS5 Proxy (RFC 1928 & RFC 1929):**
   - **Method Selection (RFC 1928):**
     - Client sends: `\x05<nmethods><methods...>`.
     - If credentials configured: server replies `\x05\x02` (Username/Password authentication required).
     - If no credentials: server replies `\x05\x00` (No authentication required).
   - **Authentication Handshake (RFC 1929):**
     - Client sends: `\x01<ulen><username><plen><password>`.
     - Server validates credentials against configured user/pass.
     - If match: replies `\x01\x00` (Success).
     - If mismatch: replies `\x01\x01` (Failure) and closes connection.
   - **Connection Request:**
     - Client sends: `\x05\x01\x00<atyp><dst_addr><dst_port>`.
     - Supports IPv4 (`atyp=0x01`), Domain Name (`atyp=0x03` - verifies remote DNS resolution), and IPv6 (`atyp=0x04`).
     - Server replies `\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00` (Connection succeeded).
     - Relays payload bytes.

3. **Chaos & Kill-Switch Simulation:**
   - Method `server.trigger_network_drop()` abruptly closes all client connections and refuses new sockets.
   - Tests assert that GNDROiD's proxy manager detects the failure within heartbeat window and immediately executes `iptables -I OUTPUT 1 -j DROP`.

#### Key Code Contract
```python
class MockDualProxyServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 0, protocol: str = "http", auth_user: Optional[str] = "admin", auth_pass: Optional[str] = "p@ss123"):
        self.host = host
        self.port = 0
        self.protocol = protocol.lower()  # "http" or "socks5"
        self.auth_user = auth_user
        self.auth_pass = auth_pass
        self.requests_log: List[Dict[str, Any]] = []
        self.auth_successes = 0
        self.auth_failures = 0
        self.active_tunnels = 0
        
    def start(self): ...
    def stop(self): ...
    def trigger_network_drop(self): ...
    def __enter__(self) -> "MockDualProxyServer": ...
    def __exit__(self, exc_type, exc_val, exc_tb): ...
```

---

### 4.4 `tests/fixtures/mock_scrcpy.py`

#### Purpose & Architecture
An in-memory TCP server listening on `127.0.0.1:0` emulating Scrcpy 4.1's binary control socket protocol. Decodes and validates touch and key events emitted by `InputSyncMultiplexer`, `Keymapper`, and `MacroEngine`, verifying packet alignment, boundary constraints, and coordinate normalization mathematics.

#### Binary Wire Protocol Formats
1. **Touch Event Packet (`CONTROL_MSG_TYPE_INJECT_TOUCH_EVENT = 2`):**
   - **Exact Wire Length:** **32 bytes**
   - **Binary Struct Format:** `>BBQIIHHHII` (10 fields: type, action, pointer_id, x, y, width, height, pressure, action_button, buttons)
   - **Field Layout:**
     - `0x00` (1B): `uint8` Type = `0x02`
     - `0x01` (1B): `uint8` Action (`0` = DOWN, `1` = UP, `2` = MOVE)
     - `0x02` (8B): `uint64` Pointer ID (Big-Endian)
     - `0x0A` (4B): `uint32` X Coordinate (Pixels on target display)
     - `0x0E` (4B): `uint32` Y Coordinate (Pixels on target display)
     - `0x12` (2B): `uint16` Screen Width (Target instance width)
     - `0x14` (2B): `uint16` Screen Height (Target instance height)
     - `0x16` (2B): `uint16` Pressure (`0xFFFF` = 1.0f full pressure)
     - `0x18` (4B): `uint32` Action Button (`1` = Primary)
     - `0x1C` (4B): `uint32` Buttons State (`1` = Primary Pressed)

2. **Key Event Packet (`CONTROL_MSG_TYPE_INJECT_KEY_EVENT = 0`):**
   - **Exact Wire Length:** **14 bytes**
   - **Binary Struct Format:** `>BBIII`
   - **Field Layout:**
     - `0x00` (1B): `uint8` Type = `0x00`
     - `0x01` (1B): `uint8` Action (`0` = KEY_DOWN, `1` = KEY_UP)
     - `0x02` (4B): `uint32` Keycode (Android `AKEYCODE_*`, e.g. `AKEYCODE_W = 51`)
     - `0x06` (4B): `uint32` Repeat Count (`0`)
     - `0x0A` (4B): `uint32` Metastate (`0` or modifier mask)

3. **Coordinate Transformation Verification:**
   - Validates multi-instance scaling from Master ($W_m \times H_m$) to Slave ($W_s \times H_s$):
     $$x_s = \text{round}\left(\frac{x_m}{W_m} \times W_s\right), \quad y_s = \text{round}\left(\frac{y_m}{H_m} \times H_s\right)$$
   - Verifies that packet coordinates stay strictly within $[0, W_s]$ and $[0, H_s]$.

#### Key Code Contract
```python
class MockScrcpyControlServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 0):
        self.host = host
        self.port = 0
        self.received_touch_packets: List[Dict[str, Any]] = []
        self.received_key_packets: List[Dict[str, Any]] = []
        self.total_bytes_received = 0
        
    def start(self): ...
    def stop(self): ...
    def wait_for_touch_count(self, count: int, timeout: float = 2.0) -> bool: ...
    def wait_for_key_count(self, count: int, timeout: float = 2.0) -> bool: ...
    def __enter__(self) -> "MockScrcpyControlServer": ...
    def __exit__(self, exc_type, exc_val, exc_tb): ...
```

---

### 4.5 `tests/fixtures/bundle_generator.py`

#### Purpose & Architecture
A pure-Python generator creating valid, on-the-fly application package bundle fixtures (`.xapk`, `.apkm`, `.apks`, `.aab`, and `.apk`) without requiring external Java runtime, `bundletool.jar`, or compilation tools. Also produces controlled corrupt and adversarial archives for boundary testing.

#### Supported Bundle Configurations
1. **`.xapk` Archive (APKPure Standard):**
   - Valid ZIP containing:
     - `manifest.json`: Specification schema (`package_name`, `version_code`, `version_name`, `split_configs`, `expansions`).
     - `base.apk`: Minimal valid ZIP format.
     - Split APKs: `config.arm64_v8a.apk`, `config.xxhdpi.apk`, `config.en.apk`.
     - `Android/obb/<package_name>/main.<vcode>.<pkg>.obb`: Real binary expansion payload.
     - `icon.png`: Valid image asset header.

2. **`.apkm` Archive (APKMirror Standard):**
   - Valid ZIP containing:
     - `info.json`: Metadata schema (`pname`, `versioncode`, `splits` list).
     - `base.apk`, `split_config.arm64_v8a.apk`, `split_config.en.apk`.

3. **`.apks` Archive (Bundletool Split Archive):**
   - Valid ZIP containing:
     - `toc.pb`: Protocol buffer Table of Contents header.
     - `splits/base-master.apk`, `splits/base-arm64_v8a.apk`, `splits/base-xxhdpi.apk`.

4. **`.aab` Archive (Raw Android App Bundle):**
   - Valid ZIP containing:
     - `BundleConfig.pb`
     - `base/manifest/AndroidManifest.xml`
     - `base/dex/classes.dex`
     - `base/res/values/strings.xml`

5. **Corrupted & Adversarial Archive Variants (Tier 2 & Tier 5):**
   - `empty_archive`: Zero files in ZIP.
   - `missing_base`: Contains split APKs but omits `base.apk`.
   - `malformed_json`: Syntax errors in `manifest.json` / `info.json`.
   - `zero_byte_splits`: Splits with 0 bytes size.
   - `zip_slip`: Contains directory traversal paths (`../../evil.sh`) to assert path sanitization.
   - `truncated_archive`: Abruptly truncated byte stream.

#### Key Code Contract
```python
class SyntheticBundleGenerator:
    @staticmethod
    def create_xapk(output_path: str, package_name: str = "com.indusbridge.app", version_code: int = 100, splits: Optional[List[str]] = None, with_obb: bool = True) -> str: ...
    
    @staticmethod
    def create_apkm(output_path: str, package_name: str = "com.indusbridge.app", version_code: int = 100) -> str: ...
    
    @staticmethod
    def create_apks(output_path: str, package_name: str = "com.indusbridge.app", version_code: int = 100) -> str: ...
    
    @staticmethod
    def create_aab(output_path: str, package_name: str = "com.indusbridge.app", version_code: int = 100) -> str: ...
    
    @staticmethod
    def create_corrupted_bundle(output_path: str, corruption_type: str) -> str: ...
```

---

## 5. Test Suite File Structure & Layout

All automated test modules reside strictly within `tests/`:

```
tests/
├── conftest.py                       # Global pytest hooks and shared fixture setup
├── run_all_e2e_tests.py              # Canonical test runner and CLI orchestrator
│
├── fixtures/
│   ├── __init__.py
│   ├── mock_adb.py
│   ├── mock_qemu.py
│   ├── mock_proxy.py
│   ├── mock_scrcpy.py
│   └── bundle_generator.py
│
├── test_package_installer.py         # Features 1–5: Split Unpacker, Session Streaming, OBB, GMS, Polyfill
├── test_region_controller.py         # Features 6–9: 4-Tier Region Changer (Telephony, OS, Hardware, Network)
├── test_proxy_manager.py             # Features 10–12: Local Auth Proxy, Tun2Socks, DNS, Kill-Switch
├── test_sync_multiplexer.py          # Feature 13: Multi-Instance Input Synchronizer
├── test_eco_and_memory.py            # Features 14–15: Eco Mode Throttler & 1-Click Memory Trimmer
├── test_sensor_console.py            # Feature 16: Extended Sensors & GPX Route Player
├── test_keymapper_and_macro.py       # Features 17–18: Precision Keymapping & Macro Engine
├── test_gaming_profile.py            # Feature 19: Gaming Mode Launch Profile
├── test_gui_integration.py           # Features 20–23: Region Tab, Sideload Dialog, Toolbar, Keymap HUD
├── test_tier3_cross_feature.py       # Tier 3: 25+ Pairwise Combinations
└── test_tier4_real_world.py          # Tier 4: 15+ End-to-End Scenarios
```

---

## 6. Unified Test Runner (`tests/run_all_e2e_tests.py`)

### CLI Invocation Syntax
```powershell
# Run the complete test suite across all tiers
python tests/run_all_e2e_tests.py

# Run only a specific tier
python tests/run_all_e2e_tests.py --tier 1
python tests/run_all_e2e_tests.py --tier 2
python tests/run_all_e2e_tests.py --tier 3
python tests/run_all_e2e_tests.py --tier 4

# Run tests targeting a specific feature ID (1–23)
python tests/run_all_e2e_tests.py --feature 10

# Generate JUnit XML test report for CI/CD pipeline
python tests/run_all_e2e_tests.py --junit artifacts/test-results.xml

# Enable verbose per-test progress reporting
python tests/run_all_e2e_tests.py --verbose
```

### Execution Output Format
The runner outputs a structured ASCII summary table and returns exit code 0 if and only if 100% of selected tests pass:

```
========================================================================================
                          GNDROiD NEXT-GEN E2E TEST RUNNER
========================================================================================
  Target: Windows x86_64 | Integrity: Development | Ephemeral Sockets Active
----------------------------------------------------------------------------------------
  Suite                                   Total   Passed   Failed   Skipped   Duration
----------------------------------------------------------------------------------------
  test_package_installer.py                 20       20        0         0      1.42s
  test_region_controller.py                 20       20        0         0      1.18s
  test_proxy_manager.py                     20       20        0         0      2.05s
  test_sync_multiplexer.py                  10       10        0         0      0.84s
  test_eco_and_memory.py                    20       20        0         0      1.22s
  test_sensor_console.py                    10       10        0         0      0.95s
  test_keymapper_and_macro.py               20       20        0         0      1.51s
  test_gaming_profile.py                    10       10        0         0      0.72s
  test_gui_integration.py                   40       40        0         0      3.10s
  test_tier3_cross_feature.py               25       25        0         0      4.20s
  test_tier4_real_world.py                  15       15        0         0      6.50s
----------------------------------------------------------------------------------------
  TOTAL                                    210      210        0         0     23.69s
========================================================================================
  OVERALL STATUS: SUCCESS (100% Pass Rate)
========================================================================================
```

---

## 7. Quality Gates & Acceptance Thresholds

1. **Pass Rate Requirement:**
   - **100% test pass rate required.** A single assertion failure or unexpected exception fails the milestone.
   - Zero tests skipped unless gated by explicit platform capability checks (documented in handoff caveats).

2. **Code Coverage Target:**
   - Minimum **90% branch coverage** across all modules in `nexus/` (`nexus/package_installer.py`, `nexus/region_controller.py`, `nexus/proxy_manager.py`, `nexus/sync_multiplexer.py`, `nexus/eco_throttler.py`, `nexus/memory_trimmer.py`, `nexus/sensor_console.py`, `nexus/keymapper.py`, `nexus/macro_engine.py`, `nexus/gaming_profile.py`).

3. **Performance Budget:**
   - Complete E2E verification suite execution time must not exceed **60 seconds** on standard developer workstation hardware.
   - All network socket timeouts must be bounded ($\le 2.0\text{ seconds}$).
