# E2E Test Infra: GNDROiD Platform Audit & Remediation

## Test Philosophy
- Opaque-box, requirement-driven test architecture derived strictly from `ORIGINAL_REQUEST.md`.
- Comprehensive multi-tier test methodology: Category-Partition (Tier 1), Boundary Value Analysis (Tier 2), Pairwise Combinations (Tier 3), and Real-World Workload Testing (Tier 4).
- Zero tolerance for simulated assertions, hardcoded `pass_5 = True`, tautologies (`or True`), or mock length hacks.

## Feature Inventory & Test Coverage Requirements
| # | Feature Area | Requirement Source | Tier 1 (Min 5) | Tier 2 (Min 5) | Tier 3 (Pairwise) | Tier 4 (Scenario) |
|---|--------------|-------------------|:--------------:|:--------------:|:-----------------:|:-----------------:|
| 1 | VM Lifecycle Management | R3 & R4 | 5 | 5 | ✓ | ✓ |
| 2 | Scrcpy Phone Mirroring & Virtual Displays | R3 & R4 | 5 | 5 | ✓ | ✓ |
| 3 | App Sandboxing & Multi-Account Cloning | R3 & R4 | 5 | 5 | ✓ | ✓ |
| 4 | ADB Doctor Diagnostics & Network Routing | R2 & R4 | 5 | 5 | ✓ | ✓ |
| 5 | Native Rust CLI Orchestrator Commands | R1, R3, R4 | 5 | 5 | ✓ | ✓ |

## Test Architecture
- Test Runner: `python scripts/run_e2e_verification.py`
- Test cases located in `tests/e2e/` and `scripts/`
- Zero crashes when offline or when no emulator is pre-booted: test runner must mock or start instances cleanly without crashing on `/dev/tun` checks.

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Expected Outcome |
|---|----------|--------------------|------------------|
| 1 | Full VM Cold Boot & Teardown | VM Lifecycle, Process Safety | Clean start, PID tracking, clean shutdown with zero orphan processes |
| 2 | Scrcpy Virtual Display App Launch | Scrcpy Mirroring, App Drawer, CLI | Launch in dedicated floating window without pipe buffer stall |
| 3 | Multi-Account App Clone & Pin | App Cloner, Sandboxing, Shortcuts | Inode isolation across users, working desktop `.lnk` shortcut |
| 4 | Network Doctor & Guest MTU Clamp | ADB Doctor, VpnService, MTU 1380 | Real shell commands pass, no tautological `or True` returns |
| 5 | CLI Orchestrator Full Control Flow | Rust CLI (`gndroid.exe`), Launch, Mirror | Correct CLI argument routing to backend without crashes |
