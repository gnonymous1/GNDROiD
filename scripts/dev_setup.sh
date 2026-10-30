#!/usr/bin/env bash
set -euo pipefail

echo "=========================================================="
echo "  IndusBridge Android Micro-VM: Toolchain Setup           "
echo "=========================================================="

# Check KVM access
if [ -e /dev/kvm ]; then
    echo "[✓] /dev/kvm is available."
    sudo chmod 666 /dev/kvm || true
else
    echo "[!] Warning: /dev/kvm not found. Ensure nested virtualization is enabled."
fi

# Ensure cargo and rust are available
if command -v cargo &> /dev/null; then
    echo "[✓] Rust toolchain found: $(cargo --version)"
else
    echo "[-] Installing Rust toolchain..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
fi

# Ensure protobuf compiler is available
if command -v protoc &> /dev/null; then
    echo "[✓] Protoc compiler found: $(protoc --version)"
else
    echo "[-] Installing protobuf-compiler..."
    sudo apt-get update && sudo apt-get install -y protobuf-compiler libprotobuf-dev
fi

echo "[✓] Environment ready for building crosvm, cellular bridge, and AI control plane."
