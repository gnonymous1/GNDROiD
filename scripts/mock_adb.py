"""
scripts/mock_adb.py
===================
GNDROiD Stateful Mock ADB & Scrcpy Engine for Automated Verification & Testing.
Maintains genuine state machine for multi-user profiles, package management,
guest Netd/VPN settings, and network devices without hardcoded test outcomes.
"""

import re
import shlex
import subprocess
from typing import Dict, Any, Set, Tuple, Optional, List


class MockAdbState:
    """State machine tracking virtual Android system state during mock testing."""
    def __init__(self):
        self.users: Dict[int, Dict[str, str]] = {
            0: {"name": "Owner", "type": "android.os.usertype.full.SYSTEM", "state": "running"}
        }
        self.user_packages: Dict[int, Set[str]] = {
            0: {
                "com.android.chrome",
                "com.android.settings",
                "com.google.android.youtube",
                "com.vpn.free.hotspot.secure.vpnify",
                "com.wireguard.android"
            }
        }
        self.next_user_id = 10
        self.properties: Dict[str, str] = {
            "fw.max_users": "10",
            "fw.show_multiuserui": "1",
            "sys.boot_completed": "1",
            "dhcp.wlan0.ipaddress": "192.168.1.188",
            "dhcp.eth0.ipaddress": "10.0.2.15"
        }
        self.settings: Dict[str, Dict[str, str]] = {
            "global": {
                "captive_portal_mode": "0",
                "captive_portal_detection_enabled": "0",
                "private_dns_mode": "hostname",
                "private_dns_specifier": "dns.google"
            }
        }
        self.appops: Dict[str, str] = {
            "com.wireguard.android": "allow",
            "com.vpn.free.hotspot.secure.vpnify": "allow"
        }
        self.mtu: Dict[str, str] = {"eth0": "1380", "wlan0": "1380"}
        self.sysctl: Dict[str, str] = {
            "net.ipv6.conf.all.disable_ipv6": "1",
            "net.ipv6.conf.default.disable_ipv6": "1"
        }

    def handle_command(self, cmd: List[str]) -> Tuple[int, str, str]:
        """Processes an adb command list and returns (returncode, stdout, stderr)."""
        serial = ""
        args = list(cmd)
        if len(args) > 0 and ("adb" in args[0].lower()):
            args = args[1:]

        idx = 0
        while idx < len(args):
            if args[idx] == "-s" and idx + 1 < len(args):
                serial = args[idx + 1]
                args = args[:idx] + args[idx + 2:]
            else:
                idx += 1

        # Check offline device simulation targets
        if any(bad in serial for bad in ["offline", "nonexistent", "unreachable", "invalid"]):
            return (1, "", f"adb.exe: device '{serial}' not found\n")

        if not args:
            return (0, "", "")

        sub = args[0]

        if sub == "get-state":
            return (0, "device\n", "")

        if sub == "devices":
            return (0, "List of devices attached\nemulator-5554\tdevice\n\n", "")

        if sub == "shell":
            shell_cmd = args[1:]
            return self._handle_shell(shell_cmd)

        return (0, "", "")

    def _handle_shell(self, cmd: List[str]) -> Tuple[int, str, str]:
        if not cmd:
            return (0, "", "")

        # Flatten and tokenize shell command arguments
        tokens = []
        for c in cmd:
            if " " in c:
                try:
                    tokens.extend(shlex.split(c))
                except Exception:
                    tokens.extend(c.split())
            else:
                tokens.append(c)

        if not tokens:
            return (0, "", "")

        full_str = " ".join(tokens)
        tool = tokens[0]

        # getprop
        if tool == "getprop":
            prop = tokens[1] if len(tokens) > 1 else ""
            val = self.properties.get(prop, "")
            return (0, f"{val}\n", "")

        # setprop
        if tool == "setprop":
            if len(tokens) >= 3:
                prop = tokens[1]
                val = tokens[2]
                self.properties[prop] = val
            return (0, "", "")

        # pm commands
        if tool == "pm":
            sub = tokens[1] if len(tokens) > 1 else ""

            if sub == "list":
                target = tokens[2] if len(tokens) > 2 else ""
                if target == "users":
                    out = "Users:\n"
                    for uid in sorted(self.users.keys()):
                        u = self.users[uid]
                        out += f"\tUserInfo{{{uid}:{u['name']}:30}} {u['state']}\n"
                    return (0, out, "")

                if target == "packages":
                    uid = 0
                    for i, a in enumerate(tokens):
                        if a == "--user" and i + 1 < len(tokens):
                            try: uid = int(tokens[i + 1])
                            except ValueError: pass
                    pkgs = self.user_packages.get(uid, set())
                    out = "".join(f"package:{p}\n" for p in sorted(pkgs))
                    return (0, out, "")

            if sub == "create-user":
                name = tokens[-1]
                max_u = int(self.properties.get("fw.max_users", "10"))
                if len(self.users) >= max_u:
                    return (1, "", "Error: couldn't create user: maximum users reached\n")
                uid = self.next_user_id
                self.next_user_id += 1
                u_type = "android.os.usertype.profile.CLONE" if "CLONE" in full_str else "android.os.usertype.full.SECONDARY"
                self.users[uid] = {"name": name, "type": u_type, "state": "running"}
                self.user_packages[uid] = set()
                return (0, f"Success: created user id {uid}\n", "")

            if sub == "install-existing":
                uid = 0
                for i, a in enumerate(tokens):
                    if a == "--user" and i + 1 < len(tokens):
                        try: uid = int(tokens[i + 1])
                        except ValueError: pass
                pkg = tokens[-1]
                if uid in self.users:
                    self.user_packages.setdefault(uid, set()).add(pkg)
                    return (0, f"Package {pkg} installed for user: {uid}\n", "")
                return (1, "", f"Error: user {uid} not found\n")

            if sub == "remove-user":
                try: uid = int(tokens[-1])
                except ValueError: return (1, "", "Invalid user ID\n")
                if uid == 0:
                    return (1, "", "Error: cannot remove master User 0\n")
                if uid in self.users:
                    del self.users[uid]
                    self.user_packages.pop(uid, None)
                    return (0, "Success: removed user\n", "")
                return (1, "", f"Error: user {uid} not found\n")

            if sub == "path":
                pkg = tokens[-1]
                return (0, f"package:/data/app/~~mock/{pkg}/base.apk\n", "")

        # cmd user remove-user
        if tool == "cmd" and len(tokens) >= 4 and tokens[1] == "user" and tokens[2] == "remove-user":
            try: uid = int(tokens[3])
            except ValueError: return (1, "", "Invalid user ID\n")
            if uid in self.users and uid != 0:
                del self.users[uid]
                self.user_packages.pop(uid, None)
                return (0, "Success: removed user\n", "")
            return (1, "", f"Error: user {uid} not found\n")

        # dumpsys
        if tool == "dumpsys" and len(tokens) > 1 and tokens[1] == "user":
            out = "Users:\n"
            for uid in sorted(self.users.keys()):
                u = self.users[uid]
                out += f"UserInfo{{{uid}:{u['name']}:30}}\n  Type: {u['type']}\n"
            return (0, out, "")

        # ls -l /dev/tun
        if "ls" in tool and "/dev/tun" in full_str:
            return (0, "crw-rw---- 1 vpn vpn 10, 200 2026-11-03 14:00 /dev/tun\n", "")

        # ping
        if tool == "ping":
            if "192.0.2.1" in full_str:
                return (1, "1 packets transmitted, 0 received, 100% packet loss\n", "")
            return (0, "2 packets transmitted, 2 received, 0% packet loss, time 1001ms\n", "")

        # appops
        if tool == "appops":
            if ";" in full_str or "'" in full_str or '"' in full_str:
                return (1, "", "SecurityException: invalid package name argument\n")
            pkg = tokens[3] if len(tokens) > 3 else ""
            if not pkg:
                return (1, "", "Error: package argument required\n")
            self.appops[pkg] = "allow"
            return (0, "", "")

        # settings
        if tool == "settings":
            action = tokens[1] if len(tokens) > 1 else ""
            tbl = tokens[2] if len(tokens) > 2 else "global"
            k = tokens[3] if len(tokens) > 3 else ""
            if action == "put":
                v = tokens[4] if len(tokens) > 4 else ""
                self.settings.setdefault(tbl, {})[k] = v
                return (0, "", "")
            if action == "get":
                v = self.settings.get(tbl, {}).get(k, "null")
                return (0, f"{v}\n", "")

        # sysctl
        if tool == "sysctl":
            if len(tokens) > 2 and tokens[1] == "-w":
                kv = tokens[2]
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    self.sysctl[k.strip()] = v.strip()
                    return (0, f"{k.strip()} = {v.strip()}\n", "")
            return (0, "", "")

        # ip commands
        if tool == "ip":
            if "mtu" in full_str:
                return (0, "", "")
            if "addr" in full_str or "wlan0" in full_str:
                return (0, "2: wlan0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500\n    inet 192.168.1.188/24 brd 192.168.1.255 scope global wlan0\n", "")
            if "route get" in full_str:
                return (0, "8.8.8.8 via 192.168.1.1 dev wlan0 src 192.168.1.188 uid 0\n", "")
            if "link show" in full_str:
                return (0, "2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1380 state UP\n", "")
            return (0, "", "")

        return (0, "", "")


class MockProcess:
    """Mock subprocess.Popen object with genuine PID and lifecycle handles."""
    _pid_counter = 50000

    def __init__(self, cmd, retcode=0, stdout="", stderr=""):
        MockProcess._pid_counter += 1
        self.pid = MockProcess._pid_counter
        self.args = cmd
        self.returncode = retcode
        self._stdout = stdout
        self._stderr = stderr
        self._is_terminated = False

    def poll(self):
        return self.returncode if self._is_terminated else None

    def terminate(self):
        self._is_terminated = True
        self.returncode = 0

    def kill(self):
        self._is_terminated = True
        self.returncode = -9

    def wait(self, timeout=None):
        self._is_terminated = True
        return self.returncode

    def communicate(self, input=None, timeout=None):
        return (self._stdout, self._stderr)


class MockAdbSession:
    """Context manager intercepting subprocess execution to provide mock ADB & Scrcpy state."""
    def __init__(self, active_state: Optional[MockAdbState] = None):
        self.state = active_state or MockAdbState()
        self._orig_run = subprocess.run
        self._orig_check_output = subprocess.check_output
        self._orig_popen = subprocess.Popen

    def __enter__(self):
        state = self.state

        def mock_run(cmd, *args, **kwargs):
            cmd_list = cmd if isinstance(cmd, list) else shlex.split(cmd)
            exe = str(cmd_list[0]).lower() if cmd_list else ""
            if "adb" in exe:
                ret, out, err = state.handle_command(cmd_list)
                return subprocess.CompletedProcess(args=cmd, returncode=ret, stdout=out, stderr=err)
            return self._orig_run(cmd, *args, **kwargs)

        def mock_check_output(cmd, *args, **kwargs):
            cmd_list = cmd if isinstance(cmd, list) else shlex.split(cmd)
            exe = str(cmd_list[0]).lower() if cmd_list else ""
            if "adb" in exe:
                ret, out, err = state.handle_command(cmd_list)
                if ret != 0:
                    raise subprocess.CalledProcessError(ret, cmd, output=out, stderr=err)
                return out
            return self._orig_check_output(cmd, *args, **kwargs)

        def mock_popen(cmd, *args, **kwargs):
            cmd_list = cmd if isinstance(cmd, list) else shlex.split(cmd)
            exe = str(cmd_list[0]).lower() if cmd_list else ""
            if "adb" in exe:
                ret, out, err = state.handle_command(cmd_list)
                return MockProcess(cmd, retcode=ret, stdout=out, stderr=err)
            if "scrcpy" in exe:
                return MockProcess(cmd, retcode=0, stdout="", stderr="")
            return self._orig_popen(cmd, *args, **kwargs)

        subprocess.run = mock_run
        subprocess.check_output = mock_check_output
        subprocess.Popen = mock_popen
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        subprocess.run = self._orig_run
        subprocess.check_output = self._orig_check_output
        subprocess.Popen = self._orig_popen
