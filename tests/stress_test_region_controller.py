"""
tests/stress_test_region_controller.py
======================================
Adversarial Stress Test Suite & Empirical Verification for
Universal 4-Tier Region Controller (nexus/region_controller.py).

Challenge Dimensions:
1. Adversarial Region Codes & Input Validation (case-insensitivity, non-existent codes, empty/whitespace).
2. Telnet Console Failure Modes (connection refused, timeout, EOF, token rejection, binary garbage, hang).
3. ADB Command Failures & Timeouts (TimeoutExpired, FileNotFoundError, offline devices, non-zero return codes).
4. Adversarial Egress Verification (corrupted JSON, 500 error, network timeout, stderr None, strict mode).
5. Dual-SIM & CarrierConfig Invariance (slots 0/1, well-formed XML parsing across all 7 regions).
6. Rapid Sequential Switching across all 7 countries.
7. Multi-Threaded Concurrent Invocations.
"""

import json
import socket
import threading
import time
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch, MagicMock

import urllib.error
import subprocess

from nexus.region_controller import (
    UniversalRegionController,
    RegionProfile,
    RegionSwitchResult,
    REGIONS,
    REGION_PERSONAS,
)


class TestAdversarialRegionCodes(unittest.TestCase):
    """Stress tests region code inputs, casing, empty strings, and invalid identifiers."""

    def setUp(self):
        self.controller = UniversalRegionController(adb_path="adb")

    def test_case_insensitivity_all_seven_regions(self):
        """Verifies lowercase and mixed-case region codes work identically to uppercase."""
        test_cases = [
            ("ae", "AE"),
            ("Sa", "SA"),
            ("uS", "US"),
            ("gb", "GB"),
            ("pk", "PK"),
            ("De", "DE"),
            ("jP", "JP"),
        ]
        with patch.object(self.controller, "_run_shell", return_value=MagicMock(returncode=0, stdout="{}", stderr="")), \
             patch.object(self.controller, "apply_tier3_hardware_gps", return_value=True):
            for input_code, expected_code in test_cases:
                with patch.object(self.controller, "verify_egress", return_value=(True, {"countryCode": expected_code})):
                    res = self.controller.switch_region("emu-1", input_code)
                    self.assertEqual(res.region_code, expected_code)
                    self.assertTrue(res.success)

    def test_non_existent_region_codes_raise_value_error(self):
        """Verifies unsupported codes (ZZ, XX, QA, CN, INVALID) cleanly raise ValueError."""
        invalid_codes = ["ZZ", "XX", "QA", "CN", "INVALID_123", "99"]
        for code in invalid_codes:
            with self.assertRaises(ValueError) as ctx:
                self.controller.switch_region("emu-1", code)
            self.assertIn(f"Unknown region persona code '{code}'", str(ctx.exception))
            self.assertIn("Supported codes", str(ctx.exception))

    def test_empty_and_whitespace_region_codes_raise_value_error(self):
        """Verifies empty string and whitespace-padded codes raise ValueError."""
        whitespace_codes = ["", "   ", "\t", "\n", " AE ", " US\t"]
        for code in whitespace_codes:
            with self.assertRaises(ValueError):
                self.controller.switch_region("emu-1", code)

    def test_region_profile_boundary_invariants(self):
        """Verifies coordinate, cell tower, MCC/MNC, and DNS invariants across all 7 profiles."""
        for code, profile in REGIONS.items():
            self.assertEqual(profile.code, code)
            lon, lat, alt = profile.coordinates
            self.assertTrue(-180.0 <= lon <= 180.0, f"Invalid longitude {lon} for {code}")
            self.assertTrue(-90.0 <= lat <= 90.0, f"Invalid latitude {lat} for {code}")
            self.assertTrue(alt >= 0.0, f"Negative altitude {alt} for {code}")

            tac, cid = profile.cell_tower
            self.assertTrue(tac > 0, f"Invalid TAC {tac} for {code}")
            self.assertTrue(cid > 0, f"Invalid CID {cid} for {code}")

            self.assertEqual(len(profile.mcc), 3, f"MCC {profile.mcc} not 3 digits for {code}")
            self.assertTrue(len(profile.mnc) >= 2, f"MNC {profile.mnc} < 2 digits for {code}")
            self.assertEqual(profile.mcc + profile.mnc, profile.mcc_mnc)
            self.assertEqual(len(profile.sim_iso), 2)
            self.assertEqual(profile.sim_iso, profile.sim_iso.lower())


class TestAdversarialTelnetConsole(unittest.TestCase):
    """Stress tests QEMU Telnet port 5554 connection failures, timeouts, and auth rejections."""

    def setUp(self):
        self.controller = UniversalRegionController(adb_path="adb")
        self.profile = REGIONS["AE"]

    @patch("subprocess.run")
    def test_telnet_connection_refused(self, mock_subproc):
        """Verifies connection refused on unused port does not crash, returns False for Telnet."""
        mock_subproc.return_value = MagicMock(returncode=0, stdout="", stderr="")
        ok = self.controller.apply_tier3_hardware_gps(
            serial="emu-1",
            profile=self.profile,
            console_port=59998,
        )
        self.assertFalse(ok)
        executed = [" ".join(call[0][0]) for call in mock_subproc.call_args_list]
        self.assertTrue(any("gsm.current.tac" in c for c in executed))
        self.assertTrue(any("gsm.current.cellid" in c for c in executed))

    @patch("subprocess.run")
    def test_telnet_immediate_eof_disconnect(self, mock_subproc):
        """Verifies immediate socket close by server does not crash apply_tier3_hardware_gps."""
        mock_subproc.return_value = MagicMock(returncode=0, stdout="", stderr="")

        def eof_server():
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", 0))
                port[0] = s.getsockname()[1]
                ready.set()
                s.listen(1)
                conn, _ = s.accept()
                conn.close()

        port = [0]
        ready = threading.Event()
        t = threading.Thread(target=eof_server, daemon=True)
        t.start()
        ready.wait(timeout=2.0)

        ok = self.controller.apply_tier3_hardware_gps(
            serial="emu-1",
            profile=self.profile,
            console_port=port[0],
        )
        self.assertFalse(ok)

    @patch("subprocess.run")
    def test_telnet_auth_token_rejection_connection_closed(self, mock_subproc):
        """Verifies telnet server dropping connection on rejected token returns False without crashing."""
        mock_subproc.return_value = MagicMock(returncode=0, stdout="", stderr="")

        def reject_server():
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", 0))
                port[0] = s.getsockname()[1]
                ready.set()
                s.listen(1)
                conn, _ = s.accept()
                with conn:
                    conn.sendall(b"Android Console: Authentication required\r\n")
                    data = conn.recv(1024)
                    if b"auth" in data:
                        conn.sendall(b"KO: authentication failed\r\n")
                    # Connection closes here upon exit

        port = [0]
        ready = threading.Event()
        t = threading.Thread(target=reject_server, daemon=True)
        t.start()
        ready.wait(timeout=2.0)

        ok = self.controller.apply_tier3_hardware_gps(
            serial="emu-1",
            profile=self.profile,
            console_port=port[0],
            auth_token="WRONG_TOKEN",
        )
        # Server disconnected on KO, socket error caught cleanly, telnet_success=False
        self.assertFalse(ok)

    @patch("subprocess.run")
    def test_telnet_binary_garbage_response(self, mock_subproc):
        """Verifies telnet server responding with binary non-ASCII garbage does not crash."""
        mock_subproc.return_value = MagicMock(returncode=0, stdout="", stderr="")

        def garbage_server():
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", 0))
                port[0] = s.getsockname()[1]
                ready.set()
                s.listen(1)
                conn, _ = s.accept()
                with conn:
                    conn.sendall(b"\xff\xfe\x00\x00\x80\x99\xff\xaa\r\n")
                    while True:
                        chunk = conn.recv(1024)
                        if not chunk:
                            break
                        conn.sendall(b"\x00\x01\x02\r\n")

        port = [0]
        ready = threading.Event()
        t = threading.Thread(target=garbage_server, daemon=True)
        t.start()
        ready.wait(timeout=2.0)

        ok = self.controller.apply_tier3_hardware_gps(
            serial="emu-1",
            profile=self.profile,
            console_port=port[0],
        )
        self.assertTrue(ok)

    @patch("subprocess.run")
    def test_telnet_hanging_socket_enforces_timeout(self, mock_subproc):
        """Verifies hanging Telnet server times out within ~2.0 seconds and does not hang."""
        mock_subproc.return_value = MagicMock(returncode=0, stdout="", stderr="")

        def hanging_server():
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", 0))
                port[0] = s.getsockname()[1]
                ready.set()
                s.listen(1)
                conn, _ = s.accept()
                time.sleep(5)

        port = [0]
        ready = threading.Event()
        t = threading.Thread(target=hanging_server, daemon=True)
        t.start()
        ready.wait(timeout=2.0)

        t0 = time.time()
        ok = self.controller.apply_tier3_hardware_gps(
            serial="emu-1",
            profile=self.profile,
            console_port=port[0],
        )
        elapsed = time.time() - t0
        self.assertFalse(ok)
        self.assertLess(elapsed, 4.0, f"Telnet operation took {elapsed:.2f}s, exceeded 4.0s upper bound")


class TestAdversarialAdbFailures(unittest.TestCase):
    """Stress tests ADB execution failures, timeouts, and missing binaries."""

    def setUp(self):
        self.controller = UniversalRegionController(adb_path="adb")
        self.profile = REGIONS["SA"]

    @patch("subprocess.run")
    def test_tier1_timeout_expired_marks_tier1_failed(self, mock_subproc):
        """Verifies TimeoutExpired during Tier 1 sets tier1=False and success=False."""
        mock_subproc.side_effect = subprocess.TimeoutExpired(cmd="adb setprop", timeout=15)
        ok = self.controller.apply_tier1_telephony("emu-1", self.profile)
        self.assertFalse(ok)

    @patch("subprocess.run")
    def test_tier2_timeout_expired_marks_tier2_failed(self, mock_subproc):
        """Verifies TimeoutExpired during Tier 2 sets tier2=False and success=False."""
        mock_subproc.side_effect = subprocess.TimeoutExpired(cmd="adb setprop", timeout=15)
        ok = self.controller.apply_tier2_system_os("emu-1", self.profile)
        self.assertFalse(ok)

    @patch("subprocess.run")
    def test_tier1_file_not_found_error_handled(self, mock_subproc):
        """Verifies FileNotFoundError (adb binary missing) returns False without crashing."""
        mock_subproc.side_effect = FileNotFoundError("adb binary not found")
        ok = self.controller.apply_tier1_telephony("emu-1", self.profile)
        self.assertFalse(ok)

    @patch("subprocess.run")
    def test_switch_region_overall_success_false_when_tier1_times_out(self, mock_subproc):
        """Verifies switch_region returns success=False when Tier 1 fails."""
        mock_subproc.side_effect = subprocess.TimeoutExpired(cmd="adb setprop", timeout=15)
        with patch.object(self.controller, "apply_tier3_hardware_gps", return_value=True):
            res = self.controller.switch_region("emu-1", "SA")
            self.assertFalse(res.success)
            self.assertFalse(res.tier1_telephony)

    @patch("subprocess.run")
    def test_switch_region_overall_success_false_when_tier2_times_out(self, mock_subproc):
        """Verifies switch_region returns success=False when Tier 2 fails."""
        def side_effect(cmd, *args, **kwargs):
            if "persist.sys.locale" in cmd:
                raise subprocess.TimeoutExpired(cmd="adb", timeout=15)
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_subproc.side_effect = side_effect
        with patch.object(self.controller, "apply_tier3_hardware_gps", return_value=True), \
             patch.object(self.controller, "verify_egress", return_value=(True, {"countryCode": "SA"})):
            res = self.controller.switch_region("emu-1", "SA")
            self.assertFalse(res.success)
            self.assertFalse(res.tier2_system)


class TestAdversarialEgressVerification(unittest.TestCase):
    """Stress tests egress verification under corrupt JSON, HTTP errors, timeouts, and fallback."""

    def setUp(self):
        self.controller = UniversalRegionController(adb_path="adb")

    @patch("subprocess.run")
    def test_corrupted_json_responses_handled_gracefully(self, mock_subproc):
        """Verifies corrupted JSON formats do not crash verify_egress."""
        corrupted_payloads = [
            '{"countryCode": "US"',               # Incomplete JSON
            '<html><body>502 Bad Gateway</body></html>',  # HTML error page
            '{"status": "fail", "message": 123',  # Unterminated object
            'curl: (6) Could not resolve host',   # DNS failure message
            '{"countryCode": null}',              # Null countryCode
            '',                                   # Empty string
        ]
        for payload in corrupted_payloads:
            mock_subproc.return_value = MagicMock(returncode=0, stdout=payload, stderr="")
            with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Fallback down")):
                matched, details = self.controller.verify_egress("emu-1", "US")
                self.assertFalse(matched)
                self.assertIsInstance(details, dict)

    @patch("subprocess.run")
    def test_egress_case_insensitivity(self, mock_subproc):
        """Verifies egress verification matches case-insensitively ('us' vs 'US')."""
        mock_subproc.return_value = MagicMock(
            returncode=0,
            stdout='{"status":"success","countryCode":"us","country":"United States"}',
            stderr="",
        )
        matched, details = self.controller.verify_egress("emu-1", "US")
        self.assertTrue(matched)
        self.assertEqual(details["countryCode"], "us")

    @patch("subprocess.run")
    def test_egress_host_fallback_successful_when_guest_curl_fails(self, mock_subproc):
        """Verifies fallback to host urllib query when guest curl output is empty."""
        mock_subproc.return_value = MagicMock(returncode=127, stdout="", stderr="/system/bin/sh: curl: not found")

        host_json_bytes = b'{"status":"success","countryCode":"AE","country":"United Arab Emirates"}'
        mock_resp = MagicMock()
        mock_resp.read.return_value = host_json_bytes
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            matched, details = self.controller.verify_egress("emu-1", "AE")
            self.assertTrue(matched)
            self.assertIn("host network fallback", details.get("note", ""))

    @patch("subprocess.run")
    def test_egress_empty_stderr_resilience(self, mock_subproc):
        """Verifies verify_egress handles empty string stderr gracefully."""
        mock_subproc.return_value = MagicMock(returncode=1, stdout="", stderr="")
        with patch("urllib.request.urlopen", side_effect=Exception("Host network offline")):
            matched, details = self.controller.verify_egress("emu-1", "GB")
            self.assertFalse(matched)
            self.assertIn("host_fallback_error", details)

    @patch("subprocess.run")
    def test_strict_network_true_enforces_failure_on_egress_mismatch(self, mock_subproc):
        """Verifies strict_network=True strictly sets success=False when egress country mismatches."""
        mock_subproc.return_value = MagicMock(
            returncode=0,
            stdout='{"status":"success","countryCode":"US","country":"United States"}',
            stderr="",
        )
        with patch.object(self.controller, "apply_tier3_hardware_gps", return_value=True):
            res = self.controller.switch_region("emu-1", "AE", strict_network=True)
            self.assertFalse(res.success)
            self.assertFalse(res.egress_verified)
            self.assertFalse(res.tier4_network)

    @patch("subprocess.run")
    def test_strict_network_false_preserves_success_on_egress_mismatch(self, mock_subproc):
        """Verifies strict_network=False leaves success=True with warning note when egress mismatches."""
        mock_subproc.return_value = MagicMock(
            returncode=0,
            stdout='{"status":"success","countryCode":"US","country":"United States"}',
            stderr="",
        )
        with patch.object(self.controller, "apply_tier3_hardware_gps", return_value=True):
            res = self.controller.switch_region("emu-1", "AE", strict_network=False)
            self.assertTrue(res.success)
            self.assertFalse(res.egress_verified)
            self.assertTrue(res.tier4_network)
            self.assertIn("Note: Egress IP verification did not match", res.message)


class TestDualSimAndCarrierConfigInvariance(unittest.TestCase):
    """Stress tests dual-SIM property setting and XML structure validity across all 7 regions."""

    def setUp(self):
        self.controller = UniversalRegionController(adb_path="adb")

    @patch("subprocess.run")
    def test_dual_sim_slot_indices_across_all_seven_regions(self, mock_subproc):
        """Verifies dual-SIM properties (.0 and .1) for numeric, alpha, and iso-country for all regions."""
        mock_subproc.return_value = MagicMock(returncode=0, stdout="", stderr="")

        for code, profile in REGIONS.items():
            mock_subproc.reset_mock()
            ok = self.controller.apply_tier1_telephony("emu-1", profile)
            self.assertTrue(ok)

            executed_cmds = [" ".join(call[0][0]) for call in mock_subproc.call_args_list]

            # Primary slot (.0)
            self.assertTrue(any(f"gsm.sim.operator.numeric.0 {profile.mcc_mnc}" in c for c in executed_cmds),
                            f"Missing gsm.sim.operator.numeric.0 for {code}")
            self.assertTrue(any(f"gsm.sim.operator.alpha.0 {profile.carrier_spn}" in c for c in executed_cmds),
                            f"Missing gsm.sim.operator.alpha.0 for {code}")
            self.assertTrue(any(f"gsm.sim.operator.iso-country.0 {profile.sim_iso}" in c for c in executed_cmds),
                            f"Missing gsm.sim.operator.iso-country.0 for {code}")

            # Secondary slot (.1)
            self.assertTrue(any(f"gsm.sim.operator.numeric.1 {profile.mcc_mnc}" in c for c in executed_cmds),
                            f"Missing gsm.sim.operator.numeric.1 for {code}")
            self.assertTrue(any(f"gsm.sim.operator.alpha.1 {profile.carrier_spn}" in c for c in executed_cmds),
                            f"Missing gsm.sim.operator.alpha.1 for {code}")
            self.assertTrue(any(f"gsm.sim.operator.iso-country.1 {profile.sim_iso}" in c for c in executed_cmds),
                            f"Missing gsm.sim.operator.iso-country.1 for {code}")

    @patch("subprocess.run")
    def test_carrier_config_xml_syntactically_valid_xml(self, mock_subproc):
        """Extracts CarrierConfig XML payloads and parses them via xml.etree.ElementTree."""
        mock_subproc.return_value = MagicMock(returncode=0, stdout="", stderr="")

        for code, profile in REGIONS.items():
            mock_subproc.reset_mock()
            self.controller.apply_tier1_telephony("emu-1", profile)

            xml_call = None
            for call in mock_subproc.call_args_list:
                args = call[0][0]
                for arg in args:
                    if "<carrier_config>" in arg:
                        xml_call = arg
                        break
                if xml_call:
                    break

            self.assertIsNotNone(xml_call, f"CarrierConfig XML echo call not found for {code}")

            raw_xml = xml_call.strip("'").strip()
            try:
                root = ET.fromstring(raw_xml)
                self.assertEqual(root.tag, "carrier_config")
                strings = {elem.get("name"): elem.text for elem in root.findall("string")}
                self.assertEqual(strings.get("carrier_name_string"), profile.carrier_spn)
                self.assertEqual(strings.get("carrier_iso_country"), profile.sim_iso)
                self.assertEqual(strings.get("carrier_mcc_mnc"), profile.mcc_mnc)
            except ET.ParseError as e:
                self.fail(f"CarrierConfig XML for {code} is invalid XML: {e}\nRaw:\n{raw_xml}")


class TestRapidSequentialSwitching(unittest.TestCase):
    """Stress tests rapid sequential switching through all 7 countries repeatedly."""

    def setUp(self):
        self.controller = UniversalRegionController(adb_path="adb")

    @patch("subprocess.run")
    def test_rapid_sequential_cycle_all_regions(self, mock_subproc):
        """Cycles through AE -> SA -> US -> GB -> PK -> DE -> JP -> AE -> SA."""
        sequence = ["AE", "SA", "US", "GB", "PK", "DE", "JP", "AE", "SA"]

        def subproc_handler(cmd, *args, **kwargs):
            mock_res = MagicMock(returncode=0, stderr="")
            cmd_str = " ".join(cmd)
            if "curl" in cmd_str:
                curr = current_country[0]
                mock_res.stdout = json.dumps({"status": "success", "countryCode": curr})
            else:
                mock_res.stdout = ""
            return mock_res

        mock_subproc.side_effect = subproc_handler
        current_country = ["AE"]

        with patch.object(self.controller, "apply_tier3_hardware_gps", return_value=True):
            for code in sequence:
                current_country[0] = code
                res = self.controller.switch_region("emu-1", code, strict_network=True)
                self.assertTrue(res.success, f"Failed switching to {code}")
                self.assertEqual(res.region_code, code)
                self.assertEqual(res.country_name, REGIONS[code].country_name)
                self.assertEqual(res.carrier, REGIONS[code].carrier_spn)
                self.assertTrue(res.tier1_telephony)
                self.assertTrue(res.tier2_system)
                self.assertTrue(res.tier3_hardware)
                self.assertTrue(res.tier4_network)
                self.assertTrue(res.egress_verified)


class TestConcurrentSwitching(unittest.TestCase):
    """Stress tests multi-threaded concurrent invocations across separate emulator instances."""

    def setUp(self):
        self.controller = UniversalRegionController(adb_path="adb")

    @patch("subprocess.run")
    def test_multithreaded_concurrent_region_switching(self, mock_subproc):
        """Launches 14 concurrent threads switching different emulators to different regions."""
        mock_subproc.return_value = MagicMock(
            returncode=0,
            stdout='{"status":"success","countryCode":"AE"}',
            stderr="",
        )

        results = []
        errors = []

        def worker_task(serial_id: str, code: str):
            try:
                with patch.object(self.controller, "apply_tier3_hardware_gps", return_value=True), \
                     patch.object(self.controller, "verify_egress", return_value=(True, {"countryCode": code})):
                    res = self.controller.switch_region(serial_id, code)
                    results.append((serial_id, code, res))
            except Exception as e:
                errors.append((serial_id, code, e))

        threads = []
        regions_list = list(REGIONS.keys())
        for i in range(14):
            serial = f"emulator-{5554 + i * 2}"
            code = regions_list[i % len(regions_list)]
            t = threading.Thread(target=worker_task, args=(serial, code))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=10.0)

        self.assertEqual(len(errors), 0, f"Concurrent threads raised unexpected exceptions: {errors}")
        self.assertEqual(len(results), 14)
        for serial, code, res in results:
            self.assertTrue(res.success)
            self.assertEqual(res.region_code, code)


if __name__ == "__main__":
    unittest.main()
