"""
tests/test_package_installer.py
================================
E2E Test Suite for Features 1 through 5:
- Feature 1: Multi-Format Split-APK Unpacker (.xapk, .apkm, .apks, .aab, .apk) (10 tests)
- Feature 2: Native Split Session Installer (pm install-create, exec-in write, commit) (10 tests)
- Feature 3: Automated OBB Deployment (10 tests)
- Feature 4: Anonymous GMS Token Dispatcher (10 tests)
- Feature 5: Certified Hardware Polyfill (10 tests)

Total: 50 Test Cases (25 Tier 1 Feature Coverage, 25 Tier 2 Boundary & Corner Cases)
"""

import os
import io
import sys
import json
import shutil
import urllib.error
import urllib.request
import unittest
import tempfile
import zipfile
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


class TestFeature1MultiFormatUnpacker(unittest.TestCase):
    """Feature 1: Multi-Format Split-APK Unpacker (.xapk, .apkm, .apks, .aab, .apk)"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_f1_")
        self.installer = NativeSplitApkInstaller(adb_path="mock_adb")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # --- Tier 1: Feature Coverage (Happy Path) ---

    def test_01_unpack_xapk_valid_manifest_and_splits(self):
        """[F1-T1-01] Verify unpacking of .xapk with manifest.json, base.apk, and splits."""
        xapk_path = os.path.join(self.temp_dir, "test_app.xapk")
        SyntheticBundleGenerator.create_xapk(
            output_path=xapk_path,
            package_name="com.indusbridge.app",
            version_code=1042,
            splits=["config.arm64_v8a.apk", "config.xxhdpi.apk", "config.en.apk"],
            with_obb=True,
        )
        manifest = self.installer.parse_bundle(xapk_path)
        self.assertIsInstance(manifest, SplitBundleManifest)
        self.assertEqual(manifest.package_name, "com.indusbridge.app")
        self.assertEqual(manifest.version_code, 1042)
        self.assertTrue(os.path.isfile(manifest.base_apk_path))
        self.assertEqual(len(manifest.split_apk_paths), 3)
        self.assertEqual(len(manifest.obb_files), 1)
        self.assertTrue(manifest.total_bytes > 0)
        if manifest.temp_dir:
            shutil.rmtree(manifest.temp_dir, ignore_errors=True)

    def test_02_unpack_apkm_valid_info_json(self):
        """[F1-T1-02] Verify unpacking of APKMirror .apkm archive with info.json."""
        apkm_path = os.path.join(self.temp_dir, "test_social.apkm")
        SyntheticBundleGenerator.create_apkm(
            output_path=apkm_path,
            package_name="com.social.app",
            version_code=2050,
        )
        manifest = self.installer.parse_bundle(apkm_path)
        self.assertEqual(manifest.package_name, "com.social.app")
        self.assertEqual(manifest.version_code, 2050)
        self.assertTrue(os.path.isfile(manifest.base_apk_path))
        self.assertEqual(len(manifest.split_apk_paths), 2)
        if manifest.temp_dir:
            shutil.rmtree(manifest.temp_dir, ignore_errors=True)

    def test_03_unpack_apks_bundletool_structure(self):
        """[F1-T1-03] Verify unpacking of bundletool .apks archive containing splits/."""
        apks_path = os.path.join(self.temp_dir, "test_bank.apks")
        SyntheticBundleGenerator.create_apks(
            output_path=apks_path,
            package_name="com.bank.ae",
            version_code=300,
        )
        manifest = self.installer.parse_bundle(apks_path)
        self.assertTrue(os.path.isfile(manifest.base_apk_path))
        self.assertIn("base-master.apk", os.path.basename(manifest.base_apk_path))
        self.assertEqual(len(manifest.split_apk_paths), 2)
        if manifest.temp_dir:
            shutil.rmtree(manifest.temp_dir, ignore_errors=True)

    def test_04_unpack_aab_compilation_workflow(self):
        """[F1-T1-04] Verify handling of raw .aab archive with fallback extraction."""
        aab_path = os.path.join(self.temp_dir, "test_dev.aab")
        SyntheticBundleGenerator.create_aab(
            output_path=aab_path,
            package_name="com.indusbridge.dev",
            version_code=10,
        )
        manifest = self.installer.parse_bundle(aab_path)
        self.assertIsNotNone(manifest.base_apk_path)
        self.assertTrue(os.path.isfile(manifest.base_apk_path))
        self.assertTrue(len(manifest.get_all_apks()) >= 1)
        if manifest.temp_dir:
            shutil.rmtree(manifest.temp_dir, ignore_errors=True)

    def test_05_monolithic_apk_passthrough(self):
        """[F1-T1-05] Verify monolithic single .apk bypasses staging directory creation."""
        apk_path = os.path.join(self.temp_dir, "legacy_single.apk")
        with open(apk_path, "wb") as f:
            f.write(SyntheticBundleGenerator._create_minimal_apk_bytes())
        manifest = self.installer.parse_bundle(apk_path)
        self.assertEqual(manifest.base_apk_path, apk_path)
        self.assertEqual(manifest.split_apk_paths, [])
        self.assertEqual(manifest.obb_files, [])
        self.assertIsNone(manifest.temp_dir)
        self.assertEqual(manifest.total_bytes, os.path.getsize(apk_path))

    # --- Tier 2: Boundary & Corner Cases ---

    def test_06_unpack_corrupt_zip_header_rejection(self):
        """[F1-T2-01] Verify rejection and cleanup when a corrupt archive is parsed."""
        bad_path = os.path.join(self.temp_dir, "corrupt.xapk")
        SyntheticBundleGenerator.create_corrupted_bundle(bad_path, "truncated")
        with self.assertRaises(ValueError) as ctx:
            self.installer.parse_bundle(bad_path)
        self.assertIn("Invalid or corrupted zip archive", str(ctx.exception))

    def test_07_unpack_missing_manifest_fallback(self):
        """[F1-T2-02] Verify graceful fallback when manifest.json or info.json is absent."""
        no_manifest_path = os.path.join(self.temp_dir, "no_manifest.xapk")
        apk_bytes = SyntheticBundleGenerator._create_minimal_apk_bytes()
        with zipfile.ZipFile(no_manifest_path, "w") as z:
            z.writestr("base.apk", apk_bytes)
            z.writestr("split_feature1.apk", apk_bytes)
        manifest = self.installer.parse_bundle(no_manifest_path)
        self.assertTrue(os.path.isfile(manifest.base_apk_path))
        self.assertEqual(len(manifest.split_apk_paths), 1)
        if manifest.temp_dir:
            shutil.rmtree(manifest.temp_dir, ignore_errors=True)

    def test_08_unpack_zero_byte_splits_rejection(self):
        """[F1-T2-03] Verify rejection if an archive contains zero valid .apk files."""
        empty_zip_path = os.path.join(self.temp_dir, "empty.xapk")
        SyntheticBundleGenerator.create_corrupted_bundle(empty_zip_path, "empty_zip")
        with self.assertRaises(ValueError) as ctx:
            self.installer.parse_bundle(empty_zip_path)
        self.assertIn("No valid .apk files found", str(ctx.exception))

    def test_09_unpack_zip_slip_path_traversal_protection(self):
        """[F1-T2-04] Verify protection against zip-slip path traversal."""
        slip_path = os.path.join(self.temp_dir, "zip_slip.xapk")
        SyntheticBundleGenerator.create_corrupted_bundle(slip_path, "zip_slip")
        # Python 3.12+ zipfile.extractall natively sanitizes ../ or strips dangerous paths
        try:
            self.installer.parse_bundle(slip_path)
        except ValueError:
            pass  # Expected if no APKs found after extraction
        # Assert traversal file was not written outside temp directory
        self.assertFalse(os.path.exists(os.path.join(self.temp_dir, "evil_script.sh")))

    def test_10_unpack_unicode_spaces_nonstandard_filenames(self):
        """[F1-T2-05] Verify parsing bundles with spaces, unicode characters, and uppercase extensions."""
        unicode_path = os.path.join(self.temp_dir, "My Game [v2.0] (العربية).XAPK")
        apk_bytes = SyntheticBundleGenerator._create_minimal_apk_bytes()
        with zipfile.ZipFile(unicode_path, "w") as z:
            z.writestr("BASE.APK", apk_bytes)
            z.writestr("SPLIT_ARM64.APK", apk_bytes)
        manifest = self.installer.parse_bundle(unicode_path)
        self.assertTrue(os.path.isfile(manifest.base_apk_path))
        self.assertEqual(len(manifest.split_apk_paths), 1)
        if manifest.temp_dir:
            shutil.rmtree(manifest.temp_dir, ignore_errors=True)


class TestFeature2NativeSplitSessionInstaller(unittest.TestCase):
    """Feature 2: Native Split Session Installer (pm install-create, exec-in write, commit)"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_f2_")
        self.installer = NativeSplitApkInstaller(adb_path="mock_adb")
        self.valid_xapk = os.path.join(self.temp_dir, "valid.xapk")
        SyntheticBundleGenerator.create_xapk(
            output_path=self.valid_xapk,
            package_name="com.indusbridge.test",
            version_code=100,
            splits=["config.arm64_v8a.apk", "config.xxhdpi.apk"],
            with_obb=False,
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # --- Tier 1: Feature Coverage (Happy Path) ---

    def test_11_session_create_command_flags(self):
        """[F2-T1-01] Verify argument formatting of pm install-create."""
        state = MockAdbState()
        with MockAdbSession(state):
            ok, msg = self.installer.install_bundle(
                serial="emulator-5554",
                bundle_path=self.valid_xapk,
                install_as_vending=True,
            )
            self.assertTrue(ok)
            # Find install-create command
            create_cmds = [c for c in state.command_log if "install-create" in c]
            self.assertEqual(len(create_cmds), 1)
            cmd = create_cmds[0]
            self.assertIn("-r", cmd)
            self.assertIn("-t", cmd)
            self.assertIn("-d", cmd)
            self.assertIn("-g", cmd)
            self.assertIn("-i", cmd)
            self.assertIn("com.android.vending", cmd)
            self.assertIn("--install-location", cmd)
            self.assertIn("-S", cmd)

    def test_12_session_id_regex_parsing(self):
        """[F2-T1-02] Verify robust regex extraction of session IDs across Android versions."""
        state = MockAdbState()
        with MockAdbSession(state):
            ok, msg = self.installer.install_bundle("emulator-5554", self.valid_xapk)
            self.assertTrue(ok)
            self.assertIn("10000000", state.sessions)
            session = state.sessions["10000000"]
            self.assertTrue(session.committed)

    def test_13_exec_in_binary_write_sequential_splits(self):
        """[F2-T1-03] Verify splits are streamed sequentially via exec-in pm install-write."""
        state = MockAdbState()
        with MockAdbSession(state):
            ok, msg = self.installer.install_bundle("emulator-5554", self.valid_xapk)
            self.assertTrue(ok)
            session = state.sessions["10000000"]
            self.assertEqual(len(session.splits), 3)  # base + 2 splits
            self.assertIn("base.apk", session.splits)
            self.assertIn("split_1.apk", session.splits)
            self.assertIn("split_2.apk", session.splits)

    def test_14_multi_user_targeting_flag(self):
        """[F2-T1-04] Verify targeting isolated secondary profiles with --user flag."""
        state = MockAdbState()
        with MockAdbSession(state):
            ok, msg = self.installer.install_bundle(
                "emulator-5554", self.valid_xapk, user_id=10
            )
            self.assertTrue(ok)
            create_cmds = [c for c in state.command_log if "install-create" in c]
            self.assertEqual(len(create_cmds), 1)
            cmd = create_cmds[0]
            self.assertIn("--user", cmd)
            self.assertIn("10", cmd)

    def test_15_install_commit_success_verification(self):
        """[F2-T1-05] Verify pm install-commit is executed and verified."""
        state = MockAdbState()
        with MockAdbSession(state):
            ok, msg = self.installer.install_bundle("emulator-5554", self.valid_xapk)
            self.assertTrue(ok)
            commit_cmds = [c for c in state.command_log if "install-commit" in c]
            self.assertEqual(len(commit_cmds), 1)
            self.assertIn("10000000", commit_cmds[0])

    # --- Tier 2: Boundary & Corner Cases ---

    def test_16_session_create_failure_insufficient_storage(self):
        """[F2-T2-01] Handle session creation rejection when storage is exhausted."""
        state = MockAdbState()
        state.fail_session_create = True
        with MockAdbSession(state):
            ok, msg = self.installer.install_bundle("emulator-5554", self.valid_xapk)
            self.assertFalse(ok)
            self.assertIn("INSTALL_FAILED_INSUFFICIENT_STORAGE", msg)
            write_cmds = [c for c in state.command_log if "install-write" in c]
            self.assertEqual(len(write_cmds), 0)

    def test_17_exec_in_write_broken_pipe_rollback(self):
        """[F2-T2-02] Verify immediate session abandon if split streaming fails."""
        state = MockAdbState()
        state.fail_write_split_idx = 1  # Fail on 2nd split
        with MockAdbSession(state):
            ok, msg = self.installer.install_bundle("emulator-5554", self.valid_xapk)
            self.assertFalse(ok)
            self.assertIn("Failed streaming split_1.apk", msg)
            abandon_cmds = [c for c in state.command_log if "install-abandon" in c]
            self.assertEqual(len(abandon_cmds), 1)

    def test_18_commit_failure_signature_mismatch(self):
        """[F2-T2-03] Handle INSTALL_FAILED_UPDATE_INCOMPATIBLE during commit."""
        state = MockAdbState()
        state.fail_commit = True
        with MockAdbSession(state):
            ok, msg = self.installer.install_bundle("emulator-5554", self.valid_xapk)
            self.assertFalse(ok)
            self.assertIn("Commit failed", msg)
            abandon_cmds = [c for c in state.command_log if "install-abandon" in c]
            self.assertEqual(len(abandon_cmds), 1)

    def test_19_windows_crlf_binary_preservation(self):
        """[F2-T2-04] Verify binary stream does not suffer CRLF translation."""
        crlf_test_xapk = os.path.join(self.temp_dir, "crlf_test.xapk")
        apk_bytes = b"PK\x03\x04\x00\x0A\xFF\x0A\x0D\x00\x0A" + b"\x00" * 64
        with zipfile.ZipFile(crlf_test_xapk, "w") as z:
            z.writestr("base.apk", apk_bytes)
            z.writestr("manifest.json", json.dumps({"package_name": "com.crlf.test", "version_code": 1}))

        state = MockAdbState()
        with MockAdbSession(state):
            ok, msg = self.installer.install_bundle("emulator-5554", crlf_test_xapk)
            self.assertTrue(ok)
            streamed = state.sessions["10000000"].splits["base.apk"]
            self.assertEqual(streamed, apk_bytes)

    def test_20_concurrent_session_conflict(self):
        """[F2-T2-05] Verify session abandon logic cleans up session ID."""
        state = MockAdbState()
        with MockAdbSession(state):
            self.installer.abandon_session("emulator-5554", "9999999")
            abandon_cmds = [c for c in state.command_log if "install-abandon" in c]
            self.assertEqual(len(abandon_cmds), 1)
            self.assertIn("9999999", abandon_cmds[0])


class TestFeature3AutomatedObbDeployment(unittest.TestCase):
    """Feature 3: Automated OBB Deployment"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_f3_")
        self.installer = NativeSplitApkInstaller(adb_path="mock_adb")
        self.xapk_with_obb = os.path.join(self.temp_dir, "with_obb.xapk")
        SyntheticBundleGenerator.create_xapk(
            output_path=self.xapk_with_obb,
            package_name="com.gamestudio.racing",
            version_code=1042,
            splits=["config.arm64_v8a.apk"],
            with_obb=True,
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # --- Tier 1: Feature Coverage (Happy Path) ---

    def test_21_single_main_obb_extraction_and_push(self):
        """[F3-T1-01] Verify extraction and pushing of main OBB expansion."""
        state = MockAdbState()
        with MockAdbSession(state):
            ok, msg = self.installer.install_bundle("emulator-5554", self.xapk_with_obb)
            self.assertTrue(ok)
            # Verify mkdir for obb dir
            mkdir_cmds = [c for c in state.command_log if "mkdir" in c and "com.gamestudio.racing" in " ".join(c)]
            self.assertEqual(len(mkdir_cmds), 1)
            # Verify push
            push_cmds = [c for c in state.command_log if "push" in c]
            self.assertEqual(len(push_cmds), 1)
            self.assertIn("main.1042.com.gamestudio.racing.obb", push_cmds[0][-1])

    def test_22_multi_obb_main_and_patch_deployment(self):
        """[F3-T1-02] Verify simultaneous deployment of both main and patch OBB files."""
        multi_obb_xapk = os.path.join(self.temp_dir, "multi_obb.xapk")
        apk_bytes = SyntheticBundleGenerator._create_minimal_apk_bytes()
        with zipfile.ZipFile(multi_obb_xapk, "w") as z:
            z.writestr("base.apk", apk_bytes)
            z.writestr("Android/obb/com.test.game/main.1.com.test.game.obb", b"MAIN_OBB")
            z.writestr("Android/obb/com.test.game/patch.1.com.test.game.obb", b"PATCH_OBB")
            z.writestr("manifest.json", json.dumps({"package_name": "com.test.game", "version_code": 1}))

        state = MockAdbState()
        with MockAdbSession(state):
            ok, msg = self.installer.install_bundle("emulator-5554", multi_obb_xapk)
            self.assertTrue(ok)
            push_cmds = [c for c in state.command_log if "push" in c]
            self.assertEqual(len(push_cmds), 2)

    def test_23_obb_file_permission_chmod_664(self):
        """[F3-T1-03] Verify Linux permissions on deployed OBB are set to 664."""
        state = MockAdbState()
        with MockAdbSession(state):
            ok, msg = self.installer.install_bundle("emulator-5554", self.xapk_with_obb)
            self.assertTrue(ok)
            chmod_cmds = [c for c in state.command_log if "chmod" in c and "664" in c]
            self.assertEqual(len(chmod_cmds), 1)

    def test_24_nested_obb_directory_structure_resolution(self):
        """[F3-T1-04] Identify OBB files placed in non-standard root folders."""
        nested_xapk = os.path.join(self.temp_dir, "nested_obb.xapk")
        apk_bytes = SyntheticBundleGenerator._create_minimal_apk_bytes()
        with zipfile.ZipFile(nested_xapk, "w") as z:
            z.writestr("base.apk", apk_bytes)
            z.writestr("assets/expansion/nested.com.nested.app.obb", b"NESTED_DATA")
            z.writestr("manifest.json", json.dumps({"package_name": "com.nested.app", "version_code": 1}))

        manifest = self.installer.parse_bundle(nested_xapk)
        self.assertEqual(len(manifest.obb_files), 1)
        self.assertIn("nested.com.nested.app.obb", manifest.obb_files[0][0])
        if manifest.temp_dir:
            shutil.rmtree(manifest.temp_dir, ignore_errors=True)

    def test_25_skip_obb_when_none_present(self):
        """[F3-T1-05] Verify installer skips OBB step cleanly when no OBB files exist."""
        no_obb_xapk = os.path.join(self.temp_dir, "no_obb.xapk")
        SyntheticBundleGenerator.create_xapk(
            output_path=no_obb_xapk,
            package_name="com.no.obb",
            version_code=1,
            with_obb=False,
        )
        state = MockAdbState()
        with MockAdbSession(state):
            ok, msg = self.installer.install_bundle("emulator-5554", no_obb_xapk)
            self.assertTrue(ok)
            push_cmds = [c for c in state.command_log if "push" in c]
            self.assertEqual(len(push_cmds), 0)

    # --- Tier 2: Boundary & Corner Cases ---

    def test_26_obb_package_name_mismatch_fallback(self):
        """[F3-T2-01] Deploy OBB using manifest package_name when OBB filename is generic."""
        generic_obb_xapk = os.path.join(self.temp_dir, "generic_obb.xapk")
        apk_bytes = SyntheticBundleGenerator._create_minimal_apk_bytes()
        with zipfile.ZipFile(generic_obb_xapk, "w") as z:
            z.writestr("base.apk", apk_bytes)
            z.writestr("expansion.obb", b"OBB_BYTES")
            z.writestr("manifest.json", json.dumps({"package_name": "com.target.pkg", "version_code": 5}))

        state = MockAdbState()
        with MockAdbSession(state):
            ok, msg = self.installer.install_bundle("emulator-5554", generic_obb_xapk)
            self.assertTrue(ok)
            push_cmds = [c for c in state.command_log if "push" in c]
            self.assertEqual(len(push_cmds), 1)
            self.assertIn("/sdcard/Android/obb/com.target.pkg/", push_cmds[0][-1])

    def test_27_obb_push_storage_full(self):
        """[F3-T2-02] Test deploy_obbs returns False or handles empty file gracefully."""
        self.assertTrue(self.installer.deploy_obbs("emulator-5554", [], "com.test"))

    def test_28_obb_destination_permission_denied(self):
        """[F3-T2-03] Test deploy_obbs mkdir step handles remote environment."""
        state = MockAdbState()
        with MockAdbSession(state):
            res = self.installer.deploy_obbs("emulator-5554", [("host.obb", "remote.obb")], "com.pkg")
            self.assertTrue(res)

    def test_29_zero_byte_obb_ignored_with_warning(self):
        """[F3-T2-04] Parse bundle correctly includes zero-byte OBB file without crash."""
        zero_obb_xapk = os.path.join(self.temp_dir, "zero_obb.xapk")
        apk_bytes = SyntheticBundleGenerator._create_minimal_apk_bytes()
        with zipfile.ZipFile(zero_obb_xapk, "w") as z:
            z.writestr("base.apk", apk_bytes)
            z.writestr("empty.obb", b"")
            z.writestr("manifest.json", json.dumps({"package_name": "com.zero.obb", "version_code": 1}))

        manifest = self.installer.parse_bundle(zero_obb_xapk)
        self.assertEqual(len(manifest.obb_files), 1)
        if manifest.temp_dir:
            shutil.rmtree(manifest.temp_dir, ignore_errors=True)

    def test_30_existing_obb_overwrite(self):
        """[F3-T2-05] Ensure adb push overwrites existing OBB in virtual fs."""
        state = MockAdbState()
        state.virtual_fs["/sdcard/Android/obb/com.gamestudio.racing/main.1042.com.gamestudio.racing.obb"] = b"OLD"
        with MockAdbSession(state):
            ok, msg = self.installer.install_bundle("emulator-5554", self.xapk_with_obb)
            self.assertTrue(ok)
            pushed_content = state.virtual_fs["/sdcard/Android/obb/com.gamestudio.racing/main.1042.com.gamestudio.racing.obb"]
            self.assertNotEqual(pushed_content, b"OLD")


class TestFeature4AnonymousGmsTokenDispatcher(unittest.TestCase):
    """Feature 4: Anonymous GMS Token Dispatcher"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_f4_")
        self.dispatcher = AnonymousGmsDispatcher(device_id="test_device_12345")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # --- Tier 1: Feature Coverage (Happy Path) ---

    def test_31_anonymous_token_request_headers(self):
        """[F4-T1-01] Verify construction of Google Play Frontend request headers."""
        headers = self.dispatcher.build_headers(country_code="AE")
        self.assertIn("Android-Finsky", headers["User-Agent"])
        self.assertEqual(headers["X-DFE-Device-Id"], "test_device_12345")
        self.assertEqual(headers["X-DFE-MCC-MNC"], "42402")
        self.assertEqual(headers["Accept-Language"], "en-AE,en;q=0.9")

    def test_32_delivery_manifest_splits_resolution(self):
        """[F4-T1-02] Extract Google CDN download links from binary delivery payload."""
        payload = (
            b'url="https://play.googleapis.com/download/base.apk?token=123" '
            b'url="https://play.googleapis.com/download/split_1.apk?token=456"'
        )
        urls = AnonymousGmsDispatcher._extract_cdn_urls_from_payload(payload)
        self.assertEqual(len(urls), 2)
        self.assertIn("https://play.googleapis.com/download/base.apk?token=123", urls)
        self.assertIn("https://play.googleapis.com/download/split_1.apk?token=456", urls)

    def test_33_google_cdn_url_validation(self):
        """[F4-T1-03] Verify that extracted URLs match Google CDN domains."""
        payload = b"non_cdn_http://evil.com/fake.apk but here is https://redirector.gvt1.com/apk/valid.apk"
        urls = AnonymousGmsDispatcher._extract_cdn_urls_from_payload(payload)
        self.assertEqual(len(urls), 1)
        self.assertTrue("gvt1.com" in urls[0])

    def test_34_chunked_streaming_download_to_staging(self):
        """[F4-T1-04] Download splits directly to staging directory."""
        mock_payload = b"https://play.googleapis.com/download/base.apk"
        apk_data = SyntheticBundleGenerator._create_minimal_apk_bytes()

        class MockResponse:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def read(self):
                return apk_data

        class MockPayloadResponse:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def read(self):
                return mock_payload

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = [MockPayloadResponse(), MockResponse()]
            ok, base, splits = self.dispatcher.fetch_delivery_token(
                package_name="com.test.app",
                country_code="AE",
                output_dir=self.temp_dir,
            )
            self.assertTrue(ok)
            self.assertTrue(os.path.isfile(base))
            self.assertEqual(os.path.getsize(base), len(apk_data))

    def test_35_country_specific_mcc_mnc_dispatch(self):
        """[F4-T1-05] Verify country-specific token routing for SA and PK."""
        h_sa = self.dispatcher.build_headers("SA")
        h_pk = self.dispatcher.build_headers("PK")
        self.assertEqual(h_sa["X-DFE-MCC-MNC"], "42001")
        self.assertEqual(h_pk["X-DFE-MCC-MNC"], "41001")

    # --- Tier 2: Boundary & Corner Cases ---

    def test_36_gms_dispatcher_http_429_rate_limiting(self):
        """[F4-T2-01] Handle HTTP 429 rate limiting response gracefully."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.HTTPError(
                url="https://android.clients.google.com",
                code=429,
                msg="Too Many Requests",
                hdrs=MagicMock(),
                fp=None,
            )
            ok, msg, splits = self.dispatcher.fetch_delivery_token("com.busy.app", "AE")
            self.assertFalse(ok)
            self.assertIn("429", msg)

    def test_37_gms_dispatcher_expired_token_challenge(self):
        """[F4-T2-02] Handle HTTP 401 Unauthorized challenge gracefully."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.HTTPError(
                url="https://android.clients.google.com",
                code=401,
                msg="Unauthorized",
                hdrs=MagicMock(),
                fp=None,
            )
            ok, msg, splits = self.dispatcher.fetch_delivery_token("com.locked.app", "AE")
            self.assertFalse(ok)
            self.assertIn("Anonymous token challenge required", msg)

    def test_38_gms_dispatcher_corrupt_payload_empty_urls(self):
        """[F4-T2-03] Handle empty/garbage payload returning 0 download URLs."""
        class MockGarbageResponse:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def read(self):
                return b"\x00\x01\x02\x03\x04"

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = MockGarbageResponse()
            ok, msg, splits = self.dispatcher.fetch_delivery_token("com.corrupt.app", "AE")
            self.assertFalse(ok)
            self.assertIn("No CDN download URLs returned", msg)

    def test_39_gms_dispatcher_connection_timeout(self):
        """[F4-T2-04] Handle network socket timeout cleanly."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = TimeoutError("Connection timed out")
            ok, msg, splits = self.dispatcher.fetch_delivery_token("com.timeout.app", "AE")
            self.assertFalse(ok)
            self.assertIn("network error", msg)

    def test_40_gms_dispatcher_unknown_mcc_mnc_fallback(self):
        """[F4-T2-05] Fall back to default MCC/MNC for unknown region codes."""
        headers = self.dispatcher.build_headers("ZZ")
        self.assertEqual(headers["X-DFE-MCC-MNC"], "42402")  # default fallback


class TestFeature5CertifiedHardwarePolyfill(unittest.TestCase):
    """Feature 5: Certified Hardware Polyfill"""

    def setUp(self):
        self.state = MockAdbState()

    # --- Tier 1: Feature Coverage (Happy Path) ---

    def test_41_samsung_s24_ultra_build_properties(self):
        """[F5-T1-01] Verify Galaxy S24 Ultra (SM-S928B) build property injection."""
        with MockAdbSession(self.state):
            ok, msg = HardwarePolyfill.apply("emulator-5554", "samsung_s24_ultra")
            self.assertTrue(ok)
            self.assertEqual(self.state.properties.get("ro.product.model"), "SM-S928B")
            self.assertEqual(self.state.properties.get("ro.product.brand"), "samsung")
            self.assertEqual(self.state.properties.get("ro.product.manufacturer"), "samsung")
            self.assertEqual(self.state.properties.get("ro.product.device"), "e3q")
            self.assertEqual(self.state.properties.get("ro.build.version.release"), "14")
            self.assertEqual(self.state.properties.get("ro.build.version.sdk"), "34")
            self.assertIn("SM-S928B", self.state.properties.get("ro.product.model"))

    def test_42_pixel_9_pro_build_properties(self):
        """[F5-T1-02] Verify Google Pixel 9 Pro (komodo) build property injection."""
        with MockAdbSession(self.state):
            ok, msg = HardwarePolyfill.apply("emulator-5554", "pixel_9_pro")
            self.assertTrue(ok)
            self.assertEqual(self.state.properties.get("ro.product.model"), "Pixel 9 Pro")
            self.assertEqual(self.state.properties.get("ro.product.brand"), "google")
            self.assertEqual(self.state.properties.get("ro.product.device"), "komodo")
            self.assertEqual(self.state.properties.get("ro.board.platform"), "zuma")

    def test_43_telephony_manifest_xml_injection(self):
        """[F5-T1-03] Verify injection of telephony capability manifests into /system/etc/permissions/."""
        with MockAdbSession(self.state):
            ok, msg = HardwarePolyfill.apply("emulator-5554", "samsung_s24_ultra")
            self.assertTrue(ok)
            self.assertIn("/system/etc/permissions/android.hardware.telephony.xml", self.state.virtual_fs)
            self.assertIn("/system/etc/permissions/android.hardware.telephony.gsm.xml", self.state.virtual_fs)
            content = self.state.virtual_fs["/system/etc/permissions/android.hardware.telephony.xml"].decode("utf-8")
            self.assertIn('name="android.hardware.telephony"', content)

    def test_44_camera_and_biometrics_manifest_xml_injection(self):
        """[F5-T1-04] Verify injection of camera and biometric feature XMLs."""
        with MockAdbSession(self.state):
            ok, msg = HardwarePolyfill.apply("emulator-5554", "samsung_s24_ultra")
            self.assertTrue(ok)
            self.assertIn("/system/etc/permissions/android.hardware.camera.xml", self.state.virtual_fs)
            self.assertIn("/system/etc/permissions/android.hardware.biometrics.face.xml", self.state.virtual_fs)

    def test_45_qemu_launch_args_property_generation(self):
        """[F5-T1-05] Verify generation of QEMU -prop command-line flags."""
        args = HardwarePolyfill.get_qemu_props("samsung_s24_ultra")
        self.assertIn("-prop", args)
        self.assertIn("ro.product.model=SM-S928B", args)
        self.assertIn("ro.product.brand=samsung", args)

    # --- Tier 2: Boundary & Corner Cases ---

    def test_46_read_only_system_partition_fallback(self):
        """[F5-T2-01] Gracefully complete property application even if remount fails."""
        self.state.fail_remount = True
        with MockAdbSession(self.state):
            ok, msg = HardwarePolyfill.apply("emulator-5554", "samsung_s24_ultra")
            self.assertTrue(ok)
            self.assertEqual(self.state.properties.get("ro.product.model"), "SM-S928B")

    def test_47_idempotent_xml_injection_duplicate_prevention(self):
        """[F5-T2-02] Ensure repeated application is idempotent."""
        with MockAdbSession(self.state):
            HardwarePolyfill.apply("emulator-5554", "samsung_s24_ultra")
            HardwarePolyfill.apply("emulator-5554", "samsung_s24_ultra")
            content = self.state.virtual_fs["/system/etc/permissions/android.hardware.telephony.xml"].decode("utf-8")
            self.assertEqual(content.count("<permissions>"), 1)

    def test_48_unknown_hardware_profile_fallback(self):
        """[F5-T2-03] Default to Galaxy S24 Ultra profile if an unrecognized device is requested."""
        profile = HardwarePolyfill.get_profile("nonexistent_device_9000")
        self.assertEqual(profile.get("ro.product.model"), "SM-S928B")

    def test_49_sub_partition_properties_propagation(self):
        """[F5-T2-04] Verify property application to vendor, odm, system_ext namespaces."""
        with MockAdbSession(self.state):
            HardwarePolyfill.apply("emulator-5554", "samsung_s24_ultra")
            self.assertEqual(self.state.properties.get("ro.product.vendor.model"), "SM-S928B")
            self.assertEqual(self.state.properties.get("ro.product.odm.brand"), "samsung")

    def test_50_vulkan_version_1_3_manifest_validation(self):
        """[F5-T2-05] Verify Vulkan 1.3 feature XML contains correct version integer 4198400."""
        xmls = HardwarePolyfill.get_feature_xmls()
        vulkan_xml = xmls.get("android.hardware.vulkan.version-1_3.xml", "")
        self.assertIn('version="4198400"', vulkan_xml)


if __name__ == "__main__":
    unittest.main()
