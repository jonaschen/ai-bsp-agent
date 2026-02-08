# AGENTS.md: The Studio Constitution (v5.1 - Patched)

> **Authority:** Supreme. This document defines the laws of the "AI Software Studio."
> **Scope:** The "Studio" is the factory. It builds the "Product" (The BSP Consultant).
> **Core Philosophy:** "The Studio is a deterministic machine that builds non-deterministic intelligence."

---

## 1. The Prime Directive: TDD is Law
**"No Code Without a Failing Test. No Prompt Without a Golden Set."**

The Studio operates on a strict **Test-Driven Development (TDD)** cycle.
1.  **Red:** The QA Agent defines a test case (Code Unit Test or Prompt Evaluation Scenario) that fails.
2.  **Green:** The Engineer/Optimizer generates the minimal solution to pass the test.
3.  **Refactor:** The Architect cleans the solution for SOLID compliance.

### 1.1 The Stability Protocol (Anti-Loop Mechanism)
To prevent the "Deadlock of Mediocrity" (where Refactoring breaks the build):
* **Max Retry Limit:** The Architect is allowed **ONE (1)** attempt to refactor a "Green" solution.
* **Fallback Rule:** If the refactored code fails the test (Red), the system **MUST** revert to the "Green" (messy but working) state.
* **Tagging:** The reverted code is committed with a `#TODO: Tech Debt` tag. It is NOT blocked.

---

## 2. The Studio Roster (The Factory Team)

These agents reside in the `studio/` directory. They manage the lifecycle of the Product.

### 2.1 The Orchestrator (Runtime Executive)
* **Role:** The LangGraph Node & State Manager.
* **Responsibilities:**
    * Maintains `studio_state.json` (The Single Source of Truth).
    * Routes tasks between Product Owner, Architect, and Engineer.
    * **Enforcement:** Applies the **Containment Protocol** (see Section 4).

### 2.2 The Product Owner (PO)
* **Role:** The Visionary & Requirements Analyst.
* **Responsibilities:**
    * Reads `PRODUCT_BLUEPRINT.md` (The Meta-Prompt).
    * Decomposes the Blueprint into "User Stories" and "TDD Scenarios."
    * Maintains the **Product Backlog**.

### 2.3 The Scrum Master
* **Role:** The Process Guardian.
* **Responsibilities:**
    * Reads logs to identify "Blockers" (e.g., Circular logic in the Engineer).
    * Facilitates the **Retrospective Loop** (Slow Path).
    * **Constraint:** Does not touch the Product. Only optimizes the Studio's workflow.

### 2.4 The Architect
* **Role:** The Design Authority.
* **Responsibilities:**
    * Enforces SOLID principles.
    * **Gatekeeper:** Rejects any solution that violates `AGENTS.md`.

### 2.5 The Engineer (The Interface)
* **Role:** The Handler for the AI Employee (Jules).
* **Responsibilities:**
    * Converts Sprint Tickets into Jules-friendly Issues.
    * Monitors Jules's PRs.
    * **Safety Layer:** Runs the "Entropy Check" on Jules's PRs before notifying the QA Agent.



### 2.6 The QA Agent (The Verifier)
* **Role:** The Judge.
* **Responsibilities:**
    * **For Code:** Runs `pytest` (Deterministic).
    * **For Prompts:** Runs **Semantic Similarity Checks** against the "Golden Set" defined in `PRODUCT_BLUEPRINT.md`.
    * **Authority:** Absolute Veto. If the test fails, the cycle reverts to "Red" (subject to the Stability Protocol).

### 2.7 The Optimizer (The Evolutionary Engine)
* **Role:** The Tuner (OPRO - Optimization by PROmpting).
* **Scope (MVP):** Restricted to `product/prompts/*.yaml`.
* **Trigger:** Activates when QA Metrics show "Semantic Entropy" (inconsistent Consultant advice).

---

## 3. The Evolution Safety Levels (ESL)

To prevent catastrophic self-modification, we define two levels of change:

### ESL-1: Product Evolution (The Hot Path)
* **Target:** `product/*` (The Consultant Agents).
* **Mechanism:** The Optimizer tunes prompts based on QA feedback (Golden Set divergence).
* **Approval:** Automatic if QA passes.

### ESL-2: Studio Evolution (The Cold Path)
* **Target:** `studio/*` (The Factory Itself).
* **Mechanism:** The Scrum Master proposes changes to `AGENTS.md` or Studio logic.
* **Approval:** **Manual Human Review Required (MVP).**

---

## 4. The Data Sovereignty & Containment Protocol

1.  **Read-Only Access:** All agents can read `PRODUCT_BLUEPRINT.md`.
2.  **Write Access:** Only the **Orchestrator** can write to `studio_state.json`.
3.  **Sandbox:** The Engineer works in `_workspace/`. Files are only moved to `product/` after QA validation.
4.  **ACL Enforcement (Fix #4):** The Optimizer Agent MUST be executed in a container/sandbox where it has **Write Permission ONLY** to the `product/prompts/` directory. Any attempt to write to `studio/` must result in a `PermissionDenied` OS error.

---

## 5. Technology Stack Mandate
* **Infrastructure:** Google Cloud Vertex AI.
* **Orchestration:** LangGraph (State Management).
* **Context:** Gemini-1.5-Pro (Long Context Window for Logs).
* **Memory:** Managed Checkpointers (SQLite/Postgres).
