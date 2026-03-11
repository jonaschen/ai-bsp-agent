"""
Tests for skill_improvement skills:
  - validate_skill_extension
  - suggest_pattern_improvement

All tests are isolated (no LLM, no persistent state).
The BSP_EXTENSIONS_PATH env var redirects file writes to a temp file.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

import pytest

from skills.bsp_diagnostics.skill_improvement import (
    validate_skill_extension,
    suggest_pattern_improvement,
    ValidateExtensionInput,
    SuggestPatternInput,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def ext_file(tmp_path, monkeypatch):
    """Point BSP_EXTENSIONS_PATH to a fresh temp file for each test."""
    p = tmp_path / "skill_extensions.json"
    monkeypatch.setenv("BSP_EXTENSIONS_PATH", str(p))
    return p


WATCHDOG_SNIPPET = (
    "[  52.123456] [0: kworker/u8:4:1234] BUG: soft lockup - CPU#0 stuck for 23s!\n"
    "[  52.123457] Call trace:\n"
    "[  52.123458]  vendor_drv_callback+0x3c/0x120\n"
)

UNKNOWN_SNIPPET = (
    "[  10.000000] some unrelated kernel line\n"
    "[  11.000000] another normal line\n"
)


# ---------------------------------------------------------------------------
# validate_skill_extension tests
# ---------------------------------------------------------------------------

class TestValidateSkillExtension:
    def test_matches_when_pattern_found(self):
        result = validate_skill_extension(ValidateExtensionInput(
            skill_name="analyze_watchdog_timeout",
            log_snippet=WATCHDOG_SNIPPET,
            proposed_pattern=r"kworker.*BUG.*soft lockup",
        ))
        assert result.matches is True
        assert result.match_count >= 1
        assert len(result.matched_lines) >= 1
        assert "kworker" in result.matched_lines[0]

    def test_no_match_returns_false(self):
        result = validate_skill_extension(ValidateExtensionInput(
            skill_name="analyze_watchdog_timeout",
            log_snippet=UNKNOWN_SNIPPET,
            proposed_pattern=r"BUG: soft lockup",
        ))
        assert result.matches is False
        assert result.match_count == 0
        assert result.matched_lines == []

    def test_invalid_regex_returns_error(self):
        result = validate_skill_extension(ValidateExtensionInput(
            skill_name="analyze_watchdog_timeout",
            log_snippet=WATCHDOG_SNIPPET,
            proposed_pattern=r"[unclosed",
        ))
        assert result.matches is False
        assert result.error is not None
        assert "regex" in result.error.lower()

    def test_unknown_skill_name_still_validates_regex(self):
        # validate_skill_extension only checks the regex, not the skill name
        result = validate_skill_extension(ValidateExtensionInput(
            skill_name="nonexistent_skill",
            log_snippet=WATCHDOG_SNIPPET,
            proposed_pattern=r"BUG",
        ))
        assert result.matches is True

    def test_matched_lines_limited_to_ten(self):
        many_line_log = "\n".join(f"BUG: error in line {i}" for i in range(20))
        result = validate_skill_extension(ValidateExtensionInput(
            skill_name="analyze_watchdog_timeout",
            log_snippet=many_line_log,
            proposed_pattern=r"BUG",
        ))
        assert result.match_count == 20
        assert len(result.matched_lines) <= 10

    def test_case_insensitive_match(self):
        result = validate_skill_extension(ValidateExtensionInput(
            skill_name="analyze_watchdog_timeout",
            log_snippet="BUG: SOFT LOCKUP on cpu#2",
            proposed_pattern=r"soft lockup",
        ))
        assert result.matches is True


# ---------------------------------------------------------------------------
# suggest_pattern_improvement tests
# ---------------------------------------------------------------------------

class TestSuggestPatternImprovement:
    def test_valid_pattern_accepted_and_written(self, ext_file):
        result = suggest_pattern_improvement(SuggestPatternInput(
            skill_name="analyze_watchdog_timeout",
            log_snippet=WATCHDOG_SNIPPET,
            proposed_pattern=r"kworker.*BUG.*soft lockup",
            category="soft_lockup",
            description="Qualcomm vendor kernel soft lockup format",
        ))
        assert result.accepted is True
        assert result.rejection_reason is None
        assert len(result.match_preview) >= 1
        assert str(ext_file) in result.extension_file

        # Extension file must exist and be valid JSON
        data = json.loads(ext_file.read_text())
        assert data["version"] == 1
        patterns = data["skills"]["analyze_watchdog_timeout"]["patterns"]
        assert len(patterns) == 1
        assert patterns[0]["match"] == r"kworker.*BUG.*soft lockup"
        assert patterns[0]["category"] == "soft_lockup"

    def test_appends_to_existing_extension_file(self, ext_file):
        # Pre-populate with one pattern
        existing = {
            "version": 1,
            "skills": {
                "analyze_watchdog_timeout": {
                    "patterns": [
                        {"match": "old_pattern", "category": "rcu_stall", "description": "old"}
                    ]
                }
            }
        }
        ext_file.write_text(json.dumps(existing))

        suggest_pattern_improvement(SuggestPatternInput(
            skill_name="analyze_watchdog_timeout",
            log_snippet=WATCHDOG_SNIPPET,
            proposed_pattern=r"kworker.*BUG.*soft lockup",
            category="soft_lockup",
            description="new pattern",
        ))

        data = json.loads(ext_file.read_text())
        patterns = data["skills"]["analyze_watchdog_timeout"]["patterns"]
        assert len(patterns) == 2

    def test_rejected_unknown_skill_name(self, ext_file):
        result = suggest_pattern_improvement(SuggestPatternInput(
            skill_name="nonexistent_skill",
            log_snippet=WATCHDOG_SNIPPET,
            proposed_pattern=r"BUG",
            category="soft_lockup",
            description="test",
        ))
        assert result.accepted is False
        assert "skill" in result.rejection_reason.lower()

    def test_rejected_invalid_category_for_skill(self, ext_file):
        result = suggest_pattern_improvement(SuggestPatternInput(
            skill_name="analyze_watchdog_timeout",
            log_snippet=WATCHDOG_SNIPPET,
            proposed_pattern=r"BUG",
            category="auth_failure",   # valid for early_boot, not watchdog
            description="test",
        ))
        assert result.accepted is False
        assert "category" in result.rejection_reason.lower()

    def test_rejected_invalid_regex(self, ext_file):
        result = suggest_pattern_improvement(SuggestPatternInput(
            skill_name="analyze_watchdog_timeout",
            log_snippet=WATCHDOG_SNIPPET,
            proposed_pattern=r"[unclosed",
            category="soft_lockup",
            description="test",
        ))
        assert result.accepted is False
        assert "regex" in result.rejection_reason.lower()

    def test_rejected_pattern_does_not_match_snippet(self, ext_file):
        result = suggest_pattern_improvement(SuggestPatternInput(
            skill_name="analyze_watchdog_timeout",
            log_snippet=UNKNOWN_SNIPPET,
            proposed_pattern=r"BUG: soft lockup",
            category="soft_lockup",
            description="test",
        ))
        assert result.accepted is False
        assert "match" in result.rejection_reason.lower()

    def test_second_skill_patterns_stored_separately(self, ext_file):
        suggest_pattern_improvement(SuggestPatternInput(
            skill_name="analyze_watchdog_timeout",
            log_snippet=WATCHDOG_SNIPPET,
            proposed_pattern=r"kworker.*soft lockup",
            category="soft_lockup",
            description="watchdog pattern",
        ))
        suggest_pattern_improvement(SuggestPatternInput(
            skill_name="parse_early_boot_uart_log",
            log_snippet="MT_DDR: training failed at step 3",
            proposed_pattern=r"MT_DDR.*training.*fail",
            category="ddr_init_failure",
            description="MediaTek DDR training failure",
        ))

        data = json.loads(ext_file.read_text())
        assert "analyze_watchdog_timeout" in data["skills"]
        assert "parse_early_boot_uart_log" in data["skills"]

    def test_all_skill_names_accepted(self, ext_file):
        """Every extensible skill name must be recognised."""
        from skills.bsp_diagnostics.skill_improvement import VALID_CATEGORIES
        for skill_name, categories in VALID_CATEGORIES.items():
            cat = next(iter(categories))
            snippet = f"dummy log line matching {cat}"
            result = suggest_pattern_improvement(SuggestPatternInput(
                skill_name=skill_name,
                log_snippet=snippet,
                proposed_pattern=r"dummy",
                category=cat,
                description="test",
            ))
            # Rejected only because pattern doesn't match or other reasons, not skill name
            if not result.accepted:
                assert "skill" not in result.rejection_reason.lower(), (
                    f"{skill_name}: was rejected due to unknown skill name"
                )
