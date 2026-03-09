# AARCH64_AGENT_SKILL_DEV_PLAN.md
# AArch64 Exception Diagnostic Skills — Development Plan

**Version:** 1.0
**Domain:** `kernel_pathologist` (primary), `early_boot_advisor` (secondary)
**Architecture scope:** ARMv8-A / ARMv9-A — 64-bit execution state (AArch64)
**Objective:** Define the complete skill inventory, development sequence, and testing strategy for deterministic AArch64 exception diagnosis within the Android BSP Diagnostic Expert Agent (v6).

---

## 0. Context & Placement in the Overall Roadmap

AArch64 exception diagnostics sit in the **`kernel_pathologist`** domain (see `AGENTS.md §4.2`).
The skills in this domain decode hardware-level fault registers and log patterns produced by the
Linux kernel when an exception causes a panic, oops, or hang.

These skills are **stateless** (Phases 1–5, 7): they take raw log strings as input and return
structured JSON. No source tree, toolchain, or file system access is required until Phase 8
(`resolve_oops_symbols`), which consumes the hex call trace extracted by Phase 5 skills.

The table below shows where AArch64 skills appear within the full system roadmap:

| Phase | Skills | Status |
|---|---|---|
| 1 | `decode_esr_el1`, `check_cache_coherency_panic` | ✅ DONE (31 tests) |
| 3 | `analyze_watchdog_timeout` | ✅ DONE (19 tests) |
| 5 | `extract_kernel_oops_log`, `decode_aarch64_exception` | ✅ DONE (36 tests) |
| 8 | `resolve_oops_symbols` | 🔵 PLANNED (Phase 8, stateful) |
| 9a | `check_soc_errata_tracker` | 🔵 PLANNED (Phase 9a, static table) |

---

## 1. Diagnostic Domain: AArch64 Architecture & Exceptions

### 1.1 Failure Classes Targeted

| Failure class | Key log marker | Primary skill |
|---|---|---|
| NULL pointer dereference | `Unable to handle kernel NULL pointer dereference` | `extract_kernel_oops_log` → `decode_aarch64_exception` |
| Paging / unmapped address | `Unable to handle kernel paging request` | `extract_kernel_oops_log` → `decode_aarch64_exception` |
| Kernel BUG macro | `kernel BUG at <file>:<line>` | `extract_kernel_oops_log` |
| Generic Oops | `Internal error: Oops` | `extract_kernel_oops_log` → `decode_esr_el1` |
| SError / cache coherency | `SError Interrupt on CPU`, `EC = 0x2F` | `check_cache_coherency_panic` → `decode_esr_el1` |
| Soft lockup | `BUG: soft lockup - CPU#N stuck for Xs` | `analyze_watchdog_timeout` |
| Hard lockup (NMI) | `BUG: hard lockup on CPU N` | `analyze_watchdog_timeout` |
| RCU stall | `rcu_sched detected stall on CPU N` | `analyze_watchdog_timeout` |
| Symbolisation of call trace | Hex addresses from Oops | `resolve_oops_symbols` (Phase 8) |

### 1.2 AArch64 Exception Register Model

Three hardware registers appear in every kernel panic and drive the diagnostic chain:

```
┌─────────────────────────────────────────────────────────┐
│  ESR_EL1  (Exception Syndrome Register)                 │
│  ┌──────┬────┬──────────────────────────────────────┐   │
│  │ ISS2 │ EC │ IL │ ISS                             │   │
│  │[63:32│31:26│25 │[24:0]                           │   │
│  └──────┴────┴──────────────────────────────────────┘   │
│  EC (6 bits) → exception class (Data Abort, SError…)   │
│  ISS (25 bits) → fault details (DFSC, WnR, …)          │
├─────────────────────────────────────────────────────────┤
│  FAR_EL1  (Fault Address Register)                      │
│  Valid for Data Aborts, Instruction Aborts, Alignment   │
│  NOT valid for SError (EC=0x2F)                         │
├─────────────────────────────────────────────────────────┤
│  PC / LR  (Program Counter / Link Register)             │
│  Printed as function symbols by the kernel Oops handler │
└─────────────────────────────────────────────────────────┘
```

The standard diagnostic chain is:

```
Log → extract_kernel_oops_log
          ├─► ESR_EL1 + FAR_EL1 → decode_aarch64_exception   (preferred)
          ├─► ESR_EL1 only       → decode_esr_el1
          ├─► EC=0x2F (SError)   → check_cache_coherency_panic (multi-tool synergy)
          └─► hex call trace     → resolve_oops_symbols        (Phase 8)
```

---

## 2. Completed Skills (Phases 1, 3, 5)

### 2.1 `decode_esr_el1` — ESR_EL1 Register Decoder

| Item | Detail |
|---|---|
| **File** | `skills/bsp_diagnostics/aarch64_exceptions.py` |
| **Input** | `hex_value: str` — ESR_EL1 as hex string |
| **Output** | `ESREL1Output` — EC, IL, ISS, DFSC/IFSC description, abort type flags, recommended action |
| **Tests** | `tests/product_tests/test_aarch64_exceptions.py` — 14 tests |
| **Route** | `kernel_pathologist` |

Decodes ESR_EL1 bits [31:26] (EC), [25] (IL), and [24:0] (ISS) against the ARM DDI0487 tables.
Classifies the exception as Data Abort, Instruction Abort, or SError and provides DFSC/IFSC
fault status detail. This is the entry-point decoder when FAR_EL1 is not available.

---

### 2.2 `decode_aarch64_exception` — ESR_EL1 + FAR_EL1 Pair Decoder

| Item | Detail |
|---|---|
| **File** | `skills/bsp_diagnostics/aarch64_exceptions.py` |
| **Input** | `esr_val: str`, `far_val: str` |
| **Output** | `AArch64ExceptionOutput` — all ESR fields + FAR value, exception level (EL0/EL1 inferred from EC), kernel/user address classification, fault_address_summary, confidence |
| **Tests** | 14 new tests added in Phase 5 |
| **Route** | `kernel_pathologist` |

**Key design decisions recorded:**
- `el_level` is **not** an input parameter. The exception level is inferred from EC bits [31:26]
  (EC=0x24/0x20 → EL0; EC=0x25/0x21 → EL1). Accepting `el_level` as user input would create a
  risk of contradictory inputs (e.g., EC=0x25 but `el_level=0`).
- FAR validity is the caller's responsibility: the Brain should invoke this skill only when the
  log contains both `ESR_EL1` and `FAR_EL1` values. SError (EC=0x2F) logs should go to
  `check_cache_coherency_panic` instead.
- ⚠️ **Known gap (HIGH PRIORITY):** The skill does not currently enforce the SError/FAR
  constraint internally. If called with `EC=0x2F`, it will interpret an architecturally
  UNKNOWN FAR value as a meaningful fault address. A guard clause must be added (see
  `AGENT_SKILL_PLAN_REVIEW_COMMENTS.md §3.1`).
- The AArch64 VA split heuristic (bit 63 set → kernel address) is applied directly; no KASLR
  adjustment is attempted (log-only mode).

---

### 2.3 `check_cache_coherency_panic` — SError / Cache Coherency Detector

| Item | Detail |
|---|---|
| **File** | `skills/bsp_diagnostics/aarch64_exceptions.py` |
| **Input** | `panic_log: str` |
| **Output** | `CacheCoherencyOutput` — detection flag, matched indicators, extracted ESR_EL1 hex, SError confirmation, root cause, recommended action, confidence |
| **Tests** | 17 tests |
| **Route** | `kernel_pathologist` |

Scans for seven SError/cache-coherency indicator patterns (e.g., `SError Interrupt`, `IMP DEF SError`,
`__flush_dcache_area`, `Point of Coherency`). Extracts ESR_EL1 and checks EC=0x2F. Confidence
scales linearly with indicator count (capped at 0.95).

**Multi-tool synergy (AGENTS.md §3.3):** When `extract_kernel_oops_log` finds EC=0x2F, the Brain
is expected to call both `decode_esr_el1` and `check_cache_coherency_panic` in the same session.

---

### 2.4 `extract_kernel_oops_log` — Kernel Oops/BUG Parser

| Item | Detail |
|---|---|
| **File** | `skills/bsp_diagnostics/kernel_oops.py` |
| **Input** | `dmesg_log: str` |
| **Output** | `KernelOopsOutput` — detection flag, oops type, process/PID/CPU, kernel version, ESR_EL1 hex, FAR_EL1 hex, pc/lr symbols, call trace (≤32 entries), confidence |
| **Tests** | 22 tests |
| **Route** | `kernel_pathologist` |

Detects four oops types (null_pointer, paging_request, kernel_bug, generic_oops).
Handles kernel timestamp prefixes (`[  123.456789]`). The extracted `esr_el1_hex` and `far_hex`
feed directly into `decode_esr_el1` or `decode_aarch64_exception` in the next tool-call round.

---

### 2.5 `analyze_watchdog_timeout` — Soft/Hard Lockup Parser

| Item | Detail |
|---|---|
| **File** | `skills/bsp_diagnostics/watchdog.py` |
| **Input** | `dmesg_log: str` |
| **Output** | `WatchdogOutput` — detection flag, lockup type, CPU/PID/process, stuck duration, call trace, root cause, recommended action, confidence |
| **Tests** | 19 tests |
| **Route** | `kernel_pathologist` |

Handles soft lockup (`BUG: soft lockup`), hard lockup / NMI watchdog (`BUG: hard lockup`), and
RCU stall (`rcu_sched detected stall`). Extracts call trace (capped at 30 entries) from the
30-line context window around the lockup event. Only the **first** lockup event is processed.

⚠️ **Known limitations (see `AGENT_SKILL_PLAN_REVIEW_COMMENTS.md`):**
- Only the first lockup event is extracted. On SMP systems with cascading lockups, multiple
  CPU events are missed (§3.2 — planned extension).
- Call trace cap is 30 entries; `extract_kernel_oops_log` uses 32. These should be aligned
  to a registry-wide cap of 32 (§3.8).

---

## 3. Planned Skills

### Phase 8 — `resolve_oops_symbols` (Stateful)

| Item | Detail |
|---|---|
| **File** | `skills/bsp_diagnostics/workspace.py` (new) |
| **Input** | `hex_call_trace: str` (output of `extract_kernel_oops_log`), `vmlinux_path: str` |
| **Output** | Human-readable call trace with file names and line numbers |
| **Route** | `source_analyst` (new supervisor route) |
| **Infrastructure** | `aarch64-linux-gnu-addr2line` subprocess; local build tree required |
| **Tests** | ~20 tests — mock subprocess for `addr2line`; fixture call traces |
| **Prerequisite** | Phase 5 (`extract_kernel_oops_log` provides the hex input) |

This is the **stateful half** of the Oops pipeline. Phase 5 extracts hex addresses; Phase 8
maps them back to source symbols. Option A (file path inputs) is recommended for initial
implementation. See `ANDROID_LINUX_BSP_BOOTING_SKILL_SETS.md §6 Phase 8` for the full
workspace access model analysis.

---

### Phase 9a — `check_soc_errata_tracker` (Static Table)

| Item | Detail |
|---|---|
| **File** | `skills/knowledge/errata.py` (new) |
| **Input** | `ip_block: str`, `soc_revision: str` |
| **Output** | Matching errata entries (description, workaround, kernel config fix) |
| **Route** | All routes (universal knowledge query) |
| **Tests** | ~12 tests |
| **Prerequisite** | None — can be developed in parallel |

Implemented as a Python dict lookup table (no external database). Initial coverage: Qualcomm
SM8x50 series, MediaTek MT6xxx, Samsung Exynos. The AArch64 connection is that `decode_esr_el1`
outputs can be cross-referenced against this table — a known CPU erratum producing a specific
EC+DFSC combination can be flagged proactively.

---

### Phase 9b — `query_arm_trm_database` (Deferred — RAG)

| Item | Detail |
|---|---|
| **File** | `skills/knowledge/arm_trm.py` (new) |
| **Infrastructure** | Vector DB + ARM TRM PDF ingestion + embedding pipeline |
| **Prerequisite** | Phase 9a validated in real use; separate RAG infrastructure design document |

Deferred. The vector DB investment is substantial and the diagnostic foundation must be validated
on real BSP logs before incurring this cost.

---

## 4. Multi-Tool Synergy Patterns (AGENTS.md §3.3)

The Brain is required to invoke multiple tools when failure symptoms demand it.
The following are the canonical multi-tool flows for AArch64 exceptions:

### 4.1 Oops + ESR + FAR (Full Decode)

```
1. extract_kernel_oops_log(dmesg_log)
     → oops_detected=True, esr_el1_hex, far_hex, call_trace

2. IF esr_el1_hex AND far_hex:
       decode_aarch64_exception(esr_val=esr_el1_hex, far_val=far_hex)

   ELSE IF esr_el1_hex only:
       decode_esr_el1(hex_value=esr_el1_hex)

3. IF EC == 0x2F (SError):
       check_cache_coherency_panic(panic_log=dmesg_log)
```

### 4.2 Watchdog + Concurrent SError (AGENTS.md §3.3 canonical example)

```
1. analyze_watchdog_timeout(dmesg_log)
     → lockup_detected=True

2. IF ESR_EL1 with EC=0x2F appears near the lockup:
       decode_esr_el1(hex_value=esr_el1_hex)
       check_cache_coherency_panic(panic_log=dmesg_log)
```

Conflicting outputs from these tools (e.g., lockup classification vs. SError root cause)
**must be explicitly highlighted** in the final `ConsultantResponse`.

---

## 5. Knowledge Base

### Current
- `docs/aarch64-exceptions.md` — ESR_EL1 bit layout, EC quick reference, FAR_EL1 VA split,
  Data Abort ISS decoding, SError interrupt anatomy, cache coherency failure checklist,
  kernel panic anatomy with multi-tool synergy walkthrough, ARM DDI0487 references.

### Planned (Phase 8)
- `docs/workspace-analysis.md` — DTS node naming conventions, CONFIG flag impact reference,
  `addr2line` usage guide, vmlinux symbol table layout.

---

## 6. Testing Strategy

All AArch64 skills follow the **TDD protocol** from `AGENTS.md §4.2` and `CLAUDE.md`:

1. **Red:** Write a failing test asserting the expected `Output` fields.
2. **Green:** Write the minimal implementation to pass the test.
3. **Refactor (optional):** One refactor attempt. Revert if tests break; tag `#TODO: Tech Debt`.

**No LLM invocation in skill tests.** All tests in `tests/product_tests/test_aarch64_exceptions.py`,
`tests/product_tests/test_kernel_oops_skill.py`, and `tests/product_tests/test_watchdog_skill.py`
call skill functions directly with string fixtures.

**Phase 8 tests** mock the `subprocess` call to `addr2line` and use fixture call trace files
in `tests/fixtures/`.

**Integration tests** (`tests/product_tests/test_integration.py`) exercise multi-tool synergy
flows end-to-end with fixture log files, verifying that the Brain invokes the correct tool
sequence for each failure class.

---

## 7. Skill Authoring Contract

Every new AArch64 skill must satisfy the full skill contract (see `skills/SKILL.md`):

```
skills/bsp_diagnostics/<skill>.py
  ├─ <SkillName>Input   — Pydantic BaseModel with Field descriptions
  ├─ <SkillName>Output  — Pydantic BaseModel with Field descriptions
  └─ <function>(input: str | ...) → <SkillName>Output
       ├─ Pure function: no side effects, no LLM calls, no global state
       ├─ Deterministic: same input always produces same output
       └─ Docstring: describes logic, references ARM spec sections

skills/registry.py
  ├─ TOOL_DEFINITIONS  — add Anthropic-compatible tool dict
  └─ ROUTE_TOOLS       — add tool name to "kernel_pathologist" set

tests/product_tests/test_<skill>_skill.py
  └─ pytest functions — no LLM, no external I/O, inline fixtures
```

---

## 8. ARM Architecture References

| Document | Relevance |
|---|---|
| ARM DDI0487 (Armv8/v9 Architecture Reference Manual) | ESR_EL1, FAR_EL1, ISS field layouts, DFSC/IFSC codes |
| ARM DEN0022 (PSCI specification) | CPU suspend/resume sequences; EL3 cache maintenance requirements |
| Linux `arch/arm64/kernel/traps.c` | `do_serror()`, `arm64_notify_die()` — how the kernel logs exception registers |
| Linux `arch/arm64/mm/fault.c` | `do_mem_abort()` — Data/Instruction Abort handler |
| Linux `arch/arm64/kernel/entry.S` | Exception vector table |
| Linux `arch/arm64/mm/cache.S` | `__flush_dcache_area()`, `dcache_by_line_op()` |
| Linux `Documentation/admin-guide/bug-hunting.rst` | Oops output format, call trace notation |
