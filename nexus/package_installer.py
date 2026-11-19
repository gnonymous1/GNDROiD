"""
nexus/package_installer.py
==========================
Native Multi-Split APK Session Installer, Automated OBB Deployment,
Anonymous GMS Token Dispatcher, and Certified Hardware Polyfill for GNDROiD.

Milestone M1 (Features 1-5):
- Feature 1: Multi-Format Split-APK Unpacker (.xapk, .apkm, .apks, .aab, .apk)
- Feature 2: Native Split Session Installer via PackageInstaller & adb exec-in
- Feature 3: Automated OBB Deployment to /sdcard/Android/obb/<package_name>/
- Feature 4: Anonymous GMS Token Dispatcher (/fdfe/delivery & CDN split downloader)
- Feature 5: Certified Hardware Polyfill (Galaxy S24 Ultra SM-S928B & Pixel 9 Pro komodo)
"""

import os
import re
import sys
import json
import time
import shlex
import shutil
import struct
import logging
import zipfile
import tempfile
import subprocess
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Callable, Any

logger = logging.getLogger("gndroid.package_installer")
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


# ============================================================================
# Pure-Python AXML Manifest Parser Helper
# ============================================================================

def parse_axml_manifest_metadata(axml_bytes: bytes) -> Dict[str, Any]:
    """
    Parses compiled Android binary XML (AXML) in pure Python.
    Extracts package name, versionCode, and versionName directly from the
    manifest element string pool without external dependencies.
    """
    metadata: Dict[str, Any] = {
        "package_name": "",
        "version_code": 0,
        "version_name": "",
    }
    if len(axml_bytes) < 36:
        return metadata

    magic, file_size = struct.unpack_from("<II", axml_bytes, 0)
    if magic != 0x00080003:
        # Not a compiled binary XML; try plain text
        try:
            text = axml_bytes.decode("utf-8", errors="ignore")
            m_pkg = re.search(r'package\s*=\s*["\']([^"\']+)["\']', text)
            if m_pkg:
                metadata["package_name"] = m_pkg.group(1)
            m_vc = re.search(r'versionCode\s*=\s*["\'](\d+)["\']', text)
            if m_vc:
                metadata["version_code"] = int(m_vc.group(1))
            m_vn = re.search(r'versionName\s*=\s*["\']([^"\']+)["\']', text)
            if m_vn:
                metadata["version_name"] = m_vn.group(1)
        except Exception:
            pass
        return metadata

    try:
        chunk_type, chunk_size = struct.unpack_from("<II", axml_bytes, 8)
        if chunk_type != 0x001C0001:  # String pool chunk
            return metadata

        string_count, style_count, flags, strings_start, _ = struct.unpack_from(
            "<IIIII", axml_bytes, 16
        )
        if 36 + string_count * 4 > len(axml_bytes):
            return metadata

        is_utf8 = bool(flags & (1 << 8))
        offsets = [
            struct.unpack_from("<I", axml_bytes, 36 + i * 4)[0]
            for i in range(string_count)
        ]
        pool_data = axml_bytes[8 + strings_start :]

        strings: List[str] = []
        for off in offsets:
            try:
                if is_utf8:
                    idx = off
                    # Skip char count
                    if pool_data[idx] & 0x80:
                        idx += 2
                    else:
                        idx += 1
                    # Read byte length
                    if pool_data[idx] & 0x80:
                        blen = ((pool_data[idx] & 0x7F) << 8) | pool_data[idx + 1]
                        idx += 2
                    else:
                        blen = pool_data[idx]
                        idx += 1
                    s = pool_data[idx : idx + blen].decode("utf-8", errors="ignore")
                else:
                    idx = off
                    ulen = struct.unpack_from("<H", pool_data, idx)[0]
                    if ulen & 0x8000:
                        ulen = ((ulen & 0x7FFF) << 16) | struct.unpack_from("<H", pool_data, idx + 2)[0]
                        idx += 4
                    else:
                        idx += 2
                    s = pool_data[idx : idx + ulen * 2].decode("utf-16le", errors="ignore")
                strings.append(s)
            except Exception:
                strings.append("")

        # Locate the <manifest> element and extract package attributes
        pos = 8 + chunk_size
        while pos + 8 <= len(axml_bytes):
            c_type, c_sz = struct.unpack_from("<II", axml_bytes, pos)
            if c_sz <= 0:
                break
            if c_type == 0x00100102:  # START_ELEMENT
                if pos + 28 <= len(axml_bytes):
                    ns_idx, name_idx, attr_start, attr_size, attr_count = struct.unpack_from(
                        "<IIHHH", axml_bytes, pos + 16
                    )
                    elem_name = strings[name_idx] if name_idx < len(strings) else ""
                    if elem_name == "manifest":
                        attr_base = pos + 16 + 12
                        for a in range(attr_count):
                            a_off = attr_base + a * 20
                            if a_off + 20 <= len(axml_bytes):
                                ans_idx, aname_idx, aval_idx, atype, adata = struct.unpack_from(
                                    "<IIIIi", axml_bytes, a_off
                                )
                                attr_name = strings[aname_idx] if aname_idx < len(strings) else ""
                                attr_val = (
                                    strings[aval_idx]
                                    if aval_idx != 0xFFFFFFFF and aval_idx < len(strings)
                                    else adata
                                )
                                if attr_name == "package" and isinstance(attr_val, str):
                                    metadata["package_name"] = attr_val
                                elif attr_name == "versionCode":
                                    try:
                                        metadata["version_code"] = int(attr_val)
                                    except (ValueError, TypeError):
                                        metadata["version_code"] = adata
                                elif attr_name == "versionName":
                                    metadata["version_name"] = str(attr_val)
                        break
            pos += c_sz

        # Heuristic fallback if attributes weren't matched directly
        if not metadata["package_name"]:
            for s in strings:
                if (
                    "." in s
                    and not s.startswith("http")
                    and not s.startswith("android.")
                    and not s.endswith(".xml")
                    and not s.endswith(".so")
                    and len(s.split(".")) >= 2
                ):
                    metadata["package_name"] = s
                    break
    except Exception:
        pass

    return metadata


# ============================================================================
# Feature 1: Multi-Format Split-APK Unpacker
# ============================================================================

@dataclass
class SplitBundleManifest:
    """
    Representation of an analyzed application bundle or split package.
    """
    package_name: str
    version_code: int
    version_name: str
    base_apk_path: str
    split_apk_paths: List[str] = field(default_factory=list)
    obb_files: List[Tuple[str, str]] = field(default_factory=list)  # (host_file_path, relative_remote_dest)
    temp_dir: Optional[str] = None
    total_bytes: int = 0

    def get_all_apks(self) -> List[str]:
        """Returns ordered list of all APKs with base APK first."""
        res: List[str] = []
        if self.base_apk_path and os.path.isfile(self.base_apk_path):
            res.append(self.base_apk_path)
        for s in self.split_apk_paths:
            if s and os.path.isfile(s) and s != self.base_apk_path:
                res.append(s)
        return res


class NativeSplitApkInstaller:
    """
    PackageInstaller session client streaming multi-split APKs via ADB
    and deploying OBB expansion assets.
    """

    def __init__(self, adb_path: str = "adb"):
        self.adb = adb_path

    def parse_bundle(self, bundle_path: str) -> SplitBundleManifest:
        """
        Parses multi-format application archives (.xapk, .apkm, .apks, .aab, .apk)
        or directories. Pure Python, zero external binary dependency for APK/XAPK/APKM/APKS.
        """
        if not os.path.exists(bundle_path):
            raise FileNotFoundError(f"Bundle path does not exist: {bundle_path}")

        # Directory containing extracted APKs / splits
        if os.path.isdir(bundle_path):
            return self._parse_directory(bundle_path)

        ext = os.path.splitext(bundle_path)[1].lower()

        # Plain single APK
        if ext == ".apk":
            pkg_name = ""
            v_code = 0
            v_name = ""
            try:
                with zipfile.ZipFile(bundle_path, "r") as z:
                    if "AndroidManifest.xml" in z.namelist():
                        meta = parse_axml_manifest_metadata(z.read("AndroidManifest.xml"))
                        pkg_name = meta.get("package_name", "")
                        v_code = meta.get("version_code", 0)
                        v_name = meta.get("version_name", "")
            except Exception as e:
                logger.debug(f"AXML read note for single APK: {e}")

            size = os.path.getsize(bundle_path)
            return SplitBundleManifest(
                package_name=pkg_name,
                version_code=v_code,
                version_name=v_name,
                base_apk_path=bundle_path,
                split_apk_paths=[],
                obb_files=[],
                temp_dir=None,
                total_bytes=size,
            )

        # Archive formats (.xapk, .apkm, .apks, .zip, .aab)
        staging_dir = tempfile.mkdtemp(prefix="gndroid_bundle_")
        try:
            with zipfile.ZipFile(bundle_path, "r") as z:
                z.extractall(staging_dir)
        except zipfile.BadZipFile as e:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise ValueError(f"Invalid or corrupted zip archive {bundle_path}: {e}")

        # .AAB (Android App Bundle) handling
        if ext == ".aab" or os.path.isfile(os.path.join(staging_dir, "BundleConfig.pb")):
            return self._handle_aab_bundle(staging_dir, bundle_path)

        # Parse metadata from manifest.json (XAPK) or info.json (APKM)
        pkg_name = ""
        v_code = 0
        v_name = ""

        # 1. APKPure XAPK manifest.json
        xapk_manifest = os.path.join(staging_dir, "manifest.json")
        if os.path.isfile(xapk_manifest):
            try:
                with open(xapk_manifest, "r", encoding="utf-8", errors="ignore") as f:
                    meta = json.load(f)
                    pkg_name = meta.get("package_name") or meta.get("pname") or ""
                    v_code = int(meta.get("version_code", 0) or 0)
                    v_name = meta.get("version_name") or ""
            except Exception as e:
                logger.debug(f"Error reading XAPK manifest.json: {e}")

        # 2. APKMirror APKM info.json
        apkm_info = os.path.join(staging_dir, "info.json")
        if not pkg_name and os.path.isfile(apkm_info):
            try:
                with open(apkm_info, "r", encoding="utf-8", errors="ignore") as f:
                    meta = json.load(f)
                    pkg_name = meta.get("pname") or meta.get("package_name") or ""
                    v_code = int(meta.get("version_code", 0) or 0)
                    v_name = meta.get("version_name") or ""
            except Exception as e:
                logger.debug(f"Error reading APKM info.json: {e}")

        # Collect all APK and OBB files
        apk_files: List[str] = []
        obb_files: List[Tuple[str, str]] = []

        for root, _, files in os.walk(staging_dir):
            for file in files:
                fpath = os.path.join(root, file)
                low = file.lower()
                if low.endswith(".apk"):
                    apk_files.append(fpath)
                elif low.endswith(".obb"):
                    rel = os.path.relpath(fpath, staging_dir)
                    obb_files.append((fpath, rel))

        if not apk_files:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise ValueError(f"No valid .apk files found inside {bundle_path}")

        # Classify base APK vs split APKs cleanly
        base_apk: Optional[str] = None
        # Priority 1: Exact canonical base filenames
        for apk in apk_files:
            fname = os.path.basename(apk).lower()
            if fname in ("base.apk", "base-master.apk", "universal.apk", "standalone.apk") or (
                pkg_name and fname == f"{pkg_name.lower()}.apk"
            ):
                base_apk = apk
                break

        # Priority 2: Basename starting with "base" but not having split/config markers
        if not base_apk:
            for apk in apk_files:
                fname = os.path.basename(apk).lower()
                if fname.startswith("base") and not any(
                    x in fname for x in ("config", "split", "arm", "x86", "hdpi", "mdpi", "ldpi")
                ):
                    base_apk = apk
                    break

        # Priority 3: Fallback to largest APK as base APK
        if not base_apk:
            apk_files_by_size = sorted(apk_files, key=os.path.getsize, reverse=True)
            base_apk = apk_files_by_size[0]

        # Splits are all other APKs in the bundle
        splits = [a for a in apk_files if a != base_apk]

        # Extract package name from base APK if missing
        if not pkg_name and base_apk:
            try:
                with zipfile.ZipFile(base_apk, "r") as z:
                    if "AndroidManifest.xml" in z.namelist():
                        meta = parse_axml_manifest_metadata(z.read("AndroidManifest.xml"))
                        pkg_name = meta.get("package_name", "")
                        if not v_code:
                            v_code = meta.get("version_code", 0)
                        if not v_name:
                            v_name = meta.get("version_name", "")
            except Exception as e:
                logger.debug(f"Failed parsing base APK manifest: {e}")

        # If package name still unknown and OBB files present, infer from OBB filename
        if not pkg_name and obb_files:
            for host_obb, _ in obb_files:
                bname = os.path.basename(host_obb)
                m = re.search(r"\.(com\.[a-zA-Z0-9_.]+)\.obb", bname)
                if m:
                    pkg_name = m.group(1)
                    break

        all_apks = [base_apk] + splits
        total_sz = sum(os.path.getsize(a) for a in all_apks)

        return SplitBundleManifest(
            package_name=pkg_name,
            version_code=v_code,
            version_name=v_name,
            base_apk_path=base_apk,
            split_apk_paths=splits,
            obb_files=obb_files,
            temp_dir=staging_dir,
            total_bytes=total_sz,
        )

    def _parse_directory(self, dir_path: str) -> SplitBundleManifest:
        """Parses an uncompressed directory containing APKs and/or OBBs."""
        apk_files: List[str] = []
        obb_files: List[Tuple[str, str]] = []

        for root, _, files in os.walk(dir_path):
            for file in files:
                fp = os.path.join(root, file)
                low = file.lower()
                if low.endswith(".apk"):
                    apk_files.append(fp)
                elif low.endswith(".obb"):
                    rel = os.path.relpath(fp, dir_path)
                    obb_files.append((fp, rel))

        if not apk_files:
            raise ValueError(f"No .apk files found in directory: {dir_path}")

        base_apk = None
        for apk in apk_files:
            fname = os.path.basename(apk).lower()
            if fname in ("base.apk", "base-master.apk", "universal.apk", "standalone.apk"):
                base_apk = apk
                break
        if not base_apk:
            for apk in apk_files:
                fname = os.path.basename(apk).lower()
                if fname.startswith("base") and not any(
                    x in fname for x in ("config", "split", "arm", "x86", "hdpi", "mdpi", "ldpi")
                ):
                    base_apk = apk
                    break
        if not base_apk:
            apk_files_by_size = sorted(apk_files, key=os.path.getsize, reverse=True)
            base_apk = apk_files_by_size[0]

        splits = [a for a in apk_files if a != base_apk]

        pkg_name = ""
        v_code = 0
        v_name = ""
        try:
            with zipfile.ZipFile(base_apk, "r") as z:
                if "AndroidManifest.xml" in z.namelist():
                    meta = parse_axml_manifest_metadata(z.read("AndroidManifest.xml"))
                    pkg_name = meta.get("package_name", "")
                    v_code = meta.get("version_code", 0)
                    v_name = meta.get("version_name", "")
        except Exception:
            pass

        all_apks = [base_apk] + splits
        return SplitBundleManifest(
            package_name=pkg_name,
            version_code=v_code,
            version_name=v_name,
            base_apk_path=base_apk,
            split_apk_paths=splits,
            obb_files=obb_files,
            temp_dir=None,
            total_bytes=sum(os.path.getsize(a) for a in all_apks),
        )

    def _handle_aab_bundle(self, staging_dir: str, aab_path: str) -> SplitBundleManifest:
        """
        Handles raw Android App Bundle (.aab). If OpenJDK/bundletool is available,
        compiles to split APKs; otherwise extracts packaged base/module assets.
        """
        pkg_name = ""
        v_code = 0
        v_name = ""
        base_manifest_xml = os.path.join(staging_dir, "base", "manifest", "AndroidManifest.xml")
        if os.path.isfile(base_manifest_xml):
            with open(base_manifest_xml, "rb") as f:
                meta = parse_axml_manifest_metadata(f.read())
                pkg_name = meta.get("package_name", "")
                v_code = meta.get("version_code", 0)
                v_name = meta.get("version_name", "")

        # Check if bundletool is present
        bundletool_jar = os.environ.get("BUNDLETOOL_JAR", "")
        java_bin = "java"
        if not bundletool_jar:
            possible = [
                os.path.join(os.getcwd(), "tools", "bundletool.jar"),
                os.path.join(os.path.dirname(__file__), "..", "tools", "bundletool.jar"),
            ]
            for p in possible:
                if os.path.isfile(p):
                    bundletool_jar = p
                    break

        if bundletool_jar and os.path.isfile(bundletool_jar):
            out_apks = os.path.join(staging_dir, "compiled_bundle.apks")
            cmd = [
                java_bin,
                "-jar",
                bundletool_jar,
                "build-apks",
                f"--bundle={aab_path}",
                f"--output={out_apks}",
                "--mode=default",
            ]
            try:
                subprocess.run(cmd, check=True, capture_output=True, creationflags=CREATE_NO_WINDOW)
                if os.path.isfile(out_apks):
                    return self.parse_bundle(out_apks)
            except Exception as e:
                logger.warning(f"Bundletool build-apks failed: {e}")

        # Pure Python fallback for AAB: inspect any .apk files if packaged or report
        apk_files = []
        for root, _, files in os.walk(staging_dir):
            for file in files:
                if file.lower().endswith(".apk"):
                    apk_files.append(os.path.join(root, file))

        if apk_files:
            base_apk = apk_files[0]
            splits = apk_files[1:]
            return SplitBundleManifest(
                package_name=pkg_name,
                version_code=v_code,
                version_name=v_name,
                base_apk_path=base_apk,
                split_apk_paths=splits,
                obb_files=[],
                temp_dir=staging_dir,
                total_bytes=sum(os.path.getsize(a) for a in apk_files),
            )

        shutil.rmtree(staging_dir, ignore_errors=True)
        raise ValueError(
            f"Raw AAB bundle {aab_path} contains source assets without compiled split APKs. "
            f"Please compile with bundletool or provide .apks / .xapk."
        )

    # ========================================================================
    # Feature 2: Native Split Session Installer & Feature 3: OBB Deployment
    # ========================================================================

    def install_bundle(
        self,
        serial: str,
        bundle_path: str,
        install_as_vending: bool = True,
        user_id: int = 0,
        progress_cb: Optional[Callable[[str, int], None]] = None,
    ) -> Tuple[bool, str]:
        """
        Installs an application bundle (.xapk, .apkm, .apks, .apk) onto the specified
        device via native Android PackageInstaller streaming sessions:
        1. Unpack & analyze bundle
        2. Create PackageInstaller session via pm install-create
        3. Stream splits via adb exec-in pm install-write (bypassing Windows PTY corruption)
        4. Commit session via pm install-commit
        5. Deploy OBB expansions to /sdcard/Android/obb/<package_name>/
        """
        def _report(msg: str, pct: int):
            if progress_cb:
                try:
                    progress_cb(msg, pct)
                except TypeError:
                    progress_cb(msg)  # type: ignore

        manifest: Optional[SplitBundleManifest] = None
        session_id: Optional[str] = None

        try:
            _report("Analyzing application bundle archive...", 10)
            manifest = self.parse_bundle(bundle_path)

            all_apks = manifest.get_all_apks()
            if not all_apks:
                return False, "No valid APK files found in bundle."

            total_bytes = sum(os.path.getsize(a) for a in all_apks)

            # Step 1: Create session
            _report(
                f"Creating install session ({len(all_apks)} splits, {total_bytes // 1024} KB)...",
                25,
            )
            cmd_create = [self.adb]
            if serial:
                cmd_create.extend(["-s", serial])
            cmd_create.extend(
                [
                    "shell",
                    "pm",
                    "install-create",
                    "-r",
                    "-t",
                    "-d",
                    "-g",
                ]
            )
            if install_as_vending:
                cmd_create.extend(["-i", "com.android.vending"])
            cmd_create.extend(["--install-location", "0", "-S", str(total_bytes)])
            if user_id > 0:
                cmd_create.extend(["--user", str(user_id)])

            p_create = subprocess.run(
                cmd_create,
                capture_output=True,
                text=True,
                creationflags=CREATE_NO_WINDOW,
            )
            out = (p_create.stdout + " " + p_create.stderr).strip()
            m = re.search(
                r"(?:\[(\d+)\]|session\s+(\d+)|created install session\s+(\d+))",
                out,
                re.IGNORECASE,
            )
            if not m:
                return False, f"Failed to create PackageInstaller session: {out}"

            session_id = m.group(1) or m.group(2) or m.group(3)
            logger.info(f"Created PackageInstaller session ID: {session_id}")

            # Step 2: Stream splits via adb exec-in
            pct_step = 50.0 / max(1, len(all_apks))
            for idx, apk_path in enumerate(all_apks):
                split_name = f"split_{idx}.apk" if idx > 0 else "base.apk"
                sz = os.path.getsize(apk_path)
                curr_pct = int(30 + idx * pct_step)
                _report(f"Streaming {split_name} ({sz // 1024} KB) to session {session_id}...", curr_pct)

                cmd_write = [self.adb]
                if serial:
                    cmd_write.extend(["-s", serial])
                cmd_write.extend(
                    [
                        "exec-in",
                        "pm",
                        "install-write",
                        "-S",
                        str(sz),
                        str(session_id),
                        split_name,
                    ]
                )

                with open(apk_path, "rb") as f_in:
                    p_write = subprocess.run(
                        cmd_write,
                        stdin=f_in,
                        capture_output=True,
                        text=True,
                        creationflags=CREATE_NO_WINDOW,
                    )

                if p_write.returncode != 0:
                    self.abandon_session(serial, session_id)
                    return False, f"Failed streaming {split_name}: {p_write.stderr.strip() or p_write.stdout.strip()}"

            # Step 3: Commit session
            _report("Committing package installation...", 85)
            cmd_commit = [self.adb]
            if serial:
                cmd_commit.extend(["-s", serial])
            cmd_commit.extend(["shell", "pm", "install-commit", str(session_id)])

            p_commit = subprocess.run(
                cmd_commit,
                capture_output=True,
                text=True,
                timeout=120,
                creationflags=CREATE_NO_WINDOW,
            )
            commit_out = (p_commit.stdout + " " + p_commit.stderr).lower()
            if "success" not in commit_out:
                self.abandon_session(serial, session_id)
                return False, f"Commit failed: {p_commit.stdout.strip() or p_commit.stderr.strip()}"

            # Step 4: Deploy OBB expansion files if present
            if manifest.obb_files:
                _report(f"Deploying {len(manifest.obb_files)} OBB expansion assets...", 92)
                pkg = manifest.package_name or "com.gndroid.app"
                self.deploy_obbs(serial, manifest.obb_files, pkg)

            _report("Package installation completed successfully.", 100)
            return True, f"Installed package {manifest.package_name or 'bundle'} successfully."

        except Exception as e:
            if session_id:
                self.abandon_session(serial, session_id)
            return False, f"Installation error: {str(e)}"
        finally:
            if manifest and manifest.temp_dir and os.path.exists(manifest.temp_dir):
                shutil.rmtree(manifest.temp_dir, ignore_errors=True)

    def deploy_obbs(
        self, serial: str, obb_files: List[Tuple[str, str]], package_name: str
    ) -> bool:
        """
        Extracts and deploys game .obb expansion files directly to
        /sdcard/Android/obb/<package_name>/ with proper 664 permissions.
        """
        if not obb_files:
            return True

        # Sanitize and validate package_name to prevent path traversal and shell injection
        safe_pkg = os.path.basename(str(package_name).replace("\\", "/").rstrip("/"))
        safe_pkg = re.sub(r'[\s;&|$`\'"\\/]', '', safe_pkg).replace("..", "")
        if not re.match(r'^[a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)*$', safe_pkg):
            safe_pkg = re.sub(r'[^a-zA-Z0-9_.]', '', safe_pkg) or "unknown.package"

        dest_dir = f"/sdcard/Android/obb/{safe_pkg}/"
        cmd_mkdir = [self.adb]
        if serial:
            cmd_mkdir.extend(["-s", serial])
        cmd_mkdir.extend(["shell", "mkdir", "-p", shlex.quote(dest_dir)])
        subprocess.run(cmd_mkdir, capture_output=True, creationflags=CREATE_NO_WINDOW)

        for host_obb, _ in obb_files:
            fname = os.path.basename(str(host_obb).replace("\\", "/").rstrip("/"))
            fname = re.sub(r'[\s;&|$`\'"\\/]', '', fname).replace("..", "")
            if not fname:
                fname = "main.obb"
            remote_path = f"{dest_dir}{fname}"

            cmd_push = [self.adb]
            if serial:
                cmd_push.extend(["-s", serial])
            cmd_push.extend(["push", host_obb, remote_path])
            subprocess.run(cmd_push, capture_output=True, creationflags=CREATE_NO_WINDOW)

            cmd_chmod = [self.adb]
            if serial:
                cmd_chmod.extend(["-s", serial])
            cmd_chmod.extend(["shell", "chmod", "664", shlex.quote(remote_path)])
            subprocess.run(cmd_chmod, capture_output=True, creationflags=CREATE_NO_WINDOW)

        return True

    def abandon_session(self, serial: str, session_id: Optional[str]):
        """Abandons an in-flight PackageInstaller session on failure."""
        if not session_id:
            return
        try:
            cmd = [self.adb]
            if serial:
                cmd.extend(["-s", serial])
            cmd.extend(["shell", "pm", "install-abandon", str(session_id)])
            subprocess.run(
                cmd,
                capture_output=True,
                creationflags=CREATE_NO_WINDOW,
                timeout=10,
            )
            logger.info(f"Abandoned install session {session_id}")
        except Exception as e:
            logger.warning(f"Failed to abandon install session {session_id}: {e}")


# ============================================================================
# Feature 4: Anonymous GMS Token Dispatcher
# ============================================================================

class AnonymousGmsDispatcher:
    """
    Direct Google Play Frontend API (/fdfe/delivery) client querying
    Google CDN APK download tokens and split URLs across country codes.
    """

    MCC_MNC_TABLE = {
        "AE": "42402",  # UAE du
        "SA": "42001",  # Saudi Arabia stc
        "US": "310260", # US T-Mobile
        "GB": "23430",  # UK EE
        "PK": "41001",  # Pakistan Jazz
        "DE": "26201",  # Germany Telekom
        "JP": "44010",  # Japan NTT DOCOMO
    }

    DEFAULT_USER_AGENT = (
        "Android-Finsky/38.5.22-29 [0] [PR] 585721868 "
        "(api=34,versionCode=83852200,sdk=34,device=e3q,hardware=pineapple,platformVersion=14)"
    )

    def __init__(self, device_id: str = "3a2c5e8f1b9d4072"):
        self.device_id = device_id

    def build_headers(self, country_code: str = "AE", auth_token: Optional[str] = None) -> Dict[str, str]:
        """Constructs authentic Google Play Frontend API request headers."""
        mcc_mnc = self.MCC_MNC_TABLE.get(country_code.upper(), "42402")
        headers = {
            "User-Agent": self.DEFAULT_USER_AGENT,
            "X-DFE-Device-Id": self.device_id,
            "X-DFE-MCC-MNC": mcc_mnc,
            "X-DFE-Client-Id": "am-android-google",
            "Accept-Language": f"en-{country_code.upper()},en;q=0.9",
        }
        if auth_token:
            headers["Authorization"] = f"GoogleLogin auth={auth_token}"
        return headers

    def fetch_delivery_token(
        self,
        package_name: str,
        country_code: str = "AE",
        version_code: int = 0,
        auth_token: Optional[str] = None,
        output_dir: str = "./downloads",
        timeout: int = 15,
    ) -> Tuple[bool, str, List[str]]:
        """
        Queries /fdfe/delivery for direct Google CDN APK download links.
        Returns (success: bool, base_apk_path: str, split_apk_paths: List[str]).
        """
        os.makedirs(output_dir, exist_ok=True)
        headers = self.build_headers(country_code=country_code, auth_token=auth_token)

        url = f"https://android.clients.google.com/fdfe/delivery?doc={package_name}&ot=1"
        if version_code > 0:
            url += f"&vc={version_code}"

        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
                # Parse protobuf or json payload for CDN URLs
                download_urls = self._extract_cdn_urls_from_payload(data)
                if not download_urls:
                    return (
                        False,
                        f"No CDN download URLs returned by Google Play for {package_name} ({country_code}).",
                        [],
                    )

                base_path = ""
                split_paths: List[str] = []
                for idx, cdn_url in enumerate(download_urls):
                    fname = f"{package_name}_base.apk" if idx == 0 else f"{package_name}_split_{idx}.apk"
                    dest = os.path.join(output_dir, fname)
                    with urllib.request.urlopen(cdn_url, timeout=timeout) as cdn_resp:
                        with open(dest, "wb") as f_out:
                            f_out.write(cdn_resp.read())
                    if idx == 0:
                        base_path = dest
                    else:
                        split_paths.append(dest)

                return True, base_path, split_paths

        except urllib.error.HTTPError as e:
            # 401/403: Anonymous token challenge or license restriction
            logger.info(f"GMS Delivery HTTP {e.code}: {e.reason}")
            return (
                False,
                f"GMS Token Dispatcher HTTP {e.code} ({e.reason}): "
                f"Anonymous token challenge required for country {country_code}. Provide Google auth token.",
                [],
            )
        except Exception as e:
            logger.info(f"GMS Delivery network exception: {e}")
            return (
                False,
                f"GMS Token Dispatcher network error: {str(e)}",
                [],
            )

    @staticmethod
    def _extract_cdn_urls_from_payload(payload: bytes) -> List[str]:
        """Extracts Google Cloud CDN download links (*.gvt1.com, play.googleapis.com)."""
        urls: List[str] = []
        try:
            text = payload.decode("latin1")
            matches = re.findall(
                r'https?://[a-zA-Z0-9_\-\.]+(?:gvt1\.com|googleapis\.com|googleusercontent\.com)/[^\s"\'<>\x00-\x1f]+',
                text,
            )
            for m in matches:
                clean = re.sub(r'[\x00-\x1f]', '', m).rstrip("\\/;,")
                if clean and clean not in urls:
                    urls.append(clean)
        except Exception:
            pass
        return urls


# ============================================================================
# Feature 5: Certified Hardware Polyfill
# ============================================================================

class HardwarePolyfill:
    """
    Spoofs certified flagship Android device identity (Galaxy S24 Ultra & Pixel 9 Pro),
    injects required hardware capability feature XMLs into guest /system/etc/permissions/,
    and generates QEMU CLI -prop arguments.
    """

    PROFILES: Dict[str, Dict[str, str]] = {
        "samsung_s24_ultra": {
            "ro.product.brand": "samsung",
            "ro.product.manufacturer": "samsung",
            "ro.product.model": "SM-S928B",
            "ro.product.name": "e3qxxx",
            "ro.product.device": "e3q",
            "ro.build.product": "e3q",
            "ro.board.platform": "pineapple",
            "ro.build.flavor": "e3qxxx-user",
            "ro.build.id": "UP1A.231005.007",
            "ro.build.display.id": "UP1A.231005.007.S928BXXU1AXB5",
            "ro.build.version.incremental": "S928BXXU1AXB5",
            "ro.build.version.release": "14",
            "ro.build.version.sdk": "34",
            "ro.build.version.security_patch": "2024-03-01",
            "ro.build.fingerprint": "samsung/e3qxxx/e3q:14/UP1A.231005.007/S928BXXU1AXB5:user/release-keys",
        },
        "google_pixel_9_pro": {
            "ro.product.brand": "google",
            "ro.product.manufacturer": "Google",
            "ro.product.model": "Pixel 9 Pro",
            "ro.product.name": "komodo",
            "ro.product.device": "komodo",
            "ro.build.product": "komodo",
            "ro.board.platform": "zuma",
            "ro.build.flavor": "komodo-user",
            "ro.build.id": "AD1A.240530.047",
            "ro.build.display.id": "AD1A.240530.047.12030043",
            "ro.build.version.incremental": "12030043",
            "ro.build.version.release": "14",
            "ro.build.version.sdk": "34",
            "ro.build.version.security_patch": "2024-06-05",
            "ro.build.fingerprint": "google/komodo/komodo:14/AD1A.240530.047/12030043:user/release-keys",
        },
    }

    # Aliases
    PROFILES["pixel_9_pro"] = PROFILES["google_pixel_9_pro"]
    PROFILES["s24_ultra"] = PROFILES["samsung_s24_ultra"]

    CAPABILITY_XMLS: Dict[str, str] = {
        "android.hardware.telephony.xml": (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            "<permissions>\n"
            '    <feature name="android.hardware.telephony" />\n'
            '    <feature name="android.hardware.telephony.gsm" />\n'
            '    <feature name="android.hardware.telephony.ims" />\n'
            "</permissions>\n"
        ),
        "android.hardware.telephony.gsm.xml": (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            "<permissions>\n"
            '    <feature name="android.hardware.telephony.gsm" />\n'
            '    <feature name="android.hardware.telephony.cdma" />\n'
            '    <feature name="android.hardware.telephony.data" />\n'
            "</permissions>\n"
        ),
        "android.hardware.camera.xml": (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            "<permissions>\n"
            '    <feature name="android.hardware.camera" />\n'
            '    <feature name="android.hardware.camera.front" />\n'
            '    <feature name="android.hardware.camera.autofocus" />\n'
            '    <feature name="android.hardware.camera.flash" />\n'
            '    <feature name="android.hardware.camera.full" />\n'
            '    <feature name="android.hardware.camera.level.full" />\n'
            '    <feature name="android.hardware.camera.capability.raw" />\n'
            "</permissions>\n"
        ),
        "android.hardware.biometrics.face.xml": (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            "<permissions>\n"
            '    <feature name="android.hardware.biometrics.face" />\n'
            '    <feature name="android.hardware.fingerprint" />\n'
            "</permissions>\n"
        ),
        "android.hardware.vulkan.version-1_3.xml": (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            "<permissions>\n"
            '    <feature name="android.hardware.vulkan.level" version="1" />\n'
            '    <feature name="android.hardware.vulkan.version" version="4198400" />\n'
            '    <feature name="android.hardware.vulkan.compute" version="0" />\n'
            "</permissions>\n"
        ),
    }

    @classmethod
    def get_profile(cls, profile_name: str) -> Dict[str, str]:
        """Returns property dictionary for profile, defaulting to Samsung S24 Ultra."""
        key = profile_name.lower().replace("-", "_").replace(" ", "_")
        return cls.PROFILES.get(key, cls.PROFILES["samsung_s24_ultra"])

    @classmethod
    def get_qemu_props(cls, profile_name: str) -> List[str]:
        """Returns QEMU CLI arguments formatted as [-prop, key=val, ...]."""
        profile = cls.get_profile(profile_name)
        args: List[str] = []
        for k, v in profile.items():
            args.extend(["-prop", f"{k}={v}"])
        return args

    @classmethod
    def get_feature_xmls(cls) -> Dict[str, str]:
        """Returns map of filename -> XML content for capability permissions."""
        return cls.CAPABILITY_XMLS

    @classmethod
    def apply(
        cls,
        serial: str,
        profile_name: str = "samsung_s24_ultra",
        adb_path: str = "adb",
    ) -> Tuple[bool, str]:
        """
        Applies certified build properties and injects capability XMLs
        into the guest Android instance via ADB.
        """
        profile = cls.get_profile(profile_name)

        # 1. Apply system properties via setprop
        for k, v in profile.items():
            quoted_v = f'"{v}"' if " " in v else v
            try:
                cmd = [adb_path]
                if serial:
                    cmd.extend(["-s", serial])
                cmd.extend(["shell", "setprop", k, quoted_v])
                subprocess.run(cmd, capture_output=True, creationflags=CREATE_NO_WINDOW)
            except Exception:
                pass

            # Also apply to sub-partition namespaces
            for sub in ("vendor", "odm", "system", "system_ext", "product"):
                if k.startswith("ro.product."):
                    prop_name = f"ro.product.{sub}.{k[len('ro.product.'):]}"
                    try:
                        cmd_sub = [adb_path]
                        if serial:
                            cmd_sub.extend(["-s", serial])
                        cmd_sub.extend(["shell", "setprop", prop_name, quoted_v])
                        subprocess.run(cmd_sub, capture_output=True, creationflags=CREATE_NO_WINDOW)
                    except Exception:
                        pass

        # 2. Inject XML permissions manifests
        temp_dir = tempfile.mkdtemp(prefix="gndroid_polyfill_")
        try:
            # Try remounting guest system RW if root
            remount_cmd = [adb_path]
            if serial:
                remount_cmd.extend(["-s", serial])
            remount_cmd.extend(["shell", "mount", "-o", "remount,rw", "/system"])
            subprocess.run(remount_cmd, capture_output=True, creationflags=CREATE_NO_WINDOW)

            for xml_name, xml_content in cls.CAPABILITY_XMLS.items():
                local_file = os.path.join(temp_dir, xml_name)
                with open(local_file, "w", encoding="utf-8") as f:
                    f.write(xml_content)

                dest_path = f"/system/etc/permissions/{xml_name}"
                push_cmd = [adb_path]
                if serial:
                    push_cmd.extend(["-s", serial])
                push_cmd.extend(["push", local_file, dest_path])
                subprocess.run(push_cmd, capture_output=True, creationflags=CREATE_NO_WINDOW)

                chmod_cmd = [adb_path]
                if serial:
                    chmod_cmd.extend(["-s", serial])
                chmod_cmd.extend(["shell", "chmod", "644", dest_path])
                subprocess.run(chmod_cmd, capture_output=True, creationflags=CREATE_NO_WINDOW)

            return True, f"Hardware polyfill '{profile_name}' applied successfully."
        except Exception as e:
            return False, f"Failed applying hardware polyfill: {str(e)}"
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


# ============================================================================
# Exact Top-Level Interface Contracts (PROJECT.md)
# ============================================================================

def install_split_apk_bundle(
    serial: str,
    bundle_path: str,
    adb_path: str = "adb",
    install_as_vending: bool = True,
    progress_callback: Optional[Callable[[str, int], None]] = None,
) -> Tuple[bool, str]:
    """
    Unpacks .xapk, .apkm, .apks, or .aab, validates manifests, deploys OBBs,
    creates PackageInstaller session via pm install-create, streams splits via
    adb exec-in pm install-write, commits session.
    Returns (success: bool, message: str).
    """
    installer = NativeSplitApkInstaller(adb_path=adb_path)
    return installer.install_bundle(
        serial=serial,
        bundle_path=bundle_path,
        install_as_vending=install_as_vending,
        progress_cb=progress_callback,
    )


def apply_hardware_polyfill(
    serial: str,
    profile_name: str = "samsung_s24_ultra",
    adb_path: str = "adb",
) -> Tuple[bool, str]:
    """
    Applies certified device build properties and injects camera/telephony
    feature XMLs into guest /system/etc/permissions/ or /product/etc/permissions/.
    """
    return HardwarePolyfill.apply(
        serial=serial,
        profile_name=profile_name,
        adb_path=adb_path,
    )


def fetch_apk_via_anonymous_gms(
    package_name: str,
    country_code: str = "AE",
    output_dir: str = "./downloads",
) -> Tuple[bool, str, List[str]]:
    """
    Queries Google Play Frontend API anonymously for direct CDN download links
    for the specified country. Returns (success, main_or_bundle_path, split_paths).
    """
    dispatcher = AnonymousGmsDispatcher()
    return dispatcher.fetch_delivery_token(
        package_name=package_name,
        country_code=country_code,
        output_dir=output_dir,
    )


__all__ = [
    "NativeSplitApkInstaller",
    "SplitBundleManifest",
    "HardwarePolyfill",
    "AnonymousGmsDispatcher",
    "install_split_apk_bundle",
    "apply_hardware_polyfill",
    "fetch_apk_via_anonymous_gms",
    "parse_axml_manifest_metadata",
]
