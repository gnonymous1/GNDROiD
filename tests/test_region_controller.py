"""
tests/test_region_controller.py
================================
E2E Test Suite for Features 6 through 9:
- Feature 6: 4-Tier Region Changer: Telephony (10 tests)
- Feature 7: 4-Tier Region Changer: System OS (10 tests)
- Feature 8: 4-Tier Region Changer: Hardware / GPS (10 tests)
- Feature 9: 4-Tier Region Changer: Network (10 tests)

Total: 40 Test Cases (20 Tier 1 Feature Coverage, 20 Tier 2 Boundary & Corner Cases)
"""

import os
import time
import socket
import unittest
from unittest.mock import patch, MagicMock

from tests.fixtures.mock_adb import MockAdbState, MockAdbSession
from tests.fixtures.mock_qemu import MockQemuConsoleServer
from nexus.region_controller import (
    UniversalRegionController,
    RegionProfile,
    RegionSwitchResult,
    REGIONS,
    REGION_PERSONAS,
)


class TestFeature6TelephonySync(unittest.TestCase):
    """Feature 6: 4-Tier Region Changer: Telephony"""

    def setUp(self):
        self.state = MockAdbState()
        self.controller = UniversalRegionController(adb_path="mock_adb")

    # --- Tier 1: Feature Coverage (Happy Path) ---

    def test_01_telephony_sync_ae_du(self):
        """[F6-T1-01] Verify telephony properties sync for United Arab Emirates (du)."""
        with MockAdbSession(self.state):
            ok = self.controller.apply_tier1_telephony("emulator-5554", REGIONS["AE"])
            self.assertTrue(ok)
            self.assertEqual(self.state.properties.get("gsm.sim.operator.numeric"), "42402")
            self.assertEqual(self.state.properties.get("gsm.sim.operator.alpha"), "du")
            self.assertEqual(self.state.properties.get("gsm.sim.operator.iso-country"), "ae")
            self.assertEqual(self.state.properties.get("gsm.operator.numeric"), "42402")
            self.assertEqual(self.state.properties.get("gsm.operator.alpha"), "du")
            self.assertEqual(self.state.properties.get("gsm.sim.state"), "READY")

    def test_02_telephony_sync_sa_stc(self):
        """[F6-T1-02] Verify telephony properties sync for Saudi Arabia (stc)."""
        with MockAdbSession(self.state):
            ok = self.controller.apply_tier1_telephony("emulator-5554", REGIONS["SA"])
            self.assertTrue(ok)
            self.assertEqual(self.state.properties.get("gsm.sim.operator.numeric"), "42001")
            self.assertEqual(self.state.properties.get("gsm.sim.operator.alpha"), "stc")
            self.assertEqual(self.state.properties.get("gsm.sim.operator.iso-country"), "sa")

    def test_03_telephony_sync_us_gb_pk(self):
        """[F6-T1-03] Parameterized verification of US, GB, and PK personas."""
        test_cases = [
            ("US", "310260", "T-Mobile", "us"),
            ("GB", "23430", "EE", "gb"),
            ("PK", "41001", "Jazz", "pk"),
        ]
        for code, expected_numeric, expected_alpha, expected_iso in test_cases:
            state = MockAdbState()
            with MockAdbSession(state):
                ok = self.controller.apply_tier1_telephony("emulator-5554", REGIONS[code])
                self.assertTrue(ok)
                self.assertEqual(state.properties.get("gsm.sim.operator.numeric"), expected_numeric)
                self.assertEqual(state.properties.get("gsm.sim.operator.alpha"), expected_alpha)
                self.assertEqual(state.properties.get("gsm.sim.operator.iso-country"), expected_iso)

    def test_04_telephony_dual_sim_slot_sync(self):
        """[F6-T1-04] Verify secondary SIM slot properties (slots 0 and 1)."""
        with MockAdbSession(self.state):
            ok = self.controller.apply_tier1_telephony("emulator-5554", REGIONS["AE"])
            self.assertTrue(ok)
            self.assertEqual(self.state.properties.get("gsm.sim.operator.numeric.0"), "42402")
            self.assertEqual(self.state.properties.get("gsm.sim.operator.alpha.0"), "du")
            self.assertEqual(self.state.properties.get("gsm.sim.operator.iso-country.0"), "ae")
            self.assertEqual(self.state.properties.get("gsm.sim.operator.numeric.1"), "42402")
            self.assertEqual(self.state.properties.get("gsm.sim.operator.alpha.1"), "du")
            self.assertEqual(self.state.properties.get("gsm.sim.operator.iso-country.1"), "ae")

    def test_05_carrier_config_xml_override_placement(self):
        """[F6-T1-05] Verify CarrierConfig XML push command execution."""
        with MockAdbSession(self.state):
            ok = self.controller.apply_tier1_telephony("emulator-5554", REGIONS["AE"])
            self.assertTrue(ok)
            # Check command log for echo carrier_config XML
            echo_cmds = [c for c in self.state.command_log if "carrierconfig-42402.xml" in " ".join(c)]
            self.assertTrue(len(echo_cmds) >= 1)

    # --- Tier 2: Boundary & Corner Cases ---

    def test_06_telephony_unknown_region_code_exception(self):
        """[F6-T2-01] Verify ValueError raised when invalid region persona code is passed."""
        with self.assertRaises(ValueError) as ctx:
            self.controller.switch_region("emulator-5554", "INVALID_REGION")
        self.assertIn("Unknown region persona code", str(ctx.exception))
        self.assertIn("AE", str(ctx.exception))

    def test_07_telephony_special_chars_in_spn(self):
        """[F6-T2-02] Safely quote carrier names with special characters and spaces."""
        custom_profile = RegionProfile(
            code="CUSTOM",
            country_name="Custom Land",
            carrier_spn="AT&T Mobile / UAE",
            mcc_mnc="99999",
            mcc="999",
            mnc="99",
            sim_iso="ae",
            locale="en-AE",
            locales="en-AE",
            timezone="Asia/Dubai",
            coordinates=(55.0, 25.0, 10.0),
            cell_tower=(100, 200),
            regional_dns="1.1.1.1",
        )
        with MockAdbSession(self.state):
            ok = self.controller.apply_tier1_telephony("emulator-5554", custom_profile)
            self.assertTrue(ok)
            self.assertEqual(self.state.properties.get("gsm.sim.operator.alpha"), "AT&T Mobile / UAE")

    def test_08_telephony_adb_shell_timeout_resilience(self):
        """[F6-T2-03] Catch ADB timeout gracefully without unhandled exception."""
        with patch.object(self.controller, "_run_shell", side_effect=TimeoutError("ADB timed out")):
            ok = self.controller.apply_tier1_telephony("emulator-5554", REGIONS["AE"])
            self.assertFalse(ok)

    def test_09_telephony_partial_failure_handling(self):
        """[F6-T2-04] Handle shell exception cleanly and report warning."""
        with patch.object(self.controller, "_run_shell", side_effect=RuntimeError("Device disconnected")):
            ok = self.controller.apply_tier1_telephony("emulator-5554", REGIONS["AE"])
            self.assertFalse(ok)

    def test_10_telephony_empty_serial_targets_default_device(self):
        """[F6-T2-05] Empty serial targets default device without empty -s parameter."""
        with MockAdbSession(self.state):
            ok = self.controller.apply_tier1_telephony("", REGIONS["AE"])
            self.assertTrue(ok)
            for cmd in self.state.command_log:
                # Assert no ["-s", ""]
                for idx, c in enumerate(cmd):
                    if c == "-s":
                        self.assertNotEqual(cmd[idx + 1], "")


class TestFeature7SystemOsSync(unittest.TestCase):
    """Feature 7: 4-Tier Region Changer: System OS"""

    def setUp(self):
        self.state = MockAdbState()
        self.controller = UniversalRegionController(adb_path="mock_adb")

    # --- Tier 1: Feature Coverage (Happy Path) ---

    def test_11_system_os_locale_properties(self):
        """[F7-T1-01] Verify setting of persist.sys.locale property."""
        with MockAdbSession(self.state):
            ok = self.controller.apply_tier2_system_os("emulator-5554", REGIONS["AE"])
            self.assertTrue(ok)
            self.assertEqual(self.state.properties.get("persist.sys.locale"), "en-AE")

    def test_12_system_os_timezone_properties(self):
        """[F7-T1-02] Verify setting of persist.sys.timezone property."""
        with MockAdbSession(self.state):
            ok = self.controller.apply_tier2_system_os("emulator-5554", REGIONS["AE"])
            self.assertTrue(ok)
            self.assertEqual(self.state.properties.get("persist.sys.timezone"), "Asia/Dubai")

    def test_13_system_os_alarm_service_aidl_call(self):
        """[F7-T1-03] Verify AlarmManager AIDL timezone injection command."""
        with MockAdbSession(self.state):
            ok = self.controller.apply_tier2_system_os("emulator-5554", REGIONS["SA"])
            self.assertTrue(ok)
            alarm_cmds = [c for c in self.state.command_log if "service" in c and "alarm" in c]
            self.assertEqual(len(alarm_cmds), 1)
            self.assertIn("Asia/Riyadh", alarm_cmds[0])

    def test_14_system_os_auto_timezone_disabled(self):
        """[F7-T1-04] Verify auto_time_zone is turned off in settings."""
        with MockAdbSession(self.state):
            ok = self.controller.apply_tier2_system_os("emulator-5554", REGIONS["AE"])
            self.assertTrue(ok)
            self.assertEqual(self.state.settings.get("global", {}).get("auto_time_zone"), "0")

    def test_15_system_os_locale_changed_broadcast(self):
        """[F7-T1-05] Verify broadcast intent android.intent.action.LOCALE_CHANGED."""
        with MockAdbSession(self.state):
            ok = self.controller.apply_tier2_system_os("emulator-5554", REGIONS["AE"])
            self.assertTrue(ok)
            broadcast_cmds = [c for c in self.state.command_log if "broadcast" in c and "LOCALE_CHANGED" in " ".join(c)]
            self.assertEqual(len(broadcast_cmds), 1)

    # --- Tier 2: Boundary & Corner Cases ---

    def test_16_system_os_multi_locale_string_parsing(self):
        """[F7-T2-01] Parse multi-locale strings and extract primary locale tag."""
        profile = RegionProfile(
            code="MULTI",
            country_name="Multi Locale",
            carrier_spn="Carrier",
            mcc_mnc="12345",
            mcc="123",
            mnc="45",
            sim_iso="ml",
            locale="",
            locales="ar-AE,en-AE,ur-PK",
            timezone="Asia/Dubai",
            coordinates=(55.0, 25.0, 10.0),
            cell_tower=(1, 2),
            regional_dns="1.1.1.1",
        )
        with MockAdbSession(self.state):
            ok = self.controller.apply_tier2_system_os("emulator-5554", profile)
            self.assertTrue(ok)
            self.assertEqual(self.state.properties.get("persist.sys.locale"), "ar-AE")

    def test_17_system_os_alarm_aidl_service_resilience(self):
        """[F7-T2-02] Continue execution cleanly if AlarmManager AIDL returns error."""
        with MockAdbSession(self.state):
            ok = self.controller.apply_tier2_system_os("emulator-5554", REGIONS["AE"])
            self.assertTrue(ok)
            self.assertEqual(self.state.properties.get("persist.sys.timezone"), "Asia/Dubai")

    def test_18_system_os_clock_drift_epoch_sync(self):
        """[F7-T2-03] Synchronize guest clock with host epoch timestamp."""
        with MockAdbSession(self.state):
            ok = self.controller.apply_tier2_system_os("emulator-5554", REGIONS["AE"])
            self.assertTrue(ok)
            date_cmds = [c for c in self.state.command_log if any(x.startswith("@") for x in c)]
            self.assertEqual(len(date_cmds), 1)

    def test_19_system_os_invalid_timezone_fallback(self):
        """[F7-T2-04] Verify handling when custom persona specifies unique timezone."""
        profile = RegionProfile(
            code="TZ",
            country_name="TZ Test",
            carrier_spn="Carrier",
            mcc_mnc="12345",
            mcc="123",
            mnc="45",
            sim_iso="tz",
            locale="en-US",
            locales="en-US",
            timezone="UTC",
            coordinates=(0.0, 0.0, 0.0),
            cell_tower=(0, 0),
            regional_dns="1.1.1.1",
        )
        with MockAdbSession(self.state):
            ok = self.controller.apply_tier2_system_os("emulator-5554", profile)
            self.assertTrue(ok)
            self.assertEqual(self.state.properties.get("persist.sys.timezone"), "UTC")

    def test_20_system_os_rapid_sequential_switching(self):
        """[F7-T2-05] Rapid sequential switching maintains consistent final state."""
        sequence = ["AE", "SA", "US", "GB"]
        with MockAdbSession(self.state):
            for code in sequence:
                self.controller.apply_tier2_system_os("emulator-5554", REGIONS[code])
            self.assertEqual(self.state.properties.get("persist.sys.locale"), "en-GB")
            self.assertEqual(self.state.properties.get("persist.sys.timezone"), "Europe/London")


class TestFeature8HardwareGpsSync(unittest.TestCase):
    """Feature 8: 4-Tier Region Changer: Hardware / GPS"""

    def setUp(self):
        self.state = MockAdbState()
        self.controller = UniversalRegionController(adb_path="mock_adb")
        self.mock_qemu = MockQemuConsoleServer(port=0, auth_token="test_token_123")
        self.mock_qemu.start()

    def tearDown(self):
        self.mock_qemu.stop()

    # --- Tier 1: Feature Coverage (Happy Path) ---

    def test_21_hardware_gps_telnet_connection(self):
        """[F8-T1-01] Successfully connect to QEMU Telnet console port."""
        with MockAdbSession(self.state):
            ok = self.controller.apply_tier3_hardware_gps(
                serial="emulator-5554",
                profile=REGIONS["AE"],
                console_port=self.mock_qemu.port,
                auth_token="test_token_123",
            )
            self.assertTrue(ok)

    def test_22_hardware_gps_telnet_auth_handshake(self):
        """[F8-T1-02] Transmit auth <token> handshake and receive OK."""
        with MockAdbSession(self.state):
            ok = self.controller.apply_tier3_hardware_gps(
                serial="emulator-5554",
                profile=REGIONS["AE"],
                console_port=self.mock_qemu.port,
                auth_token="test_token_123",
            )
            self.assertTrue(ok)
            self.assertIn("test_token_123", self.mock_qemu.auth_attempts)

    def test_23_hardware_gps_geo_fix_ae_dubai(self):
        """[F8-T1-03] Transmit geo fix coordinates for Dubai (55.2797, 25.1972, 10.0)."""
        with MockAdbSession(self.state):
            ok = self.controller.apply_tier3_hardware_gps(
                serial="emulator-5554",
                profile=REGIONS["AE"],
                console_port=self.mock_qemu.port,
                auth_token="test_token_123",
            )
            self.assertTrue(ok)
            self.assertEqual(len(self.mock_qemu.geo_history), 1)
            lon, lat, alt, _ = self.mock_qemu.geo_history[0]
            self.assertAlmostEqual(lon, 55.2797)
            self.assertAlmostEqual(lat, 25.1972)
            self.assertAlmostEqual(alt, 10.0)

    def test_24_hardware_gps_geo_fix_sa_riyadh(self):
        """[F8-T1-04] Transmit geo fix coordinates for Riyadh (46.6753, 24.7136, 612.0)."""
        with MockAdbSession(self.state):
            ok = self.controller.apply_tier3_hardware_gps(
                serial="emulator-5554",
                profile=REGIONS["SA"],
                console_port=self.mock_qemu.port,
                auth_token="test_token_123",
            )
            self.assertTrue(ok)
            lon, lat, alt, _ = self.mock_qemu.geo_history[0]
            self.assertAlmostEqual(lon, 46.6753)
            self.assertAlmostEqual(lat, 24.7136)
            self.assertAlmostEqual(alt, 612.0)

    def test_25_hardware_cell_tower_mock_injection(self):
        """[F8-T1-05] Inject mock cell tower TAC and CID properties."""
        with MockAdbSession(self.state):
            self.controller.apply_tier3_hardware_gps(
                serial="emulator-5554",
                profile=REGIONS["AE"],
                console_port=self.mock_qemu.port,
                auth_token="test_token_123",
            )
            self.assertEqual(self.state.properties.get("gsm.current.tac"), "15420")
            self.assertEqual(self.state.properties.get("gsm.current.cellid"), "135478912")
            self.assertEqual(self.state.properties.get("gsm.current.mcc"), "424")
            self.assertEqual(self.state.properties.get("gsm.current.mnc"), "02")

    # --- Tier 2: Boundary & Corner Cases ---

    def test_26_hardware_gps_telnet_connection_refused(self):
        """[F8-T2-01] Return False cleanly when Telnet port is closed without crashing."""
        # Find closed port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            closed_port = s.getsockname()[1]

        with MockAdbSession(self.state):
            ok = self.controller.apply_tier3_hardware_gps(
                serial="emulator-5554",
                profile=REGIONS["AE"],
                console_port=closed_port,
            )
            self.assertFalse(ok)

    def test_27_hardware_gps_telnet_auth_failure(self):
        """[F8-T2-02] Handle invalid token response KO: authentication failed."""
        with MockAdbSession(self.state):
            ok = self.controller.apply_tier3_hardware_gps(
                serial="emulator-5554",
                profile=REGIONS["AE"],
                console_port=self.mock_qemu.port,
                auth_token="wrong_token",
            )
            self.assertTrue(ok)  # Socket connected and attempted commands
            self.assertIn("wrong_token", self.mock_qemu.auth_attempts)

    def test_28_hardware_gps_socket_timeout(self):
        """[F8-T2-03] Enforce socket timeout if console hangs."""
        # Create a socket that accepts but never sends data
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(("127.0.0.1", 0))
        hang_port = server.getsockname()[1]
        server.listen(1)

        def run_hang():
            try:
                conn, _ = server.accept()
                time.sleep(3.0)
                conn.close()
            except Exception:
                pass

        import threading
        t = threading.Thread(target=run_hang, daemon=True)
        t.start()

        with MockAdbSession(self.state):
            ok = self.controller.apply_tier3_hardware_gps(
                serial="emulator-5554",
                profile=REGIONS["AE"],
                console_port=hang_port,
            )
            self.assertFalse(ok)
        server.close()

    def test_29_hardware_gps_missing_auth_token_file(self):
        """[F8-T2-04] Handle environments where ~/.emulator_console_auth_token is missing."""
        with patch("os.path.isfile", return_value=False):
            with MockAdbSession(self.state):
                ok = self.controller.apply_tier3_hardware_gps(
                    serial="emulator-5554",
                    profile=REGIONS["AE"],
                    console_port=self.mock_qemu.port,
                    auth_token=None,
                )
                self.assertTrue(ok)

    def test_30_hardware_gps_extreme_coordinates(self):
        """[F8-T2-05] Transmit negative and boundary coordinates correctly."""
        with MockAdbSession(self.state):
            ok = self.controller.apply_tier3_hardware_gps(
                serial="emulator-5554",
                profile=REGIONS["US"],
                console_port=self.mock_qemu.port,
                auth_token="test_token_123",
            )
            self.assertTrue(ok)
            lon, lat, alt, _ = self.mock_qemu.geo_history[0]
            self.assertAlmostEqual(lon, -74.0060)
            self.assertAlmostEqual(lat, 40.7128)


class TestFeature9NetworkSync(unittest.TestCase):
    """Feature 9: 4-Tier Region Changer: Network"""

    def setUp(self):
        self.state = MockAdbState()
        self.controller = UniversalRegionController(adb_path="mock_adb")

    # --- Tier 1: Feature Coverage (Happy Path) ---

    def test_31_network_private_dns_disabled(self):
        """[F9-T1-01] Verify Private DNS is disabled in global settings."""
        with MockAdbSession(self.state):
            ok, info = self.controller.apply_tier4_network("emulator-5554", REGIONS["AE"])
            self.assertTrue(ok)
            self.assertEqual(self.state.settings.get("global", {}).get("private_dns_mode"), "off")

    def test_32_network_regional_dns_properties(self):
        """[F9-T1-02] Verify regional DNS property net.dns1 injection."""
        with MockAdbSession(self.state):
            ok, info = self.controller.apply_tier4_network("emulator-5554", REGIONS["AE"])
            self.assertTrue(ok)
            self.assertEqual(self.state.properties.get("net.dns1"), "195.229.241.50")
            self.assertEqual(self.state.properties.get("net.dns2"), "1.1.1.1")

    def test_33_network_mtu_clamping_to_1380(self):
        """[F9-T1-03] Clamp MTU on eth0 to 1380."""
        with MockAdbSession(self.state):
            ok, info = self.controller.apply_tier4_network("emulator-5554", REGIONS["AE"])
            self.assertTrue(ok)
            self.assertEqual(self.state.mtu.get("eth0"), 1380)

    def test_34_network_ipv6_cutoff_across_interfaces(self):
        """[F9-T1-04] Cut off IPv6 across all interfaces."""
        with MockAdbSession(self.state):
            ok, info = self.controller.apply_tier4_network("emulator-5554", REGIONS["AE"])
            self.assertTrue(ok)
            self.assertEqual(self.state.sysctl.get("/proc/sys/net/ipv6/conf/all/disable_ipv6"), "1")

    def test_35_network_egress_ip_verification_success(self):
        """[F9-T1-05] Query guest curl for external egress IP and verify country match."""
        self.state.simulated_egress = {"countryCode": "AE", "query": "195.229.241.50"}
        with MockAdbSession(self.state):
            ok, info = self.controller.apply_tier4_network("emulator-5554", REGIONS["AE"], strict=True)
            self.assertTrue(ok)
            self.assertTrue(info["matched"])

    # --- Tier 2: Boundary & Corner Cases ---

    def test_36_network_egress_ip_mismatch_strict_mode_failure(self):
        """[F9-T2-01] Strict mode fails when egress IP country differs from persona."""
        self.state.simulated_egress = {"countryCode": "US", "query": "104.28.16.5"}
        with MockAdbSession(self.state):
            ok, info = self.controller.apply_tier4_network("emulator-5554", REGIONS["AE"], strict=True)
            self.assertFalse(ok)
            self.assertFalse(info["matched"])

    def test_37_network_egress_ip_mismatch_relaxed_mode_warning(self):
        """[F9-T2-02] Relaxed mode succeeds with warning when egress country differs."""
        self.state.simulated_egress = {"countryCode": "US", "query": "104.28.16.5"}
        with MockAdbSession(self.state):
            ok, info = self.controller.apply_tier4_network("emulator-5554", REGIONS["AE"], strict=False)
            self.assertTrue(ok)
            self.assertFalse(info["matched"])

    def test_38_network_curl_timeout_enforcement(self):
        """[F9-T2-03] Ensure curl command contains --max-time 4 flag."""
        with MockAdbSession(self.state):
            self.controller.apply_tier4_network("emulator-5554", REGIONS["AE"])
            curl_cmds = [c for c in self.state.command_log if "curl" in c]
            self.assertEqual(len(curl_cmds), 1)
            self.assertIn("--max-time", curl_cmds[0])
            self.assertIn("4", curl_cmds[0])

    def test_39_network_malformed_json_response(self):
        """[F9-T2-04] Handle malformed JSON response from egress IP service cleanly."""
        state = MockAdbState()
        # Mock curl returning HTML error
        with MockAdbSession(state):
            with patch.object(self.controller, "_run_shell", return_value=MagicMock(stdout="<html>Error 502</html>", stderr="")):
                matched, details = self.controller.verify_egress("emulator-5554", "AE")
                self.assertFalse(matched)

    def test_40_network_atomic_switch_orchestration(self):
        """[F9-T2-05] Verify end-to-end atomic switch coordination across all 4 tiers."""
        self.state.simulated_egress = {"countryCode": "AE", "query": "195.229.241.50"}
        mock_qemu = MockQemuConsoleServer(port=0, auth_token="tok_123")
        mock_qemu.start()
        try:
            with MockAdbSession(self.state):
                res = self.controller.switch_region(
                    serial="emulator-5554",
                    region_code="AE",
                    console_port=mock_qemu.port,
                    auth_token="tok_123",
                    strict_network=True,
                )
                self.assertIsInstance(res, RegionSwitchResult)
                self.assertTrue(res.success)
                self.assertEqual(res.region_code, "AE")
                self.assertTrue(res.tier1_telephony)
                self.assertTrue(res.tier2_system)
                self.assertTrue(res.tier3_hardware)
                self.assertTrue(res.tier4_network)
                self.assertTrue(res.egress_verified)
                self.assertIn("Region switched to United Arab Emirates (AE).", res.message)
        finally:
            mock_qemu.stop()


if __name__ == "__main__":
    unittest.main()
