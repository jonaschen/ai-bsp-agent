# Android BSP Diagnostic Expert

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **Version:** v6.8 (Phase 8 — Workspace Skills · 22 diagnostic skills · 539 tests)
> **Status:** Alpha — open for trial use and feedback

## Project Overview

This repository hosts the **Android BSP Diagnostic Expert**, a specialized AI agent system for diagnosing complex Android/Linux BSP (Board Support Package) issues. The system uses an Anthropic Claude tool-use loop paired with deterministic Python skills to perform accurate Root Cause Analysis (RCA) on kernel logs, power management failures, and hardware-related panics.

> **Alpha testers:** see [QUICKSTART.md](QUICKSTART.md) for the fastest path from clone to first diagnosis.

### Market Positioning

The **Android BSP Diagnostic Expert** occupies a unique niche by utilizing the Anthropic Tool-Use / Agent Skill paradigm. It serves as a **Specialized AI Agent** for:

- **Domain-Specific Expertise:** Focusing on the high-stakes, log-intensive environment of Android Board Support Package (BSP) development.
- **Deterministic Reasoning:** Replacing error-prone AI code generation with deterministic, human-authored Python tools that provide ground truth for the reasoning LLM.

### Why This Matters

- **Accuracy over Autonomy:** By enforcing strict tool use, we prevent LLM hallucinations regarding hardware state and register calculations.
- **Skill-Based Architecture:** The v6 pivot replaces the legacy code-generation factory with an expert diagnostic agent backed by pure Python Skills.

---

## Architecture

The system operates as a **Skill-Based Expert Agent** using the Anthropic Tool-Use paradigm. Three distinct layers:

### Layer 1: The Brain (Reasoning Engine)

- **`BSPDiagnosticAgent`** (`product/bsp_agent/agent.py`): Runs the Claude Sonnet tool-use loop; invokes Skills via `dispatch_tool()` and validates the final `ConsultantResponse`.
- **`SupervisorAgent`** (`product/bsp_agent/agents/supervisor.py`): Triage router — classifies incoming logs and routes to one of four specialist domains. Early boot logs (TF-A/LK/U-Boot markers, no kernel timestamp) are detected by pure regex and bypass the LLM entirely. Kernel and Android logs are sent to Claude Haiku (max_tokens=16) for a single routing token.
- **Constraint:** The Brain never performs math, parses hex offsets, or calculates memory sizes — it always delegates to Skills.

### Layer 2: The Skill Registry (Deterministic Tools)

Pure Python functions in `skills/bsp_diagnostics/`. Every skill has:
- Strict Pydantic `Input`/`Output` schemas
- Registration in `skills/registry.py` as an Anthropic-compatible tool definition
- Isolated `pytest` coverage — no LLM calls

### Layer 3: The Knowledge Base

Markdown files in `docs/` with YAML frontmatter scoping each document to a supervisor route and skill set. The Brain reads these as context to produce better `root_cause_summary` and `sop_steps` in the `ConsultantResponse`.

---

## Diagnostic Skills

22 core skills across 5 supervisor routes + 2 universal improvement tools (24 total).

### Universal triage (all routes)

| Skill | File | What it detects |
|---|---|---|
| `segment_boot_log` | `log_segmenter.py` | Identifies failing stage boundary: `early_boot` / `kernel_init` / `android_init` / `unknown`; returns suggested route and first error line. Always invoked first (AGENTS.md §3.1) |
| `validate_skill_extension` | `skill_improvement.py` | Dry-run — tests a regex pattern against a log snippet without writing anything |
| `suggest_pattern_improvement` | `skill_improvement.py` | Validates then persists a new detection pattern to `~/.bsp-diagnostics/skill_extensions.json` |

### `early_boot_advisor` route

| Skill | File | What it detects |
|---|---|---|
| `parse_early_boot_uart_log` | `early_boot.py` | TF-A auth failures, image load failures, DDR init failures, PMIC power-sequencing failures; identifies BL stage (BL1/BL2/BL31/U-Boot) and last successful handoff step |
| `analyze_lk_panic` | `early_boot.py` | LK `ASSERT FAILED` with source file/line extraction, U-Boot image magic errors, LK DDR/PMIC panics, ARM32/AArch64 register dump extraction |

### `hardware_advisor` route

| Skill | File | What it detects |
|---|---|---|
| `analyze_std_hibernation_error` | `std_hibernation.py` | STD Error -12; SUnreclaim > 10% MemTotal; SwapFree == 0 |
| `check_vendor_boot_ufs_driver` | `vendor_boot.py` | UFS driver failures during STD restore; phase-classified as probe / link_startup / resume |
| `check_pmic_rail_voltage` | `pmic.py` | PMIC OCP and undervoltage events; parses Qualcomm rpm-smd, qpnp, and generic regulator formats |
| `analyze_early_oom_killer` | `subsystems.py` | Early OOM kill events; extracts victim process, PID, oom_score_adj, and rss |

### `kernel_pathologist` route

| Skill | File | What it detects |
|---|---|---|
| `extract_kernel_oops_log` | `kernel_oops.py` | Detects `null_pointer` / `paging_request` / `kernel_bug` / `generic_oops`; extracts process, PID, CPU, ESR_EL1 hex, FAR_EL1 hex, pc/lr symbols, call trace (≤32 entries) |
| `decode_esr_el1` | `aarch64_exceptions.py` | Decodes AArch64 ESR_EL1 (EC, IL, ISS, DFSC/IFSC) against ARM DDI0487 tables |
| `decode_aarch64_exception` | `aarch64_exceptions.py` | Decodes ESR_EL1 + FAR_EL1 together; infers exception level (EL0/EL1) from EC; classifies FAR as kernel vs. user-space address |
| `check_cache_coherency_panic` | `aarch64_exceptions.py` | SError / PoC cache coherency failures; ESR_EL1 EC=0x2F |
| `analyze_watchdog_timeout` | `watchdog.py` | Soft lockup, hard lockup (NMI watchdog), RCU stall; extracts CPU, PID, process name, call trace |
| `check_clock_dependencies` | `subsystems.py` | CCF probe-defer failures (`-EPROBE_DEFER`), `clk_get` failures; extracts driver and clock name |
| `diagnose_vfs_mount_failure` | `subsystems.py` | VFS root mount errors; decodes errno, identifies device and filesystem type |
| `analyze_firmware_load_error` | `subsystems.py` | `request_firmware` failures — missing file, timeout, or load error; extracts firmware name and driver |

### `android_init_advisor` route

| Skill | File | What it detects |
|---|---|---|
| `analyze_selinux_denial` | `android_init.py` | SELinux AVC denials (dmesg and logcat formats); deduplicated by `(scontext, tcontext, tclass, permission)`; permissive-mode detection |
| `check_android_init_rc` | `android_init.py` | `init.rc` command failures and service crashes; extracts service name, exit code, and signal |

### `source_analyst` route

| Skill | File | What it detects |
|---|---|---|
| `resolve_oops_symbols` | `workspace.py` | Resolves hex addresses from an Oops call trace to source file + line via `addr2line` against a `vmlinux` |
| `compare_device_tree_nodes` | `workspace.py` | Diffs two DTS node text blocks; highlights added, removed, and changed properties |
| `diff_kernel_configs` | `workspace.py` | Diffs two kernel `.config` files; classifies changed options as added, removed, or changed |
| `validate_gpio_pinctrl_conflict` | `workspace.py` | Detects GPIO pin number conflicts and `pinctrl-0` collisions within a single DTS file |

---

## Repository Structure

```
.
├── AGENTS.md                        # The Constitution: rules and governance for all agents.
├── CLAUDE.md                        # Coding agent guidance and milestone tracker.
├── DESIGN.md                        # Software design document (class diagram, sequence diagram, roadmap).
├── QUICKSTART.md                    # Alpha-tester quick-start guide (start here).
├── README.md                        # This file.
├── pyproject.toml                   # Installable package — provides bsp-diagnostics-mcp entry point.
├── cli.py                           # CLI entry point: python cli.py --dmesg <path> [--meminfo <path>]
├── requirements.txt                 # Python dependencies (includes mcp>=1.0).
├── pytest.ini                       # Pytest configuration (pythonpath = .).
├── mcp_server/                      # MCP server — registers all skills with Claude CLI / VS Code.
│   ├── __init__.py
│   └── server.py                    # stdio MCP server; entry point: bsp-diagnostics-mcp
├── emulator_scripts/                # Log generation toolkit for real-world validation.
│   ├── setup.sh                     # One-time install: QEMU, Android SDK, AVD, Alpine ISO.
│   ├── run-android-emulator.sh      # 4 scenarios: normal, slow, SELinux, kernel panic via AVD.
│   ├── run-linux-qemu.sh            # 4 scenarios: normal, slow, panic, audit via QEMU/Alpine.
│   └── collect-logs.sh              # Normalize + merge outputs; generates INDEX.md.
├── docs/                            # Knowledge base — domain reference for the Brain.
│   ├── aarch64-exceptions.md        # ESR_EL1 field layout, EC/DFSC tables, SError checklist.
│   ├── android-init.md              # SELinux type enforcement, init.rc lifecycle, triage decision tree.
│   ├── emulator-spec.md             # Exact software/source versions for all training emulators.
│   ├── memory-reclamation.md        # STD hibernation failure logic, SUnreclaim/SwapFree thresholds.
│   ├── skill-extension-guide.md     # How to extend built-in skills for real-hardware patterns.
│   ├── subsystem-boot.md            # CCF probe-defer, VFS errno table, firmware search paths.
│   └── workspace-analysis.md        # addr2line prerequisites, DTS naming conventions, GPIO conflict resolution.
├── product/                         # Core product logic.
│   ├── bsp_agent/
│   │   ├── agent.py                 # BSPDiagnosticAgent — the main Claude tool-use loop.
│   │   └── agents/
│   │       └── supervisor.py        # SupervisorAgent — log triage router (Claude Haiku).
│   └── schemas/
│       └── __init__.py              # All Pydantic models: CaseFile, ConsultantResponse, LogPayload, …
├── skills/                          # The Skill Registry: deterministic Python tools.
│   ├── SKILL.md                     # Skill index and authoring contract.
│   ├── extensions.py                # Extension loader/writer (~/.bsp-diagnostics/skill_extensions.json)
│   ├── registry.py                  # Anthropic tool definitions + dispatch_tool() router.
│   └── bsp_diagnostics/
│       ├── log_segmenter.py         # segment_boot_log (universal triage — all routes)
│       ├── early_boot.py            # parse_early_boot_uart_log, analyze_lk_panic
│       ├── kernel_oops.py           # extract_kernel_oops_log
│       ├── std_hibernation.py       # analyze_std_hibernation_error
│       ├── aarch64_exceptions.py    # decode_esr_el1, decode_aarch64_exception, check_cache_coherency_panic
│       ├── vendor_boot.py           # check_vendor_boot_ufs_driver
│       ├── watchdog.py              # analyze_watchdog_timeout
│       ├── pmic.py                  # check_pmic_rail_voltage
│       ├── android_init.py          # analyze_selinux_denial, check_android_init_rc
│       ├── subsystems.py            # check_clock_dependencies, diagnose_vfs_mount_failure,
│       │                            #   analyze_firmware_load_error, analyze_early_oom_killer
│       ├── workspace.py             # resolve_oops_symbols, compare_device_tree_nodes,
│       │                            #   diff_kernel_configs, validate_gpio_pinctrl_conflict
│       └── skill_improvement.py     # validate_skill_extension, suggest_pattern_improvement
├── logs/validation/                 # 28 real-hardware-style log fixtures (validated 28/28 PASS)
├── reports/                         # skill_validation_report.md — latest validation run
├── tools/
│   └── skill_validation.py          # Deterministic 28-log validator (no LLM)
└── tests/
    └── product_tests/               # Isolated pytest suite (no LLM calls) — 539 tests.
        ├── test_integration.py      # End-to-end pipeline (mocked Anthropic client).
        └── fixtures/                # Golden-set log files and expected output JSON.
└── studio/                          # Legacy factory code (deprecated — do not modify).
```

---

## Getting Started

> **Alpha testers:** see [QUICKSTART.md](QUICKSTART.md) for the fastest path to a first diagnosis. This section is the complete reference.

### Prerequisites

- Python 3.11+ (`pyproject.toml` sets `requires-python = ">=3.11"`)
- Git
- `ANTHROPIC_API_KEY` — required for agent/CLI execution; **not** needed for skill unit tests or the MCP server.
  Get a key at [console.anthropic.com](https://console.anthropic.com/).

### Installation

```bash
# 1. Clone
git clone https://github.com/jonaschen/ai-bsp-agent.git
cd ai-bsp-agent

# 2. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate          # Linux / macOS
# venv\Scripts\activate           # Windows (PowerShell)

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set your Anthropic API key (required for CLI / agent)
export ANTHROPIC_API_KEY="sk-ant-..."
# Add to ~/.bashrc or ~/.zshrc to persist across sessions
```

### Running Tests

No API key needed — the full test suite is isolated:

```bash
source venv/bin/activate && python -m pytest
# Expected: 539 passed (product tests only; studio legacy tests are ignored)
```

Run a single skill test file:

```bash
source venv/bin/activate && python -m pytest tests/product_tests/test_watchdog_skill.py
```

### Using as an MCP Server (Claude CLI / Claude Code in VS Code)

All 22 BSP diagnostic skills can be registered as an MCP server so they appear
as native tools inside `claude` (CLI) or the Claude Code VS Code extension.

**Step 1 — install the package (editable, from project root):**

```bash
pip install -e .
```

**Step 2 — register the MCP server:**

```bash
# Claude CLI
claude mcp add bsp-diagnostics bsp-diagnostics-mcp

# Without installing (run from project root):
claude mcp add bsp-diagnostics -- python -m mcp_server.server
```

**Step 3 — VS Code (Claude Code extension):**

Add the following to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "bsp-diagnostics": {
      "command": "bsp-diagnostics-mcp"
    }
  }
}
```

Or, without a package install (replace `/path/to/ai-bsp-agent` with your clone path):

```json
{
  "mcpServers": {
    "bsp-diagnostics": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "/path/to/ai-bsp-agent"
    }
  }
}
```

After registration, all 24 skills (`segment_boot_log`, `extract_kernel_oops_log`,
`decode_esr_el1`, `analyze_watchdog_timeout`, `validate_skill_extension`, etc.)
appear in Claude's tool list. No `ANTHROPIC_API_KEY` is required for the MCP
server itself — the skills are pure deterministic Python functions.

---

### CLI Usage

```bash
# Basic — dmesg only
python cli.py --dmesg logs/dmesg.txt

# With meminfo (required for STD hibernation diagnosis)
python cli.py --dmesg logs/dmesg.txt --meminfo logs/meminfo.txt

# Save structured output to file
python cli.py --dmesg logs/panic.txt --device Pixel_Watch_Proto --output result.json

# Custom query
python cli.py --dmesg logs/dmesg.txt \
              --query "Device failed to resume from STD" \
              --output result.json

# Early boot UART log (TF-A / U-Boot / LK)
python cli.py --dmesg logs/uart_bl2_fail.txt \
              --query "Board fails to boot past BL2" \
              --output result.json
```

Output is a `ConsultantResponse` JSON printed to stdout. Status messages go to stderr so the JSON can be piped directly.

### Python API Usage

```python
from product.schemas import CaseFile, LogPayload
from product.bsp_agent.agent import BSPDiagnosticAgent

case = CaseFile(
    case_id="CASE-001",
    device_model="Pixel_Watch_Proto",
    source_code_mode="USER_UPLOADED",
    user_query="Device failed to resume from STD",
    log_payload=LogPayload(
        dmesg_content=open("logs/dmesg.txt").read(),
        meminfo_content=open("logs/meminfo.txt").read(),  # optional
    ),
)

agent = BSPDiagnosticAgent()  # requires ANTHROPIC_API_KEY
response = agent.run(case)
print(response.model_dump_json(indent=2))
```

---

## Generating Logs with the Emulator Scripts (Item #20)

If real hardware logs are not available, use `emulator_scripts/` to generate
realistic boot logs from an Android AVD and a Linux QEMU VM.

```bash
# 1. One-time setup (installs QEMU, Android SDK, creates AVD + Alpine disk)
cd emulator_scripts && bash setup.sh

# 2. Generate Android logs (4 scenarios: normal, slow, SELinux denials, panic)
bash run-android-emulator.sh ./logs/android

# 3. Generate Linux QEMU logs (4 scenarios: normal, slow, panic, audit)
bash run-linux-qemu.sh ./logs/linux

# 4. Normalize and merge into a single indexed collection
bash collect-logs.sh ./logs/android ./logs/linux ./logs/normalized
# → produces logs/normalized/INDEX.md with ready-to-run analysis commands
```

The normalized logs feed directly into `orchestrator.sh` (multi-agent shell
analysis) or `cli.py` (BSP diagnostic agent with MCP skills).

---

## Log Validation

The 28 emulator-generated log fixtures in `logs/validation/` have been validated against their expected skill outputs. All 28 pass.

```bash
# Run the deterministic skill validator (no LLM required)
source venv/bin/activate && python tools/skill_validation.py
# → Summary: 28 PASS, 0 PARTIAL, 0 FAIL
# → Full report: reports/skill_validation_report.md
```

See `LOG_PENDING_LIST.md` for the description and expected outcome of each log file, and `docs/emulator-spec.md` for how each log was generated.

### Emulator gaps (requires real hardware or `suggest_pattern_improvement`)

The emulator logs train on standard open-source formats. The following patterns require user extension when deploying on real BSP hardware:

| Skill | Known gap on real hardware |
|---|---|
| `segment_boot_log` | LK shell prompts from non-QEMU targets; vendor-specific pre-kernel banners |
| `parse_early_boot_uart_log` | Qualcomm DDR PHY training output; Samsung PMIC error codes |
| `analyze_lk_panic` | LK assert formats differ across Qualcomm SoC generations |
| `extract_kernel_oops_log` | GKI 4.14 / 5.10 Oops headers differ from 6.6 LTS format |
| `analyze_watchdog_timeout` | Qualcomm vendor format: `[0: kworker:1234] BUG: soft lockup` |
| `check_pmic_rail_voltage` | MediaTek / Samsung PMIC rail names not yet covered |
| `check_vendor_boot_ufs_driver` | MTK (`ufs-mediatek`) and Exynos (`ufshcd-exynos`) driver prefixes |
| `analyze_std_hibernation_error` | 10% SUnreclaim threshold may need lowering for 512 MB devices |
| `analyze_selinux_denial` | Vendor-specific `tcontext` type names outside AOSP base policy |
| `check_android_init_rc` | Board-specific init.rc service names and exit codes |

Use `validate_skill_extension` + `suggest_pattern_improvement` to extend any skill for your hardware — see `docs/skill-extension-guide.md`.

---

## Adding a New Skill

1. Create `skills/bsp_diagnostics/<skill_name>.py` with `Input`/`Output` Pydantic models and the pure function.
2. Write isolated pytest in `tests/product_tests/test_<skill_name>.py` — no LLM.
3. Register in `skills/registry.py`: add to `TOOL_DEFINITIONS`, `ROUTE_TOOLS`, and `_DISPATCH_TABLE`.
4. Add a row to `skills/SKILL.md`.

See `AGENTS.md` §4 for the full development protocol.

---

## License

This project is licensed under the **MIT License**.

- **SPDX Identifier:** [MIT](https://opensource.org/licenses/MIT)
- **License Text:** See the [LICENSE](LICENSE) file in this repository for full details.
