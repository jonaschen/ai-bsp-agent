# Product Blueprint: Android BSP Consultant Agent Team
> **Version:** 1.0 (MVP: The Virtual Consultant)
> **Status:** VERIFIED / READY FOR SCAFFOLDING
> **Scope:** Log Analysis & Root Cause Analysis (No Hardware Actuation)

---

## 1. Product Vision & Narrative

### The Problem
Android BSP (Board Support Package) engineers face "Alert Fatigue." Debugging Suspend-to-Disk (S2D) failures involves parsing millions of lines of logs (`dmesg`, `logcat`, `kernel_trace`) to find a single race condition. This manual process has a high Mean Time To Resolution (MTTR).

### The Solution: "The Virtual Consult"
We are building a **Specialized AI Consultancy Squad**—not to replace the engineer, but to act as a force multiplier. This team does not have "hands" (it cannot reset hardware), but it has "eyes" (infinite log reading) and "memory" (perfect recall of datasheets).

### The User Persona
* **Target User:** Senior BSP Engineer.
* **Interaction:** The user submits a "Case File" (Logs + Optional Source Code Context).
* **Deliverable:** A **Structured RCA Report** containing the failure timestamp, suspect code module, and a probability-weighted hypothesis.

---

## 2. The Agent Roster (Consultancy Tier)

The product consists of three specialized agents operating in a linear-recursive pipeline.

### Agent 1: The Screener (Triage Specialist)
* **Role:** The "Emergency Room Nurse."
* **Responsibility:** Rapidly ingest raw logs to filter noise and identify the "Event Horizon" (the exact second the system failed).
* **Capabilities:**
    * Parse `dmesg` timestamps.
    * Classify failure types: `Kernel Panic`, `Watchdog Timeout`, `Hang/Stall`, `Resume Fail`.
    * **Constraint:** Does NOT look at source code. Only looks at logs.

### Agent 2: The Pathologist (Deep Dive Engineer)
* **Role:** The "Lead Detective."
* **Responsibility:** Analyze the triage report, correlate it with Source Code, and formulate a hypothesis.
* **Capabilities:**
    * **Restricted File Access:** Can read C/C++ source code via `read_specific_file(path)`.
    * **Constraint:** Agent is **STRICTLY PROHIBITED** from using directory traversal tools (like `ls -R` or `grep -r`) on the source tree to prevent Context Window Overflow. Agent must derive the exact file path (e.g., `drivers/gpu/drm/msm/mdss.c`) from the log stack trace *before* requesting to read it.
    * Trace call stacks (Stack Unwinding).
    * Request external knowledge from the *Librarian*.
* **Output:** The Final RCA Report.

### Agent 3: The Librarian (Knowledge Researcher)
* **Role:** The "Legal Researcher."
* **Responsibility:** Fetch static knowledge to support the Pathologist's hypothesis.
* **Capabilities:**
    * Search ARM Architecture Manuals (e.g., "What does ESR_EL1 0x96000004 mean?").
    * Retrieve datasheet specifications.
    * **Constraint:** Read-Only access to documentation.

---

## 3. Interaction Schema (The Strict Interface)

### 3.1 Input: The Case File
*Submitted by the Human User.*
```json
{
  "case_id": "BSP-20260207-001",
  "device_model": "Pixel_Prototype_X",
  "source_code_mode": "USER_UPLOADED_ZIP", 
  "symptom_description": "Device fails to resume from hibernate after 4 hours.",
  "log_payload": {
    "dmesg_content": "<RAW_TEXT_OR_URL>",
    "logcat_content": "<RAW_TEXT_OR_URL>"
  }
}
```
Note: We assume relevant source code is uploaded by the user to a strictly defined sandbox path, avoiding the need for the Agent to clone a 50GB Git repo.

### 3.2 Output: The Triage Report (Screener -> Pathologist)
```json
{
  "status": "CRITICAL",
  "failure_type": "KERNEL_PANIC",
  "event_horizon_timestamp": "1456.7890",
  "key_evidence": [
    "Unable to handle kernel paging request at virtual address...",
    "PC is at dpm_run_callback+0x40/0x80"
  ],
  "suspected_file_hint": "drivers/base/power/main.c"
}
```
### 3.3 Internal: The Knowledge Query (Pathologist -> Librarian)
```json
{
  "query_type": "REGISTER_LOOKUP",
  "context": "ARM64 Exception Class",
  "search_term": "ESR_EL1 0x96000004"
}
```
### 3.4 Final Deliverable: The RCA Report (Pathologist -> User)
```json
{
  "diagnosis_id": "RCA-BSP-001",
  "confidence_score": 0.85,
  "root_cause_summary": "Null pointer dereference in display driver resume path.",
  "technical_detail": "The 'dpm_run_callback' invoked 'mdss_resume', which tried to access an uninitialized clock structure.",
  "suggested_fix": "Add null check for 'clk_ptr' in 'drivers/gpu/drm/msm/mdss.c' before access.",
  "references": ["ARMv8-A Architecture Reference Manual, Section D1.10"]
}
```

## 4. Definition of Done (DoD)
The Product Team is considered "Functional" when it passes the following **Synthetic Unit Tests** using the fixtures defined in Section 6.

1. **The "Null Pointer" Test:**
  * Input: fixtures/panic_log_01.txt
  * Success Criteria: Pathologist output contains "suggested_fix": "...null check...".

2. The "Watchdog" Test:
  * Input: fixtures/watchdog_log_01.txt
  * Success Criteria: Screener output contains "failure_type": "WATCHDOG_TIMEOUT".

## 5. Security & Safety
* **Read-Only Mandate:** Agents utilize File_Read permissions only. No agent is authorized to File_Write to the source tree.

* **Privacy:** Logs are processed within the secure enclave.

## 6. Test Data Fixtures (For TDD)
**Fixture:** panic_log_01.txt **(Simulated Kernel Panic)**

```plaintext
[ 1456.788012] mdss_dsi_phy_init:phy_regulator_enable failed
[ 1456.789001] Unable to handle kernel NULL pointer dereference at virtual address 0000000000000010
[ 1456.789005] Mem abort info:
[ 1456.789008]   ESR = 0x96000004
[ 1456.789012]   Exception class = DABT (current EL), IL = 32 bits
[ 1456.789015]   SET = 0, FnV = 0
[ 1456.789018]   EA = 0, S1PTW = 0
[ 1456.789025] Data abort info:
[ 1456.789028]   ISV = 0, ISS = 0x00000004
[ 1456.789031]   CM = 0, WnR = 0
[ 1456.789038] user pgtable: 4k pages, 39-bit VAs, pgdp=0000000105655000
[ 1456.789042] [0000000000000010] pgd=0000000000000000
[ 1456.789050] Internal error: Oops: 96000004 [#1] PREEMPT SMP
[ 1456.789055] Modules linked in: wlan(O)
[ 1456.789062] CPU: 4 PID: 1234 Comm: kworker/u16:12 Tainted: G        O      5.10.101-android12-9-g392849 #1
[ 1456.789066] Hardware name: Qualcomm Technologies, Inc. SM8350 MTP (DT)
[ 1456.789072] Workqueue: events_unbound dpm_run_callback
[ 1456.789078] pstate: 60400005 (nZCv daif +PAN -UAO -TCO BTYPE=--)
[ 1456.789082] pc : mdss_resume+0x24/0x80
[ 1456.789086] lr : dpm_run_callback+0x40/0x100
[ 1456.789090] sp : ffffffc010003c80
[ 1456.789093] x29: ffffffc010003c80 x28: ffffffc011499000 
[ 1456.789097] x27: 0000000000000000 x26: 0000000000000000 
[ 1456.789101] x25: ffffffc011499000 x24: ffffffc010003d60 
[ 1456.789105] x23: 0000000000000000 x22: ffffff8004561000 
[ 1456.789109] x21: ffffff8004561080 x20: 0000000000000000 
[ 1456.789113] x19: ffffff8004561000 x18: 0000000000000000 
[ 1456.789117] x17: 0000000000000000 x16: 0000000000000000 
[ 1456.789121] x15: 0000000000000000 x14: 0000000000000000 
[ 1456.789125] x13: 0000000000000000 x12: 0000000000000000 
[ 1456.789129] Call trace:
[ 1456.789133]  mdss_resume+0x24/0x80
[ 1456.789136]  dpm_run_callback+0x40/0x100
[ 1456.789140]  device_resume+0x9c/0x150
```
