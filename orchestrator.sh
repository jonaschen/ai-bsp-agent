#!/bin/bash
# ============================================================
#  Boot Log Analysis Orchestrator
#  協調多個 Claude agents 從不同角度分析開機 log
# ============================================================

set -euo pipefail

# ── 設定 ────────────────────────────────────────────────────
LOG_FILE="${1:-}"
WORK_DIR="${2:-/tmp/boot-analysis-$(date +%s)}"
MAX_ROUNDS="${3:-2}"          # 每個 agent 最多幾輪
CLAUDE_BIN="${CLAUDE_BIN:-claude}"

# 顏色輸出
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

log()  { echo -e "${CYAN}[ORCH]${NC} $*"; }
ok()   { echo -e "${GREEN}[OK]${NC}   $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()  { echo -e "${RED}[ERR]${NC}  $*" >&2; }

# ── 用法 ────────────────────────────────────────────────────
usage() {
  cat <<EOF
用法: $0 <boot_log_file> [work_dir] [max_rounds]

範例:
  $0 boot.log
  $0 /var/log/dmesg.txt /tmp/analysis 3

說明:
  Orchestrator 會啟動 5 個專門角色的 Claude agents：
    1. timing-agent    — 開機時間與效能分析
    2. error-agent     — 錯誤、警告與異常偵測
    3. driver-agent    — 驅動程式與硬體初始化
    4. service-agent   — 服務啟動順序與依賴
    5. security-agent  — 權限、SELinux、安全相關事件
  最後由 Orchestrator 整合成結論報告。
EOF
  exit 1
}

[[ -z "$LOG_FILE" ]] && usage
[[ ! -f "$LOG_FILE" ]] && { err "找不到 log 檔案: $LOG_FILE"; exit 1; }

# ── 初始化工作目錄 ───────────────────────────────────────────
mkdir -p "$WORK_DIR"/{agents,rounds,final}
LOG_ABSPATH="$(realpath "$LOG_FILE")"
SUMMARY_FILE="$WORK_DIR/final/summary.md"
DISCUSSION_FILE="$WORK_DIR/rounds/discussion.md"

log "工作目錄: $WORK_DIR"
log "分析目標: $LOG_ABSPATH"
log "最大輪數: $MAX_ROUNDS"

# ── 定義 Agents ──────────────────────────────────────────────
declare -A AGENT_ROLES=(
  [timing]="開機時間效能分析師"
  [error]="錯誤與異常偵測專家"
  [driver]="驅動程式與硬體初始化專家"
  [service]="系統服務與啟動順序分析師"
  [security]="安全性與權限稽核專家"
)

declare -A AGENT_FOCUS=(
  [timing]="專注於：各開機階段耗時（bootloader, kernel init, init, zygote, system_server, boot complete）、時間戳分析、效能瓶頸、與正常值的偏差。"
  [error]="專注於：ERROR/FATAL/WARN 訊息、kernel panic、OOM、crash、exception、ANR、watchdog timeout、硬體錯誤。"
  [driver]="專注於：驅動載入成功/失敗、硬體探測（probe）結果、firmware 載入、I2C/SPI/GPIO 初始化、感測器/顯示/音訊驅動狀態。"
  [service]="專注於：init.rc 服務啟動順序、服務依賴關係、重啟次數、property 設定時機、zygote/system_server 啟動流程。"
  [security]="專注於：SELinux denial、avc 訊息、capability 問題、ro.debuggable 狀態、verified boot 結果、加密掛載狀態。"
)

# ── 函數：呼叫單一 Agent ─────────────────────────────────────
run_agent() {
  local agent_id="$1"
  local round="$2"
  local extra_context="${3:-}"

  local role="${AGENT_ROLES[$agent_id]}"
  local focus="${AGENT_FOCUS[$agent_id]}"
  local output_file="$WORK_DIR/agents/${agent_id}_round${round}.md"
  local prev_file="$WORK_DIR/agents/${agent_id}_round$((round-1)).md"

  log "呼叫 Agent [${agent_id}] Round ${round}..."

  # 建構 prompt
  local prev_analysis=""
  if [[ $round -gt 1 && -f "$prev_file" ]]; then
    prev_analysis="

【你上一輪的分析】
$(cat "$prev_file")

【其他 agents 在上一輪的發現】
$extra_context

請根據上述資訊，深化你的分析，補充新發現，或修正先前的判斷。"
  fi

  local prompt="你是一位 Android/Linux 開機分析專家，角色定位：${role}。

${focus}

請分析以下開機 log 檔案：${LOG_ABSPATH}

輸出格式（Markdown）：
## [${role}] Round ${round} 分析

### 關鍵發現
- （條列最重要的 3~5 點）

### 詳細分析
（依時間順序或嚴重度說明）

### 疑慮與待確認項目
（列出需要其他角度確認的問題）

### 對其他 agents 的提問
（針對你觀察到但超出你專業範疇的現象，提出具體問題）
${prev_analysis}"

  # 執行 claude
  if $CLAUDE_BIN --print "$prompt" > "$output_file" 2>/dev/null; then
    ok "Agent [${agent_id}] Round ${round} 完成 → $output_file"
  else
    warn "Agent [${agent_id}] 執行失敗，建立空白輸出"
    printf "## [%s] Round %s 分析\n\n（執行失敗）\n" "${role}" "${round}" > "$output_file"
  fi

  cat "$output_file"
}

# ── 函數：彙整討論內容 ───────────────────────────────────────
compile_discussion() {
  local round="$1"
  local round_file="$WORK_DIR/rounds/round${round}.md"

  echo "# Round ${round} 討論彙整" > "$round_file"
  echo "" >> "$round_file"

  for agent_id in "${!AGENT_ROLES[@]}"; do
    local output_file="$WORK_DIR/agents/${agent_id}_round${round}.md"
    if [[ -f "$output_file" ]]; then
      cat "$output_file" >> "$round_file"
      echo -e "\n---\n" >> "$round_file"
    fi
  done

  echo "$round_file"
}

# ── 函數：產生最終結論 ───────────────────────────────────────
generate_final_report() {
  log "產生最終整合報告..."

  local all_analyses=""
  for round_file in "$WORK_DIR/rounds"/round*.md; do
    [[ -f "$round_file" ]] && all_analyses+="$(cat "$round_file")"$'\n\n'
  done

  local prompt="你是資深 Android/Linux 開機問題診斷工程師。

以下是多位專家從不同角度對開機 log（${LOG_ABSPATH}）的分析結果：

${all_analyses}

請整合所有分析，產出最終診斷報告，格式如下：

# 開機 Log 診斷報告
**分析時間**: $(date '+%Y-%m-%d %H:%M:%S')
**Log 檔案**: ${LOG_ABSPATH}

## 執行摘要
（2~3 句話說明開機狀況整體評估）

## 開機時間總覽
| 階段 | 時間戳 | 耗時 | 狀態 |
|------|--------|------|------|
（填入各階段資料）

## 嚴重問題（須立即處理）
（列出 P0/P1 等級問題，附上 log 行號或關鍵訊息）

## 警告事項（建議改善）
（列出 P2 等級問題）

## 驅動與硬體狀態
（逐項列出各硬體初始化狀態）

## 服務啟動狀態
（關鍵服務是否正常啟動）

## 安全性稽核結果
（SELinux、verified boot 等）

## 根本原因分析
（如有異常，推斷可能的根本原因）

## 建議行動
1. （優先順序排列的建議）

## 各專家觀點差異
（如果不同角度的分析有衝突或互補，在此說明）"

  $CLAUDE_BIN --print "$prompt" > "$SUMMARY_FILE" 2>/dev/null || {
    warn "最終報告產生失敗，改用彙整版本"
    cp "$WORK_DIR/rounds/round${MAX_ROUNDS}.md" "$SUMMARY_FILE"
  }

  ok "最終報告: $SUMMARY_FILE"
}

# ── 主流程 ───────────────────────────────────────────────────
main() {
  echo -e "\n${BOLD}╔══════════════════════════════════════════╗${NC}"
  echo -e "${BOLD}║   Boot Log Analysis Orchestrator         ║${NC}"
  echo -e "${BOLD}╚══════════════════════════════════════════╝${NC}\n"

  # Phase 1: 快速預處理（取得 log 基本資訊）
  log "Phase 1: 預處理 log 檔案..."
  local log_stats
  log_stats=$(wc -l < "$LOG_FILE") || true
  log "Log 行數: ${log_stats:-未知}"

  # Phase 2: 多輪討論
  for round in $(seq 1 "$MAX_ROUNDS"); do
    echo -e "\n${BOLD}━━━ Round ${round} / ${MAX_ROUNDS} ━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

    # 取得上一輪的跨 agent 摘要
    local cross_context=""
    if [[ $round -gt 1 ]]; then
      local prev_round_file="$WORK_DIR/rounds/round$((round-1)).md"
      [[ -f "$prev_round_file" ]] && cross_context=$(cat "$prev_round_file")
    fi

    # 平行（或序列）執行所有 agents
    # 注意：Claude Code CLI 通常不支援真正平行，這裡用序列
    for agent_id in timing error driver service security; do
      run_agent "$agent_id" "$round" "$cross_context"
      echo ""
    done

    # 彙整本輪討論
    compile_discussion "$round"
    log "Round ${round} 彙整完成"
  done

  # Phase 3: 整合最終報告
  echo -e "\n${BOLD}━━━ 產生最終報告 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
  generate_final_report

  # Phase 4: 輸出結果
  echo -e "\n${BOLD}╔══════════════════════════════════════════╗${NC}"
  echo -e "${BOLD}║   分析完成！                              ║${NC}"
  echo -e "${BOLD}╚══════════════════════════════════════════╝${NC}"
  echo ""
  echo -e "📁 工作目錄   : ${WORK_DIR}"
  echo -e "📄 最終報告   : ${SUMMARY_FILE}"
  echo -e "📊 各輪討論   : ${WORK_DIR}/rounds/"
  echo -e "🤖 各 Agent   : ${WORK_DIR}/agents/"
  echo ""
  echo -e "${GREEN}查看報告：${NC}"
  echo "  cat $SUMMARY_FILE"
  echo "  # 或"
  echo "  less $SUMMARY_FILE"
}

main "$@"
