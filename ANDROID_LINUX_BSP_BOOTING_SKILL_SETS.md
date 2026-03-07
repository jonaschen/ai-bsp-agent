# Android/Linux BSP Booting Troubleshooting Skill Sets for AI Agents

**Version:** 2.0
**Architecture Focus:** AArch64 / ARMv8+
**Objective:** 定義 AI Agent 解決 Boot Fail 的標準化技能集，並規範 Supervisor Agent 的路由策略，確保底層基礎設施的安全與解耦。

---

## 0. Supervisor Routing Context (任務路由矩陣)
Supervisor Agent 負責初步接收 Boot Fail 報告，並根據初步特徵將任務路由給特定的「專家技能執行緒」或「次級 Agent」。

* **Route A: Triage & Log Extraction (分流與日誌萃取)**
  * **Trigger:** 收到一段未經處理的 UART/串列埠輸出。
  * **Action:** 呼叫 `[Stateless Log Parsing Skills]`，識別死機點（BootROM, LK, Kernel, Init）。
* **Route B: Memory & Exception Analysis (記憶體與異常分析)**
  * **Trigger:** Log 中出現 `Synchronous Abort`, `Bad mode`, `Out of memory` 等關鍵字。
  * **Action:** 呼叫 Exception Decoder 與 Toolchain Skills 進行 Call Trace 還原。
* **Route C: Subsystem Diagnostics (子系統診斷)**
  * **Trigger:** Kernel 啟動中途卡死，或特定 subsystem (VFS, Clock, Firmware) 報錯。
  * **Action:** 呼叫 `[Subsystem Specific Diagnostics]` 進行針對性排查。
* **Route D: Workspace Audit (環境與組態稽核)**
  * **Trigger:** 懷疑是近期 Commit、DTS 變更或編譯環境造成的 Regression。
  * **Action:** 呼叫 `[Stateful Workspace & Toolchain Skills]` 比對歷史組態。

---

## 1. Stateless Log Parsing Skills (無狀態日誌解析技能)
*基礎設施要求：純文字處理，不需掛載源碼或 Toolchain。*

* **`parse_early_boot_uart_log`** (替換原 Image Signature 檢查)
  * **Input:** `raw_uart_log` (string)
  * **Output:** Boot stage (BootROM/TF-A/LK), Last successful init step, First error string.
  * **Description:** 解析極早期的 UART log，識別 Secure Boot 階段的錯誤碼或 BL1/BL2 載入失敗的特徵。
* **`analyze_lk_panic`**
  * **Input:** `uart_log_snippet` (string)
  * **Output:** Failing function, Register dump (if available), Assert messages.
  * **Description:** 專注解析 Little Kernel (LK) 或 U-Boot 階段的 Assert 格式與暫存器狀態。
* **`extract_kernel_oops_log`** (純 Log 版 Oops 處理)
  * **Input:** `dmesg_text` (string)
  * **Output:** Hexadecimal Call Trace, PC/LR register values, Faulting module name.
  * **Description:** 從混雜的 dmesg 中乾淨地萃取出 OOPS 區塊，不進行符號解析。
* **`decode_aarch64_exception`**
  * **Input:** `esr_val` (hex string), `far_val` (hex string), `el_level` (int)
  * **Output:** Exception class (e.g., Data Abort, Instruction Abort), Translation fault details.
  * **Description:** 根據 ARMv8/v9 架構手冊規則，靜態解碼 ESR 與 FAR 暫存器。

---

## 2. Stateful Workspace & Toolchain Skills (有狀態環境與工具鏈技能)
*基礎設施要求：需掛載 Source Tree、Out 目錄 (vmlinux)、Cross-compiler (addr2line, objdump) 與檔案系統權限。*

* **`resolve_oops_symbols`** (Toolchain 依賴版 Oops 處理)
  * **Input:** `hex_call_trace` (string), `vmlinux_path` (string)
  * **Output:** Human-readable call trace with file names and line numbers.
  * **Description:** 呼叫 `aarch64-linux-gnu-addr2line` 等工具，將十六進位位址轉換為具體的源碼行號。
* **`compare_device_tree_nodes`**
  * **Input:** `dts_a_path` (string), `dts_b_path` (string), `target_node` (string)
  * **Output:** Property differences, Pinctrl changes, Memory map diff.
  * **Description:** 靜態解析並比對 DTS 檔案間的具體節點差異。
* **`diff_kernel_configs`**
  * **Input:** `config_good_path` (string), `config_bad_path` (string)
  * **Output:** Added/Removed/Changed `CONFIG_*` flags.
  * **Description:** 比較不同編譯組態下的 `.config` 差異。

---

## 3. Subsystem Specific Diagnostics (特定子系統診斷技能)
*針對常見的 Boot 阻礙點提供的專用除錯邏輯。*

* **`check_clock_dependencies`** (新增: Clock Init)
  * **Input:** `clk_dump_log` (string) OR `dts_path` (string)
  * **Output:** Unresolved clock parents, Orphan clocks, Invalid PLL configurations.
  * **Description:** 分析 CCF (Common Clock Framework) 的初始化狀態，檢查是否有驅動程式因為拿不到 Clock 導致 probe defer 或死鎖。
* **`diagnose_vfs_mount_failure`** (新增: Mount Failures)
  * **Input:** `fstab_path` (string), `dmesg_snippet` (string)
  * **Output:** Missing block devices, Unsupported filesystems, Timing issues (e.g., waiting for root device).
  * **Description:** 針對 VFS kernel panic (`Unable to mount root fs`)，排查是 eMMC/UFS 驅動未載入，還是 fstab 參數錯誤。
* **`analyze_firmware_load_error`** (新增: Firmware Load)
  * **Input:** `dmesg_snippet` (string), `sysfs_firmware_path` (string)
  * **Output:** Missing firmware binaries, Path mismatch, Timeout errors.
  * **Description:** 分析 `Direct firmware load for xxx failed` 錯誤，確認是 rootfs 尚未就緒，還是二進位檔確實遺失。
* **`analyze_early_oom_killer`** (新增: OOM at Boot)
  * **Input:** `dmesg_memory_layout` (string), `dts_reserved_memory` (string)
  * **Output:** Exhausted memory zones, Excessive reserved memory overlaps, Slab leak indicators.
  * **Description:** 分析 Kernel 早期的 Memory Layout 輸出，比對 DTS 的 `reserved-memory` 節點，找出導致啟動初期就觸發 OOM 的記憶體配置不當。
* **`analyze_selinux_denial`**
  * **Input:** `avc_denied_log` (string)
  * **Output:** Missing permission rules (allow statements), Source/Target contexts.
  * **Description:** 解析 user-space bringup 階段的權限阻擋。

---

## 4. Knowledge Retrieval (知識檢索技能)
* **`query_arm_trm_database`**
  * **Description:** 對接內部 RAG 知識庫，查詢 ARM 架構手冊。
* **`check_soc_errata_tracker`**
  * **Description:** 查詢特定 IC 的硬體 Bug 清單與 Workaround。

---

## 5. Governed Action & Mutation Skills (受控操作與變更技能)
*基礎設施要求：需要 Human-in-the-Loop (HITL) 審批機制，或嚴格限制在 Sandbox/CI 環境中執行，防止破壞 Mainline 代碼或實體開發板。*

* **`generate_patch_and_build`**
  * **Input:** `target_file` (string), `modification_instructions` (string), `build_target` (string)
  * **Output:** Patch diff, Build success/fail status, Compiler warnings.
  * **Governance Rule:** 僅允許在獨立的 Git Branch 執行，且編譯前需檢查語法，編譯產出物（Image/DTB）不可自動 Flash，需等待人工確認。
  * **Description:** 根據假說自動修改代碼並進行局部編譯驗證。

---

## 6. Development Plan (實作計劃)

### Guiding Principles (開發原則)

1. **Log parsers before file system analysts.** Stateless skills (log text in → diagnosis out) can be built and tested immediately with no infrastructure changes. Stateful skills (require source tree, toolchain) need a workspace design decision first — defer them.
2. **Deliver new supervisor routes in the same phase as the skills that depend on them.** A route with no tools, or tools with no route, are both useless in isolation.
3. **Implement subsystem skills as log-only first.** A working log parser beats a blocked perfect one that waits for file access.
4. **Knowledge retrieval and governed actions are infrastructure milestones.** They require design decisions beyond a skill file — plan them as dedicated phases after the diagnostic foundation is validated on real logs.

---

### Phase 4 — Early Boot Skills (Stateless)

**New supervisor route:** `early_boot_advisor`
**Infrastructure needed:** None — add a route token to the supervisor prompt.
**Trigger for new route:** No kernel timestamp pattern (`[ X.XXXXXX]`) in the log; presence of TF-A / LK boot markers.

| Deliverable | Detail |
|---|---|
| `skills/bsp_diagnostics/early_boot.py` | `parse_early_boot_uart_log` + `analyze_lk_panic` |
| `tests/product_tests/test_early_boot_skill.py` | ~18 tests, no LLM |
| Supervisor update | Add `early_boot_advisor` token to triage prompt and `ROUTE_TOOLS` |
| `docs/early-boot-stages.md` | TF-A BL1/BL2 error codes, LK assert format, common DDR init failures |

**Prerequisite:** None. Can start immediately.

---

### Phase 5 — Kernel Exception & Oops Skills (Stateless)

**Route:** `kernel_pathologist` (existing, extended)
**Infrastructure needed:** None.

`extract_kernel_oops_log` is the stateless half of the oops pipeline — it extracts the hex call trace that Phase 8's `resolve_oops_symbols` will later symbolize. `decode_aarch64_exception` extends the existing `decode_esr_el1` skill with the FAR (Fault Address Register) field. The `el_level` input is **not** added — EL context is derived from ESR EC bits [31:26] to avoid contradictory inputs.

| Deliverable | Detail |
|---|---|
| `skills/bsp_diagnostics/kernel_oops.py` | `extract_kernel_oops_log` |
| Update `skills/bsp_diagnostics/aarch64_exceptions.py` | Add `decode_aarch64_exception(esr_val, far_val)` alongside existing `decode_esr_el1` |
| `tests/product_tests/test_kernel_oops_skill.py` | ~16 tests |
| Update `tests/product_tests/test_aarch64_exceptions.py` | ~8 new tests for FAR decoding |
| Update `docs/aarch64-exceptions.md` | Add FAR field layout and fault address interpretation |

**Prerequisite:** Phase 4 (supervisor pattern established).

---

### Phase 6 — Android Init Skills (Stateless)

**New supervisor route:** `android_init_advisor`
**Infrastructure needed:** None. Both skills accept log/file content as strings — no filesystem access required by the skill itself.

| Deliverable | Detail |
|---|---|
| `skills/bsp_diagnostics/android_init.py` | `analyze_selinux_denial` + `check_android_init_rc` |
| `tests/product_tests/test_android_init_skill.py` | ~20 tests |
| Supervisor update | Add `android_init_advisor` token and `ROUTE_TOOLS` entry |
| `docs/android-init.md` | SELinux type enforcement, init.rc service lifecycle, capability requirements |

**Prerequisite:** Phase 4 (supervisor route pattern).

---

### Phase 7 — Subsystem Diagnostics (Log-Only Variants)

**Routes:** `kernel_pathologist` (clock, OOM, VFS) and `android_init_advisor` (firmware load)
**Infrastructure needed:** None. `fstab_path` in `diagnose_vfs_mount_failure` becomes `fstab_content: str` — user provides file content as a string.

| Deliverable | Detail |
|---|---|
| `skills/bsp_diagnostics/subsystems.py` | `check_clock_dependencies`, `diagnose_vfs_mount_failure`, `analyze_firmware_load_error`, `analyze_early_oom_killer` |
| `tests/product_tests/test_subsystems_skill.py` | ~24 tests |
| Update `ROUTE_TOOLS` | Add new skills to appropriate existing routes |
| `docs/subsystem-boot.md` | CCF probe defer patterns, VFS mount error codes, firmware search paths, memory zone layout |

**Prerequisite:** Phases 5 and 6 (routes and kernel log patterns established).

---

### Phase 8 — Stateful Workspace Skills ⚠️ Infrastructure Decision Required

**New supervisor route:** `source_analyst`
**Infrastructure needed:** File path access + `addr2line` subprocess.

#### Infrastructure Decision (resolve before coding)

Stateful skills need access to files outside the log string. Three options:

| Option | Mechanism | Trade-off |
|---|---|---|
| **A — Path inputs** (recommended) | Skills accept file system paths; agent runs locally where build tree is mounted | Simple, zero server changes; local use only |
| **B — Content inputs** | Skills accept file text as strings; user pipes content | No FS access needed; impractical for vmlinux (binary) |
| **C — Workspace Agent** | New `WorkspaceAgent` manages a mounted source directory; skills request files by relative path | Cleanest architecture; new agent component required |

**Recommended start:** Option A (path inputs) for DTS/config skills. `resolve_oops_symbols` calls `aarch64-linux-gnu-addr2line` via subprocess. Option C can be added later for server deployment.

| Deliverable | Detail |
|---|---|
| `skills/bsp_diagnostics/workspace.py` | `resolve_oops_symbols`, `compare_device_tree_nodes`, `diff_kernel_configs`, `validate_gpio_pinctrl_conflict` |
| `tests/product_tests/test_workspace_skill.py` | ~20 tests — mock subprocess for `addr2line`; fixture DTS/config files in `tests/fixtures/` |
| Supervisor update | Add `source_analyst` route; trigger on regression/commit/DTS-change keywords |
| `docs/workspace-analysis.md` | DTS node naming conventions, CONFIG flag impact reference |

**Prerequisite:** Phase 5 (`extract_kernel_oops_log` produces hex trace that feeds `resolve_oops_symbols`). Infrastructure option agreed before coding starts.

---

### Phase 9 — Knowledge Retrieval (Two Sub-phases)

#### Phase 9a — SoC Errata Lookup (Static Table)

`check_soc_errata_tracker` implemented as a **Python dict lookup table** keyed by `(ip_block, soc_revision)`. Covers top SoCs (Qualcomm SM8x50, MTK MT6xxx, Samsung Exynos). No external database. Can be enriched incrementally.

| Deliverable | Detail |
|---|---|
| `skills/knowledge/errata.py` | Static lookup table + `check_soc_errata_tracker` |
| `tests/product_tests/test_errata_skill.py` | ~12 tests |

**Prerequisite:** Any completed phase. Can be parallelized.

#### Phase 9b — ARM TRM RAG (Vector Database)

`query_arm_trm_database` requires a vector database + embedding pipeline. ARM TRM PDFs need chunking, embedding, and indexing. This is the largest infrastructure investment in the roadmap.

**Prerequisite:** Phase 9a validated in real use. RAG infrastructure design document completed first.

---

### Phase 10 — Governed Actions ⚠️ HITL Mechanism Required

**Infrastructure needed:** HITL approval interface + sandbox/CI environment.

Start Phase 10 **only after** Phases 4–7 are producing reliable, high-confidence diagnostic outputs. The governed action's value is proportional to the accuracy of the preceding diagnosis — a wrong diagnosis producing a wrong patch is worse than no patch.

**Minimum HITL design before coding:**
- Skill returns a `PendingApproval` response with patch diff
- Engineer reviews diff and sends a signed confirmation
- Only then does the skill execute the build
- Build artefacts (Image/DTB) are never auto-flashed

| Deliverable | Detail |
|---|---|
| HITL design document | Approval interface specification |
| Sandbox/CI integration | Isolated Git branch management |
| `skills/actions/patch_and_build.py` | `generate_patch_and_build` with blocking approval gate |
| `tests/product_tests/test_patch_skill.py` | ~10 tests — mock subprocess, test approval blocking |

**Prerequisite:** Phases 4–7 validated on real BSP logs.

---

### Full Roadmap Summary

| Phase | Skills | New Routes | Infrastructure | Approx. New Tests |
|---|---|---|---|---|
| **4** Early Boot | `parse_early_boot_uart_log`, `analyze_lk_panic` | `early_boot_advisor` | None | ~18 |
| **5** Kernel Oops | `extract_kernel_oops_log`, `decode_aarch64_exception`+FAR | — (extends `kernel_pathologist`) | None | ~24 |
| **6** Android Init | `analyze_selinux_denial`, `check_android_init_rc` | `android_init_advisor` | None | ~20 |
| **7** Subsystems | `check_clock_dependencies`, `diagnose_vfs_mount_failure`, `analyze_firmware_load_error`, `analyze_early_oom_killer` | — (extends existing) | None | ~24 |
| **8** Workspace | `resolve_oops_symbols`, `compare_device_tree_nodes`, `diff_kernel_configs`, `validate_gpio_pinctrl_conflict` | `source_analyst` | File paths + addr2line subprocess | ~20 |
| **9a** Errata DB | `check_soc_errata_tracker` | — | Static lookup table | ~12 |
| **9b** RAG | `query_arm_trm_database` | — | Vector DB + embedding pipeline | TBD |
| **10** Actions | `generate_patch_and_build` | — | HITL mechanism + sandbox | ~10 |

**Phases 4–7:** ~86 new tests. No new infrastructure. Can proceed sequentially.
**Phase 8:** First infrastructure decision point — agree on workspace access model before coding.
**Phases 9b and 10:** Deferred until real-world validation confirms the diagnostic foundation is reliable.
