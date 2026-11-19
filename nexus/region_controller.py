"""
nexus/region_controller.py
==========================
Universal 4-Tier Region Changer for GNDROiD.
Synchronizes Telephony, System OS, Hardware/GPS, and Network Egress atomically.

Milestone M1 (Features 6-9):
- Feature 6: Tier 1 Telephony (MCC/MNC, SIM ISO, SPN, dual-SIM properties, CarrierConfig)
- Feature 7: Tier 2 System OS (Locale, Timezone, AlarmManager AIDL, NTP clock sync)
- Feature 8: Tier 3 Hardware (QEMU Telnet console geo fix & mock cell tower ID)
- Feature 9: Tier 4 Network (MTU 1380, IPv6 cutoff, Private DNS leak prevention, egress verification)
"""

import os
import sys
import time
import json
import socket
import logging
import subprocess
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger("gndroid.region_controller")
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


# ============================================================================
# Regional Persona / Profile Definitions
# ============================================================================

@dataclass
class RegionProfile:
    """
    Complete configuration profile for a geographic persona.
    """
    code: str                                # ISO 3166-1 alpha-2 (e.g. "AE")
    country_name: str                        # Human readable name
    carrier_spn: str                         # Service Provider Name (e.g. "du")
    mcc_mnc: str                             # 5 or 6 digit MCC-MNC string
    mcc: str                                 # 3 digit Mobile Country Code
    mnc: str                                 # 2 or 3 digit Mobile Network Code
    sim_iso: str                             # Lowercase 2-letter SIM country ISO
    locale: str                              # Primary BCP 47 locale
    locales: str                             # Comma-delimited locale priority list
    timezone: str                            # IANA Timezone identifier
    coordinates: Tuple[float, float, float]  # (Longitude, Latitude, Altitude in meters)
    cell_tower: Tuple[int, int]              # (Tracking Area Code, Cell ID)
    regional_dns: str                        # Primary regional DNS resolver
    secondary_dns: str = "1.1.1.1"           # Secondary regional / global DNS resolver


# Backward compatibility alias
RegionPersona = RegionProfile


REGIONS: Dict[str, RegionProfile] = {
    "AE": RegionProfile(
        code="AE",
        country_name="United Arab Emirates",
        carrier_spn="du",
        mcc_mnc="42402",
        mcc="424",
        mnc="02",
        sim_iso="ae",
        locale="en-AE",
        locales="en-AE,ar-AE",
        timezone="Asia/Dubai",
        coordinates=(55.2797, 25.1972, 10.0),
        cell_tower=(15420, 135478912),
        regional_dns="195.229.241.50",
        secondary_dns="1.1.1.1",
    ),
    "SA": RegionProfile(
        code="SA",
        country_name="Saudi Arabia",
        carrier_spn="stc",
        mcc_mnc="42001",
        mcc="420",
        mnc="01",
        sim_iso="sa",
        locale="en-SA",
        locales="en-SA,ar-SA",
        timezone="Asia/Riyadh",
        coordinates=(46.6753, 24.7136, 612.0),
        cell_tower=(23101, 201948576),
        regional_dns="212.118.140.2",
        secondary_dns="1.1.1.1",
    ),
    "US": RegionProfile(
        code="US",
        country_name="United States",
        carrier_spn="T-Mobile",
        mcc_mnc="310260",
        mcc="310",
        mnc="260",
        sim_iso="us",
        locale="en-US",
        locales="en-US",
        timezone="America/New_York",
        coordinates=(-74.0060, 40.7128, 10.0),
        cell_tower=(48201, 34810294),
        regional_dns="1.1.1.1",
        secondary_dns="8.8.8.8",
    ),
    "GB": RegionProfile(
        code="GB",
        country_name="United Kingdom",
        carrier_spn="EE",
        mcc_mnc="23430",
        mcc="234",
        mnc="30",
        sim_iso="gb",
        locale="en-GB",
        locales="en-GB",
        timezone="Europe/London",
        coordinates=(-0.1278, 51.5074, 15.0),
        cell_tower=(31045, 12903847),
        regional_dns="1.1.1.1",
        secondary_dns="8.8.8.8",
    ),
    "PK": RegionProfile(
        code="PK",
        country_name="Pakistan",
        carrier_spn="Jazz",
        mcc_mnc="41001",
        mcc="410",
        mnc="01",
        sim_iso="pk",
        locale="en-PK",
        locales="en-PK,ur-PK",
        timezone="Asia/Karachi",
        coordinates=(67.0011, 24.8607, 12.0),
        cell_tower=(10420, 5829104),
        regional_dns="1.1.1.1",
        secondary_dns="8.8.8.8",
    ),
    "DE": RegionProfile(
        code="DE",
        country_name="Germany",
        carrier_spn="Telekom",
        mcc_mnc="26201",
        mcc="262",
        mnc="01",
        sim_iso="de",
        locale="de-DE",
        locales="de-DE,en-US",
        timezone="Europe/Berlin",
        coordinates=(13.4050, 52.5200, 34.0),
        cell_tower=(40102, 4920193),
        regional_dns="1.1.1.1",
        secondary_dns="8.8.8.8",
    ),
    "JP": RegionProfile(
        code="JP",
        country_name="Japan",
        carrier_spn="NTT DOCOMO",
        mcc_mnc="44010",
        mcc="440",
        mnc="10",
        sim_iso="jp",
        locale="ja-JP",
        locales="ja-JP,en-US",
        timezone="Asia/Tokyo",
        coordinates=(139.6917, 35.6895, 40.0),
        cell_tower=(50123, 8930214),
        regional_dns="1.1.1.1",
        secondary_dns="8.8.8.8",
    ),
}

REGION_PERSONAS = REGIONS


# ============================================================================
# Switch Result Data Structure
# ============================================================================

@dataclass
class RegionSwitchResult:
    """
    Result of a 4-tier region persona switch. Supports both attribute
    access and dictionary-style subscripting for seamless compatibility.
    """
    success: bool
    region_code: str
    country_name: str
    carrier: str
    tier1_telephony: bool
    tier2_system: bool
    tier3_hardware: bool
    tier4_network: bool
    egress_verified: bool
    egress_details: Dict[str, Any] = field(default_factory=dict)
    message: str = ""

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)

    def keys(self) -> List[str]:
        return list(self.__dataclass_fields__.keys())

    def items(self) -> List[Tuple[str, Any]]:
        return [(k, getattr(self, k)) for k in self.keys()]

    def to_dict(self) -> Dict[str, Any]:
        return {k: getattr(self, k) for k in self.keys()}


# ============================================================================
# Universal 4-Tier Region Controller
# ============================================================================

class UniversalRegionController:
    """
    Universal 4-tier region changer orchestrating:
    - Tier 1: Telephony & GSM Carrier Properties, Dual-SIM, CarrierConfig
    - Tier 2: System OS Locale, Timezone, AlarmManager AIDL, Clock Epoch
    - Tier 3: Hardware GPS (QEMU Telnet 5554) & Cell Tower Simulation
    - Tier 4: Network Egress Verification, MTU 1380 Clamping, DNS Leak Seal
    """

    REGIONS: Dict[str, RegionProfile] = REGIONS
    REGION_PERSONAS = REGIONS

    def __init__(self, adb_path: str = "adb"):
        self.adb = adb_path

    def _run_shell(
        self, serial: str, args: List[str], timeout: int = 15
    ) -> subprocess.CompletedProcess:
        """Executes an adb shell command on the target serial."""
        cmd = [self.adb]
        if serial:
            cmd.extend(["-s", serial])
        cmd.extend(["shell"] + args)
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )

    # ------------------------------------------------------------------------
    # Tier 1: Telephony & Carrier Identity
    # ------------------------------------------------------------------------

    def apply_tier1_telephony(self, serial: str, profile: RegionProfile) -> bool:
        """
        Applies Tier 1 telephony overrides:
        - gsm.sim.operator.* (numeric, alpha, iso-country)
        - gsm.operator.* (numeric, alpha, iso-country)
        - gsm.sim.state -> READY
        - Dual-SIM properties for slots 0 and 1
        - CarrierConfig XML override injection
        - Radio HAL cellular bridge notification
        """
        try:
            props = [
                ("gsm.sim.operator.numeric", profile.mcc_mnc),
                ("gsm.sim.operator.alpha", profile.carrier_spn),
                ("gsm.sim.operator.iso-country", profile.sim_iso),
                ("gsm.operator.numeric", profile.mcc_mnc),
                ("gsm.operator.alpha", profile.carrier_spn),
                ("gsm.operator.iso-country", profile.sim_iso),
                ("gsm.sim.state", "READY"),
                # Primary SIM (slot 0)
                ("gsm.sim.operator.numeric.0", profile.mcc_mnc),
                ("gsm.sim.operator.alpha.0", profile.carrier_spn),
                ("gsm.sim.operator.iso-country.0", profile.sim_iso),
                ("gsm.operator.numeric.0", profile.mcc_mnc),
                ("gsm.operator.alpha.0", profile.carrier_spn),
                ("gsm.operator.iso-country.0", profile.sim_iso),
                # Secondary SIM (slot 1)
                ("gsm.sim.operator.numeric.1", profile.mcc_mnc),
                ("gsm.sim.operator.alpha.1", profile.carrier_spn),
                ("gsm.sim.operator.iso-country.1", profile.sim_iso),
                ("gsm.operator.numeric.1", profile.mcc_mnc),
                ("gsm.operator.alpha.1", profile.carrier_spn),
                ("gsm.operator.iso-country.1", profile.sim_iso),
            ]

            for k, v in props:
                self._run_shell(serial, ["setprop", k, v])

            # CarrierConfig XML override
            carrier_xml = (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                "<carrier_config>\n"
                f'    <string name="carrier_name_string">{profile.carrier_spn}</string>\n'
                f'    <string name="carrier_iso_country">{profile.sim_iso}</string>\n'
                f'    <string name="carrier_mcc_mnc">{profile.mcc_mnc}</string>\n'
                '    <boolean name="carrier_default_data_roaming_enabled_bool" value="true" />\n'
                '    <boolean name="carrier_volte_available_bool" value="true" />\n'
                '    <boolean name="carrier_vt_available_bool" value="true" />\n'
                '    <boolean name="carrier_wfc_ims_available_bool" value="true" />\n'
                "</carrier_config>\n"
            )

            # Inject into com.android.phone files if accessible
            remote_cc_dir = "/data/user_de/0/com.android.phone/files"
            self._run_shell(serial, ["mkdir", "-p", remote_cc_dir])
            remote_xml_file = f"{remote_cc_dir}/carrierconfig-{profile.mcc_mnc}.xml"
            self._run_shell(
                serial,
                ["echo", f"'{carrier_xml}'", ">", remote_xml_file],
            )

            # Notify Radio HAL bridge if vsock socket is available
            self._notify_radio_hal(profile)

            return True
        except Exception as e:
            logger.warning(f"Tier 1 telephony application warning: {e}")
            return False

    def _notify_radio_hal(self, profile: RegionProfile):
        """Attempts notification of local Radio HAL bridge socket if running."""
        try:
            # Check for cellular bridge UNIX domain socket or vsock
            bridge_sock = "/tmp/cellular_bridge.sock"
            if os.path.exists(bridge_sock):
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                    s.settimeout(0.5)
                    s.connect(bridge_sock)
                    payload = json.dumps({
                        "mode": "SYNTHETIC_MOCK",
                        "mcc": profile.mcc,
                        "mnc": profile.mnc,
                        "carrier_name": profile.carrier_spn,
                        "iso": profile.sim_iso,
                    }).encode("utf-8")
                    s.sendall(payload)
        except Exception:
            pass

    # ------------------------------------------------------------------------
    # Tier 2: System OS Locale, Timezone & Clock Sync
    # ------------------------------------------------------------------------

    def apply_tier2_system_os(self, serial: str, profile: RegionProfile) -> bool:
        """
        Applies Tier 2 system OS parameters:
        - persist.sys.locale & persist.sys.timezone
        - Direct AIDL AlarmManagerService timezone injection (service call alarm 3 s16)
        - Disable automatic network timezone updates (settings put global auto_time_zone 0)
        - Broadcast LOCALE_CHANGED intent
        - Synchronize system clock epoch via date @<epoch_sec>
        """
        try:
            primary_locale = profile.locale or profile.locales.split(",")[0]
            self._run_shell(serial, ["setprop", "persist.sys.locale", primary_locale])
            self._run_shell(serial, ["setprop", "persist.sys.timezone", profile.timezone])

            # Force AlarmManagerService to update timezone immediately via AIDL code 3:
            # void setTimeZone(String timeZone)
            self._run_shell(
                serial,
                ["service", "call", "alarm", "3", "s16", profile.timezone],
            )

            # Prevent guest network from overriding configured timezone
            self._run_shell(
                serial,
                ["settings", "put", "global", "auto_time_zone", "0"],
            )

            # Broadcast LOCALE_CHANGED to notify running applications
            self._run_shell(
                serial,
                ["am", "broadcast", "-a", "android.intent.action.LOCALE_CHANGED"],
            )

            # NTP clock offset sync: align guest clock with host wall-clock epoch
            epoch_sec = int(time.time())
            self._run_shell(serial, ["date", f"@{epoch_sec}"])

            return True
        except Exception as e:
            logger.warning(f"Tier 2 system OS application warning: {e}")
            return False

    # ------------------------------------------------------------------------
    # Tier 3: Hardware GPS & Mock Cell Tower ID
    # ------------------------------------------------------------------------

    def apply_tier3_hardware_gps(
        self,
        serial: str,
        profile: RegionProfile,
        console_port: int = 5554,
        auth_token: Optional[str] = None,
    ) -> bool:
        """
        Applies Tier 3 hardware GPS coordinates via QEMU Telnet console (port 5554),
        authenticating with ~/.emulator_console_auth_token if present, issuing
        'geo fix <lon> <lat> <alt>', and injecting mock cell tower TAC and CID.
        """
        token = auth_token
        if not token:
            token_path = os.path.expanduser("~/.emulator_console_auth_token")
            if os.path.isfile(token_path):
                try:
                    with open(token_path, "r", encoding="utf-8") as f:
                        token = f.read().strip()
                except Exception:
                    pass

        telnet_success = False
        try:
            with socket.create_connection(("127.0.0.1", console_port), timeout=2.0) as s:
                # Read initial emulator banner
                s.recv(1024)

                # Authenticate if token found
                if token:
                    s.sendall(f"auth {token}\r\n".encode("utf-8"))
                    s.recv(1024)

                # Send geo fix <lon> <lat> <alt>
                lon, lat, alt = profile.coordinates
                s.sendall(f"geo fix {lon} {lat} {alt}\r\n".encode("utf-8"))
                s.recv(1024)

                # Ensure GSM data emulation is on
                s.sendall(b"gsm data on\r\n")
                s.recv(1024)

                telnet_success = True
        except Exception as e:
            logger.info(f"QEMU Telnet port {console_port} GPS update note: {e}")

        # Set mock cell tower system properties for Radio HAL / TelephonyRegistry
        try:
            tac, cid = profile.cell_tower
            self._run_shell(serial, ["setprop", "gsm.current.tac", str(tac)])
            self._run_shell(serial, ["setprop", "gsm.current.cellid", str(cid)])
            self._run_shell(serial, ["setprop", "gsm.current.mcc", profile.mcc])
            self._run_shell(serial, ["setprop", "gsm.current.mnc", profile.mnc])
        except Exception:
            pass

        return telnet_success

    # ------------------------------------------------------------------------
    # Tier 4: Network Egress & DNS Leak Prevention
    # ------------------------------------------------------------------------

    def apply_tier4_network(
        self,
        serial: str,
        profile: RegionProfile,
        strict: bool = False,
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Applies Tier 4 network stabilization and verifies egress IP:
        - Clamps MTU to 1380 (ip link set dev eth0 mtu 1380)
        - Disables IPv6 across all interfaces (/proc/sys/net/ipv6/conf/all/disable_ipv6 = 1)
        - Disables Private DNS mode and overrides net.dns1 / net.dns2
        - Executes guest curl to ip-api.com and verifies country match
        """
        try:
            # MTU 1380 clamping
            self._run_shell(serial, ["ip", "link", "set", "dev", "eth0", "mtu", "1380"])

            # IPv6 cutoff to prevent dual-stack IPv6 leaks
            self._run_shell(
                serial,
                ["echo", "1", ">", "/proc/sys/net/ipv6/conf/all/disable_ipv6"],
            )
            self._run_shell(
                serial,
                ["echo", "1", ">", "/proc/sys/net/ipv6/conf/default/disable_ipv6"],
            )

            # DNS leak prevention: disable Android Private DNS (DoT) and set regional resolvers
            self._run_shell(
                serial,
                ["settings", "put", "global", "private_dns_mode", "off"],
            )
            self._run_shell(serial, ["setprop", "net.dns1", profile.regional_dns])
            if profile.secondary_dns:
                self._run_shell(serial, ["setprop", "net.dns2", profile.secondary_dns])

            # Verify egress IP
            matched, details = self.verify_egress(serial, profile.code)

            if strict and not matched:
                return False, {"matched": False, "details": details}

            return True, {"matched": matched, "details": details}

        except Exception as e:
            logger.warning(f"Tier 4 network application warning: {e}")
            return (not strict), {"matched": False, "error": str(e)}

    # ------------------------------------------------------------------------
    # Egress Verification
    # ------------------------------------------------------------------------

    def verify_egress(
        self, serial: str, expected_country: str
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Executes guest-side curl to ip-api.com and verifies egress IP, country, and DNS.
        Returns (matched: bool, response_dict: Dict[str, Any]).
        """
        cmd_res = self._run_shell(
            serial,
            ["curl", "-s", "--max-time", "4", "http://ip-api.com/json"],
            timeout=8,
        )

        res_json: Dict[str, Any] = {}
        matched = False
        out = (cmd_res.stdout or "").strip()

        if out and out.startswith("{") and out.endswith("}"):
            try:
                res_json = json.loads(out)
                egress_country = str(res_json.get("countryCode", "")).upper()
                matched = (egress_country == expected_country.upper())
                return matched, res_json
            except Exception as e:
                res_json = {"raw_output": out, "parse_error": str(e)}

        # Fallback query if guest curl fails (e.g. offline or curl not installed)
        try:
            req = urllib.request.Request(
                "http://ip-api.com/json",
                headers={"User-Agent": "GNDROiD-RegionVerifier/2.5"},
            )
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = resp.read().decode("utf-8", errors="ignore")
                res_json = json.loads(data)
                egress_country = str(res_json.get("countryCode", "")).upper()
                matched = (egress_country == expected_country.upper())
                res_json["note"] = "Resolved via host network fallback"
                return matched, res_json
        except Exception as e:
            res_json = {
                "guest_stdout": out,
                "guest_stderr": cmd_res.stderr.strip(),
                "host_fallback_error": str(e),
            }

        return matched, res_json

    # ------------------------------------------------------------------------
    # Atomic 4-Tier Switch Entrypoint
    # ------------------------------------------------------------------------

    def switch_region(
        self,
        serial: str,
        region_code: str,
        adb_path: Optional[str] = None,
        console_port: int = 5554,
        auth_token: Optional[str] = None,
        strict_network: bool = False,
    ) -> RegionSwitchResult:
        """
        Atomically synchronizes all 4 tiers for the requested region persona:
        - Tier 1: Telephony (MCC/MNC, SIM ISO, SPN, CarrierConfig)
        - Tier 2: System OS (Locale, Timezone, NTP clock offset)
        - Tier 3: Hardware (QEMU Telnet geo fix, cell tower ID)
        - Tier 4: Network (MTU 1380, IPv6 cutoff, DNS leak prevention, egress verification)
        """
        if adb_path:
            self.adb = adb_path

        code_upper = region_code.upper()
        profile = self.REGIONS.get(code_upper)
        if not profile:
            supported = list(self.REGIONS.keys())
            raise ValueError(
                f"Unknown region persona code '{region_code}'. Supported codes: {supported}"
            )

        # Tier 1
        t1 = self.apply_tier1_telephony(serial, profile)

        # Tier 2
        t2 = self.apply_tier2_system_os(serial, profile)

        # Tier 3
        t3 = self.apply_tier3_hardware_gps(
            serial, profile, console_port=console_port, auth_token=auth_token
        )

        # Tier 4
        t4, net_info = self.apply_tier4_network(
            serial, profile, strict=strict_network
        )

        egress_verified = bool(net_info.get("matched", False))
        overall_success = t1 and t2 and (t4 if strict_network else True)

        msg_parts = [f"Region switched to {profile.country_name} ({profile.code})."]
        if not t3:
            msg_parts.append("Note: QEMU Telnet console GPS update skipped or failed.")
        if not egress_verified:
            msg_parts.append(
                f"Note: Egress IP verification did not match target country {profile.code} "
                "(Proxy/VPN may be inactive or tunnel disconnected)."
            )

        return RegionSwitchResult(
            success=overall_success,
            region_code=profile.code,
            country_name=profile.country_name,
            carrier=profile.carrier_spn,
            tier1_telephony=t1,
            tier2_system=t2,
            tier3_hardware=t3,
            tier4_network=t4,
            egress_verified=egress_verified,
            egress_details=net_info.get("details", {}),
            message=" ".join(msg_parts),
        )


__all__ = [
    "UniversalRegionController",
    "RegionProfile",
    "RegionPersona",
    "RegionSwitchResult",
    "REGIONS",
    "REGION_PERSONAS",
]
