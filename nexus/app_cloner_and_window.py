"""
GNDROiD Native App Cloner & Dedicated Multi-Window Engine
Author: Ghulam Nabi Kalhoro / GNDROiD Core Team
Workspace: c:\\Users\\Reader-Branch\\Desktop\\Android Emulator

Provides:
  1. AppCloneManager: Android Native Multi-User / App Cloner Engine (AOSP user profiles)
  2. AppWindowManager: Dedicated Separate Floating Windows per App / Clone via Scrcpy Virtual Displays
"""

import os
import sys
import re
import time
import shutil
import logging
import subprocess
import threading
import ctypes
from ctypes import wintypes
from typing import List, Dict, Any, Optional

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] [NexusCloner] %(message)s")
logger = logging.getLogger("NexusAppCloner")

CREATE_NO_WINDOW = 0x08000000


class Win32JobManager:
    """
    Win32 Job Object manager for child process containment and orphan prevention.
    Configured with JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE so child processes terminate
    cleanly when the host application exits or crashes.
    """
    _instance: Optional["Win32JobManager"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._job_handle = None
        self._tracked_pids = set()
        self._tracked_procs: List[subprocess.Popen] = []
        self._init_job_object()

    @classmethod
    def get_instance(cls) -> "Win32JobManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = Win32JobManager()
            return cls._instance

    def _init_job_object(self):
        if sys.platform != "win32":
            return
        try:
            k32 = ctypes.windll.kernel32
            JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
            JobObjectExtendedLimitInformation = 9

            class IO_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ('ReadOperationCount', ctypes.c_uint64),
                    ('WriteOperationCount', ctypes.c_uint64),
                    ('OtherOperationCount', ctypes.c_uint64),
                    ('ReadTransferCount', ctypes.c_uint64),
                    ('WriteTransferCount', ctypes.c_uint64),
                    ('OtherTransferCount', ctypes.c_uint64),
                ]

            class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ('PerProcessUserTimeLimit', ctypes.c_int64),
                    ('PerJobUserTimeLimit', ctypes.c_int64),
                    ('LimitFlags', wintypes.DWORD),
                    ('MinimumWorkingSetSize', ctypes.c_size_t),
                    ('MaximumWorkingSetSize', ctypes.c_size_t),
                    ('ActiveProcessLimit', wintypes.DWORD),
                    ('Affinity', ctypes.c_size_t),
                    ('PriorityClass', wintypes.DWORD),
                    ('SchedulingClass', wintypes.DWORD),
                ]

            class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ('BasicLimitInformation', JOBOBJECT_BASIC_LIMIT_INFORMATION),
                    ('IoInfo', IO_COUNTERS),
                    ('ProcessMemoryLimit', ctypes.c_size_t),
                    ('JobMemoryLimit', ctypes.c_size_t),
                    ('PeakProcessMemoryLimit', ctypes.c_size_t),
                    ('PeakJobMemoryLimit', ctypes.c_size_t),
                ]

            h_job = k32.CreateJobObjectW(None, None)
            if h_job:
                info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
                info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                res = k32.SetInformationJobObject(
                    h_job,
                    JobObjectExtendedLimitInformation,
                    ctypes.byref(info),
                    ctypes.sizeof(info)
                )
                if res:
                    self._job_handle = h_job
                    logger.info(f"Win32 Job Object initialized successfully (handle={h_job}) with KILL_ON_JOB_CLOSE.")
        except Exception as e:
            logger.debug(f"Job Object initialization note: {e}")

    def assign_process(self, proc_or_pid) -> bool:
        """
        Assigns a subprocess.Popen object or an integer PID to the Job Object.
        Also tracks the process object for graceful shutdown.
        """
        if proc_or_pid is None:
            return False

        proc = proc_or_pid if isinstance(proc_or_pid, subprocess.Popen) else None
        pid = proc.pid if proc else int(proc_or_pid)

        with self._lock:
            self._tracked_pids.add(pid)
            if proc and proc not in self._tracked_procs:
                self._tracked_procs.append(proc)

        if sys.platform != "win32" or not self._job_handle:
            return True

        try:
            k32 = ctypes.windll.kernel32
            # 1. Prefer proc._handle if available (opened with PROCESS_ALL_ACCESS)
            if proc and hasattr(proc, "_handle") and proc._handle:
                res = k32.AssignProcessToJobObject(self._job_handle, int(proc._handle))
                if res:
                    return True

            # 2. OpenProcess fallback
            PROCESS_SET_QUOTA = 0x0100
            PROCESS_TERMINATE = 0x0001
            h_proc = k32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, pid)
            if h_proc:
                try:
                    res = k32.AssignProcessToJobObject(self._job_handle, h_proc)
                    return bool(res)
                finally:
                    k32.CloseHandle(h_proc)
        except Exception as e:
            logger.debug(f"AssignProcessToJobObject note for PID {pid}: {e}")
        return False

    def get_tracked_pids(self) -> List[int]:
        with self._lock:
            return list(self._tracked_pids)

    def terminate_all_tracked_processes(self, timeout: float = 3.0):
        """Gracefully terminates and waits for all tracked child processes."""
        with self._lock:
            procs = list(self._tracked_procs)

        for p in procs:
            if hasattr(p, "poll") and p.poll() is None:
                try:
                    p.terminate()
                except Exception:
                    pass

        start = time.time()
        for p in procs:
            remaining = max(0.1, timeout - (time.time() - start))
            if hasattr(p, "poll") and p.poll() is None:
                try:
                    p.wait(timeout=remaining)
                except Exception:
                    try:
                        p.kill()
                    except Exception:
                        pass


def get_job_manager() -> Win32JobManager:
    return Win32JobManager.get_instance()


def assign_to_job_object(proc_or_pid) -> bool:
    return Win32JobManager.get_instance().assign_process(proc_or_pid)



def get_base_dir() -> str:
    """Returns the GNDROiD project base directory."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    cur = os.path.dirname(os.path.abspath(__file__))
    # If in nexus/ subdirectory, root is the parent
    if os.path.basename(cur).lower() == "nexus":
        return os.path.dirname(cur)
    return cur


def get_adb() -> str:
    """Resolves path to adb.exe."""
    base = get_base_dir()
    for cand in [
        os.path.join(base, "adb.exe"),
        os.path.join(base, "dist", "gndroid", "adb.exe"),
        os.path.join(base, "dist", "AndroidMobilePlayer", "adb.exe"),
        os.path.join(base, "scrcpy", "adb.exe"),
    ]:
        if os.path.exists(cand):
            return cand
    for env_k in ["ANDROID_HOME", "ANDROID_SDK_ROOT"]:
        v = os.environ.get(env_k)
        if v:
            cand = os.path.join(v, "platform-tools", "adb.exe")
            if os.path.exists(cand):
                return cand
    loc = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk", "platform-tools", "adb.exe")
    if os.path.exists(loc):
        return loc
    return "adb"


def get_scrcpy() -> str:
    """Resolves path to scrcpy.exe."""
    base = get_base_dir()
    for cand in [
        os.path.join(base, "dist", "gndroid", "scrcpy.exe"),
        os.path.join(base, "scrcpy.exe"),
        os.path.join(base, "dist", "AndroidMobilePlayer", "scrcpy.exe"),
        os.path.join(base, "scrcpy", "scrcpy.exe"),
    ]:
        if os.path.exists(cand):
            return cand
    w = shutil.which("scrcpy")
    return w if w else "scrcpy"


def get_icon() -> str:
    """Resolves path to gndroid icon."""
    base = get_base_dir()
    for cand in [
        os.path.join(base, "gndroid.ico"),
        os.path.join(base, "dist", "gndroid", "gndroid.ico"),
    ]:
        if os.path.exists(cand):
            return cand
    return ""


def run_adb_shell(serial: str, shell_args: List[str], timeout: int = 15, retries: int = 3) -> subprocess.CompletedProcess:
    """Helper to run an adb shell command cleanly without popping a console window, with automatic retry for transient socket resets."""
    adb = get_adb()
    cmd = [adb]
    if serial:
        cmd.extend(["-s", serial])
    cmd.append("shell")
    cmd.extend(shell_args)
    last_res = None
    for attempt in range(retries):
        last_res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            creationflags=CREATE_NO_WINDOW,
            timeout=timeout
        )
        out_err = (last_res.stdout + " " + last_res.stderr).lower()
        # If succeeded cleanly, return immediately
        if last_res.returncode == 0 and "error: closed" not in out_err and "can't find service" not in out_err:
            return last_res
        if ("error: closed" in out_err or "device offline" in out_err or "can't find service" in out_err) and attempt < retries - 1:
            time.sleep(1.5)
        else:
            return last_res
    return last_res


class AppCloneEntry(dict):
    """Represents an app package entry with master/clone tagging."""
    def __init__(self, package_name: str, user_id: int, app_title: str = ""):
        super().__init__()
        user_tag = "[Master]" if user_id == 0 else f"[Clone #{user_id}]"
        label = f"{package_name} {user_tag}"
        self["package_name"] = package_name
        self["user_id"] = user_id
        self["label"] = label
        self["user_label"] = user_tag
        self["is_clone"] = (user_id != 0)
        self["display_name"] = app_title or package_name.split(".")[-1].capitalize()

    def __str__(self) -> str:
        return self["label"]

    def __repr__(self) -> str:
        return f"<AppCloneEntry {self['label']}>"


class AppCloneManager:
    """
    Native Android App Cloner Engine.
    Uses AOSP user profile sandboxing (`android.os.usertype.profile.CLONE` or secondary users).
    Enables true zero-APK modification multi-account app isolation.
    """

    @staticmethod
    def get_clone_users(serial: str) -> List[Dict[str, Any]]:
        """
        Parses `pm list users` and returns existing clone profiles
        (`android.os.usertype.profile.CLONE` or secondary users with user_id != 0).
        """
        logger.info(f"Retrieving clone users for device: {serial}")
        clone_users: List[Dict[str, Any]] = []

        try:
            res = run_adb_shell(serial, ["pm", "list", "users"], timeout=10)
            if res.returncode != 0:
                logger.warning(f"pm list users returned code {res.returncode}: {res.stderr}")
                return clone_users

            # Query dumpsys user to inspect exact user types (e.g. android.os.usertype.profile.CLONE)
            user_types: Dict[int, str] = {}
            try:
                dumpsys_res = run_adb_shell(serial, ["dumpsys", "user"], timeout=10)
                if dumpsys_res.returncode == 0:
                    current_uid = None
                    for line in dumpsys_res.stdout.splitlines():
                        m_uid = re.search(r"UserInfo\{(\d+):", line)
                        if m_uid:
                            current_uid = int(m_uid.group(1))
                        elif current_uid is None:
                            m_uid2 = re.search(r"User\s+(\d+):", line)
                            if m_uid2:
                                current_uid = int(m_uid2.group(1))
                        if current_uid is not None:
                            m_type = re.search(r"Type:\s*([a-zA-Z0-9_\.]+)", line)
                            if m_type:
                                user_types[current_uid] = m_type.group(1)
                                current_uid = None
            except Exception as e:
                logger.debug(f"dumpsys user query note: {e}")

            # Typical line: UserInfo{10:GNDROiD Clone 1:10000030} running
            # or UserInfo{10:Clone 1:30}
            for line in res.stdout.splitlines():
                line = line.strip()
                m = re.search(r"UserInfo\{(\d+):([^:]*):([0-9a-fA-F]+)\}(?:\s+(\w+))?", line)
                if m:
                    uid = int(m.group(1))
                    name = m.group(2)
                    flags = m.group(3)
                    state = m.group(4) or "unknown"

                    # user_id 0 is Master / Owner; non-zero are clone or secondary profiles
                    if uid != 0:
                        u_type = user_types.get(uid, "android.os.usertype.profile.CLONE")
                        user_info = {
                            "id": uid,
                            "user_id": uid,
                            "name": name,
                            "flags": flags,
                            "state": state,
                            "running": (state.lower() == "running"),
                            "type": u_type,
                            "is_clone": True
                        }
                        clone_users.append(user_info)
                        logger.info(f"Found clone user: ID={uid}, Name='{name}', Type='{u_type}', State='{state}'")

        except Exception as e:
            logger.error(f"Error getting clone users: {e}")

        return clone_users

    @staticmethod
    def create_clone_user(serial: str, name: str = "GNDROiD Clone 1") -> int:
        """
        Tiered Multi-Clone Creation:
        1. If no clone profile exists for user 0, attempt:
           `pm create-user --profileOf 0 --user-type android.os.usertype.profile.CLONE <name>`.
        2. If that fails with `Cannot add more profiles of type ... CLONE` (error code 6)
           or if a clone profile already exists, seamlessly fall back to creating a secondary user:
           `pm create-user <name>` (ensuring `setprop fw.max_users 32`).
        3. Activate profile via `am start-user <userId>`.
        4. Return the new `userId` (e.g. 10). Returns -1 on failure.
        """
        logger.info(f"Creating clone profile '{name}' on device: {serial}")
        user_id = -1

        try:
            # Query existing users and clone profiles before creation
            pre_users = set()
            try:
                res_pre = run_adb_shell(serial, ["pm", "list", "users"], timeout=5)
                for line in res_pre.stdout.splitlines():
                    m = re.search(r"UserInfo\{(\d+):", line)
                    if m:
                        pre_users.add(int(m.group(1)))
            except Exception:
                pass

            existing_clones = AppCloneManager.get_clone_users(serial)
            has_clone_profile = any(u.get("type") == "android.os.usertype.profile.CLONE" for u in existing_clones)

            attempt_clone_profile = not has_clone_profile
            combined_out = ""

            if attempt_clone_profile:
                # 1. Primary approach: AOSP native clone profile linked to user 0
                cmd1 = ["pm", "create-user", "--profileOf", "0", "--user-type", "android.os.usertype.profile.CLONE", name]
                res = run_adb_shell(serial, cmd1, timeout=20)
                combined_out = res.stdout + " " + res.stderr

                m = re.search(r"(?:created\s+user\s+id|user\s+id|id)\s*[:=]?\s*(\d+)", combined_out, re.IGNORECASE)
                if res.returncode == 0 and m:
                    user_id = int(m.group(1))
                    logger.info(f"Successfully created clone profile {user_id} via CLONE user-type")
                else:
                    logger.warning(f"CLONE profileOf creation output: {combined_out.strip()}. Attempting fallback secondary user creation...")
            else:
                logger.info("Clone profile already exists for User 0; seamlessly creating secondary user profile.")

            if user_id <= 0:
                # 2. Seamless Fallback: ensure setprop fw.max_users 32 and create secondary user
                run_adb_shell(serial, ["setprop", "fw.max_users", "32"], timeout=5)
                run_adb_shell(serial, ["setprop", "fw.show_multiuserui", "1"], timeout=5)

                cmd2 = ["pm", "create-user", name]
                res2 = run_adb_shell(serial, cmd2, timeout=20)
                combined_out2 = res2.stdout + " " + res2.stderr
                m2 = re.search(r"(?:created\s+user\s+id|user\s+id|id)\s*[:=]?\s*(\d+)", combined_out2, re.IGNORECASE)
                if m2:
                    user_id = int(m2.group(1))
                    logger.info(f"Successfully created user {user_id} via fallback pm create-user")
                else:
                    # 3. Third approach: check user diff in pm list users
                    try:
                        res_post = run_adb_shell(serial, ["pm", "list", "users"], timeout=5)
                        post_users = set()
                        for line in res_post.stdout.splitlines():
                            mp = re.search(r"UserInfo\{(\d+):", line)
                            if mp:
                                post_users.add(int(mp.group(1)))
                        diff = post_users - pre_users
                        if diff:
                            user_id = list(diff)[0]
                            logger.info(f"Discovered created user ID {user_id} via pre/post diff")
                    except Exception as diff_ex:
                        logger.error(f"Diff discovery error: {diff_ex}")

            if user_id <= 0:
                logger.error(f"All create-user strategies failed: {combined_out.strip()} | {combined_out2 if 'combined_out2' in locals() else ''}")
                return -1

            # 4. Start user runtime
            logger.info(f"Starting user {user_id} via am start-user...")
            start_res = run_adb_shell(serial, ["am", "start-user", str(user_id)], timeout=15)
            logger.info(f"am start-user output: {start_res.stdout.strip()}")
            # Give Android user runtime 1.5 seconds to spin up essential user services
            time.sleep(1.5)
            return user_id

        except Exception as e:
            logger.error(f"Exception during create_clone_user: {e}")

        return user_id

    @staticmethod
    def clone_app_to_user(serial: str, package_name: str, user_id: int) -> bool:
        """
        Executes `pm install-existing --user <userId> <package_name>`
        to provision an isolated sandbox with zero APK modifications.
        Returns True on success.
        """
        logger.info(f"Cloning package '{package_name}' into User {user_id} sandbox on device: {serial}")
        try:
            res = run_adb_shell(serial, ["pm", "install-existing", "--user", str(user_id), package_name], timeout=25)
            out = (res.stdout + " " + res.stderr).lower()
            logger.info(f"pm install-existing output: {out.strip()}")

            if res.returncode == 0 and ("installed" in out or "package" in out) and "error" not in out and "exception" not in out:
                logger.info(f"Package '{package_name}' cloned successfully into user {user_id}!")
                return True

            # Fallback with cmd package install-existing
            cmd_res = run_adb_shell(serial, ["cmd", "package", "install-existing", "--user", str(user_id), package_name], timeout=25)
            cmd_out = (cmd_res.stdout + " " + cmd_res.stderr).lower()
            if cmd_res.returncode == 0 and ("installed" in cmd_out or "package" in cmd_out) and "error" not in cmd_out:
                logger.info(f"Package '{package_name}' cloned successfully via cmd package into user {user_id}!")
                return True

            logger.error(f"Failed to clone package '{package_name}': {out} | {cmd_out}")
            return False

        except Exception as e:
            logger.error(f"Exception during clone_app_to_user: {e}")
            return False

    @staticmethod
    def remove_clone_user(serial: str, user_id: int) -> bool:
        """
        Executes `pm remove-user <userId>`.
        Returns True on success.
        """
        if user_id == 0:
            logger.warning("Refusing to remove master User 0!")
            return False

        logger.info(f"Removing clone user profile {user_id} on device: {serial}")
        try:
            res = run_adb_shell(serial, ["pm", "remove-user", str(user_id)], timeout=20)
            out = (res.stdout + " " + res.stderr).lower()
            logger.info(f"pm remove-user output: {out.strip()}")

            if res.returncode == 0 and ("success" in out or "removed" in out) and "error" not in out:
                return True

            # Fallback: cmd user remove-user
            cmd_res = run_adb_shell(serial, ["cmd", "user", "remove-user", str(user_id)], timeout=20)
            return cmd_res.returncode == 0
        except Exception as e:
            logger.error(f"Exception removing user {user_id}: {e}")
            return False

    @staticmethod
    def list_apps_with_clones(serial: str) -> List[AppCloneEntry]:
        """
        Returns all third-party and main packages for User 0 and any clone user profiles
        with labels like `[Master]` and `[Clone #10]`.
        """
        logger.info(f"Listing apps across all master and clone profiles for device: {serial}")
        app_entries: List[AppCloneEntry] = []

        # 1. Discover all active users (Master 0 + Clones)
        clone_users = AppCloneManager.get_clone_users(serial)
        user_ids = [0] + [u["id"] for u in clone_users]

        def fetch_user_packages(uid: int) -> List[str]:
            pkgs = set()
            # A. Third-party packages
            res_3p = run_adb_shell(serial, ["pm", "list", "packages", "--user", str(uid), "-3"], timeout=10)
            for line in res_3p.stdout.splitlines():
                if line.startswith("package:"):
                    p = line.split(":", 1)[1].strip()
                    if p:
                        pkgs.add(p)

            # B. Launchable activities for that user
            res_launch = run_adb_shell(
                serial,
                ["cmd", "package", "query-activities", "--user", str(uid), "-a", "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER"],
                timeout=10
            )
            for line in res_launch.stdout.splitlines():
                line = line.strip()
                m_pkg = re.search(r"packageName=([a-zA-Z0-9_\.]+)", line)
                if m_pkg:
                    pkgs.add(m_pkg.group(1))
                elif "/" in line:
                    cand = line.split("/")[0].split()[-1]
                    if "." in cand:
                        pkgs.add(cand)

            # C. Main built-in apps if launcher query was empty (e.g. Chrome, Settings, Camera)
            if not pkgs:
                res_all = run_adb_shell(serial, ["pm", "list", "packages", "--user", str(uid)], timeout=10)
                for line in res_all.stdout.splitlines():
                    if line.startswith("package:"):
                        p = line.split(":", 1)[1].strip()
                        if any(k in p for k in ["chrome", "browser", "youtube", "gallery", "camera", "deskclock", "settings", "calculator"]):
                            pkgs.add(p)

            return sorted(list(pkgs))

        for uid in user_ids:
            pkgs = fetch_user_packages(uid)
            for pkg in pkgs:
                # Derive friendly title
                short_name = pkg.split(".")[-1].capitalize()
                entry = AppCloneEntry(package_name=pkg, user_id=uid, app_title=short_name)
                app_entries.append(entry)

        return app_entries


class AppWindowManager:
    """
    Dedicated Separate Floating Windows per App / Clone.
    Leverages Scrcpy 4.1 virtual display engine (`--new-display`) to project
    individual Android apps and isolated clone sandboxes directly onto the Windows desktop.
    """
    _active_windows: List[Dict[str, Any]] = []
    _windows_lock = threading.Lock()

    @classmethod
    def get_active_windows(cls) -> List[Dict[str, Any]]:
        """Returns a snapshot of all active dedicated floating app windows."""
        with cls._windows_lock:
            # Purge terminated processes
            cls._active_windows = [
                w for w in cls._active_windows
                if w.get("proc") and (hasattr(w["proc"], "poll") and w["proc"].poll() is None)
            ]
            return list(cls._active_windows)

    @classmethod
    def terminate_all_windows(cls, timeout: float = 2.0):
        """Gracefully terminates and closes all dedicated floating app windows."""
        with cls._windows_lock:
            procs = [w.get("proc") for w in cls._active_windows if w.get("proc")]
            cls._active_windows.clear()

        for p in procs:
            if hasattr(p, "poll") and p.poll() is None:
                try:
                    p.terminate()
                except Exception:
                    pass

        start = time.time()
        for p in procs:
            rem = max(0.05, timeout - (time.time() - start))
            if hasattr(p, "poll") and p.poll() is None:
                try:
                    p.wait(timeout=rem)
                except Exception:
                    try:
                        p.kill()
                    except Exception:
                        pass

    @staticmethod
    def launch_app_in_dedicated_window(
        serial: str,
        package_name: str,
        app_title: str,
        user_id: int = 0,
        width: int = 1080,
        height: int = 2400,
        density: int = 420
    ) -> subprocess.Popen:
        """
        Uses bundled scrcpy.exe (dist/gndroid/scrcpy.exe or SystemPaths) with:
        ["scrcpy", "-s", serial, f"--new-display={width}x{height}/{density}", f"--start-app=+{package_name}",
         f"--window-title=GNDROiD: {app_title}" + (f" [Clone #{user_id}]" if user_id != 0 else ""),
         "--no-audio", "--pause-on-exit=false", "-x"]

        Spawns with creationflags = 0x08000000 (CREATE_NO_WINDOW) so no black terminal flashes.
        Returns the spawned subprocess.Popen handle.
        """
        scrcpy_exe = get_scrcpy()
        if not os.path.exists(scrcpy_exe):
            logger.warning(f"Scrcpy executable '{scrcpy_exe}' not found directly, checking fallback...")

        window_title = f"GNDROiD: {app_title}" + (f" [Clone #{user_id}]" if user_id != 0 else "")

        cmd = [
            scrcpy_exe,
            "-s", serial,
            f"--new-display={width}x{height}/{density}",
            f"--start-app=+{package_name}",
            f"--window-title={window_title}",
            "--no-audio",
            "--pause-on-exit=false",
            "-x"
        ]

        logger.info(f"Launching dedicated floating app window: {' '.join(cmd)}")
        scrcpy_dir = os.path.dirname(scrcpy_exe) if os.path.isabs(scrcpy_exe) else get_base_dir()

        proc = subprocess.Popen(
            cmd,
            cwd=scrcpy_dir,
            creationflags=CREATE_NO_WINDOW,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        # Assign process to Win32 Job Object for strict lifecycle containment
        try:
            Win32JobManager.get_instance().assign_process(proc)
        except Exception as e:
            logger.debug(f"Job Object assignment note for dedicated window: {e}")

        # Register in active instance registry
        entry = {
            "proc": proc,
            "pid": proc.pid if hasattr(proc, "pid") else None,
            "serial": serial,
            "package": package_name,
            "app_title": app_title,
            "user_id": user_id,
            "window_title": window_title,
            "launch_time": time.time()
        }
        with AppWindowManager._windows_lock:
            AppWindowManager._active_windows.append(entry)

        # If user_id is a clone profile, dispatch background trigger to ensure
        # the clone user's isolated data sandbox is foregrounded on the newly opened virtual display
        if user_id != 0:
            def _ensure_clone_user_active():
                time.sleep(1.5)
                adb = get_adb()
                target_disp = None
                try:
                    res = subprocess.run(
                        [adb, "-s", serial, "shell", "dumpsys", "window", "displays"],
                        capture_output=True,
                        text=True,
                        creationflags=CREATE_NO_WINDOW,
                        timeout=5
                    )
                    for line in res.stdout.splitlines():
                        m = re.search(r"mDisplayId=(\d+)", line)
                        if m and int(m.group(1)) != 0:
                            target_disp = int(m.group(1))
                            break
                except Exception as ex:
                    logger.debug(f"Virtual display query note: {ex}")

                try:
                    if target_disp is not None:
                        subprocess.run(
                            [adb, "-s", serial, "shell", "am", "start", "--user", str(user_id), "--display", str(target_disp), package_name],
                            capture_output=True,
                            text=True,
                            creationflags=CREATE_NO_WINDOW,
                            timeout=5
                        )
                    else:
                        subprocess.run(
                            [adb, "-s", serial, "shell", "am", "start", "--user", str(user_id), package_name],
                            capture_output=True,
                            text=True,
                            creationflags=CREATE_NO_WINDOW,
                            timeout=5
                        )
                except Exception as ex:
                    logger.debug(f"Clone user foreground sync: {ex}")

            threading.Thread(target=_ensure_clone_user_active, daemon=True).start()

        return proc

    @staticmethod
    def create_app_desktop_shortcut(app_title: str, package_name: str, user_id: int = 0) -> str:
        """
        Creates a Windows .lnk shortcut on the PC desktop that launches the app directly into its own separate window.
        Returns the created .lnk file path or empty string on failure.
        """
        clean_title = "".join(c for c in app_title if c.isalnum() or c in " _-").strip()
        if not clean_title:
            clean_title = package_name.split(".")[-1].capitalize()

        if user_id == 0:
            lnk_name = f"{clean_title} (GNDROiD).lnk"
        else:
            lnk_name = f"{clean_title} [Clone #{user_id}] (GNDROiD).lnk"

        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        base_dir = get_base_dir()
        icon_path = get_icon()
        this_script = os.path.abspath(__file__)
        pythonw_exe = sys.executable.replace("python.exe", "pythonw.exe")

        gndroid_exe = os.path.join(base_dir, "gndroid.exe")
        gndroid_pyw = os.path.join(base_dir, "gndroid.pyw")

        if os.path.exists(gndroid_exe):
            target_bin = gndroid_exe
            target_args = f'--app {package_name} --user {user_id} --window --title "{clean_title}"'
            ps_args_str = f'--app {package_name} --user {user_id} --window --title \\"{clean_title}\\"'
        elif os.path.exists(gndroid_pyw):
            target_bin = pythonw_exe
            target_args = f'"{gndroid_pyw}" --app {package_name} --user {user_id} --window --title "{clean_title}"'
            ps_args_str = f'\\"{gndroid_pyw}\\" --app {package_name} --user {user_id} --window --title \\"{clean_title}\\"'
        else:
            target_bin = pythonw_exe
            target_args = f'"{this_script}" --launch {package_name} --title "{clean_title}" --user {user_id}'
            ps_args_str = f'\\"{this_script}\\" --launch {package_name} --title \\"{clean_title}\\" --user {user_id}'

        # 1. Try via COM WScript.Shell
        try:
            import win32com.client
            shell = win32com.client.Dispatch("WScript.Shell")
            special_desktop = shell.SpecialFolders("Desktop")
            if special_desktop and os.path.exists(special_desktop):
                desktop = special_desktop

            lnk_path = os.path.join(desktop, lnk_name)
            shortcut = shell.CreateShortcut(lnk_path)
            shortcut.TargetPath = target_bin
            shortcut.Arguments = target_args
            shortcut.WorkingDirectory = base_dir
            if icon_path and os.path.exists(icon_path):
                shortcut.IconLocation = f"{icon_path},0"
            shortcut.Description = f"Launch {clean_title} in dedicated GNDROiD window"
            shortcut.Save()
            logger.info(f"Created desktop shortcut via win32com: {lnk_path}")
            return lnk_path
        except Exception as e:
            logger.warning(f"win32com desktop shortcut creation failed: {e}. Trying PowerShell...")

        # 2. Fallback via PowerShell
        try:
            lnk_path = os.path.join(desktop, lnk_name)
            icon_arg = f'$s.IconLocation = "{icon_path},0";' if icon_path and os.path.exists(icon_path) else ""
            ps_cmd = (
                f'$w = New-Object -ComObject WScript.Shell; '
                f'$s = $w.CreateShortcut("{lnk_path}"); '
                f'$s.TargetPath = "{target_bin}"; '
                f'$s.Arguments = "{ps_args_str}"; '
                f'$s.WorkingDirectory = "{base_dir}"; '
                f'{icon_arg} '
                f'$s.Save()'
            )
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                creationflags=CREATE_NO_WINDOW,
                timeout=10
            )
            if res.returncode == 0 and os.path.exists(lnk_path):
                logger.info(f"Created desktop shortcut via PowerShell: {lnk_path}")
                return lnk_path
            else:
                logger.error(f"PowerShell shortcut creation error: {res.stderr}")
        except Exception as ex:
            logger.error(f"Fallback shortcut creation error: {ex}")

        return ""


# ----------------------------------------------------------------------
# CLI Runner for Standalone Invocations & Desktop Shortcut Execution
# ----------------------------------------------------------------------
def find_active_serial() -> str:
    """Finds the first online adb device or returns 'emulator-5554'."""
    adb = get_adb()
    try:
        res = subprocess.run([adb, "devices"], capture_output=True, text=True, creationflags=CREATE_NO_WINDOW, timeout=5)
        for line in res.stdout.splitlines()[1:]:
            parts = line.strip().split()
            if len(parts) >= 2 and parts[1] == "device":
                return parts[0]
    except Exception:
        pass
    return "emulator-5554"


def main():
    import argparse
    parser = argparse.ArgumentParser(description="GNDROiD Native App Cloner & Dedicated Window Engine")
    parser.add_argument("--launch", type=str, help="Package name to launch in dedicated window")
    parser.add_argument("--app", type=str, default="", help="Alias for --launch / package name")
    parser.add_argument("--window", action="store_true", help="Launch in dedicated floating window")
    parser.add_argument("--title", type=str, default="", help="Window title for launched app")
    parser.add_argument("--user", type=int, default=0, help="User ID (0 for Master, 10+ for Clone)")
    parser.add_argument("--serial", type=str, default="", help="Target device serial")
    parser.add_argument("--shortcut", type=str, help="Create desktop shortcut for package name")
    parser.add_argument("--list-clones", action="store_true", help="List all clone user profiles")
    parser.add_argument("--list-apps", action="store_true", help="List all apps across profiles")

    args = parser.parse_args()
    serial = args.serial or find_active_serial()
    target_pkg = args.launch or args.app

    if target_pkg:
        title = args.title or target_pkg.split(".")[-1].capitalize()
        logger.info(f"Launching '{target_pkg}' on serial '{serial}' for user {args.user}...")
        proc = AppWindowManager.launch_app_in_dedicated_window(
            serial=serial,
            package_name=target_pkg,
            app_title=title,
            user_id=args.user
        )
        print(f"Launched dedicated window PID: {proc.pid}")
    elif args.shortcut:
        title = args.title or args.shortcut.split(".")[-1].capitalize()
        lnk = AppWindowManager.create_app_desktop_shortcut(app_title=title, package_name=args.shortcut, user_id=args.user)
        print(f"Created shortcut: {lnk}")
    elif args.list_clones:
        clones = AppCloneManager.get_clone_users(serial)
        print("Clone users:", clones)
    elif args.list_apps:
        apps = AppCloneManager.list_apps_with_clones(serial)
        for a in apps:
            print(f"- {a['label']} (User {a['user_id']})")


if __name__ == "__main__":
    main()
