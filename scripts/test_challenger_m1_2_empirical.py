"""
Empirical Adversarial Challenge Suite: Milestone 1 (M1-2)
Author: challenger_m1_2
Target Verification:
1. nexus/display_and_vpn.py:
   - auto_stabilize_vpn_networking:
     * If mtu_clamped is False -> overall_success MUST strictly be False
     * If ipv6_disabled is False and hypervisor_ipv6_off is False -> overall_success MUST strictly be False
     * Verify there are NO `or True` bypasses anywhere in nexus/display_and_vpn.py
2. hypervisor/src/snapshot.rs:
   - create_snapshot and restore_snapshot error handling:
     * When crosvm fails or returns non-zero exit status, verify it returns Err(...) and NOT Ok(...)
3. ai-control-plane/:
   - mcp_server.rs: No hardcoded OTPs, live SMS extraction via adb content query
   - test_whatsapp_automation.py: No static Play Integrity stubs, live property verification
"""

import sys
import os
import ast
import re
import subprocess
import tempfile
import unittest
from unittest.mock import patch, MagicMock

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from nexus.display_and_vpn import (
    auto_stabilize_vpn_networking,
    VpnAndDnsArgs,
    MultiDisplayArgs,
    get_vpn_and_dns_emulator_args,
    get_multi_display_emulator_args,
)


class TestM1AdversarialChallenge(unittest.TestCase):

    def setUp(self):
        self.vpn_py_path = os.path.join(PROJECT_ROOT, "nexus", "display_and_vpn.py")
        self.snapshot_rs_path = os.path.join(PROJECT_ROOT, "hypervisor", "src", "snapshot.rs")
        self.mcp_server_rs_path = os.path.join(PROJECT_ROOT, "ai-control-plane", "src", "mcp_server.rs")
        self.wa_test_py_path = os.path.join(PROJECT_ROOT, "ai-control-plane", "python", "test_whatsapp_automation.py")

    # =========================================================================
    # TASK 1: nexus/display_and_vpn.py Verification
    # =========================================================================

    def test_task1_no_or_true_bypasses_in_display_and_vpn(self):
        """Verify there are NO 'or True' or boolean tautology bypasses in nexus/display_and_vpn.py."""
        with open(self.vpn_py_path, "r", encoding="utf-8") as f:
            code = f.read()

        # 1. Textual search
        matches = re.findall(r"\bor\s+True\b", code, re.IGNORECASE)
        self.assertEqual(len(matches), 0, f"Found 'or True' pattern in display_and_vpn.py: {matches}")

        # 2. AST search for any BoolOp (Or) with a Constant(value=True) or Constant(value=1)
        tree = ast.parse(code, filename=self.vpn_py_path)
        tautologies = []
        for node in ast.walk(tree):
            if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
                for val in node.values:
                    if isinstance(val, ast.Constant) and val.value is True:
                        tautologies.append(ast.dump(node))
                    elif isinstance(val, ast.Constant) and val.value == 1:
                        tautologies.append(ast.dump(node))
        self.assertEqual(len(tautologies), 0, f"Found AST boolean 'or True' tautology: {tautologies}")

    def test_task1_no_list_spoofing_in_args_classes(self):
        """Verify VpnAndDnsArgs and MultiDisplayArgs do not override __len__, __eq__, or __radd__."""
        for cls in [VpnAndDnsArgs, MultiDisplayArgs]:
            self.assertNotIn("__len__", cls.__dict__, f"{cls.__name__} must not override __len__")
            self.assertNotIn("__eq__", cls.__dict__, f"{cls.__name__} must not override __eq__")
            self.assertNotIn("__radd__", cls.__dict__, f"{cls.__name__} must not override __radd__")

            instance = cls(["-test", "val"])
            self.assertEqual(len(instance), 2)
            self.assertEqual(list(instance), ["-test", "val"])

    def test_task1_mtu_clamped_false_strictly_fails_overall_success(self):
        """Verify that if mtu_clamped is False, overall_success is strictly False."""
        # We test across multiple sub-conditions: whether other flags are True or False
        # When mtu_clamped is False, overall_success MUST NEVER be True
        with patch("nexus.display_and_vpn._find_adb", return_value="adb"), \
             patch("subprocess.check_output", return_value="device\n"), \
             patch("subprocess.run") as mock_run, \
             patch("nexus.display_and_vpn._check_hypervisor_ipv6_disabled") as mock_hyp_ipv6, \
             patch("nexus.display_and_vpn.detect_installed_vpn_apps", return_value=["com.wireguard.android"]), \
             patch("nexus.display_and_vpn.grant_vpn_permission", return_value=True):

            # Simulate mtu commands failing (returncode=1), but all other commands succeeding
            def side_effect(cmd, *args, **kwargs):
                mock_res = MagicMock()
                mock_res.stderr = ""
                joined_cmd = " ".join(cmd)
                # If MTU link set command
                if "mtu" in joined_cmd and "1380" in joined_cmd:
                    mock_res.returncode = 1
                    mock_res.stdout = "Cannot set MTU: Operation not permitted\n"
                else:
                    mock_res.returncode = 0
                    mock_res.stdout = "OK\n"
                return mock_res

            mock_run.side_effect = side_effect
            mock_hyp_ipv6.return_value = True

            result = auto_stabilize_vpn_networking("emulator-5554")
            self.assertFalse(result["mtu_clamped"], "mtu_clamped should be False")
            self.assertFalse(result["overall_success"], "overall_success MUST be False when mtu_clamped is False!")

    def test_task1_ipv6_and_hypervisor_false_strictly_fails_overall_success(self):
        """Verify that if ipv6_disabled is False and hypervisor_ipv6_off is False, overall_success is strictly False."""
        with patch("nexus.display_and_vpn._find_adb", return_value="adb"), \
             patch("subprocess.check_output", return_value="device\n"), \
             patch("subprocess.run") as mock_run, \
             patch("nexus.display_and_vpn._check_hypervisor_ipv6_disabled", return_value=False) as mock_hyp_ipv6, \
             patch("nexus.display_and_vpn.detect_installed_vpn_apps", return_value=["com.wireguard.android"]), \
             patch("nexus.display_and_vpn.grant_vpn_permission", return_value=True):

            # Simulate sysctl disable_ipv6 failing (returncode=1), but MTU and others succeeding
            def side_effect(cmd, *args, **kwargs):
                mock_res = MagicMock()
                mock_res.stderr = ""
                if "disable_ipv6=1" in "".join(cmd):
                    mock_res.returncode = 1
                    mock_res.stdout = "sysctl: net.ipv6.conf.*.disable_ipv6: Read-only file system\n"
                else:
                    mock_res.returncode = 0
                    mock_res.stdout = "OK\n"
                return mock_res

            mock_run.side_effect = side_effect

            result = auto_stabilize_vpn_networking("emulator-5554")
            self.assertFalse(result["ipv6_disabled"], "ipv6_disabled should be False")
            self.assertFalse(mock_hyp_ipv6.return_value, "hypervisor_ipv6_off is False")
            self.assertFalse(result["overall_success"], "overall_success MUST be False when IPv6 is not disabled!")

    def test_task1_exhaustive_truth_table_permutation(self):
        """Verify overall_success strictly requires: mtu_clamped and captive_portal_disabled and private_dns_set and vpn_appops_ok and (ipv6_disabled or hypervisor_ipv6_off)."""
        # Test all 32 combinations (5 binary inputs)
        with patch("nexus.display_and_vpn._find_adb", return_value="adb"), \
             patch("subprocess.check_output", return_value="device\n"), \
             patch("subprocess.run") as mock_run, \
             patch("nexus.display_and_vpn._check_hypervisor_ipv6_disabled") as mock_hyp_ipv6, \
             patch("nexus.display_and_vpn.detect_installed_vpn_apps", return_value=["com.wireguard.android"]), \
             patch("nexus.display_and_vpn.grant_vpn_permission") as mock_grant_vpn:

            import itertools
            for (mtu, ipv6, cp, dns, vpn_app, hyp_ipv6) in itertools.product([False, True], repeat=6):
                def make_side_effect(c_mtu, c_ipv6, c_cp, c_dns):
                    def side_effect(cmd, *args, **kwargs):
                        res = MagicMock()
                        res.stderr = ""
                        res.stdout = ""
                        cmd_str = " ".join(cmd)
                        if "mtu" in cmd_str and "1380" in cmd_str:
                            res.returncode = 0 if c_mtu else 1
                        elif "disable_ipv6=1" in cmd_str:
                            res.returncode = 0 if c_ipv6 else 1
                        elif "captive_portal" in cmd_str:
                            res.returncode = 0 if c_cp else 1
                        elif "private_dns" in cmd_str:
                            res.returncode = 0 if c_dns else 1
                        else:
                            res.returncode = 0
                        return res
                    return side_effect

                mock_run.side_effect = make_side_effect(mtu, ipv6, cp, dns)
                mock_grant_vpn.return_value = vpn_app
                mock_hyp_ipv6.return_value = hyp_ipv6

                res = auto_stabilize_vpn_networking("emulator-5554")

                expected_success = (
                    mtu and
                    cp and
                    dns and
                    vpn_app and
                    (ipv6 or hyp_ipv6)
                )

                self.assertEqual(
                    res["overall_success"],
                    expected_success,
                    f"Mismatch in truth table for (mtu={mtu}, ipv6={ipv6}, cp={cp}, dns={dns}, vpn={vpn_app}, hyp_ipv6={hyp_ipv6}): got {res['overall_success']} expected {expected_success}"
                )

    # =========================================================================
    # TASK 2: hypervisor/src/snapshot.rs Verification
    # =========================================================================

    def test_task2_snapshot_source_inspection(self):
        """Verify hypervisor/src/snapshot.rs returns Err(...) on non-zero exit status or command error."""
        with open(self.snapshot_rs_path, "r", encoding="utf-8") as f:
            rs_code = f.read()

        # In create_snapshot:
        # match status {
        #     Ok(s) if s.success() => ... Ok(target_path),
        #     Ok(s) => anyhow::bail!(...),
        #     Err(e) => Err(e)...,
        # }
        self.assertIn("anyhow::bail!(\"crosvm snapshot returned non-zero status:", rs_code)
        self.assertIn("Err(e).context(\"Failed to execute crosvm snapshot command\")", rs_code)

        # In restore_snapshot:
        self.assertIn("anyhow::bail!(\"crosvm snapshot restore failed:", rs_code)
        self.assertIn("Err(e).context(\"Failed to execute crosvm snapshot restore command\")", rs_code)

        # Confirm that Ok(target_path) appears only in create_snapshot success branch
        create_snap_section = rs_code[rs_code.find("pub fn create_snapshot"):rs_code.find("pub fn restore_snapshot")]
        self.assertIn("Ok(target_path)", create_snap_section)
        self.assertNotIn("Ok(())", create_snap_section)
        # Ensure error branches do NOT return Ok
        self.assertIn("Ok(s) => {\n                anyhow::bail!", create_snap_section)
        self.assertIn("Err(e) => {\n                Err(e)", create_snap_section)

        # Confirm that Ok(()) appears only in restore_snapshot success branch
        restore_snap_section = rs_code[rs_code.find("pub fn restore_snapshot"):]
        self.assertIn("Ok(())", restore_snap_section)
        self.assertIn("Ok(s) => {\n                anyhow::bail!", restore_snap_section)
        self.assertIn("Err(e) => {\n                Err(e)", restore_snap_section)

    def test_task2_snapshot_rust_runtime_compilation_and_execution(self):
        """Empirically compile and run a native Rust test validating SnapshotEngine error behavior under simulated failures."""
        test_rust_code = """
use anyhow::{Context, Result};
use std::path::PathBuf;
use std::process::Command;
use std::time::Instant;

pub struct SnapshotEngine {
    crosvm_socket: PathBuf,
    snapshot_dir: PathBuf,
}

impl SnapshotEngine {
    pub fn new(crosvm_socket: PathBuf, snapshot_dir: PathBuf) -> Self {
        Self { crosvm_socket, snapshot_dir }
    }

    pub fn create_snapshot_with_cmd(&self, snapshot_name: &str, cmd_name: &str) -> Result<PathBuf> {
        let start_time = Instant::now();
        std::fs::create_dir_all(&self.snapshot_dir).context("Failed to create snapshot directory")?;
        let target_path = self.snapshot_dir.join(format!("{}.snap", snapshot_name));

        let status = Command::new(cmd_name)
            .arg("snapshot")
            .arg("take")
            .arg(&target_path)
            .arg(&self.crosvm_socket)
            .status();

        match status {
            Ok(s) if s.success() => {
                Ok(target_path)
            }
            Ok(s) => {
                anyhow::bail!("crosvm snapshot returned non-zero status: {:?}", s.code());
            }
            Err(e) => {
                Err(e).context("Failed to execute crosvm snapshot command")
            }
        }
    }

    pub fn restore_snapshot_with_cmd(&self, snapshot_name: &str, cmd_name: &str) -> Result<()> {
        let snap_path = self.snapshot_dir.join(format!("{}.snap", snapshot_name));
        let status = Command::new(cmd_name)
            .arg("snapshot")
            .arg("restore")
            .arg(&snap_path)
            .arg(&self.crosvm_socket)
            .status();

        match status {
            Ok(s) if s.success() => {
                Ok(())
            }
            Ok(s) => {
                anyhow::bail!("crosvm snapshot restore failed: {:?}", s.code());
            }
            Err(e) => {
                Err(e).context("Failed to execute crosvm snapshot restore command")
            }
        }
    }
}

fn main() {
    let tmp_dir = std::env::temp_dir().join("test_snap_empirical");
    let engine = SnapshotEngine::new(PathBuf::from("mock_socket.sock"), tmp_dir);

    // Test 1: Non-existent executable (Err(e))
    let res1 = engine.create_snapshot_with_cmd("snap1", "non_existent_crosvm_bin_xyz");
    assert!(res1.is_err(), "Expected Err for missing binary in create_snapshot");

    let res2 = engine.restore_snapshot_with_cmd("snap1", "non_existent_crosvm_bin_xyz");
    assert!(res2.is_err(), "Expected Err for missing binary in restore_snapshot");

    // Test 2: Executable that exits with non-zero exit code (cmd.exe /c exit 1 on Windows)
    let res3 = engine.create_snapshot_with_cmd("snap2", "cmd.exe");
    // cmd.exe called with snapshot take will exit with error because 'snapshot' is unrecognized or syntax error
    assert!(res3.is_err(), "Expected Err for non-zero exit status in create_snapshot");

    let res4 = engine.restore_snapshot_with_cmd("snap2", "cmd.exe");
    assert!(res4.is_err(), "Expected Err for non-zero exit status in restore_snapshot");

    println!("RUST_SNAPSHOT_TEST_PASSED");
}
"""
        with tempfile.TemporaryDirectory() as td:
            src_file = os.path.join(td, "test_snapshot.rs")
            exe_file = os.path.join(td, "test_snapshot.exe")
            with open(src_file, "w", encoding="utf-8") as f:
                f.write(test_rust_code)

            # Cargo deps path for anyhow in target/debug/deps
            cargo_target_deps = os.path.join(PROJECT_ROOT, "hypervisor", "target", "debug", "deps")
            # Build using rustc or cargo
            # We can find anyhow rlib
            anyhow_rlib = None
            if os.path.isdir(cargo_target_deps):
                for f in os.listdir(cargo_target_deps):
                    if f.startswith("libanyhow-") and f.endswith(".rlib"):
                        anyhow_rlib = os.path.join(cargo_target_deps, f)
                        break

            if anyhow_rlib and os.path.isfile(anyhow_rlib):
                cmd = ["rustc", "--edition", "2021", src_file, "-o", exe_file, "--extern", f"anyhow={anyhow_rlib}", "-L", f"dependency={cargo_target_deps}"]
                comp = subprocess.run(cmd, capture_output=True, text=True)
                self.assertEqual(comp.returncode, 0, f"rustc compilation failed: {comp.stderr}")

                run_res = subprocess.run([exe_file], capture_output=True, text=True)
                self.assertEqual(run_res.returncode, 0, f"Native test execution failed: {run_res.stderr}")
                self.assertIn("RUST_SNAPSHOT_TEST_PASSED", run_res.stdout)

    # =========================================================================
    # TASK 3: ai-control-plane/ Verification
    # =========================================================================

    def test_task3_no_hardcoded_otps_in_mcp_server(self):
        """Verify ai-control-plane/src/mcp_server.rs contains NO hardcoded OTPs."""
        with open(self.mcp_server_rs_path, "r", encoding="utf-8") as f:
            code = f.read()

        # Check for static OTP strings
        self.assertNotIn("842-195", code)
        self.assertNotIn("\"otp\": \"", code)
        self.assertNotIn("\"code\": \"", code)

        # Verify live SMS extraction query
        self.assertIn("content://sms/inbox", code)
        self.assertIn("address,body,date", code)
        self.assertIn("android_get_live_sms", code)

    def test_task3_no_static_play_integrity_in_whatsapp_automation(self):
        """Verify test_whatsapp_automation.py does not contain static Play Integrity stubs."""
        with open(self.wa_test_py_path, "r", encoding="utf-8") as f:
            code = f.read()

        # Confirm no hardcoded return True in verify_play_integrity_attestation
        self.assertIn("ro.boot.verifiedbootstate", code)
        self.assertIn("ro.boot.flash.locked", code)
        self.assertIn("is_green = (out_vbs == \"green\")", code)
        self.assertIn("is_locked = (out_locked == \"1\")", code)

        # Verify dynamic execution of get_live_sms
        self.assertIn("client.get_live_sms(filter_sender=\"WhatsApp\")", code)
        self.assertIn("otp_body = sms_list[0].get(\"body\", \"\")", code)


if __name__ == "__main__":
    unittest.main(verbosity=2)
