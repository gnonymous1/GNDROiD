"""
tests/fixtures/__init__.py
==========================
High-fidelity synthetic test fixtures for GNDROiD E2E testing:
- mock_adb: Stateful subprocess interceptor for ADB PackageInstaller, properties, and shell.
- mock_qemu: TCP Telnet console server on 127.0.0.1:0 with auth handshake and geo fix.
- mock_proxy: Dual HTTP CONNECT / SOCKS5 proxy server with RFC 1928/1929 auth and kill-switch simulation.
- mock_scrcpy: Binary TCP server decoding Scrcpy 4.1 touch (>BBQIIHHHII) and key (>BBIII) events.
- bundle_generator: Pure-Python synthetic generator for .xapk, .apkm, .apks, and .aab bundles.
"""

from .mock_adb import MockAdbState, MockAdbSession, StagedInstallSession
from .mock_qemu import MockQemuConsoleServer
from .mock_proxy import MockDualProxyServer
from .mock_scrcpy import MockScrcpyControlServer
from .bundle_generator import SyntheticBundleGenerator

__all__ = [
    "MockAdbState",
    "MockAdbSession",
    "StagedInstallSession",
    "MockQemuConsoleServer",
    "MockDualProxyServer",
    "MockScrcpyControlServer",
    "SyntheticBundleGenerator",
]
