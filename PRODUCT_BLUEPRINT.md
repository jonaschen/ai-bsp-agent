# PRODUCT_BLUEPRINT.md: The Android BSP Consultant (v6.0)

> **Authority:** This document is the **Product Vision** for the Android BSP Diagnostic Expert Agent (v6).
> It describes the system as built, validated, and currently deployed.
> See `AGENTS.md` for the authoritative architecture constitution, and `DESIGN.md` for the detailed software design.

---

## 1. Product Vision: "The Force Multiplier"

We are building a **Skill-Based Diagnostic Expert Agent** for Android BSP Engineers.

* **Problem:** Alert Fatigue and high MTTR in debugging Suspend-to-Disk (STD) failures and Kernel Panics.
* **Solution:** A "Read-Only" Consultant that analyzes kernel logs (`dmesg`, `/proc/meminfo`), calls deterministic Python Skills to extract facts, and produces a **Standard Operating Procedure (SOP)** for the human to execute.
* **Constraint:** The Agent **DOES NOT** have hands. It cannot reset hardware or write to the kernel tree. It only offers high-confidence, evidence-backed advice.

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
* Routes to one of three destinations:
  * `kernel_pathologist` — kernel panics, null-pointer dereferences, oops
  * `hardware_advisor` — STD / Suspend-to-Disk failures, watchdog timeouts, power management
  * `clarify_needed` — invalid or ambiguous input

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
* **Skill Purity:** All diagnostic logic lives in deterministic Python functions — no LLM calls inside Skills.
* **No Vector Store (Phase 4):** Datasheet RAG is deferred to Phase 4. Current Hardware Advisor Skills parse structured log fields directly.
* **Security:**
  * **Read-Only:** Agents cannot execute shell commands on the user's host.
  * **Privacy:** Logs are processed in-process; no log content is written to disk or external storage by the Agent.
* **Testing:** Every Skill has isolated `pytest` coverage that does NOT invoke the LLM. Integration tests mock the Anthropic API.
