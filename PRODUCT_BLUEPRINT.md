# PRODUCT_BLUEPRINT.md: The Android BSP Consultant (v5.1 - Patched)

> **META-INSTRUCTION FOR STUDIO:**
> This document is the **Source of Truth** for the Product Owner Agent.
> You must build a system that satisfies the **User Persona**, **Capabilities**, and **Golden Set Tests** defined below.

---

## 1. Product Vision: "The Force Multiplier"
We are building a **Specialized AI Consultancy Squad** for Android BSP Engineers.
* **Problem:** Alert Fatigue and high MTTR in debugging Suspend-to-Disk (S2D) and Kernel Panics.
* **Solution:** A "Read-Only" Consultant that analyzes logs, correlates them with datasheets, and produces a **Standard Operating Procedure (SOP)** for the human to execute.
* **Constraint:** The Agent **DOES NOT** have hands. It cannot reset hardware or write to the kernel tree. It only offers high-confidence advice.

---

## 2. The Consultant Squad (The Product Roster)

The Studio must instantiate the following Multi-Agent System:

### Agent A: The Supervisor (Interface Layer)
* **Role:** Triage & User Interaction.
* **Input:** User Chat + Case Files (Logs).
* **Responsibility:**
    * **Validation (Fix #2):** Check if input is valid (e.g., is it a log?). If invalid, return `STATUS: CLARIFY_NEEDED`.
    * **Chunking (Fix #3):** If Log Size > 50MB, extract the "Event Horizon" (last 5000 lines OR timestamp of failure ± 10s) before passing to specialists.
    * Route the case to the Specialist (Pathologist or Hardware Advisor).
    * Compile the final **RCA Report**.

### Agent B: The Kernel Pathologist (Log Specialist)
* **Role:** The Software Detective.
* **Capabilities:**
    * **Log Parsing:** `dmesg`, `logcat`, `kernel_trace`.
    * **Context:** Uses **Vertex AI Context Caching** to load the specific Android Kernel Version source tree.
    * **Tool (Fix #7):** MUST implement `verify_file_exists(path)` and call it before recommending any file modification.
    * **Output:** Stack Trace Analysis & Suspect Code Module.

### Agent C: The Hardware Advisor (Spec Specialist)
* **Role:** The EE Consultant.
* **Capabilities:**
    * **RAG Retrieval:** Searches indexed Datasheets (PMIC, DRAM, SoC Specs).
    * **Task:** "Check the voltage requirements for component X."
    * **Output:** Safe Operating Area (SOA) validation & Measurement Instructions.

---

## 2.5 The Build Roadmap: Phased Delivery with Explicit Dependencies

To enforce **Test-Driven Development** and prevent infrastructure-before-specification mistakes, the Studio MUST build in the following order:

### Phase 0: Foundation (Specification & Validation)

**TKT-001: Define Agent Personas & Input/Output Contracts**
* **Objective:** Formalize the interfaces between Supervisor, Pathologist, and Hardware Advisor.
* **Deliverables:**
  - Supervisor input schema (user query + log file format)
  - Pathologist output schema (suspected module, confidence score, evidence)
  - Hardware Advisor input schema (component name, query type)
  - Hardware Advisor output schema (voltage specs, timing specs, SOA)
* **Acceptance Criteria:**
  - All three agents have formal Pydantic models in `product/schemas.py`
  - Each model is documented with examples
  - JSON serialization tests pass for all schemas
* **Blocked By:** None
* **Blocks:** TKT-002

**TKT-002: Define Data Contracts & Metadata Schema (Datasheet Repository)**
* **Objective:** Specify the structure, metadata, and retrieval patterns for the datasheet repository.
* **Deliverables:**
  - Datasheet metadata schema (component_type, part_number, voltage_range, timing_specs, etc.)
  - Sample datasheet JSON structures (minimum 3 different types: PMIC, DRAM, SoC)
  - Vector embedding strategy (what fields get embedded for RAG?)
  - Example retrieval queries the Hardware Advisor will make
* **Acceptance Criteria:**
  - Schema is defined in `product/schemas/datasheet.py`
  - 5 representative sample datasheets exist in `fixtures/datasheets/`
  - Retrieval query patterns documented with examples
* **Blocked By:** TKT-001
* **Blocks:** TKT-003, TKT-004

**TKT-003: Create RCA Workflow Test Fixtures (Golden Set)**
* **Objective:** Build the test cases required by PRODUCT_BLUEPRINT Section 4.
* **Deliverables:**
  - `fixtures/panic_log_01.txt` - Null pointer dereference scenario
  - `fixtures/suspend_hang_02.txt` - Watchdog timeout scenario
  - `fixtures/healthy_boot_03.txt` - Clean boot (no anomaly scenario)
  - `fixtures/expected_output_*.json` - Expected RCA reports for each test case
* **Acceptance Criteria:**
  - All 3 log fixtures exist and are valid (can be parsed by real dmesg parsers)
  - Expected outputs follow the SOP schema from Section 3
  - Ensure at least one log fixture contains approximately 1500 lines of standard system noise preceding the actual crash event. This will serve as the benchmark to test the Supervisor's keyword filtering and log segmentation logic."
* **Blocked By:** TKT-002
* **Blocks:** TKT-005 (Agent Implementation)

### Phase 1: Agent Implementation (Code)

**TKT-005: Implement Supervisor Agent**
* **Objective:** Build the triage and routing agent.
* **Acceptance Criteria:**
  - Passes on TKT-003 fixtures
  - Correctly routes to Pathologist vs. Hardware Advisor
  - The Supervisor Agent MUST implement a pre-processing pipeline for log files. It must not send raw logs directly to the LLM.
* **Requirement:** Implement a slicing and keyword-analysis algorithm (e.g., searching for Call trace:, Kernel panic, watchdog:, BUG:) that takes a ~1500-line raw log and extracts a concentrated segment of < 500 lines. Only this filtered segment is passed to the Kernel Pathologist."
* **Blocked By:** TKT-003
* **Blocks:** TKT-008 (End-to-End Tests)

**TKT-006: Implement Kernel Pathologist Agent**
* **Objective:** Build the software analysis specialist.
* **Acceptance Criteria:**
  - Correctly identifies null pointer dereference in Test Case 1
  - Correctly diagnoses watchdog timeout in Test Case 2
  - Returns high confidence on Test Case 3 (no anomaly)
* **Blocked By:** TKT-003
* **Blocks:** TKT-008

**TKT-007: Implement Hardware Advisor Agent (with Vector Store)**
* **Objective:** Build the hardware specialist with datasheet retrieval.
* **Acceptance Criteria:**
  - Successfully retrieves datasheets from vector store using semantic similarity
  - Returns SOA validation for queried components
  - Integrates with vector store backend from TKT-004
* **Blocked By:** TKT-002, TKT-003, TKT-004
* **Blocks:** TKT-008

### Phase 2: Infrastructure

**TKT-004: Implement Vector Store Manager**
* **Objective:** Build the datasheet indexing and retrieval system.
* **Technology Choice:** Vertex Vector Search (per AGENTS.md Section 5 Technology Stack Mandate)
* **Deliverables:**
  - Vector store initialization code
  - Datasheet ingestion pipeline
  - Semantic retrieval methods
  - Integration with Hardware Advisor agent
* **Data Model:** Uses schema from TKT-002
* **Test Data:** Uses fixtures from TKT-002
* **Acceptance Criteria:**
  - Successfully indexes sample datasheets from `fixtures/datasheets/`
  - Retrieval returns semantically similar components
  - Latency < 500ms for single query
  - Supports concurrent Hardware Advisor queries
* **Blocked By:** TKT-002, TKT-003
* **Blocks:** TKT-007

### Phase 3: Integration & Validation

**TKT-008: End-to-End RCA Workflow Tests**
* **Objective:** Validate the entire system against golden set.
* **Acceptance Criteria:**
  - All 3 golden set test cases pass with semantic similarity > 85%
  - Confidence scores align with expected keypoints
  - SOP steps are actionable and correctly formatted
* **Blocked By:** TKT-005, TKT-006, TKT-007

### Dependency Graph

```
TKT-001 (Agent Personas)
  └─→ TKT-002 (Data Contracts)
       ├─→ TKT-003 (Test Fixtures)
       │    ├─→ TKT-005 (Supervisor)
       │    ├─→ TKT-006 (Pathologist)
       │    └─→ TKT-007 (Hardware Advisor) ←─┐
       │                                      │
       └─→ TKT-004 (Vector Store) ───────────┘
            └─→ TKT-008 (E2E Tests) ←─ TKT-005, TKT-006, TKT-007
```

---

## 3. The Interactive Debugging Workflow (SOP)

The Product output is NOT just a text answer. It MUST adhere to this **Strict JSON Schema (Fix #6):**

```json
{
  "diagnosis_id": "RCA-BSP-001",
  "confidence_score": 0.0 to 1.0,
  "status": "CRITICAL" | "WARNING" | "INFO",
  "root_cause_summary": "Brief description",
  "evidence": [
    "Timestamp 1450.02: i2c_transfer_timeout"
  ],
  "sop_steps": [
    {
      "step_id": 1,
      "action_type": "MEASUREMENT" | "CODE_PATCH",
      "instruction": "Probe Test Point TP34 (I2C_SDA)",
      "expected_value": "Held High (1.8V)",
      "file_path": "N/A"
    }
  ]
}
```


## 4. Evaluation Criteria: The "Golden Set" (TDD)
Instruction to QA Agent: To verify the Product, you must run the following scenarios. Use LLM-as-a-Judge (Semantic Similarity) to compare the Product's output against the "Expected Output."

### Test Case 1: The "Null Pointer" (Software Panic)
* **Input:** fixtures/panic_log_01.txt (Contains a NULL pointer dereference in mdss_dsi.c).

* **Expected Output (Semantic Keypoints):**

    * **Diagnosis:** "Null Pointer Dereference."

    * **Location:** drivers/gpu/drm/msm/mdss.c.

    * **Recommendation:** "Add check for clk_ptr before access."

    * **Confidence:** > 85%.

### Test Case 2: The "Sleep Zombie" (Hardware Hang)
* **Input:** fixtures/suspend_hang_02.txt (System freezes during S2D, valid dmesg ends abruptly).

* **Expected Output (Semantic Keypoints):**

    * **Diagnosis:** "Watchdog Timeout / Hard Lockup."

    * **Suspect:** "PMIC or DRAM Self-Refresh failure."

    * **Action:** "Connect JTAG and check Program Counter (PC)."

### Test Case 3: The "False Alarm" (Fix #5)
* **Input:** fixtures/healthy_boot_03.txt (A standard, error-free Android boot log).

* **Expected Output (Semantic Keypoints):**

    * **Diagnosis:** "No Anomaly Detected."

    * **Status:** "INFO".

    * **Action:** "None required."

    * **Confidence:** > 90%.

## 5. Technical Constraints (For the Architect)
* **Context Window:** Must support up to 1M tokens (for full dmesg).

* **Retrieval:** Must implement a Vector Store for Datasheets.

* **Security:**

    * **Read-Only:** Agents cannot execute shell commands on the user's host.

    * **Privacy:** Logs are processed in a transient container.
