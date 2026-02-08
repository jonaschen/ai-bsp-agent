# PRODUCT_BLUEPRINT.md: The Android BSP Consultant (MVP)

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
    * Identify the "Event Horizon" (Failure Timestamp).
    * Route the case to the Specialist (Pathologist or Hardware Advisor).
    * Compile the final **RCA Report**.

### Agent B: The Kernel Pathologist (Log Specialist)
* **Role:** The Software Detective.
* **Capabilities:**
    * **Log Parsing:** `dmesg`, `logcat`, `kernel_trace`.
    * **Context:** Uses **Vertex AI Context Caching** to load the specific Android Kernel Version source tree.
    * **Output:** Stack Trace Analysis & Suspect Code Module.

### Agent C: The Hardware Advisor (Spec Specialist)
* **Role:** The EE Consultant.
* **Capabilities:**
    * **RAG Retrieval:** Searches indexed Datasheets (PMIC, DRAM, SoC Specs).
    * **Task:** "Check the voltage requirements for component X."
    * **Output:** Safe Operating Area (SOA) validation & Measurement Instructions.

---

## 3. The Interactive Debugging Workflow (SOP)

The Product output is NOT just a text answer. It is a structured **SOP (Standard Operating Procedure)**:

1.  **Hypothesis:** "The PMIC Watchdog triggered due to I2C bus stall."
2.  **Evidence:** "Timestamp 1450.02: `i2c_transfer_timeout`."
3.  **Action Plan (The SOP):**
    * *Step 1:* "Probe Test Point TP34 (I2C_SDA)."
    * *Step 2:* "Check if waveform is held Low."
    * *Step 3:* "Apply patch `fix_i2c_timeout.diff` (Generated Code)."

---

## 4. Evaluation Criteria: The "Golden Set" (TDD)

**Instruction to QA Agent:**
To verify the Product, you must run the following scenarios. Use **LLM-as-a-Judge** (Semantic Similarity) to compare the Product's output against the "Expected Output."

### Test Case 1: The "Null Pointer" (Software Panic)
* **Input:** `fixtures/panic_log_01.txt` (Contains a NULL pointer dereference in `mdss_dsi.c`).
* **Expected Output (Semantic Keypoints):**
    * Diagnosis: "Null Pointer Dereference."
    * Location: `drivers/gpu/drm/msm/mdss.c`.
    * Recommendation: "Add check for `clk_ptr` before access."
    * Confidence: > 85%.

### Test Case 2: The "Sleep Zombie" (Hardware Hang)
* **Input:** `fixtures/suspend_hang_02.txt` (System freezes during S2D, valid `dmesg` ends abruptly).
* **Expected Output (Semantic Keypoints):**
    * Diagnosis: "Watchdog Timeout / Hard Lockup."
    * Suspect: "PMIC or DRAM Self-Refresh failure."
    * Action: "Connect JTAG and check Program Counter (PC)."

---

## 5. Technical Constraints (For the Architect)
* **Context Window:** Must support up to 1M tokens (for full `dmesg`).
* **Retrieval:** Must implement a Vector Store for Datasheets.
* **Security:**
    * **Read-Only:** Agents cannot execute shell commands on the user's host.
    * **Privacy:** Logs are processed in a transient container.
