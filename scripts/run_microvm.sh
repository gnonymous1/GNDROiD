#!/usr/bin/env bash
set -euo pipefail

WORKSPACE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN_PATH="${WORKSPACE_DIR}/target/release/emulator-hypervisor"

if [ ! -f "${BIN_PATH}" ]; then
    echo "[*] Building emulator hypervisor binary..."
    cargo build --package emulator-hypervisor --release
fi

echo "[*] Starting enterprise Android micro-VM via crosvm..."
exec "${BIN_PATH}" --dry-run
