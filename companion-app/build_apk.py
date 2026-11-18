#!/usr/bin/env python3
"""
companion-app/build_apk.py
==========================
Automated Standalone Android Build Toolchain for GNDROiD Companion APK.
Compiles resources with AAPT2, compiles Java sources with Javac, translates to DEX
with D8, aligns with Zipalign, and signs with Apksigner using modern Android SDK 34.
"""

import os
import sys
import glob
import shutil
import zipfile
import subprocess

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)

# Toolchain discovery
SDK_DIR = os.path.expanduser(r"~\AppData\Local\Android\Sdk")
BUILD_TOOLS_DIR = os.path.join(SDK_DIR, "build-tools", "34.0.0")
PLATFORM_JAR = os.path.join(SDK_DIR, "platforms", "android-34", "android.jar")

AAPT2 = os.path.join(BUILD_TOOLS_DIR, "aapt2.exe")
D8_BAT = os.path.join(BUILD_TOOLS_DIR, "d8.bat")
ZIPALIGN = os.path.join(BUILD_TOOLS_DIR, "zipalign.exe")
APKSIGNER_BAT = os.path.join(BUILD_TOOLS_DIR, "apksigner.bat")

JAVA_HOME = r"C:\Program Files\Eclipse Adoptium\jdk-17.0.20.8-hotspot"
JAVAC = os.path.join(JAVA_HOME, "bin", "javac.exe") if os.path.exists(os.path.join(JAVA_HOME, "bin", "javac.exe")) else "javac"
KEYTOOL = os.path.join(JAVA_HOME, "bin", "keytool.exe") if os.path.exists(os.path.join(JAVA_HOME, "bin", "keytool.exe")) else "keytool"
JARSIGNER = os.path.join(JAVA_HOME, "bin", "jarsigner.exe") if os.path.exists(os.path.join(JAVA_HOME, "bin", "jarsigner.exe")) else "jarsigner"

BUILD_DIR = os.path.join(BASE_DIR, "build")
RES_DIR = os.path.join(BASE_DIR, "app", "src", "main", "res")
ASSETS_DIR = os.path.join(BASE_DIR, "app", "src", "main", "assets")
MANIFEST = os.path.join(BASE_DIR, "app", "src", "main", "AndroidManifest.xml")
JAVA_SRC_DIR = os.path.join(BASE_DIR, "app", "src", "main", "java")
KEYSTORE = os.environ.get("GNDROID_KEYSTORE_PATH", os.path.join(BASE_DIR, "gndroid.keystore"))
KS_PASS = os.environ.get("GNDROID_KEYSTORE_PASS", "gndroid2026")
KEY_ALIAS = os.environ.get("GNDROID_KEY_ALIAS", "gndroid")
KEY_PASS = os.environ.get("GNDROID_KEY_PASS", KS_PASS)


def run_cmd(cmd, desc=""):
    print(f"[*] {desc}: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=BASE_DIR, shell=isinstance(cmd, str))
    if res.returncode != 0:
        print(f"[!] FAILED: {desc}")
        if res.stdout:
            print(f"STDOUT:\n{res.stdout}")
        if res.stderr:
            print(f"STDERR:\n{res.stderr}")
        sys.exit(1)
    return res


def ensure_keystore():
    if not os.path.exists(KEYSTORE):
        print("[*] Generating production signing keystore: gndroid.keystore...")
        cmd = [
            KEYTOOL, "-genkeypair", "-v",
            "-keystore", KEYSTORE,
            "-alias", KEY_ALIAS,
            "-keyalg", "RSA",
            "-keysize", "2048",
            "-validity", "10000",
            "-storepass", KS_PASS,
            "-keypass", KS_PASS,
            "-dname", "CN=GNDROiD Suite, OU=Engineering, O=IndusBridge, L=Karachi, ST=Sindh, C=PK"
        ]
        run_cmd(cmd, "Keytool Keystore Generation")


def build():
    print("=" * 70)
    print("  GNDROiD Companion App (GNDROiD Link) — Automated Build Pipeline")
    print("=" * 70)

    # 1. Clean build directory
    if os.path.exists(BUILD_DIR):
        shutil.rmtree(BUILD_DIR)
    os.makedirs(BUILD_DIR, exist_ok=True)
    gen_dir = os.path.join(BUILD_DIR, "gen")
    classes_dir = os.path.join(BUILD_DIR, "classes")
    dex_dir = os.path.join(BUILD_DIR, "dex")
    os.makedirs(gen_dir, exist_ok=True)
    os.makedirs(classes_dir, exist_ok=True)
    os.makedirs(dex_dir, exist_ok=True)

    # 2. Compile resources
    compiled_res = os.path.join(BUILD_DIR, "compiled_res.zip")
    run_cmd([AAPT2, "compile", "--dir", RES_DIR, "-o", compiled_res], "AAPT2 Compile Resources")

    # 3. Link resources & generate R.java
    res_apk = os.path.join(BUILD_DIR, "res_linked.apk")
    link_cmd = [
        AAPT2, "link",
        "-I", PLATFORM_JAR,
        "--manifest", MANIFEST,
        "-o", res_apk,
        "--java", gen_dir,
        "--auto-add-overlay",
    ]
    if os.path.exists(ASSETS_DIR):
        link_cmd.extend(["-A", ASSETS_DIR])
    link_cmd.append(compiled_res)
    run_cmd(link_cmd, "AAPT2 Link Resources & Gen R.java")

    # 4. Gather all Java files
    java_files = []
    for root, _, files in os.walk(JAVA_SRC_DIR):
        for f in files:
            if f.endswith(".java"):
                java_files.append(os.path.join(root, f))
    for root, _, files in os.walk(gen_dir):
        for f in files:
            if f.endswith(".java"):
                java_files.append(os.path.join(root, f))

    print(f"[*] Found {len(java_files)} Java source files to compile.")

    # 5. Compile Java files
    javac_cmd = [
        JAVAC,
        "-encoding", "UTF-8",
        "-source", "8",
        "-target", "8",
        "-cp", PLATFORM_JAR,
        "-d", classes_dir
    ] + java_files
    run_cmd(javac_cmd, "Javac Source Compilation")

    # 6. Translate classes to DEX
    class_files = []
    for root, _, files in os.walk(classes_dir):
        for f in files:
            if f.endswith(".class"):
                class_files.append(os.path.join(root, f))
    print(f"[*] Compiling {len(class_files)} classes to DEX with D8...")

    d8_cmd = f'"{D8_BAT}" --min-api 24 --lib "{PLATFORM_JAR}" --output "{dex_dir}" ' + " ".join([f'"{cf}"' for cf in class_files])
    run_cmd(d8_cmd, "D8 DEX Bytecode Translation")

    classes_dex = os.path.join(dex_dir, "classes.dex")
    if not os.path.exists(classes_dex):
        print("[!] Error: classes.dex was not generated!")
        sys.exit(1)

    # 7. Merge DEX into APK
    unaligned_apk = os.path.join(BUILD_DIR, "unaligned.apk")
    shutil.copyfile(res_apk, unaligned_apk)

    # Add classes.dex into unaligned_apk
    with zipfile.ZipFile(unaligned_apk, "a", compression=zipfile.ZIP_DEFLATED) as z:
        z.write(classes_dex, "classes.dex")
    print("[*] Merged classes.dex into unaligned.apk")

    # 8. Jarsigner V1 JAR Signing
    ensure_keystore()
    jarsigner_cmd = [
        JARSIGNER,
        "-keystore", KEYSTORE,
        "-storepass", KS_PASS,
        "-keypass", KEY_PASS,
        unaligned_apk,
        KEY_ALIAS
    ]
    run_cmd(jarsigner_cmd, "Jarsigner V1 JAR Signing")

    # 9. Zipalign (must be executed after v1 signing and before v2/v3 signing)
    aligned_apk = os.path.join(BUILD_DIR, "aligned.apk")
    run_cmd([ZIPALIGN, "-f", "-p", "4", unaligned_apk, aligned_apk], "Zipalign 4-byte Alignment")

    # 10. Apksigner V2 + V3 Full-APK Signing
    final_apk = os.path.join(BUILD_DIR, "GNDROiD_Companion.apk")
    sign_cmd = f'"{APKSIGNER_BAT}" sign --v1-signing-enabled true --v2-signing-enabled true --v3-signing-enabled true --ks "{KEYSTORE}" --ks-pass pass:{KS_PASS} --ks-key-alias {KEY_ALIAS} --key-pass pass:{KEY_PASS} --out "{final_apk}" "{aligned_apk}"'
    run_cmd(sign_cmd, "Apksigner V2+V3 Signing")

    # 11. Verify signature
    verify_cmd = f'"{APKSIGNER_BAT}" verify --verbose "{final_apk}"'
    res_v = run_cmd(verify_cmd, "Apksigner Verification")
    print(res_v.stdout.strip())

    apk_size = os.path.getsize(final_apk)
    print(f"\n🎉 Successfully built signed APK: {final_apk} ({apk_size:,} bytes)")

    # 11. Distribute to target directories
    targets = [
        os.path.join(PROJECT_ROOT, "nexus", "GNDROiD_Companion.apk"),
        os.path.join(PROJECT_ROOT, "nexus", "NexusAI_Mobile_Client.apk"),  # Backward compatibility
        os.path.join(PROJECT_ROOT, "tools", "GNDROiD_Companion.apk"),
        os.path.join(PROJECT_ROOT, "dist", "gndroid", "nexus", "GNDROiD_Companion.apk"),
        os.path.join(PROJECT_ROOT, "dist", "gndroid", "nexus", "NexusAI_Mobile_Client.apk"),
        os.path.join(PROJECT_ROOT, "dist", "gndroid", "tools", "GNDROiD_Companion.apk"),
    ]

    for t in targets:
        os.makedirs(os.path.dirname(t), exist_ok=True)
        shutil.copyfile(final_apk, t)
        print(f"  -> Deployed: {os.path.relpath(t, PROJECT_ROOT)}")

    print("=" * 70)
    print("  GNDROiD Companion App build and distribution completed 100%!")
    print("=" * 70)


if __name__ == "__main__":
    build()
