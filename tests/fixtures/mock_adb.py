"""
tests/fixtures/mock_adb.py
===========================
High-fidelity stateful mock ADB server intercepting subprocess calls.
Simulates PackageInstaller sessions, exec-in binary streaming, system properties,
settings, network device MTU, sysctl, iptables kill-switch, and virtual filesystems.
"""

import os
import re
import shlex
import json
import subprocess
from typing import Dict, List, Set, Tuple, Optional, Any
from dataclasses import dataclass, field


@dataclass
class StagedInstallSession:
    session_id: str
    total_size: int
    user_id: int
    installer_package: str
    splits: Dict[str, bytes] = field(default_factory=dict)
    committed: bool = False
    abandoned: bool = False


class MockAdbState:
    def __init__(self):
        self.sessions: Dict[str, StagedInstallSession] = {}
        self.next_session_id = 10000000
        self.installed_packages: Set[str] = {
            "com.android.chrome",
            "com.android.settings",
            "com.google.android.gms",
            "com.google.android.vending",
        }
        self.properties: Dict[str, str] = {
            "sys.boot_completed": "1",
            "ro.product.model": "sdk_gphone64_x86_64",
            "ro.product.brand": "google",
            "ro.build.version.sdk": "34",
            "gsm.sim.state": "READY",
        }
        self.settings: Dict[str, Dict[str, str]] = {
            "global": {"private_dns_mode": "off"},
            "system": {},
            "secure": {},
        }
        self.mtu: Dict[str, int] = {"eth0": 1500, "wlan0": 1500}
        self.sysctl: Dict[str, str] = {
            "/proc/sys/net/ipv6/conf/all/disable_ipv6": "0",
            "/proc/sys/net/ipv6/conf/default/disable_ipv6": "0",
            "/proc/sys/vm/drop_caches": "0",
            "/proc/sys/vm/compact_memory": "0",
        }
        self.iptables_rules: List[str] = []
        self.virtual_fs: Dict[str, bytes] = {}
        self.command_log: List[List[str]] = []
        self.simulated_egress: Dict[str, Any] = {
            "status": "success",
            "country": "United Arab Emirates",
            "countryCode": "AE",
            "city": "Dubai",
            "query": "195.229.241.50",
        }
        self.simulate_root: bool = True
        self.simulate_offline: bool = False
        self.fail_session_create: bool = False
        self.fail_session_create_msg: str = "Failure [INSTALL_FAILED_INSUFFICIENT_STORAGE]"
        self.fail_commit: bool = False
        self.fail_commit_msg: str = "Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE: Package signatures do not match]"
        self.fail_write_split_idx: Optional[int] = None
        self.fail_remount: bool = False

    def handle_command(self, cmd: List[str], stdin: Optional[Any] = None) -> Tuple[int, str, str]:
        self.command_log.append(list(cmd))
        args = [str(c) for c in cmd if c != ""]
        if args and ("adb" in os.path.basename(args[0]).lower()):
            args = args[1:]

        serial = ""
        idx = 0
        while idx < len(args):
            if args[idx] == "-s" and idx + 1 < len(args):
                serial = args[idx + 1]
                args = args[:idx] + args[idx + 2:]
            else:
                idx += 1

        if self.simulate_offline or "offline" in serial:
            return 1, "", f"adb.exe: device '{serial}' not found\n"

        if not args:
            return 0, "", ""

        sub = args[0]
        if sub == "devices":
            return 0, "List of devices attached\nemulator-5554\tdevice\n\n", ""
        if sub == "get-state":
            return 0, "device\n", ""

        # push <src> <dest>
        if sub == "push":
            if len(args) >= 3:
                src, dest = args[1], args[2]
                content = b""
                if os.path.isfile(src):
                    with open(src, "rb") as f:
                        content = f.read()
                self.virtual_fs[dest] = content
                return 0, f"1 file pushed, 0 skipped. 10.5 MB/s ({len(content)} bytes in 0.010s)\n", ""
            return 1, "", "adb: push requires source and destination\n"

        # exec-in pm install-write -S <size> <sessionId> <splitName>
        if sub == "exec-in":
            sub_args = args[1:]
            if len(sub_args) >= 6 and sub_args[0] == "pm" and sub_args[1] == "install-write":
                size = int(sub_args[3])
                session_id = sub_args[4]
                split_name = sub_args[5]

                if session_id not in self.sessions or self.sessions[session_id].abandoned:
                    return 1, "", f"Failure [INSTALL_FAILED_INVALID_SESSION: Session {session_id} not found]\n"

                current_split_count = len(self.sessions[session_id].splits)
                if self.fail_write_split_idx is not None and current_split_count == self.fail_write_split_idx:
                    return 1, "", f"Failure [INSTALL_FAILED_MEDIA_UNAVAILABLE: Broken pipe streaming {split_name}]\n"

                payload = b""
                if stdin is not None:
                    if hasattr(stdin, "read"):
                        payload = stdin.read()
                    elif isinstance(stdin, bytes):
                        payload = stdin
                    elif isinstance(stdin, str):
                        payload = stdin.encode("utf-8")

                self.sessions[session_id].splits[split_name] = payload
                return 0, f"Success: streamed {len(payload)} bytes\n", ""

        # shell commands
        if sub == "shell":
            return self._handle_shell(args[1:])

        return 0, "", ""

    def _handle_shell(self, shell_args: List[str]) -> Tuple[int, str, str]:
        if not shell_args:
            return 0, "", ""

        tokens: List[str] = []
        if len(shell_args) == 1:
            cmd_str = shell_args[0]
            if ">" in cmd_str:
                parts = cmd_str.split(">", 1)
                tokens = parts[0].strip().split() + [">", parts[1].strip()]
            else:
                try:
                    tokens = shlex.split(cmd_str)
                except Exception:
                    tokens = cmd_str.split()
        else:
            tokens = [str(x).strip('"\'') for x in shell_args]

        if len(tokens) >= 2 and tokens[0] == "su" and tokens[1] == "0":
            if not self.simulate_root:
                return 1, "", "Permission denied (you must be root)\n"
            tokens = tokens[2:]

        if not tokens:
            return 0, "", ""

        tool = tokens[0]
        flat = " ".join(tokens)

        # mount -o remount,rw /system
        if "mount" in tokens and "remount" in flat:
            if self.fail_remount or not self.simulate_root:
                return 1, "", "remount of /system failed: Read-only file system\n"
            return 0, "remount succeeded\n", ""

        # 1. pm install-create / pm install-commit / pm install-abandon
        if tool == "pm":
            sub = tokens[1] if len(tokens) > 1 else ""
            if sub == "install-create":
                if self.fail_session_create:
                    return 1, "", f"{self.fail_session_create_msg}\n"

                sz = 0
                pkg_inst = "com.android.vending"
                uid = 0
                for i, t in enumerate(tokens):
                    if t == "-S" and i + 1 < len(tokens):
                        try:
                            sz = int(tokens[i + 1])
                        except ValueError:
                            pass
                    if t == "-i" and i + 1 < len(tokens):
                        pkg_inst = tokens[i + 1]
                    if t == "--user" and i + 1 < len(tokens):
                        try:
                            uid = int(tokens[i + 1])
                        except ValueError:
                            pass

                sid = str(self.next_session_id)
                self.next_session_id += 1
                self.sessions[sid] = StagedInstallSession(
                    session_id=sid, total_size=sz, user_id=uid, installer_package=pkg_inst
                )
                return 0, f"Success: created install session [{sid}]\n", ""

            if sub == "install-commit":
                sid = tokens[2] if len(tokens) > 2 else ""
                if self.fail_commit:
                    return 1, "", f"{self.fail_commit_msg}\n"
                if sid not in self.sessions or self.sessions[sid].abandoned:
                    return 1, "", f"Failure [INSTALL_FAILED_INVALID_SESSION: {sid}]\n"
                session = self.sessions[sid]
                session.committed = True
                self.installed_packages.add("com.installed.app")
                return 0, "Success\n", ""

            if sub == "install-abandon":
                sid = tokens[2] if len(tokens) > 2 else ""
                if sid in self.sessions:
                    self.sessions[sid].abandoned = True
                return 0, "Success\n", ""

            if sub == "path":
                pkg = tokens[2] if len(tokens) > 2 else ""
                if pkg in self.installed_packages:
                    return 0, f"package:/data/app/~~mock/{pkg}/base.apk\n", ""
                return 1, "", f"Error: package {pkg} not found\n"

        # 2. setprop / getprop
        if tool == "setprop" and len(tokens) >= 3:
            self.properties[tokens[1]] = " ".join(tokens[2:]) if len(tokens) > 3 else tokens[2]
            return 0, "", ""
        if tool == "getprop":
            prop = tokens[1] if len(tokens) > 1 else ""
            return 0, f"{self.properties.get(prop, '')}\n", ""

        # 3. settings put / get / delete
        if tool == "settings" and len(tokens) >= 3:
            action, tbl = tokens[1], tokens[2]
            if action == "put" and len(tokens) >= 5:
                key, val = tokens[3], tokens[4]
                self.settings.setdefault(tbl, {})[key] = val
                return 0, "", ""
            if action == "get" and len(tokens) >= 4:
                key = tokens[3]
                v = self.settings.get(tbl, {}).get(key, "null")
                return 0, f"{v}\n", ""
            if action == "delete" and len(tokens) >= 4:
                key = tokens[3]
                if tbl in self.settings and key in self.settings[tbl]:
                    del self.settings[tbl][key]
                return 0, "", ""

        # 4. ip link set dev <dev> mtu <mtu>
        if tool == "ip" and "mtu" in flat:
            for i, t in enumerate(tokens):
                if t == "dev" and i + 1 < len(tokens):
                    dev = tokens[i + 1]
                    if "mtu" in tokens:
                        m_idx = tokens.index("mtu")
                        if m_idx + 1 < len(tokens):
                            try:
                                self.mtu[dev] = int(tokens[m_idx + 1])
                            except ValueError:
                                pass
            return 0, "", ""

        # 5. echo <val> > <path>
        if tool == "echo" and ">" in tokens:
            v_idx = 1
            redirect_idx = tokens.index(">")
            val = tokens[v_idx].strip("'\"")
            target_path = tokens[redirect_idx + 1] if redirect_idx + 1 < len(tokens) else ""
            if target_path:
                self.sysctl[target_path] = val
            return 0, "", ""

        # 6. iptables kill-switch
        if tool == "iptables":
            if not self.simulate_root:
                return 1, "", "iptables: Permission denied (you must be root)\n"
            if "-I" in tokens and "OUTPUT" in tokens and "DROP" in tokens:
                self.iptables_rules.insert(0, "OUTPUT 1 DROP")
                return 0, "", ""
            if "-D" in tokens and "OUTPUT" in tokens:
                if self.iptables_rules:
                    self.iptables_rules.pop(0)
                return 0, "", ""
            if "TCPMSS" in tokens or "ip_forward" in flat:
                return 0, "", ""

        # 7. am trim-memory
        if tool == "am" and len(tokens) >= 3 and tokens[1] == "trim-memory":
            return 0, "Trim memory successful.\n", ""

        # 8. service call alarm 3 s16 <tz>
        if tool == "service" and "alarm" in tokens:
            return 0, "Result: Parcel(00000000  '....')\n", ""

        # 9. am broadcast
        if tool == "am" and "broadcast" in tokens:
            return 0, "Broadcasting: Intent { ... }\nBroadcast completed: result=0\n", ""

        # 10. curl http://ip-api.com/json
        if tool == "curl" and "ip-api.com" in flat:
            return 0, json.dumps(self.simulated_egress) + "\n", ""

        # 11. appops
        if tool == "appops":
            return 0, "Success\n", ""

        # 12. date @<epoch>
        if tool == "date":
            return 0, "Clock updated\n", ""

        # 13. sysctl
        if tool == "sysctl":
            return 0, "", ""

        # 14. mkdir / chmod
        if tool in ("mkdir", "chmod"):
            return 0, "", ""

        return 0, "", ""


class MockAdbSession:
    def __init__(self, initial_state: Optional[MockAdbState] = None):
        self.state = initial_state or MockAdbState()
        self._orig_run = subprocess.run
        self._orig_check_output = subprocess.check_output
        self._orig_popen = subprocess.Popen

    def __enter__(self):
        state = self.state

        def mock_run(cmd, *args, **kwargs):
            cmd_list = cmd if isinstance(cmd, list) else shlex.split(str(cmd))
            exe = os.path.basename(str(cmd_list[0])).lower() if cmd_list else ""
            if "adb" in exe:
                ret, out, err = state.handle_command(cmd_list, stdin=kwargs.get("stdin"))
                return subprocess.CompletedProcess(args=cmd, returncode=ret, stdout=out, stderr=err)
            return self._orig_run(cmd, *args, **kwargs)

        def mock_check_output(cmd, *args, **kwargs):
            cmd_list = cmd if isinstance(cmd, list) else shlex.split(str(cmd))
            exe = os.path.basename(str(cmd_list[0])).lower() if cmd_list else ""
            if "adb" in exe:
                ret, out, err = state.handle_command(cmd_list, stdin=kwargs.get("stdin"))
                if ret != 0:
                    raise subprocess.CalledProcessError(ret, cmd, output=out, stderr=err)
                return out
            return self._orig_check_output(cmd, *args, **kwargs)

        subprocess.run = mock_run
        subprocess.check_output = mock_check_output
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        subprocess.run = self._orig_run
        subprocess.check_output = self._orig_check_output


class MockAdbServer:
    """Convenience adapter exposing an executable_path and direct run_cmd method."""

    def __init__(self, state: Optional[MockAdbState] = None):
        self.state = state or MockAdbState()
        self.executable_path = "mock_adb"

    def run_cmd(self, cmd: List[str], serial: Optional[str] = None, stdin: Optional[Any] = None) -> subprocess.CompletedProcess:
        full_cmd = ["mock_adb"]
        if serial:
            full_cmd.extend(["-s", serial])
        full_cmd.extend(cmd)
        ret, out, err = self.state.handle_command(full_cmd, stdin=stdin)
        return subprocess.CompletedProcess(args=full_cmd, returncode=ret, stdout=out, stderr=err)
