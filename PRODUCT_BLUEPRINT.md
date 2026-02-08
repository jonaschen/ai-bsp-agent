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
