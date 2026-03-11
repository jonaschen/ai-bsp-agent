# Skill Extension Guide — Improving Skills on Real Hardware

The BSP Diagnostic Agent ships with skills trained on emulator-generated logs
(see `docs/emulator-spec.md` for the exact versions). Emulators cannot reproduce
every SoC-specific log format, so skills may miss patterns on real hardware.

This guide explains how an **end-user's agent** can close that gap by extending
the built-in skills without modifying the core codebase.

---

## 1. When to Extend

A skill needs extension when:

- The agent returns `confidence < 0.5` for a log that clearly contains a known
  failure class (e.g. watchdog timeout lines that the skill does not detect).
- The agent returns `error_type: "none"` or `root_cause: "unknown"` for a log
  that the user knows is a failure.
- A skill identifies the wrong category (e.g. classifies a DDR training failure
  as `generic_error` instead of `ddr_init_failure`).

Check `docs/emulator-spec.md §5` (Known Emulator Gaps) first — if your pattern
class is listed there, it is expected to require an extension.

---

## 2. The Two-Skill Workflow

Two skills are available specifically for end-user agents to improve the system:

| Skill | Function | Purpose |
|---|---|---|
| `validate_skill_extension` | Dry-run | Test a regex against a log snippet without writing anything |
| `suggest_pattern_improvement` | Persist | Validate + write the pattern to `~/.bsp-diagnostics/skill_extensions.json` |

**Always call `validate_skill_extension` first**, then `suggest_pattern_improvement`
if the dry-run confirms a match.

### 2.1 Step 1 — validate_skill_extension

```python
from skills.bsp_diagnostics.skill_improvement import (
    validate_skill_extension, ValidateExtensionInput
)

result = validate_skill_extension(ValidateExtensionInput(
    skill_name="parse_early_boot_uart_log",
    log_snippet="""
        MT_DDRPHY: [CHANNEL 0][RANK 0] DQ0 training fail
        MT_DDRPHY: ddr_init_flow fail, error code: 0x0003
    """,
    proposed_pattern=r"MT_DDRPHY.*training.*fail|MT_DDRPHY.*ddr_init.*fail",
))

# result.matches      → True/False
# result.match_count  → number of matching lines
# result.matched_lines → up to 10 sample lines
# result.error        → set if the regex is invalid
```

The pattern is compiled with `re.IGNORECASE`. Fix the regex until `matches=True`
before proceeding.

### 2.2 Step 2 — suggest_pattern_improvement

```python
from skills.bsp_diagnostics.skill_improvement import (
    suggest_pattern_improvement, SuggestPatternInput
)

result = suggest_pattern_improvement(SuggestPatternInput(
    skill_name="parse_early_boot_uart_log",
    log_snippet="""
        MT_DDRPHY: [CHANNEL 0][RANK 0] DQ0 training fail
        MT_DDRPHY: ddr_init_flow fail, error code: 0x0003
    """,
    proposed_pattern=r"MT_DDRPHY.*training.*fail|MT_DDRPHY.*ddr_init.*fail",
    category="ddr_init_failure",
    description="MediaTek MT_DDRPHY DDR training failure (MT6xxx family)",
))

# result.accepted         → True if written
# result.match_preview    → lines that matched
# result.extension_file   → path written to
# result.rejection_reason → set if rejected (with reason)
```

On `accepted=True`, the pattern is immediately active. The next call to
`parse_early_boot_uart_log` with a matching log will return
`error_type: "ddr_init_failure"`.

---

## 3. Valid Categories per Skill

Each skill only accepts category values from a fixed set. Supplying an unknown
category causes `suggest_pattern_improvement` to return `accepted=False`.

| Skill | Valid categories |
|---|---|
| `parse_early_boot_uart_log` | `auth_failure`, `image_load_failure`, `ddr_init_failure`, `pmic_failure`, `generic_error` |
| `analyze_lk_panic` | `assert`, `ddr_failure`, `image_load`, `pmic_failure`, `generic` |
| `extract_kernel_oops_log` | `null_pointer`, `paging_request`, `kernel_bug`, `generic_oops` |
| `check_cache_coherency_panic` | `cache_coherency` |
| `analyze_std_hibernation_error` | `high_sunreclaim`, `swap_exhausted`, `generic_hibernation_error` |
| `check_vendor_boot_ufs_driver` | `probe`, `link_startup`, `resume` |
| `analyze_watchdog_timeout` | `soft_lockup`, `hard_lockup`, `rcu_stall` |
| `check_pmic_rail_voltage` | `ocp`, `undervoltage` |
| `segment_boot_log` | `early_boot`, `kernel_init`, `android_init` |

---

## 4. Extension File Format

Extensions are stored in:
```
~/.bsp-diagnostics/skill_extensions.json
```

Override the path for testing:
```bash
export BSP_EXTENSIONS_PATH=/tmp/test_extensions.json
```

Schema (version 1):
```json
{
  "version": 1,
  "skills": {
    "parse_early_boot_uart_log": {
      "patterns": [
        {
          "match": "MT_DDRPHY.*training.*fail",
          "category": "ddr_init_failure",
          "description": "MediaTek DDR training failure",
          "added": "2026-03-11"
        }
      ]
    },
    "analyze_watchdog_timeout": {
      "patterns": [
        {
          "match": "vendor_wdt.*timeout.*cpu#(\\d+)",
          "category": "hard_lockup",
          "description": "Vendor watchdog driver hard lockup (SM8550)",
          "added": "2026-03-11"
        }
      ]
    }
  }
}
```

The file is read at every skill invocation — no restart required.

---

## 5. Common Extension Examples

### 5.1 Qualcomm SM8550 PMIC OCP (new rail name)

The emulator trains on `qpnp-regulator: vreg_lcd_vsp: over-current fault`.
A real SM8550 may use `pm8550b`:

```python
suggest_pattern_improvement(SuggestPatternInput(
    skill_name="check_pmic_rail_voltage",
    log_snippet="[    3.123456] pm8550b: L2B: over-current protection triggered",
    proposed_pattern=r"pm8550b.*L\d+[A-Z]:\s+over-current",
    category="ocp",
    description="Qualcomm PM8550B OCP event format (SM8550)",
))
```

### 5.2 MediaTek Helio G99 — UFS resume failure

```python
suggest_pattern_improvement(SuggestPatternInput(
    skill_name="check_vendor_boot_ufs_driver",
    log_snippet="[   12.345678] ufshcd-mtk 11270000.ufs: ufshcd_host_reset_and_restore: ufshcd_reset_and_restore failed -5",
    proposed_pattern=r"ufshcd-mtk.*ufshcd_host_reset.*failed",
    category="resume",
    description="MediaTek ufshcd UFS resume failure (Helio G99 / MT6789)",
))
```

### 5.3 Older kernel (5.10 GKI) soft lockup format

Alpine 3.19 ships kernel 6.6. A 5.10 GKI kernel uses a slightly different header:

```python
suggest_pattern_improvement(SuggestPatternInput(
    skill_name="analyze_watchdog_timeout",
    log_snippet="[  45.678901] BUG: soft lockup - CPU#2 stuck for 22s! [kworker/2:1:4567]",
    proposed_pattern=r"BUG: soft lockup - CPU#(\d+) stuck for (\d+)s",
    category="soft_lockup",
    description="5.10 GKI soft lockup header (bracket after stuck duration)",
))
```

---

## 6. Agent Workflow for Hardware Validation

Recommended sequence for an end-user agent working on real BSP hardware:

```
1. Run cli.py with the real hardware log
   → If confidence ≥ 0.75 across all domains: no extension needed.

2. For each low-confidence or wrong-category result:
   a. Identify the specific log lines that should have been matched.
   b. Call validate_skill_extension with a candidate regex.
   c. Refine regex until matches=True and matched_lines look correct.
   d. Call suggest_pattern_improvement with the validated regex + category.
   e. Re-run cli.py — confirm confidence improves.

3. Commit ~/.bsp-diagnostics/skill_extensions.json to the project's
   hardware-specific overlay (outside this repo).

4. File a PR against this repo with:
   - The new log sample (anonymised) in logs/validation/
   - The proposed pattern and category in skills/bsp_diagnostics/<skill>.py
     (or submit it here and the maintainer will promote it to a built-in).
```

---

## 7. MCP Server Usage

The same skills are exposed via the MCP server:

```bash
# Register the MCP server (one-time)
pip install -e .
claude mcp add bsp-diagnostics bsp-diagnostics-mcp

# In a Claude conversation, invoke the extension skills directly:
# "validate_skill_extension" and "suggest_pattern_improvement"
# are available as MCP tools alongside the core diagnostic skills.
```

Both `validate_skill_extension` and `suggest_pattern_improvement` are already
registered in `skills/registry.py` as `_UNIVERSAL_TOOLS` and are exposed by the
MCP server automatically — no extra registration step is needed.

---

## 8. Promoting Extensions to Built-In Skills

An extension pattern that proves reliable across multiple hardware samples should
be promoted to a built-in pattern in the skill source file:

1. Add the regex to the appropriate `_PATTERNS` dict or compiled-pattern list in
   `skills/bsp_diagnostics/<skill>.py`.
2. Write a pytest fixture with a representative log sample in
   `tests/product_tests/test_<skill>.py`.
3. Remove the entry from `skill_extensions.json` (or leave it — duplicates are
   harmless, built-in patterns take precedence).
4. Update the skill's row in `skills/SKILL.md` with the new category if it is new.
5. Add the log to `LOG_PENDING_LIST.md` as a new validation entry.
