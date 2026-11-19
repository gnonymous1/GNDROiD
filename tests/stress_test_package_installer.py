"""
tests/stress_test_package_installer.py
=======================================
Adversarial Stress Test Suite & Empirical Verification Harness for nexus/package_installer.py.

Focus Areas:
1. Malformed and Adversarial Archives (truncated, corrupted ZIP headers, zero APKs, zero-byte APKs, missing base APK, complex split hierarchies).
2. Malformed AXML Manifests (truncated chunks, corrupted string pool headers, struct.error triggers, UTF-8/UTF-16 boundary anomalies).
3. Security & Path Traversal in OBB files & Package Names (directory traversal, command injection via shell arguments).
4. Mock ADB Failures & Resilience (pm install-create failure, exec-in write mid-stream broken pipe, pm install-commit failure/timeout, session abandon and temp dir cleanup verification).
5. Anonymous GMS Token Dispatcher Adversarial Tests (Protobuf wire tag delimiters, control characters, HTTP errors, urllib InvalidURL crash).
6. Hardware Polyfill Edge Cases (unquoted spaces in setprop, remount failure resilience).
"""

import os
import io
import glob
import json
import shutil
import struct
import tempfile
import zipfile
import unittest
import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch

from tests.fixtures.mock_adb import MockAdbState, MockAdbSession
from tests.fixtures.bundle_generator import SyntheticBundleGenerator
from nexus.package_installer import (
    NativeSplitApkInstaller,
    SplitBundleManifest,
    AnonymousGmsDispatcher,
    HardwarePolyfill,
    install_split_apk_bundle,
    apply_hardware_polyfill,
    fetch_apk_via_anonymous_gms,
    parse_axml_manifest_metadata,
)


class TestStressMalformedArchives(unittest.TestCase):
    """Stress testing archive parsing with adversarial and malformed inputs."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="stress_arch_")
        self.installer = NativeSplitApkInstaller(adb_path="mock_adb")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_truncated_archive_at_various_byte_offsets(self):
        """Verify behavior when archives are truncated at various byte lengths."""
        valid_xapk = os.path.join(self.temp_dir, "valid.xapk")
        SyntheticBundleGenerator.create_xapk(valid_xapk, "com.test.trunc", 100)
        with open(valid_xapk, "rb") as f:
            full_data = f.read()

        offsets = [0, 4, 16, 64, len(full_data) // 2, len(full_data) - 10]
        for off in offsets:
            trunc_path = os.path.join(self.temp_dir, f"trunc_{off}.xapk")
            with open(trunc_path, "wb") as f:
                f.write(full_data[:off])

            with self.assertRaises(ValueError, msg=f"Failed to raise ValueError for truncation at {off} bytes") as ctx:
                self.installer.parse_bundle(trunc_path)
            self.assertIn("Invalid or corrupted zip archive", str(ctx.exception))

    def test_02_corrupted_crc32_archive(self):
        """Verify handling of ZIP archives with corrupted CRC32 checksums."""
        bad_crc_path = os.path.join(self.temp_dir, "bad_crc.xapk")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("base.apk", b"VALID_APK_PAYLOAD_HERE")
            z.writestr("manifest.json", json.dumps({"package_name": "com.crc.test"}))
        raw = bytearray(buf.getvalue())
        idx = raw.find(b"VALID_APK_PAYLOAD_HERE")
        if idx != -1:
            raw[idx : idx + 5] = b"CORRU"
        with open(bad_crc_path, "wb") as f:
            f.write(raw)

        try:
            self.installer.parse_bundle(bad_crc_path)
        except ValueError as e:
            self.assertIn("Invalid or corrupted zip archive", str(e))
        except zipfile.BadZipFile:
            pass

    def test_03_archive_with_zero_apks(self):
        """Verify archive with no .apk files raises ValueError and cleans up temp dir."""
        no_apk_path = os.path.join(self.temp_dir, "no_apks.xapk")
        with zipfile.ZipFile(no_apk_path, "w") as z:
            z.writestr("readme.txt", "No APKs here!")
            z.writestr("manifest.json", json.dumps({"package_name": "com.empty"}))
            z.writestr("assets/image.png", b"\x89PNG\r\n\x1a\n")

        with self.assertRaises(ValueError) as ctx:
            self.installer.parse_bundle(no_apk_path)
        self.assertIn("No valid .apk files found", str(ctx.exception))

    def test_04_archive_missing_base_apk_only_splits(self):
        """Archive with only config splits: picks largest split as fallback base APK."""
        only_splits_path = os.path.join(self.temp_dir, "only_splits.xapk")
        apk_data = SyntheticBundleGenerator._create_minimal_apk_bytes()
        with zipfile.ZipFile(only_splits_path, "w") as z:
            z.writestr("split_config.arm64_v8a.apk", apk_data + b"LARGE" * 20)
            z.writestr("split_config.xxhdpi.apk", apk_data)
            z.writestr("manifest.json", json.dumps({"package_name": "com.splits.only"}))

        manifest = self.installer.parse_bundle(only_splits_path)
        self.assertIsNotNone(manifest.base_apk_path)
        self.assertIn("split_config.arm64_v8a.apk", os.path.basename(manifest.base_apk_path))
        self.assertEqual(len(manifest.split_apk_paths), 1)
        if manifest.temp_dir:
            shutil.rmtree(manifest.temp_dir, ignore_errors=True)

    def test_05_archive_multiple_conflicting_base_apks(self):
        """Archive with multiple candidate base APKs: prioritizes base.apk or canonical names."""
        multi_base_path = os.path.join(self.temp_dir, "multi_base.xapk")
        apk_data = SyntheticBundleGenerator._create_minimal_apk_bytes()
        with zipfile.ZipFile(multi_base_path, "w") as z:
            z.writestr("standalone.apk", apk_data)
            z.writestr("base.apk", apk_data)
            z.writestr("universal.apk", apk_data)
            z.writestr("split_config.en.apk", apk_data)
            z.writestr("manifest.json", json.dumps({"package_name": "com.multi.base"}))

        manifest = self.installer.parse_bundle(multi_base_path)
        self.assertEqual(os.path.basename(manifest.base_apk_path).lower(), "base.apk")
        self.assertEqual(len(manifest.split_apk_paths), 3)
        if manifest.temp_dir:
            shutil.rmtree(manifest.temp_dir, ignore_errors=True)

    def test_06_complex_split_hierarchy_15_splits(self):
        """Stress-test archive with 15 splits spanning ABIs, densities, and languages."""
        complex_path = os.path.join(self.temp_dir, "complex_15_splits.xapk")
        apk_data = SyntheticBundleGenerator._create_minimal_apk_bytes()
        split_names = [
            "config.arm64_v8a.apk",
            "config.armeabi_v7a.apk",
            "config.x86.apk",
            "config.x86_64.apk",
            "config.ldpi.apk",
            "config.mdpi.apk",
            "config.hdpi.apk",
            "config.xhdpi.apk",
            "config.xxhdpi.apk",
            "config.xxxhdpi.apk",
            "config.en.apk",
            "config.ar.apk",
            "config.ur.apk",
            "config.de.apk",
            "config.es.apk",
        ]
        with zipfile.ZipFile(complex_path, "w") as z:
            z.writestr("base.apk", apk_data)
            for s in split_names:
                z.writestr(s, apk_data)
            z.writestr("manifest.json", json.dumps({"package_name": "com.complex.splits", "version_code": 999}))

        manifest = self.installer.parse_bundle(complex_path)
        self.assertEqual(os.path.basename(manifest.base_apk_path).lower(), "base.apk")
        self.assertEqual(len(manifest.split_apk_paths), 15)
        self.assertEqual(len(manifest.get_all_apks()), 16)
        if manifest.temp_dir:
            shutil.rmtree(manifest.temp_dir, ignore_errors=True)


class TestStressMalformedAxmlManifest(unittest.TestCase):
    """Stress testing the pure-Python AXML manifest parser with corrupted binaries."""

    def test_07_axml_buffer_shorter_than_36_bytes(self):
        """AXML buffers under 36 bytes must return empty metadata without crashing."""
        for sz in [0, 1, 8, 20, 35]:
            meta = parse_axml_manifest_metadata(b"\x00" * sz)
            self.assertEqual(meta["package_name"], "")
            self.assertEqual(meta["version_code"], 0)

    def test_08_axml_plain_text_fallback_with_regex(self):
        """Plain XML text buffer fallback should parse package and versionCode."""
        plain_xml = (
            b'<manifest xmlns:android="http://schemas.android.com/apk/res/android" '
            b'package="com.plain.text.app" versionCode="42" versionName="2.1.0">'
            b'</manifest>'
        )
        meta = parse_axml_manifest_metadata(plain_xml)
        self.assertEqual(meta["package_name"], "com.plain.text.app")
        self.assertEqual(meta["version_code"], 42)
        self.assertEqual(meta["version_name"], "2.1.0")

    def test_09_axml_corrupted_string_count_struct_error_finding(self):
        """
        FINDING 1: Corrupted AXML header with string_count exceeding available buffer.
        If len(axml_bytes) is 36, but string_count header indicates 5,
        unpack_from('<I', axml_bytes, 36 + i * 4) raises struct.error.
        The implementation MUST handle this gracefully rather than crashing.
        """
        truncated_header = struct.pack(
            "<IIIIIIIII",
            0x00080003,  # magic
            36,          # file_size
            0x001C0001,  # chunk_type (string pool)
            28,          # chunk_size
            5,           # string_count (claims 5 strings)
            0,           # style_count
            0,           # flags
            28,          # strings_start
            0,           # styles_start
        )
        self.assertEqual(len(truncated_header), 36)

        try:
            meta = parse_axml_manifest_metadata(truncated_header)
            self.assertIsInstance(meta, dict)
        except struct.error as e:
            self.fail(f"UNHANDLED CRASH in parse_axml_manifest_metadata on truncated header: {e}")

    def test_10_axml_chunk_size_zero_or_negative_break(self):
        """Verify chunk loop terminates if c_sz <= 0 and does not loop infinitely."""
        header = struct.pack(
            "<IIIIIIIII",
            0x00080003,  # magic
            44,          # file_size
            0x001C0001,  # chunk_type (string pool)
            28,          # chunk_size (offset 8 + 28 = 36)
            0,           # string_count
            0,           # style_count
            0,           # flags
            0,           # strings_start
            0,           # styles_start
        )
        bad_chunk = struct.pack("<II", 0x00100102, 0)
        data = header + bad_chunk
        meta = parse_axml_manifest_metadata(data)
        self.assertEqual(meta["package_name"], "")


class TestStressSecurityAndPathTraversal(unittest.TestCase):
    """Stress testing security boundaries: path traversal and command injection in OBBs and manifests."""

    def setUp(self):
        self.state = MockAdbState()
        self.installer = NativeSplitApkInstaller(adb_path="mock_adb")
        self.temp_dir = tempfile.mkdtemp(prefix="stress_sec_")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_11_path_traversal_in_manifest_package_name(self):
        """
        FINDING 2: Malicious package_name with directory traversal in manifest.json.
        e.g., package_name: '../../../../data/local/tmp'
        The implementation MUST sanitize package_name and reject path traversal outside the OBB directory.
        """
        with MockAdbSession(self.state):
            self.installer.deploy_obbs(
                serial="emulator-5554",
                obb_files=[("my_game.obb", "my_game.obb")],
                package_name="../../../../data/local/tmp",
            )
            push_cmds = [c for c in self.state.command_log if "push" in c]
            self.assertTrue(len(push_cmds) >= 1)
            pushed_dest = push_cmds[0][-1]
            self.assertNotIn(
                "..",
                pushed_dest,
                "VULNERABILITY: Path traversal in OBB deploy destination! Remote path escaped OBB directory: "
                f"{pushed_dest}",
            )

    def test_12_shell_command_injection_in_manifest_package_name(self):
        """
        FINDING 3: Shell metacharacters in package_name passed to adb shell.
        e.g., package_name: 'com.evil; rm -rf /sdcard'
        The implementation MUST prevent shell command injection.
        """
        with MockAdbSession(self.state):
            self.installer.deploy_obbs(
                serial="emulator-5554",
                obb_files=[("payload.obb", "payload.obb")],
                package_name="com.evil; reboot",
            )
            mkdir_cmds = [c for c in self.state.command_log if "mkdir" in c]
            self.assertTrue(len(mkdir_cmds) >= 1)
            flat_cmd = " ".join(mkdir_cmds[0])
            self.assertNotIn(
                ";",
                flat_cmd,
                "VULNERABILITY: Unescaped shell command separator ';' detected in ADB shell command: "
                f"{flat_cmd}",
            )

    def test_13_multi_obb_expansions_deployment(self):
        """Verify multiple OBB expansions (main, patch, dlc) are all deployed."""
        with MockAdbSession(self.state):
            obbs = [
                ("host_main.obb", "main.100.com.game.obb"),
                ("host_patch.obb", "patch.100.com.game.obb"),
                ("host_dlc.obb", "dlc.100.com.game.obb"),
            ]
            res = self.installer.deploy_obbs("emulator-5554", obbs, "com.game")
            self.assertTrue(res)
            push_cmds = [c for c in self.state.command_log if "push" in c]
            self.assertEqual(len(push_cmds), 3)


class TestStressAdbSessionFailuresAndCleanup(unittest.TestCase):
    """Stress testing PackageInstaller session failure modes and resource cleanup."""

    def setUp(self):
        self.state = MockAdbState()
        self.installer = NativeSplitApkInstaller(adb_path="mock_adb")
        self.temp_dir = tempfile.mkdtemp(prefix="stress_adb_")
        self.bundle_path = os.path.join(self.temp_dir, "test_bundle.xapk")
        SyntheticBundleGenerator.create_xapk(
            output_path=self.bundle_path,
            package_name="com.resilience.test",
            version_code=100,
            splits=["config.arm64_v8a.apk", "config.xxhdpi.apk"],
            with_obb=False,
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_14_pm_install_create_failure_cleans_staging_dir(self):
        """When pm install-create fails, returns (False, msg) and cleans staging dir."""
        self.state.fail_session_create = True
        self.state.fail_session_create_msg = "Failure [INSTALL_FAILED_INSUFFICIENT_STORAGE]"

        pre_dirs = set(glob.glob(os.path.join(tempfile.gettempdir(), "gndroid_bundle_*")))

        with MockAdbSession(self.state):
            ok, msg = self.installer.install_bundle("emulator-5554", self.bundle_path)
            self.assertFalse(ok)
            self.assertIn("INSTALL_FAILED_INSUFFICIENT_STORAGE", msg)

        post_dirs = set(glob.glob(os.path.join(tempfile.gettempdir(), "gndroid_bundle_*")))
        new_leaked_dirs = post_dirs - pre_dirs
        self.assertEqual(len(new_leaked_dirs), 0, f"Leaked temporary staging directories: {new_leaked_dirs}")

    def test_15_exec_in_write_midstream_failure_abandons_session(self):
        """When exec-in write fails on split 1, verifies pm install-abandon is called with session ID."""
        self.state.fail_write_split_idx = 1
        pre_dirs = set(glob.glob(os.path.join(tempfile.gettempdir(), "gndroid_bundle_*")))

        with MockAdbSession(self.state):
            ok, msg = self.installer.install_bundle("emulator-5554", self.bundle_path)
            self.assertFalse(ok)
            self.assertIn("Failed streaming split_1.apk", msg)

            abandon_cmds = [c for c in self.state.command_log if "install-abandon" in c]
            self.assertEqual(len(abandon_cmds), 1)
            self.assertIn("10000000", abandon_cmds[0])

        post_dirs = set(glob.glob(os.path.join(tempfile.gettempdir(), "gndroid_bundle_*")))
        self.assertEqual(len(post_dirs - pre_dirs), 0, "Staging directory leaked after write failure")

    def test_16_pm_install_commit_rejection_abandons_session(self):
        """When pm install-commit is rejected, verifies pm install-abandon is called."""
        self.state.fail_commit = True
        self.state.fail_commit_msg = "Failure [INSTALL_FAILED_VERSION_DOWNGRADE]"
        pre_dirs = set(glob.glob(os.path.join(tempfile.gettempdir(), "gndroid_bundle_*")))

        with MockAdbSession(self.state):
            ok, msg = self.installer.install_bundle("emulator-5554", self.bundle_path)
            self.assertFalse(ok)
            self.assertIn("Commit failed", msg)
            self.assertIn("INSTALL_FAILED_VERSION_DOWNGRADE", msg)

            abandon_cmds = [c for c in self.state.command_log if "install-abandon" in c]
            self.assertEqual(len(abandon_cmds), 1)
            self.assertIn("10000000", abandon_cmds[0])

        post_dirs = set(glob.glob(os.path.join(tempfile.gettempdir(), "gndroid_bundle_*")))
        self.assertEqual(len(post_dirs - pre_dirs), 0, "Staging directory leaked after commit failure")

    def test_17_repeated_failure_temp_dir_leak_stress(self):
        """Run 10 consecutive failed installations to ensure zero cumulative leak."""
        self.state.fail_session_create = True
        pre_dirs = set(glob.glob(os.path.join(tempfile.gettempdir(), "gndroid_bundle_*")))

        with MockAdbSession(self.state):
            for i in range(10):
                self.installer.install_bundle("emulator-5554", self.bundle_path)

        post_dirs = set(glob.glob(os.path.join(tempfile.gettempdir(), "gndroid_bundle_*")))
        self.assertEqual(len(post_dirs - pre_dirs), 0, "Cumulative temp directories leaked across 10 failures")


class TestStressAnonymousGmsDispatcher(unittest.TestCase):
    """Stress testing the Anonymous GMS Token Dispatcher payload parsing and network errors."""

    def setUp(self):
        self.dispatcher = AnonymousGmsDispatcher(device_id="adversarial_test_device")

    def test_18_protobuf_wire_tag_delimiter_url_splitting_finding(self):
        """
        FINDING 4: In binary Protobuf payloads, URLs are delimited by protobuf wire tags
        (e.g. \\x0a, \\x12, \\x1a). The regex '[^\\s\"\\'<>]+' does not treat \\x12 as a separator,
        concatenating multiple URLs into a single corrupted string with control characters.
        The parser MUST extract each URL cleanly without control characters.
        """
        payload = (
            b"\x0a\x30https://play.googleapis.com/download/base.apk?token=123"
            b"\x12\x30https://play.googleapis.com/download/split_1.apk?token=456"
        )
        urls = AnonymousGmsDispatcher._extract_cdn_urls_from_payload(payload)

        self.assertEqual(
            len(urls),
            2,
            f"PROTOCOL BUG: Expected 2 separate URLs from binary Protobuf payload, but got {len(urls)}: {urls}",
        )
        for u in urls:
            self.assertNotIn("\x12", u, f"CORRUPTED URL: Contains unstripped binary protobuf wire tag: {u!r}")

    def test_19_http_status_errors_resilience(self):
        """Verify graceful handling of HTTP 403, 404, 500 without crashing."""
        for code, reason in [(403, "Forbidden"), (404, "Not Found"), (500, "Internal Server Error")]:
            with patch("urllib.request.urlopen") as mock_urlopen:
                mock_urlopen.side_effect = urllib.error.HTTPError(
                    url="https://android.clients.google.com",
                    code=code,
                    msg=reason,
                    hdrs=MagicMock(),
                    fp=None,
                )
                ok, msg, splits = self.dispatcher.fetch_delivery_token("com.status.app", "AE")
                self.assertFalse(ok)
                self.assertIn(str(code), msg)
                self.assertEqual(splits, [])

    def test_20_network_socket_timeout_resilience(self):
        """Verify network socket timeout returns graceful False without unhandled exception."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = TimeoutError("Socket timed out after 15 seconds")
            ok, msg, splits = self.dispatcher.fetch_delivery_token("com.timeout.app", "AE")
            self.assertFalse(ok)
            self.assertIn("network error", msg)
            self.assertEqual(splits, [])


class TestStressHardwarePolyfill(unittest.TestCase):
    """Stress testing HardwarePolyfill property application and command formatting."""

    def setUp(self):
        self.state = MockAdbState()

    def test_21_unquoted_property_spaces_finding(self):
        """
        FINDING 5: Build properties with spaces (e.g. 'Pixel 9 Pro') passed via
        adb shell setprop <key> <val>. On Android shell, arguments are concatenated with spaces.
        Without explicit shell quoting or escaping, 'setprop ro.product.model Pixel 9 Pro'
        passes 3 arguments to setprop instead of 2.
        """
        with MockAdbSession(self.state):
            ok, msg = HardwarePolyfill.apply("emulator-5554", "pixel_9_pro")
            self.assertTrue(ok)
            setprop_cmds = [c for c in self.state.command_log if "setprop" in c and "ro.product.model" in c]
            self.assertTrue(len(setprop_cmds) >= 1)
            cmd = setprop_cmds[0]
            val_arg = cmd[-1]
            # Val arg passed to adb shell must be shell-quoted or escaped if it contains spaces
            self.assertTrue(
                val_arg.startswith('"') or val_arg.startswith("'") or (" " not in val_arg),
                f"COMMAND FORMATTING BUG: Property value '{val_arg}' with spaces is passed unquoted to adb shell.",
            )

    def test_22_case_insensitive_profile_resolution(self):
        """Verify profile lookup handles mixed case, dashes, and underscores."""
        p1 = HardwarePolyfill.get_profile("SAMSUNG-S24-ULTRA")
        p2 = HardwarePolyfill.get_profile("Samsung_S24_Ultra")
        p3 = HardwarePolyfill.get_profile("PIXEL-9-PRO")
        self.assertEqual(p1["ro.product.model"], "SM-S928B")
        self.assertEqual(p2["ro.product.model"], "SM-S928B")
        self.assertEqual(p3["ro.product.model"], "Pixel 9 Pro")


if __name__ == "__main__":
    unittest.main()
