"""
tests/fixtures/bundle_generator.py
===================================
Pure-Python in-memory generator for genuine .xapk, .apkm, .apks, and .aab archives.
Supports creation of valid multi-split packages, OBB expansion directories,
and malformed archives for boundary and adversarial testing.
"""

import os
import io
import json
import zipfile
from typing import List, Optional


class SyntheticBundleGenerator:
    @staticmethod
    def _create_minimal_apk_bytes() -> bytes:
        """Constructs a valid minimal in-memory ZIP archive representing an APK."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("AndroidManifest.xml", b"\x00\x00\x08\x00\x24\x00\x00\x00\x01\x00")
            z.writestr("classes.dex", b"dex\n035\x00" + b"\x00" * 32)
        return buf.getvalue()

    @classmethod
    def create_xapk(
        cls,
        output_path: str,
        package_name: str = "com.indusbridge.app",
        version_code: int = 100,
        splits: Optional[List[str]] = None,
        with_obb: bool = True,
    ) -> str:
        if splits is None:
            splits = ["config.arm64_v8a.apk", "config.xxhdpi.apk", "config.en.apk"]

        manifest = {
            "xapk_version": 1,
            "package_name": package_name,
            "name": "SyntheticApp",
            "version_code": str(version_code),
            "version_name": "1.0.0",
            "min_sdk_version": "26",
            "target_sdk_version": "34",
            "split_configs": splits,
            "expansions": [],
        }

        apk_bytes = cls._create_minimal_apk_bytes()
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("base.apk", apk_bytes)
            for s in splits:
                s_name = s if s.endswith(".apk") else f"config.{s}.apk"
                z.writestr(s_name, apk_bytes)
            if with_obb:
                obb_rel = f"Android/obb/{package_name}/main.{version_code}.{package_name}.obb"
                z.writestr(obb_rel, b"OBB_PAYLOAD_TEST_DATA_" * 100)
                manifest["expansions"].append({"file": obb_rel, "install_location": "EXTERNAL_STORAGE"})
            z.writestr("manifest.json", json.dumps(manifest, indent=2))
        return output_path

    @classmethod
    def create_apkm(
        cls,
        output_path: str,
        package_name: str = "com.indusbridge.app",
        version_code: int = 100,
    ) -> str:
        info = {
            "pname": package_name,
            "package_name": package_name,
            "versioncode": version_code,
            "version_code": version_code,
            "versionname": "1.0.0",
            "splits": [
                {"name": "base.apk", "type": "base"},
                {"name": "split_config.arm64_v8a.apk", "type": "config.abi"},
                {"name": "split_config.en.apk", "type": "config.locale"},
            ],
        }
        apk_bytes = cls._create_minimal_apk_bytes()
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("info.json", json.dumps(info, indent=2))
            z.writestr("base.apk", apk_bytes)
            z.writestr("split_config.arm64_v8a.apk", apk_bytes)
            z.writestr("split_config.en.apk", apk_bytes)
        return output_path

    @classmethod
    def create_apks(
        cls,
        output_path: str,
        package_name: str = "com.indusbridge.app",
        version_code: int = 100,
        splits: Optional[List[str]] = None,
    ) -> str:
        apk_bytes = cls._create_minimal_apk_bytes()
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("toc.pb", b"\x08\x01\x12\x05table")
            z.writestr("splits/base-master.apk", apk_bytes)
            if splits:
                for s in splits:
                    s_name = s if s.endswith(".apk") else f"{s}.apk"
                    z.writestr(f"splits/{s_name}", apk_bytes)
            else:
                z.writestr("splits/base-arm64_v8a.apk", apk_bytes)
                z.writestr("splits/base-xxhdpi.apk", apk_bytes)
        return output_path

    @classmethod
    def create_aab(
        cls,
        output_path: str,
        package_name: str = "com.indusbridge.app",
        version_code: int = 100,
    ) -> str:
        apk_bytes = cls._create_minimal_apk_bytes()
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("BundleConfig.pb", b"\x0a\x04test")
            z.writestr("base/manifest/AndroidManifest.xml", b"\x00\x00\x08\x00")
            z.writestr("base/dex/classes.dex", b"dex\n035\x00" + b"\x00" * 16)
            # Include a pre-packaged split apk to allow pure-Python fallback unpacking without bundletool
            z.writestr("base.apk", apk_bytes)
            z.writestr("split_config.arm64.apk", apk_bytes)
        return output_path

    @classmethod
    def create_corrupted_bundle(cls, output_path: str, corruption_type: str) -> str:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        if corruption_type == "empty_zip":
            with zipfile.ZipFile(output_path, "w") as z:
                pass
        elif corruption_type == "missing_base":
            apk_bytes = cls._create_minimal_apk_bytes()
            with zipfile.ZipFile(output_path, "w") as z:
                z.writestr("manifest.json", json.dumps({"package_name": "com.test"}))
                z.writestr("config.arm64_v8a.apk", apk_bytes)
        elif corruption_type == "malformed_json":
            with zipfile.ZipFile(output_path, "w") as z:
                z.writestr("manifest.json", b"{malformed_json: missing_quotes")
        elif corruption_type == "zip_slip":
            with zipfile.ZipFile(output_path, "w") as z:
                z.writestr("../../evil_script.sh", b"echo hacked")
        elif corruption_type == "truncated":
            with open(output_path, "wb") as f:
                f.write(b"PK\x03\x04\x14\x00\x00\x00\x08\x00")  # Partial ZIP header
        return output_path


# Alias for compatibility
BundleGenerator = SyntheticBundleGenerator
