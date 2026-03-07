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
