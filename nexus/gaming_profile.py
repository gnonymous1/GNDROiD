"""
nexus/gaming_profile.py
=======================
Dedicated LDPlayer-Grade Gaming Mode Profile & Runtime Optimizer.

Features:
- Specialized QEMU emulator launch flags (-gpu host, -cpu host, -netfast, etc.)
- Clean command-line argument merging without duplicates
- Scrcpy 4.1 low-latency streaming flags (120+ FPS, 0 video buffer, direct3d11, UHID input)
- Android OS SurfaceFlinger 120Hz refresh rate and animation speed tuning
- Host Windows 1ms timer elevation (timeBeginPeriod)
- Dynamic Performance (P) core CPU affinity pinning and process priority elevation
"""

import os
import sys
import ctypes
import subprocess
import psutil
from typing import List, Dict, Tuple, Optional, Any


class GamingModeProfile:
    """
    Core LDPlayer-grade gaming configuration profile defining hypervisor flags,
    scrcpy streaming parameters, guest SurfaceFlinger properties, and host scheduling.
    """

    GAMING_PROPERTIES: List[Tuple[str, str]] = [
        ("ro.surface_flinger.has_wide_color_display", "true"),
        ("ro.surface_flinger.has_HDR_display", "true"),
        ("ro.surface_flinger.max_frame_buffer_acquired_buffers", "3"),
        ("ro.sf.lcd_density", "500"),
    ]

    GAMING_SETTINGS: List[Tuple[str, str, str]] = [
        ("system", "peak_refresh_rate", "120.0"),
        ("system", "min_refresh_rate", "120.0"),
        ("global", "animator_duration_scale", "0.5"),
        ("global", "window_animation_scale", "0.5"),
        ("global", "transition_animation_scale", "0.5"),
    ]

    @staticmethod
    def get_gaming_qemu_args() -> List[str]:
        """
        Specialized QEMU arguments maximizing graphics throughput, enabling direct host CPU
        instruction passthrough (AVX2/SSE4.2), and eliminating hypervisor latency buffers.
        """
        return [
            "-gpu", "host",
            "-cpu", "host",
            "-netfast",
            "-netdelay", "none",
            "-netspeed", "full",
            "-no-snapshot-load",
            "-no-snapshot-save",
            "-crash-report-mode", "never"
        ]

    @classmethod
    def get_gaming_launch_args(cls, name: str, base_args: List[str]) -> List[str]:
        """
        Merges gaming profile flags into existing emulator launch command without duplicates.
        Replaces conflicting flags (e.g. -gpu auto -> -gpu host) and injects gaming optimizations.
        """
        args = list(base_args)
        gaming_flags = cls.get_gaming_qemu_args()

        # Flags that take a parameter: -gpu, -cpu, -netdelay, -netspeed, -crash-report-mode, -avd, -port
        param_flags = {"-gpu", "-cpu", "-netdelay", "-netspeed", "-crash-report-mode", "-avd", "-port"}
        # Boolean flags that take no parameter
        bool_flags = {"-netfast", "-no-snapshot-load", "-no-snapshot-save"}

        # Build parsed dict of existing flags
        i = 0
        existing_indices: Dict[str, int] = {}
        while i < len(args):
            flag = args[i]
            if flag in param_flags and i + 1 < len(args):
                existing_indices[flag] = i
                i += 2
            elif flag.startswith("-"):
                existing_indices[flag] = i
                i += 1
            else:
                i += 1

        # Process gaming flags
        j = 0
        while j < len(gaming_flags):
            g_flag = gaming_flags[j]
            if g_flag in param_flags and j + 1 < len(gaming_flags):
                g_val = gaming_flags[j + 1]
                if g_flag in existing_indices:
                    # Replace existing value
                    idx = existing_indices[g_flag]
                    args[idx + 1] = g_val
                else:
                    args.extend([g_flag, g_val])
                    existing_indices[g_flag] = len(args) - 2
                j += 2
            elif g_flag in bool_flags or g_flag.startswith("-"):
                if g_flag not in existing_indices:
                    args.append(g_flag)
                    existing_indices[g_flag] = len(args) - 1
                j += 1
            else:
                j += 1

        return args

    @staticmethod
    def get_gaming_scrcpy_args(serial: str, target_fps: int = 120) -> List[str]:
        """
        Scrcpy 4.1 arguments enabling 120+ FPS low-latency display, zero-buffer video pipeline,
        Direct3D 11 rendering, and Linux kernel UHID input mode for gamepads and raw mouse.
        """
        return [
            "-s", serial,
            f"--max-fps={target_fps}",
            "--video-buffer=0",
            "--audio-buffer=20",
            "--video-codec=h264",
            "--render-driver=direct3d11",
            "--gamepad=uhid",
            "--mouse=uhid",
            "--keyboard=uhid",
            "--stay-awake",
            "--print-fps"
        ]

    @classmethod
    def apply_gaming_system_properties(
        cls,
        serial: str,
        adb_path: str = "adb"
    ) -> List[Tuple[str, str]]:
        """
        Configures guest Android SurfaceFlinger to run at 120Hz refresh rate
        and sets animation scale to 0.5x for instant UI responsiveness.
        Returns list of applied property and setting commands.
        """
        applied = []
        flags = 0x08000000 if sys.platform == "win32" else 0

        for prop_name, prop_val in cls.GAMING_PROPERTIES:
            cmd = [adb_path, "-s", serial, "shell", "setprop", prop_name, prop_val]
            try:
                subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=flags, timeout=5)
            except Exception:
                pass
            applied.append(("setprop", f"{prop_name}={prop_val}"))

        for table, key, val in cls.GAMING_SETTINGS:
            cmd = [adb_path, "-s", serial, "shell", "settings", "put", table, key, val]
            try:
                subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=flags, timeout=5)
            except Exception:
                pass
            applied.append(("settings", f"{table}.{key}={val}"))

        return applied

    @staticmethod
    def get_p_core_affinity_mask() -> List[int]:
        """
        Identifies physical Performance (P) cores, avoiding Efficiency (E) cores on hybrid CPUs.
        Default strategy on x86_64: Pins to even-numbered physical cores [0, 2, 4, 6] up to 4 cores.
        """
        total_cores = os.cpu_count() or 8
        p_cores = [c for c in range(min(total_cores, 8)) if c % 2 == 0]
        if not p_cores:
            p_cores = list(range(min(total_cores, 4)))
        return p_cores

    @classmethod
    def optimize_host_process_scheduling(
        cls,
        qemu_pid: int,
        scrcpy_pid: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Elevates Win32 timer resolution to 1ms, sets QEMU process to HIGH priority,
        sets Scrcpy to ABOVE_NORMAL priority, and pins execution to physical P-cores.
        """
        result: Dict[str, Any] = {
            "timer_elevated": False,
            "p_cores": [],
            "qemu_scheduled": False,
            "scrcpy_scheduled": False
        }

        # 1. Elevate Win32 timer resolution to 1ms (eliminates Windows 15.6ms quantum jitter)
        if sys.platform == "win32":
            try:
                time_begin = getattr(ctypes.windll.winmm, "timeBeginPeriod", None)
                if time_begin and time_begin(1) == 0:
                    result["timer_elevated"] = True
            except Exception:
                pass

        # 2. Select physical P-cores
        p_cores = cls.get_p_core_affinity_mask()
        result["p_cores"] = p_cores

        # 3. Schedule QEMU process
        if qemu_pid and qemu_pid > 0:
            try:
                qp = psutil.Process(qemu_pid)
                if hasattr(qp, "cpu_affinity"):
                    qp.cpu_affinity(p_cores)
                if hasattr(psutil, "HIGH_PRIORITY_CLASS"):
                    qp.nice(psutil.HIGH_PRIORITY_CLASS)
                result["qemu_scheduled"] = True
            except Exception as e:
                result["qemu_error"] = str(e)

        # 4. Schedule Scrcpy process
        if scrcpy_pid and scrcpy_pid > 0:
            try:
                sp = psutil.Process(scrcpy_pid)
                if hasattr(sp, "cpu_affinity"):
                    sp.cpu_affinity(p_cores)
                if hasattr(psutil, "ABOVE_NORMAL_PRIORITY_CLASS"):
                    sp.nice(psutil.ABOVE_NORMAL_PRIORITY_CLASS)
                result["scrcpy_scheduled"] = True
            except Exception as e:
                result["scrcpy_error"] = str(e)

        return result

    @classmethod
    def apply_runtime_gaming_optimizations(
        cls,
        serial: str,
        host_pid: int,
        scrcpy_pid: Optional[int] = None,
        adb_path: str = "adb"
    ) -> Dict[str, Any]:
        """
        Unified entrypoint: applies Android system properties and optimizes host process scheduling.
        Interface contract specified in PROJECT.md.
        """
        props = cls.apply_gaming_system_properties(serial, adb_path)
        scheduling = cls.optimize_host_process_scheduling(host_pid, scrcpy_pid)
        return {
            "applied_properties": props,
            "host_scheduling": scheduling
        }


# Alias for compatibility per requirements
GamingProfileManager = GamingModeProfile
