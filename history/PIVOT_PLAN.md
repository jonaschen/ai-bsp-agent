# Architecture Pivot Plan: From Code-Gen Factory to Skill-Based Expert Agent

## 1. Context & Rationale (The Pivot)
This repository (`ai-bsp-agent`) was originally designed as a complex Meta-Agent factory (an automated software engineering pipeline). It used a LangGraph Orchestrator with Product Owner, Architect, Engineer (Jules), and QA Verifier agents to dynamically write, test, and merge code in isolated Docker sandboxes.

**The Pivot:** We are abandoning the "Automated Code-Generation Factory" paradigm. The infrastructure overhead (Git branch syncing, Docker volume mounting, namespace collisions) has outweighed the domain value. 
We are adopting the **Anthropic Tool-Use / Agent Skill paradigm**. 

**The New Goal:** Transform the Orchestrator into a dedicated Android BSP (Board Support Package) Diagnostic Expert. Instead of asking the AI to write code, we will equip a reasoning LLM with highly deterministic, human-written Python tools (Skills) to parse logs and diagnose kernel/hardware issues.

## 2. Deprecation Notice (What NOT to do)
To the AI Assistant (Claude Code) reading this:
* **IGNORE `issues.md`:** Do not attempt to fix the legacy test suite, `test_recovery.py`, `git_utils.py`, or any namespace collisions.
* **DO NOT fix the Sandbox:** Ignore all Docker, `QA_Verifier`, and `Watch_Tower` logic.
* **DO NOT generate AI-coding loops:** We are no longer generating code via LLM loops. 
* **FROZEN DIRS:** Treat the legacy factory logic in `studio/subgraphs/engineer.py` and `studio/utils/sandbox.py` as deprecated.

## 3. The New Architecture (What to build)
The system will now consist of:
1.  **The Brain (LangGraph / LLM):** A simplified Orchestrator that receives user queries (e.g., "Why did STD hibernation fail?").
2.  **The Skill Registry (`skills/` or `tools/`):** A new directory containing pure Python functions (Tools) with strict Pydantic schemas.
3.  **The Domain Knowledge:** Markdown files (e.g., `SKILL.md`) using progressive disclosure to feed the LLM context.

## 4. First Milestone: The STD Hibernation Diagnostic Skill
Our immediate task is to build the first Agent Skill based on the Android STD (Suspend to Disk) debugging SOP.

**Domain Context:**
When a wearable device transitions through STD phases (Freeze/Thaw/Poweroff/Restore), it may fail at "Checkpoint 2: Insufficient memory allocation for image" with the log message `Error -12 creating hibernation image`. This is often due to the `SUnreclaim` memory being too high or Swap space being insufficient.

**Target Implementation:**
1.  Create a new directory: `tools/bsp_diagnostics/`.
2.  Implement a pure Python function: `analyze_std_hibernation_error(dmesg_log: str, meminfo_log: str) -> dict`.
3.  **Logic Requirements:** * Parse the `dmesg_log` for `Error -12 creating hibernation image`.
    * Parse the `meminfo_log` to extract `SUnreclaim`, `MemTotal`, and `SwapFree`.
    * Calculate if `SUnreclaim` exceeds 10% of total physical memory.
    * Return a structured JSON/dict containing the root cause and the recommended action (e.g., `echo 3 > /proc/sys/vm/drop_caches`).
4.  Bind this function as an Anthropic-compatible tool to our core Agent.

## 5. Instructions for Claude Code
When executing tasks based on this plan:
1.  Always use strict typing and Pydantic for tool inputs/outputs.
2.  Write simple, fast, isolated `pytest` cases for the Python tool functions ONLY. Do not invoke the legacy Orchestrator in these tests.
3.  Prioritize pure functions over complex state objects.
