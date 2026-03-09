# AGENT_SKILL_PLAN_REVIEW_COMMENTS.md
# Review Comments — AARCH64_AGENT_SKILL_DEV_PLAN.md

**Reviewer:** Copilot Code Agent
**Review date:** 2026-03-09
**Plan version reviewed:** AARCH64_AGENT_SKILL_DEV_PLAN.md v1.0
**Companion documents also reviewed:** `ANDROID_LINUX_BSP_BOOTING_SKILL_SETS.md`,
`DESIGN.md`, `PRODUCT_BLUEPRINT.md`, `AGENTS.md`, `docs/aarch64-exceptions.md`,
`skills/bsp_diagnostics/aarch64_exceptions.py`, `skills/bsp_diagnostics/kernel_oops.py`,
`skills/bsp_diagnostics/watchdog.py`, `skills/registry.py`

---

## 1. Executive Summary

The plan captures a solid, well-sequenced foundation for AArch64 exception diagnostics. The
three-layer architecture (Brain / Skill Registry / Knowledge Base) is correctly applied, the
TDD discipline is sound, and the decision to derive exception level from ESR EC bits rather than
accepting an `el_level` input parameter is the right call.

The main gaps are in **ARM specification coverage depth**, **multi-event SMP analysis**,
**SError/FAR validity guard**, and **errata integration**. All of these are addressable without
architectural changes. The plan is ready to proceed with the suggestions below incorporated as
follow-on items.

---

## 2. Strengths

1. **Correct `el_level` design decision.** The plan explicitly records *why* `el_level` is not
   an input to `decode_aarch64_exception`: it would allow contradictory inputs. EL inference from
   EC bits is deterministic and correct per ARM DDI0487. This rationale should be preserved as
   a comment in the skill source.

2. **Stateless-first ordering.** Phases 1–5 (all stateless log parsers) are correctly ordered
   before Phase 8 (stateful `resolve_oops_symbols`). This minimises infrastructure risk and
   allows real-world validation before introducing subprocess dependencies.

3. **Multi-tool synergy patterns are explicit.** Section 4 documents the canonical tool-call
   chains for each failure class. This is exactly what AGENTS.md §3.3 requires and ensures the
   Brain constructs the correct tool sequence.

4. **Skill contract is enforced.** The plan requires every new skill to have Pydantic I/O
   schemas, a pure-function constraint, and isolated pytest coverage. This prevents the common
   failure mode of LLM calls inside tools.

5. **Phase 8 prerequisite dependency is correctly documented.** `resolve_oops_symbols` depends
   on the hex call trace extracted by `extract_kernel_oops_log`. The plan records this data-flow
   dependency explicitly.

---

## 3. Identified Gaps & Issues

### 3.1 SError / FAR Validity Guard (HIGH PRIORITY)

**Issue:** `decode_aarch64_exception` accepts any `(esr_val, far_val)` pair but the ARM
architecture specifies that `FAR_EL1` is **UNKNOWN** (architecturally unpredictable) when
`EC = 0x2F` (SError Interrupt). The skill currently does not guard against this case.

**Impact:** If the Brain calls `decode_aarch64_exception` with an SError ESR value, the skill
will interpret a garbage FAR as a meaningful fault address, potentially generating a misleading
`fault_address_summary` (e.g., classifying a random kernel address as a "use-after-free").

**Suggestion:**
```python
# In decode_aarch64_exception(), after decoding ESR:
if esr_decoded.is_serror:
    # FAR_EL1 is UNKNOWN for SError — do not classify it
    far_is_kernel = False
    fault_address_summary = (
        "SError Interrupt — FAR_EL1 is architecturally UNKNOWN for EC=0x2F. "
        "Use check_cache_coherency_panic instead."
    )
    recommended_action = (
        "Run check_cache_coherency_panic on the full panic log. "
        "Do not use FAR_EL1 to localise the fault address for SError exceptions."
    )
    confidence = 0.50
```

The plan should add an explicit instruction: *"The Brain must not call
`decode_aarch64_exception` when `EC = 0x2F`; route to `check_cache_coherency_panic` instead."*

---

### 3.2 `analyze_watchdog_timeout` Processes Only the First Lockup Event (MEDIUM)

**Issue:** The skill stops after finding the first lockup line (`if lockup_type is not None: break`).
On SMP systems, a cascade of lockups (multiple CPUs hanging within the same watchdog window) is
common and diagnostically important. The first lockup may be a symptom; the CPU that locked up
first may be the root cause.

**Impact:** For a 6-core SoC where CPUs 0, 1, and 3 all lock up within 1 s of each other, the
skill returns only CPU 0's entry. The engineer misses the cascading pattern.

**Suggestion:** Add an optional `lockup_events: list[LockupEvent]` field to `WatchdogOutput`
that captures all lockup events (up to a cap, e.g., 8). Mark the existing `cpu`, `pid`, etc.
fields as the *first* event (for backward compatibility). In the `root_cause` string, note when
multiple CPUs are affected.

The plan should include a follow-on item:
> **Item 5.1 (Phase 5 follow-on):** Extend `analyze_watchdog_timeout` to capture all lockup
> events in the log and flag cascading SMP lockup patterns.

---

### 3.3 ISS2 Field (ESR_EL1 bits [63:32]) Not Decoded (MEDIUM)

**Issue:** Both `decode_esr_el1` and `decode_aarch64_exception` treat ESR as a 32-bit value.
ARMv8.2+ and ARMv9 extend ESR_EL1 to 64 bits, adding the `ISS2` field in bits [63:32]. The
Linux kernel has been logging the full 64-bit value since 5.15+. The current parser silently
discards the upper 32 bits.

**Impact:** For hardware memory-tagging faults (MTE, FEAT_MTE) and GCS pointer authentication
faults (FEAT_GCS), the ISS2 field carries essential context that the current skills ignore.

**Suggestion:** Add a `iss2: Optional[int]` field to `ESREL1Output` and `AArch64ExceptionOutput`.
Parse the full 64-bit value when the input is a 16-digit hex string. Add an `iss2_detail`
string for known ISS2 decodings (MTE fault type, GCS fault type). If the upper 32 bits are
zero (the common case pre-ARMv9), set `iss2 = None` and emit no noise.

The plan should add:
> **Item 5.2 (Phase 5 follow-on):** Decode ISS2 (ESR_EL1[63:32]) for ARMv9/MTE fault context.

---

### 3.4 `ANDROID_LINUX_BSP_BOOTING_SKILL_SETS.md` Spec vs. Implementation Conflict (LOW / Hygiene)

**Issue:** `ANDROID_LINUX_BSP_BOOTING_SKILL_SETS.md §1` still lists `el_level (int)` as an
input to `decode_aarch64_exception`. The actual implementation (correctly) omits it, and
`ANDROID_LINUX_BSP_BOOTING_SKILL_SETS.md §6 Phase 5` explicitly records the removal.
This creates a contradictory spec document.

**Suggestion:** Update the skill description in `ANDROID_LINUX_BSP_BOOTING_SKILL_SETS.md §1`
to remove the `el_level` field and add a note: *"EL is inferred from EC bits [31:26]; see
Phase 5 rationale."* This is a one-line change but prevents future confusion.

---

### 3.5 `check_cache_coherency_panic` Does Not Fully Decode Its Own ESR_EL1 Extraction (LOW)

**Issue:** `check_cache_coherency_panic` extracts `esr_el1_hex` from the log and sets
`esr_is_serror = True` when EC=0x2F. However, it does not return the full ISS or recommended
action for non-SError EC values it happens to extract (e.g., if the panic log contains an ESR
for a different exception class alongside the SError message).

**Impact:** Minor: the field `esr_el1_hex` is returned for the caller to pass to `decode_esr_el1`,
which is the correct pattern. The current behaviour is acceptable but could be confusing.

**Suggestion:** Add a comment in the skill and in the plan stating: *"The `esr_el1_hex` output
field is intentionally raw — the caller (Brain) should pass it to `decode_esr_el1` for full
decoding. `check_cache_coherency_panic` only confirms the SError nature, not the full ISS."*

---

### 3.6 No `decode_esr_el1` Coverage in `early_boot_advisor` Route (LOW)

**Issue:** `decode_esr_el1` is registered only in the `kernel_pathologist` route tools
(`ROUTE_TOOLS`). However, TF-A (Trusted Firmware-A) at EL3 can generate its own exception
syndrome values in UART logs, and some platforms (Qualcomm AOSS) print `ESR_EL1` or `ESR_EL3`
values in pre-kernel crash output.

**Impact:** If the Supervisor routes a TF-A crash to `early_boot_advisor`, `decode_esr_el1` is
not available. The Brain cannot decode the ESR value even though it is present in the log.

**Suggestion:** Consider adding `decode_esr_el1` to `_UNIVERSAL_TOOLS` (alongside
`segment_boot_log`) or to the `early_boot_advisor` route tools set. This is a one-line registry
change and does not require a new skill. The plan should note this as a registry configuration
item.

---

### 3.7 `check_soc_errata_tracker` (Phase 9a) Has No Integration Path with AArch64 Skills (LOW)

**Issue:** Phase 9a defines `check_soc_errata_tracker` as a standalone lookup skill, but the
plan does not describe *how* its output is connected to the AArch64 exception diagnostic chain.

**Scenario:** `decode_esr_el1` returns EC=0x25, DFSC=0x10 (Synchronous External Abort). This
could be a known CPU erratum on specific SoC revisions (e.g., Cortex-A55 erratum 1530923) where
a data cache eviction causes an external abort under specific conditions.

**Suggestion:** Add an integration note to Phase 9a:
> When `decode_esr_el1` returns `DFSC in {0x10, 0x18}` (external or ECC abort), the Brain
> should call `check_soc_errata_tracker(ip_block="A55-dcache", soc_revision=...)` to look for
> known errata matches. This is a second-pass enrichment, not a replacement for ESR decoding.

---

### 3.8 Call Trace Cap Inconsistency Between Skills (LOW / Hygiene)

**Issue:** `extract_kernel_oops_log` caps `call_trace` at 32 entries; `analyze_watchdog_timeout`
caps at 30. There is no documented rationale for the difference.

**Suggestion:** Align both to the same cap (32 is more defensible: a typical AArch64 call stack
rarely exceeds 24 frames before hitting the idle loop, and 32 gives headroom for
interrupt-context frames). Document the cap value in `skills/SKILL.md` as a registry-wide
convention:

> **Call trace cap:** All skills return at most 32 call trace entries to avoid oversized
> tool outputs. Entries beyond index 31 are silently dropped.

---

### 3.9 Confidence Score Algorithm Is Undocumented and Inconsistent (MEDIUM)

**Issue:** Each skill has its own ad-hoc confidence scoring:
- `decode_aarch64_exception`: `0.88` if EC in known abort set, else `0.70`
- `extract_kernel_oops_log`: starts at `0.75`, adds `0.10` for ESR, `0.05` for call trace
- `check_cache_coherency_panic`: `0.6 + 0.1 * len(found)`, capped at `0.95`
- `analyze_watchdog_timeout`: `0.90` with call trace, `0.70` without

There is no shared definition of what a confidence score means, and the scoring ranges are not
comparable across skills (a `0.70` from `decode_aarch64_exception` does not mean the same thing
as a `0.70` from `analyze_watchdog_timeout`).

**Suggestion:** Add a **confidence scoring contract** to `skills/SKILL.md`:

```
| Score range | Meaning |
|---|---|
| 0.90 – 1.00 | High confidence: all diagnostic fields extracted; exception class unambiguous |
| 0.70 – 0.89 | Medium confidence: key fields extracted; some ambiguity in root cause |
| 0.50 – 0.69 | Low confidence: partial extraction; significant ambiguity |
| 0.10 – 0.49 | Very low: indicator present but not confirmed; pattern match only |
```

Each skill's confidence calculation should be documented inline with comments referencing
this table.

---

### 3.10 No Regression Test Fixture for SError + Watchdog Multi-Tool Synergy in Plan (LOW)

**Issue:** The plan describes multi-tool synergy patterns but does not enumerate which integration
test fixtures cover the SError + watchdog co-occurrence case (a CPU locks up AND generates an
SError within the same panic window).

**Impact:** The current integration test suite (`test_integration.py`) has a
`watchdog_esr_synergy_04.txt` fixture, but the plan (§4.2) does not reference it. A future
reader of the plan cannot determine whether this scenario is tested.

**Suggestion:** Add a "Test Coverage" subsection to §4 that maps each multi-tool synergy
pattern to its integration test fixture:

```
| Synergy pattern | Fixture | Test class |
|---|---|---|
| Oops + ESR + FAR | panic_log_01.txt | TestKernelPanicScenario |
| Watchdog + SError | watchdog_esr_synergy_04.txt | TestMultiToolSynergy |
| Cache coherency only | (add fixture) | TestCacheCoherency |
```

---

## 4. Architecture Observations

### 4.1 The Skill-Registry Coupling to ROUTE_TOOLS Is Well-Designed

The `_UNIVERSAL_TOOLS` set in `skills/registry.py` that merges `segment_boot_log` into every
route is an elegant pattern. The suggestion in §3.6 to add `decode_esr_el1` to universal tools
or `early_boot_advisor` should follow the same pattern (a set union, not a hardcoded list).

### 4.2 Phase 8 Workspace Option A Is the Right Starting Choice

The plan recommends file path inputs for `resolve_oops_symbols` (Option A). This is correct for
local developer use. However, the plan should explicitly note that Option C (WorkspaceAgent) is
the right target architecture for server deployment, and that Option A should be implemented in
a way that makes it straightforward to wrap into Option C later (i.e., the skill itself should
not hard-code path resolution logic; keep that in the caller layer).

### 4.3 Phase 9b RAG Deferral Is Correct

ARM TRM RAG requires chunking ~12,000 pages of PDF specification. Deferring this until the
stateless diagnostic layer is validated on real logs is the right call. However, the plan should
add a prerequisite checklist for Phase 9b so the team knows *when* to revisit it:

> **Phase 9b prerequisites:**
> - [ ] Phases 4–7 validated on ≥20 distinct real-world BSP log cases
> - [ ] Phase 9a errata table populated for at least 3 SoC families
> - [ ] RAG infrastructure design document approved
> - [ ] ARM TRM license review completed (re-distribution constraints)

---

## 5. Testing Strategy Observations

### 5.1 Integration Test for `decode_aarch64_exception` with SError ESR Is Missing

There is no integration test fixture that sends `EC=0x2F` to `decode_aarch64_exception` and
verifies that the skill correctly refuses to interpret FAR. This should be added as part of
the SError/FAR validity guard fix (§3.1).

### 5.2 Property-Based Testing Would Strengthen ESR Decoding

The EC table covers ~28 known EC values out of a 6-bit (0–63) space. The remaining 35 values
are "Reserved" by the ARM architecture. The tests should include at least one property-based
test (using `hypothesis` or a manual loop over reserved EC values) to verify that
`decode_esr_el1` does not panic on unknown EC values and returns a sensible fallback message.

### 5.3 Fuzzing the Call Trace Extractor Is Recommended

`extract_kernel_oops_log` uses regex over arbitrary log text. Malformed or adversarial logs
(e.g., lines that look like call trace entries but are not) could produce incorrect extractions.
At minimum, the test suite should include:
- A log where the call trace header appears but is immediately followed by unrelated content
- A log where `pc :` and `lr :` appear multiple times (the first match wins — verify this)
- A log with UTF-8 multibyte characters in function names (some vendor kernels add locale text)

---

## 6. Recommended Priority Actions

| Priority | Item | Section | Effort |
|---|---|---|---|
| 🔴 High | Add SError/FAR validity guard to `decode_aarch64_exception` | §3.1 | 1–2 h |
| 🟡 Medium | Document confidence scoring contract in `skills/SKILL.md` | §3.9 | 1 h |
| 🟡 Medium | Extend `analyze_watchdog_timeout` to capture all lockup events | §3.2 | 2–3 h |
| 🟡 Medium | Add ISS2 (ESR[63:32]) decoding for ARMv9/MTE coverage | §3.3 | 2–4 h |
| 🟢 Low | Fix `el_level` spec conflict in `ANDROID_LINUX_BSP_BOOTING_SKILL_SETS.md §1` | §3.4 | 15 min |
| 🟢 Low | Add `decode_esr_el1` to `early_boot_advisor` route tools | §3.6 | 15 min |
| 🟢 Low | Align call trace cap to 32 in `analyze_watchdog_timeout` | §3.8 | 15 min |
| 🟢 Low | Add integration path note for `check_soc_errata_tracker` + ESR DFSC | §3.7 | 30 min |
| 🟢 Low | Add test coverage table to plan §4 (fixture → test mapping) | §3.10 | 30 min |
| 🟢 Low | Add Phase 9b prerequisite checklist | §4.3 | 30 min |

---

## 7. Summary

The `AARCH64_AGENT_SKILL_DEV_PLAN.md` is a well-structured plan that correctly captures the
current implementation state, the phased development sequence, and the key design decisions for
AArch64 exception diagnostics. The most important fix before proceeding to Phase 8 is the
**SError/FAR validity guard** (§3.1) — this is an ARM architecture correctness issue, not a
preference. All other items are improvements and hygiene changes that can be addressed
incrementally.

The plan is approved to proceed with the following items tracked as follow-on work in the Phase
5/6 backlog: SError FAR guard (§3.1), multi-CPU lockup extension (§3.2), ISS2 decoding (§3.3),
and the confidence scoring contract (§3.9).
