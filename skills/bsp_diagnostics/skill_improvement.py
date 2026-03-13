"""
Skill Improvement Tools.

Provides two agent-callable skills that let an end-user's agent propose and
persist new detection patterns when a core skill misses a real-hardware log:

  validate_skill_extension  — dry-run: test a regex against a log snippet.
  suggest_pattern_improvement — validate + write to ~/.bsp-diagnostics/.

Patterns are stored in ~/.bsp-diagnostics/skill_extensions.json (or the path
set in BSP_EXTENSIONS_PATH).  Each existing skill checks that file at call
time and applies matching user patterns when its built-in detection misses.

Valid categories are skill-specific; see VALID_CATEGORIES below.
"""
from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field

from skills.extensions import write_extension_pattern


# ---------------------------------------------------------------------------
# Valid categories — the only constraint on user-supplied category values.
# Keys must match the registered tool names in skills/registry.py.
# ---------------------------------------------------------------------------

VALID_CATEGORIES: dict[str, set[str]] = {
    "parse_early_boot_uart_log": {
        "auth_failure", "image_load_failure", "ddr_init_failure",
        "pmic_failure", "generic_error",
    },
    "analyze_lk_panic": {
        "assert", "ddr_failure", "image_load", "pmic_failure", "generic",
    },
    "extract_kernel_oops_log": {
        "null_pointer", "paging_request", "kernel_bug", "generic_oops",
    },
    "check_cache_coherency_panic": {
        "cache_coherency",
    },
    "analyze_std_hibernation_error": {
        "high_sunreclaim", "swap_exhausted", "generic_hibernation_error",
    },
    "check_vendor_boot_ufs_driver": {
        "probe", "link_startup", "resume",
    },
    "analyze_watchdog_timeout": {
        "soft_lockup", "hard_lockup", "rcu_stall",
    },
    "check_pmic_rail_voltage": {
        "ocp", "undervoltage",
    },
    "segment_boot_log": {
        "early_boot", "kernel_init", "android_init",
    },
    "analyze_selinux_denial": {
        "avc_denied",
    },
    "check_android_init_rc": {
        "command_failure", "service_crash",
    },
    "check_clock_dependencies": {
        "probe_defer", "clk_get_failure",
    },
    "diagnose_vfs_mount_failure": {
        "mount_failure",
    },
    "analyze_firmware_load_error": {
        "firmware_missing", "firmware_timeout",
    },
    "analyze_early_oom_killer": {
        "oom_kill",
    },
    "resolve_oops_symbols": {
        "unresolved_symbol",
    },
    "compare_device_tree_nodes": {
        "property_mismatch",
    },
    "diff_kernel_configs": {
        "config_mismatch",
    },
    "validate_gpio_pinctrl_conflict": {
        "gpio_conflict",
    },
}


# ---------------------------------------------------------------------------
# Schemas — validate_skill_extension
# ---------------------------------------------------------------------------

class ValidateExtensionInput(BaseModel):
    skill_name: str = Field(
        ...,
        description="Name of the skill to extend (e.g. 'analyze_watchdog_timeout')",
    )
    log_snippet: str = Field(
        ...,
        description="Log text snippet to test the pattern against",
    )
    proposed_pattern: str = Field(
        ...,
        description="Python regex pattern to test (re.IGNORECASE applied automatically)",
    )


class ValidateExtensionOutput(BaseModel):
    matches: bool = Field(..., description="True if the pattern matched at least one line")
    match_count: int = Field(..., description="Total number of matching lines")
    matched_lines: list[str] = Field(
        ...,
        description="Up to 10 lines from the snippet that matched the pattern",
    )
    error: Optional[str] = Field(
        None,
        description="Set when the pattern is not a valid regex",
    )


# ---------------------------------------------------------------------------
# Schemas — suggest_pattern_improvement
# ---------------------------------------------------------------------------

class SuggestPatternInput(BaseModel):
    skill_name: str = Field(
        ...,
        description=(
            "Name of the skill to improve. Must be one of the keys in VALID_CATEGORIES."
        ),
    )
    log_snippet: str = Field(
        ...,
        description=(
            "Log excerpt (≥ 1 line) that the existing skill failed to classify. "
            "The proposed pattern must match at least one line here."
        ),
    )
    proposed_pattern: str = Field(
        ...,
        description="Python regex (re.IGNORECASE) that matches the missed log line(s)",
    )
    category: str = Field(
        ...,
        description=(
            "Skill-specific output category to assign when this pattern matches. "
            "Must be a value listed in VALID_CATEGORIES for the given skill_name."
        ),
    )
    description: str = Field(
        ...,
        description="Human-readable explanation of what this pattern detects",
    )


class SuggestPatternOutput(BaseModel):
    accepted: bool = Field(
        ...,
        description="True if the pattern was validated and written to the extension file",
    )
    match_preview: list[str] = Field(
        ...,
        description="Lines from log_snippet that matched (empty if not accepted)",
    )
    extension_file: str = Field(
        ...,
        description="Absolute path of the extension file that was written to",
    )
    rejection_reason: Optional[str] = Field(
        None,
        description="Human-readable reason the pattern was not accepted (when accepted=False)",
    )


# ---------------------------------------------------------------------------
# Skill 1 — validate_skill_extension
# ---------------------------------------------------------------------------

def validate_skill_extension(inp: ValidateExtensionInput) -> ValidateExtensionOutput:
    """
    Dry-run a proposed regex against a log snippet.

    Call this before suggest_pattern_improvement to confirm the pattern
    actually matches the lines you intend to capture.

    Args:
        inp: ValidateExtensionInput

    Returns:
        ValidateExtensionOutput with match results or an error message.
    """
    try:
        compiled = re.compile(inp.proposed_pattern, re.IGNORECASE)
    except re.error as exc:
        return ValidateExtensionOutput(
            matches=False,
            match_count=0,
            matched_lines=[],
            error=f"Invalid regex: {exc}",
        )

    matched: list[str] = []
    for line in inp.log_snippet.splitlines():
        if compiled.search(line):
            matched.append(line.rstrip())

    return ValidateExtensionOutput(
        matches=len(matched) > 0,
        match_count=len(matched),
        matched_lines=matched[:10],
        error=None,
    )


# ---------------------------------------------------------------------------
# Skill 2 — suggest_pattern_improvement
# ---------------------------------------------------------------------------

def suggest_pattern_improvement(inp: SuggestPatternInput) -> SuggestPatternOutput:
    """
    Validate and persist a new detection pattern for an existing skill.

    Performs four checks in order:
      1. skill_name is recognised (key in VALID_CATEGORIES).
      2. category is valid for that skill.
      3. proposed_pattern compiles as a Python regex.
      4. proposed_pattern matches at least one line in log_snippet.

    If all four pass, the pattern is written to the extension file and all
    subsequent calls to that skill will use it.

    Args:
        inp: SuggestPatternInput

    Returns:
        SuggestPatternOutput — accepted=True and the written file path, or
        accepted=False with a rejection_reason.
    """
    from skills.extensions import _extensions_path  # read path for output

    ext_file_path = str(_extensions_path())

    # 1 — skill name must be known
    if inp.skill_name not in VALID_CATEGORIES:
        known = ", ".join(sorted(VALID_CATEGORIES))
        return SuggestPatternOutput(
            accepted=False,
            match_preview=[],
            extension_file=ext_file_path,
            rejection_reason=(
                f"Unknown skill name '{inp.skill_name}'. "
                f"Extensible skills: {known}."
            ),
        )

    # 2 — category must be valid for this skill
    valid_cats = VALID_CATEGORIES[inp.skill_name]
    if inp.category not in valid_cats:
        return SuggestPatternOutput(
            accepted=False,
            match_preview=[],
            extension_file=ext_file_path,
            rejection_reason=(
                f"Invalid category '{inp.category}' for skill '{inp.skill_name}'. "
                f"Valid categories: {', '.join(sorted(valid_cats))}."
            ),
        )

    # 3 — regex must compile
    try:
        compiled = re.compile(inp.proposed_pattern, re.IGNORECASE)
    except re.error as exc:
        return SuggestPatternOutput(
            accepted=False,
            match_preview=[],
            extension_file=ext_file_path,
            rejection_reason=f"Invalid regex pattern: {exc}",
        )

    # 4 — pattern must match at least one line in the snippet
    matched = [
        line.rstrip()
        for line in inp.log_snippet.splitlines()
        if compiled.search(line)
    ]
    if not matched:
        return SuggestPatternOutput(
            accepted=False,
            match_preview=[],
            extension_file=ext_file_path,
            rejection_reason=(
                "The proposed pattern did not match any line in the provided "
                "log_snippet. Verify the pattern and re-submit with a representative "
                "log excerpt that demonstrates the miss."
            ),
        )

    # All checks passed — write to extension file
    written_path = write_extension_pattern(
        inp.skill_name,
        {
            "match": inp.proposed_pattern,
            "category": inp.category,
            "description": inp.description,
        },
    )

    return SuggestPatternOutput(
        accepted=True,
        match_preview=matched[:10],
        extension_file=written_path,
        rejection_reason=None,
    )
