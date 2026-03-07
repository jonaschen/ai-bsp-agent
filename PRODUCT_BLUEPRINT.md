# PRODUCT_BLUEPRINT.md: The Android BSP Consultant (v6.0)

> **Authority:** This document is the **Product Vision** for the Android BSP Diagnostic Expert Agent (v6).
> It describes the system as built, validated, and currently deployed.
> See `AGENTS.md` for the authoritative architecture constitution, and `DESIGN.md` for the detailed software design.

---

## 1. Product Vision: "The Force Multiplier"

We are building a **Skill-Based Diagnostic Expert Agent** for Android BSP Engineers.

* **Problem:** Alert Fatigue and high MTTR in debugging Android/Linux BSP boot failures — spanning the full boot sequence from BootROM through Android userspace: early boot (TF-A/LK/U-Boot), kernel initialization (panics, exceptions, watchdog), subsystem bring-up (clocks, VFS, firmware), and Android init (SELinux, init.rc, PMIC/UFS hardware).
* **Solution:** A Consultant that analyzes logs (UART, `dmesg`, `/proc/meminfo`, logcat, AVC denials), calls deterministic Python Skills to extract facts, and produces a **Standard Operating Procedure (SOP)** for the human to execute.
* **Constraint (Phases 1–7):** The Agent is **Read-Only**. It cannot execute shell commands, reset hardware, or write to the kernel tree. It only offers high-confidence, evidence-backed advice.
* **Constraint (Phase 8+):** Stateful skills (toolchain, source tree) run locally with file path access. Governed action skills (Phase 10) require explicit Human-in-the-Loop approval before any code is written or built.

---

## 2. System Architecture (Three-Layer Expert)

The v6 architecture replaces the legacy multi-agent code-generation factory with a leaner, more accurate **Skill-Based Expert** system. See `PIVOT_PLAN.md` for the rationale.

```
┌───────────────────────────────────────────────────────────┐
│  Layer 1 — The Brain (Reasoning Engine)                   │
│  BSPDiagnosticAgent  ←→  SupervisorAgent (Claude Haiku)   │
│  (Claude Sonnet)                                          │
└────────────────────────┬──────────────────────────────────┘
                         │ dispatches
┌────────────────────────▼──────────────────────────────────┐
│  Layer 2 — The Skill Registry (Deterministic Tools)       │
│  skills/registry.py  →  skills/bsp_diagnostics/*.py       │
└────────────────────────┬──────────────────────────────────┘
                         │ references
┌────────────────────────▼──────────────────────────────────┐
│  Layer 3 — The Knowledge Base (Markdown Docs)             │
│  skills/SKILL.md  |  docs/  |  AGENTS.md                  │
└───────────────────────────────────────────────────────────┘
```

### Layer 1: The Brain

**`BSPDiagnosticAgent`** (`product/bsp_agent/agent.py`)
* Orchestrates the full diagnostic session.
* Accepts a `CaseFile` (containing a `LogPayload`), calls the Supervisor to triage and chunk the log, then runs the Anthropic tool-use loop with route-appropriate Skills.
* Returns a validated `ConsultantResponse`.
* Model: `claude-sonnet-4-6` (configurable). Never does math, parses hex, or calculates memory sizes — always delegates to Skills.

**`SupervisorAgent`** (`product/bsp_agent/agents/supervisor.py`)
* Fast triage router powered by `claude-haiku-4-5-20251001` (low-cost, single-token response).
* Validates that the input is a kernel log (regex timestamp check). Returns `clarify_needed` immediately if not.
* **Event-Horizon Chunking:** If log exceeds 50 MB, extracts ±10 s around the detected failure timestamp (falls back to last 5 000 lines).
* Routes to one of the registered destination tokens:

| Route token | Trigger | Phase |
|---|---|---|
| `kernel_pathologist` | Kernel panics, null-pointer dereferences, ESR_EL1, oops, watchdog | Current |
| `hardware_advisor` | STD / Suspend-to-Disk, PMIC, UFS, power management | Current |
| `clarify_needed` | Invalid or ambiguous input | Current |
| `early_boot_advisor` | No kernel timestamp pattern; TF-A / LK / U-Boot boot markers present | Phase 4 |
| `android_init_advisor` | SELinux AVC denials, init.rc `[FAILED]` markers, firmware load errors | Phase 6 |
| `source_analyst` | Regression / DTS change / commit keywords; workspace files provided | Phase 8 |

### Layer 2: The Skill Registry

Pure Python functions in `skills/bsp_diagnostics/`. Registered in `skills/registry.py`.

| Skill file | Function | Route | Domain |
|---|---|---|---|
| `std_hibernation.py` | `analyze_std_hibernation_error(dmesg_log, meminfo_log)` | `hardware_advisor` | STD / Suspend-to-Disk |
| `vendor_boot.py` | `check_vendor_boot_ufs_driver(dmesg_log)` | `hardware_advisor` | UFS Driver / STD Restore |
| `pmic.py` | `check_pmic_rail_voltage(dmesg_log, logcat_log)` | `hardware_advisor` | PMIC Rail Voltages |
| `aarch64_exceptions.py` | `decode_esr_el1(hex_value)` | `kernel_pathologist` | AArch64 Exceptions |
| `aarch64_exceptions.py` | `check_cache_coherency_panic(panic_log)` | `kernel_pathologist` | AArch64 Cache Coherency |
| `watchdog.py` | `analyze_watchdog_timeout(dmesg_log)` | `kernel_pathologist` | Watchdog / Soft+Hard Lockup |

**Skill contract:** Every Skill is a pure function — no side effects, no LLM calls, no global state. Every Skill has strict Pydantic `Input`/`Output` schemas and an isolated `pytest` in `tests/product_tests/` that does NOT invoke the LLM.

`skills/registry.py` exports:
* `TOOL_DEFINITIONS` — Anthropic-compatible tool dicts auto-generated from each Skill's Pydantic `Input` model.
* `ROUTE_TOOLS` — Maps supervisor routes to the relevant tool name set (reduces noise and token cost).
* `dispatch_tool(name, input_dict)` — Routes by name to the correct Skill function.

### Layer 3: The Knowledge Base

* `skills/SKILL.md` — Skill Registry index and authoring contract.
* `AGENTS.md` — Architecture constitution (authoritative; do not modify).
* `docs/memory-reclamation.md` — Deep-dive: `/proc/meminfo`, SUnreclaim thresholds, STD image sizing.
* `docs/aarch64-exceptions.md` — Deep-dive: ESR_EL1 bit fields, cache coherency indicators, TrustZone context.

---

## 2.5 Development Roadmap

### Phase 1 — Core Infrastructure ✓ DONE

All pieces of the v6 architecture are in place and tested.

| Item | Deliverable |
|---|---|
| Skill: `analyze_std_hibernation_error` | `skills/bsp_diagnostics/std_hibernation.py` — 14 tests |
| Skill Registry | `skills/registry.py` — `TOOL_DEFINITIONS`, `ROUTE_TOOLS`, `dispatch_tool()` — 11 tests |
| BSPDiagnosticAgent | `product/bsp_agent/agent.py` — tool-use loop, Supervisor integration, route-based tool selection |
| SupervisorAgent | `product/bsp_agent/agents/supervisor.py` — migrated to `claude-haiku-4-5-20251001` — 11 tests |
| Product Schemas | `product/schemas/__init__.py` — `CaseFile`, `LogPayload`, `ConsultantResponse`, `SOPStep`, all agent I/O contracts |
| Skill: `decode_esr_el1` | `skills/bsp_diagnostics/aarch64_exceptions.py` — 14 tests |
| Skill: `check_cache_coherency_panic` | `skills/bsp_diagnostics/aarch64_exceptions.py` — 17 tests |

### Phase 2 — Runnable & Validated ✓ DONE

| Item | Deliverable |
|---|---|
| CLI entry point | `cli.py` — `python cli.py --dmesg <path> [--meminfo <path>] [--output <path>]` |
| End-to-end integration test | `tests/product_tests/test_integration.py` — 25 tests across 3 fixture scenarios |
| Golden-set fixtures | `fixtures/panic_log_01.txt`, `fixtures/suspend_hang_02.txt`, `fixtures/healthy_boot_03.txt` + `expected_output_*.json` |
| Knowledge base docs | `docs/memory-reclamation.md`, `docs/aarch64-exceptions.md` |

### Phase 3 — Expanded Domain Coverage ✓ DONE

| # | Item | Route | Deliverable |
|---|---|---|---|
| 8 | Skill: `check_vendor_boot_ufs_driver` | `hardware_advisor` | `skills/bsp_diagnostics/vendor_boot.py` — 16 tests; phase-classified (probe/link_startup/resume) |
| 9 | Skill: `analyze_watchdog_timeout` | `kernel_pathologist` | `skills/bsp_diagnostics/watchdog.py` — 19 tests; soft/hard lockup, RCU stall, call trace extraction |
| 10 | Skill: `check_pmic_rail_voltage` | `hardware_advisor` | `skills/bsp_diagnostics/pmic.py` — 19 tests; OCP + undervoltage detection, rpm-smd/qpnp/generic formats |
| 11 | Real-world log validation | — | FUTURE — run against actual BSP logs; tune thresholds; document edge cases |
| | **Total product tests** | | **231 passing** |

### Phase 4 — Early Boot Skills (NEXT)

New supervisor route: `early_boot_advisor`.

| Deliverable | Detail |
|---|---|
| `skills/bsp_diagnostics/early_boot.py` | `parse_early_boot_uart_log`, `analyze_lk_panic` — ~18 tests |
| Supervisor update | Add `early_boot_advisor` route token + `ROUTE_TOOLS` entry |
| `docs/early-boot-stages.md` | TF-A BL1/BL2 error codes, LK assert format, DDR init failures |

### Phase 5 — Kernel Exception & Oops Skills (PLANNED)

Extends `kernel_pathologist` route. No new supervisor route.

| Deliverable | Detail |
|---|---|
| `skills/bsp_diagnostics/kernel_oops.py` | `extract_kernel_oops_log` — stateless hex call trace extractor — ~16 tests |
| Update `skills/bsp_diagnostics/aarch64_exceptions.py` | Add `decode_aarch64_exception(esr_val, far_val)` with FAR field — ~8 new tests |
| Update `docs/aarch64-exceptions.md` | FAR field layout, fault address interpretation |

### Phase 6 — Android Init Skills (PLANNED)

New supervisor route: `android_init_advisor`.

| Deliverable | Detail |
|---|---|
| `skills/bsp_diagnostics/android_init.py` | `analyze_selinux_denial`, `check_android_init_rc` — ~20 tests |
| Supervisor update | Add `android_init_advisor` route token + `ROUTE_TOOLS` entry |
| `docs/android-init.md` | SELinux type enforcement, init.rc service lifecycle, capability requirements |

### Phase 7 — Subsystem Diagnostics (PLANNED)

Log-only variants; extends existing routes. No new supervisor route.

| Deliverable | Detail |
|---|---|
| `skills/bsp_diagnostics/subsystems.py` | `check_clock_dependencies`, `diagnose_vfs_mount_failure`, `analyze_firmware_load_error`, `analyze_early_oom_killer` — ~24 tests |
| `docs/subsystem-boot.md` | CCF probe defer patterns, VFS mount error codes, firmware search paths |

### Phase 8 — Stateful Workspace Skills (PLANNED — infrastructure decision required)

New supervisor route: `source_analyst`. First phase requiring file system access.
Recommended implementation: file path inputs + `addr2line` subprocess (Option A). See `ANDROID_LINUX_BSP_BOOTING_SKILL_SETS.md` §6 for the full option analysis.

| Deliverable | Detail |
|---|---|
| `skills/bsp_diagnostics/workspace.py` | `resolve_oops_symbols`, `compare_device_tree_nodes`, `diff_kernel_configs`, `validate_gpio_pinctrl_conflict` — ~20 tests |
| Supervisor update | Add `source_analyst` route token + `ROUTE_TOOLS` entry |
| `docs/workspace-analysis.md` | DTS node naming conventions, CONFIG flag impact reference |

### Phase 9a — SoC Errata Lookup (PLANNED)

| Deliverable | Detail |
|---|---|
| `skills/knowledge/errata.py` | `check_soc_errata_tracker` — static dict keyed by `(ip_block, soc_revision)` — ~12 tests |

### Phase 9b — ARM TRM RAG (DEFERRED)

`query_arm_trm_database`. Requires vector DB + embedding pipeline. Deferred until Phase 9a is validated in real use.

### Phase 10 — Governed Actions (DEFERRED)

`generate_patch_and_build` with HITL blocking approval gate and sandbox/CI environment. Deferred until Phases 4–7 are validated on real BSP logs.

---

**Full test count target after Phases 4–7:** ~317 product tests (~86 new + 231 current).

---

## 3. The Diagnostic Workflow & Output Schema

The product output is NOT just a text answer. Every diagnostic session produces a `ConsultantResponse` — a validated Pydantic model serialised to JSON.

**`ConsultantResponse` schema** (`product/schemas/__init__.py`):

```json
{
  "diagnosis_id": "RCA-BSP-001",
  "confidence_score": 0.0 to 1.0,
  "status": "CRITICAL | WARNING | INFO | CLARIFY_NEEDED",
  "root_cause_summary": "Brief description of the root cause",
  "evidence": [
    "[ 1450.02] i2c_transfer_timeout"
  ],
  "sop_steps": [
    {
      "step_id": 1,
      "action_type": "MEASUREMENT | CODE_PATCH",
      "instruction": "Probe Test Point TP34 (I2C_SDA)",
      "expected_value": "Held High (1.8V)",
      "file_path": "N/A"
    }
  ]
}
```

**`status` values:**
* `CRITICAL` — High-confidence failure identified; immediate action required.
* `WARNING` — Potential issue detected; action recommended.
* `INFO` — No anomaly; system appears healthy.
* `CLARIFY_NEEDED` — Input was invalid or ambiguous; more information required from the user.

**CLI usage:**
```bash
python cli.py --dmesg fixtures/panic_log_01.txt [--meminfo /proc/meminfo] [--output report.json]
```

---

## 4. Evaluation Criteria: The Golden Set (TDD)

The three canonical test scenarios exercise each major diagnostic path. Fixture files live in `fixtures/`. Expected outputs live in `fixtures/expected_output_*.json`. Integration tests run in `tests/product_tests/test_integration.py`.

### Test Case 1: The "Null Pointer" (Software Panic)

* **Input:** `fixtures/panic_log_01.txt` — NULL pointer dereference in `mdss_dsi.c`.
* **Supervisor route:** `kernel_pathologist`
* **Expected output (`fixtures/expected_output_panic_log_01.json`):**

```json
{
  "diagnosis_id": "RCA-BSP-001",
  "confidence_score": 0.95,
  "status": "CRITICAL",
  "root_cause_summary": "Null Pointer Dereference in mdss_dsi driver.",
  "evidence": [
    "[ 102.553882] BUG: kernel NULL pointer dereference, address: 0000000000000008",
    "pc : mdss_dsi_probe+0x34/0x110"
  ],
  "sop_steps": [
    {
      "step_id": 1,
      "action_type": "CODE_PATCH",
      "instruction": "Add NULL check for clock pointer in mdss_dsi_probe before access.",
      "expected_value": "Kernel boots without panic.",
      "file_path": "drivers/gpu/drm/msm/mdss_dsi.c"
    }
  ]
}
```

### Test Case 2: The "Sleep Zombie" (Hardware Hang)

* **Input:** `fixtures/suspend_hang_02.txt` — System freezes during STD; dmesg ends with watchdog hard lockup.
* **Supervisor route:** `hardware_advisor`
* **Expected output (`fixtures/expected_output_suspend_hang_02.json`):**

```json
{
  "diagnosis_id": "RCA-BSP-002",
  "confidence_score": 0.85,
  "status": "CRITICAL",
  "root_cause_summary": "Watchdog Timeout / Hard Lockup during suspend.",
  "evidence": [
    "watchdog: Watchdog detected hard lockup on CPU 0",
    "Kernel panic - not syncing: watchdog: Watchdog detected hard lockup on CPU 0"
  ],
  "sop_steps": [
    {
      "step_id": 1,
      "action_type": "MEASUREMENT",
      "instruction": "Connect JTAG and check Program Counter (PC) to identify the hang location.",
      "expected_value": "PC points to a specific loop or blocked function.",
      "file_path": "N/A"
    }
  ]
}
```

### Test Case 3: The "False Alarm" (Healthy Boot)

* **Input:** `fixtures/healthy_boot_03.txt` — A standard, error-free Android boot log.
* **Supervisor route:** `kernel_pathologist` or `hardware_advisor` (no failure present)
* **Expected output (`fixtures/expected_output_healthy_boot_03.json`):**

```json
{
  "diagnosis_id": "RCA-BSP-003",
  "confidence_score": 0.98,
  "status": "INFO",
  "root_cause_summary": "No Anomaly Detected. Clean boot sequence completed.",
  "evidence": [
    "systemd[1]: Reached target Multi-User System.",
    "systemd[1]: Startup finished in 2.104s."
  ],
  "sop_steps": [
    {
      "step_id": 1,
      "action_type": "MEASUREMENT",
      "instruction": "None required.",
      "expected_value": "System remains stable.",
      "file_path": "N/A"
    }
  ]
}
```

---

## 5. Technical Constraints

* **LLM Provider:** Anthropic API (`claude-sonnet-4-6` for diagnosis, `claude-haiku-4-5-20251001` for triage).
* **Context Window:** Up to 200 K tokens per request; large logs are chunked by the Supervisor's Event-Horizon algorithm before LLM dispatch.
* **Skill Purity (Phases 1–7):** All diagnostic logic lives in deterministic Python functions — no LLM calls inside Skills. Pure functions: no side effects, no I/O, no global state.
* **Stateful Skills (Phase 8):** `resolve_oops_symbols` calls `aarch64-linux-gnu-addr2line` via subprocess. DTS/config skills read files from paths provided by the user. These are the only Skills permitted to touch the file system, and only in read-only mode.
* **Governed Actions (Phase 10):** `generate_patch_and_build` may write files and invoke a build system, but only inside an isolated Git branch and only after receiving a signed Human-in-the-Loop approval token. Build artefacts are never auto-flashed.
* **No Vector Store (Phases 1–9a):** Datasheet RAG is deferred to Phase 9b. Current Skills parse structured log fields directly.
* **Security:**
  * **Read-Only (Phases 1–7):** Agents cannot execute shell commands on the user's host.
  * **Privacy:** Logs are processed in-process; no log content is written to disk or external storage by the Agent.
* **Testing:** Every Skill has isolated `pytest` coverage that does NOT invoke the LLM. Integration tests mock the Anthropic API. Stateful skills (Phase 8) mock subprocess calls and use fixture files in `tests/fixtures/`.
