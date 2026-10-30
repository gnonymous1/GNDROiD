.PHONY: all build-all build-cli clean dev-setup test-all run-microvm build-kernel

all: build-all

build-cli:
	@echo "==> Building GNDROiD native Windows CLI & launcher..."
	cargo build -p gndroid --target x86_64-pc-windows-gnu --release
	cp target/x86_64-pc-windows-gnu/release/gndroid.exe ./gndroid.exe || true
	cp target/x86_64-pc-windows-gnu/release/gndroid.exe ./dist/gndroid/gndroid.exe || true

build-all: build-cli
	@echo "==> Building Rust micro-VM hypervisor, cellular bridge, and AI control plane..."
	cargo build --workspace --release

build-kernel:
	@echo "==> Building custom GKI 6.6 kernel with KernelSU & eBPF..."
	bash scripts/build_gki_kernel.sh

run-microvm:
	@echo "==> Launching crosvm Android micro-VM..."
	bash scripts/run_microvm.sh

test-all:
	@echo "==> Running workspace unit and integration tests..."
	cargo test --workspace
	python3 ai-control-plane/python/test_whatsapp_automation.py
	python3 deployment/ios-bridge/dual_device_controller.py
