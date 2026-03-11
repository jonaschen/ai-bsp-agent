#!/bin/bash
# ============================================================
#  collect-logs.sh
#  Normalize Android + Linux logs into a unified format
#  ready for the boot-log-analyzer orchestrator
# ============================================================
set -euo pipefail

ANDROID_LOGS="${1:-./logs/android}"
LINUX_LOGS="${2:-./logs/linux}"
OUTPUT_DIR="${3:-./logs/normalized}"

CYAN='\033[0;36m'; GREEN='\033[0;32m'; BOLD='\033[1m'; NC='\033[0m'

log() { echo -e "${CYAN}[COLLECT]${NC} $*"; }
ok()  { echo -e "${GREEN}[OK]${NC}     $*"; }

mkdir -p "$OUTPUT_DIR"/{android,linux,combined}
shopt -s nullglob   # prevent literal glob strings when directories are empty

# ── Android: merge logcat + dmesg per scenario ────────────────
normalize_android() {
  local scenario="$1"
  local src="$ANDROID_LOGS/$scenario"
  local dst="$OUTPUT_DIR/android/${scenario}.log"

  [[ -d "$src" ]] || return

  log "Normalizing Android/$scenario..."

  {
    echo "================================================================"
    echo "  Android Boot Log — Scenario: $scenario"
    echo "  Generated: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "================================================================"
    echo ""

    # Kernel section
    echo "-------- KERNEL DMESG --------"
    for f in "$src"/dmesg_*.txt; do
      [[ -f "$f" ]] && cat "$f"
    done

    echo ""
    echo "-------- LOGCAT (ALL BUFFERS) --------"
    for f in "$src"/logcat_*.txt; do
      [[ -f "$f" ]] && cat "$f"
    done

    echo ""
    echo "-------- BOOT EVENTS --------"
    for f in "$src"/boot_events_*.txt; do
      [[ -f "$f" ]] && cat "$f"
    done

    echo ""
    echo "-------- SELINUX / AVC --------"
    for f in "$src"/selinux_*.txt; do
      [[ -f "$f" ]] && cat "$f"
    done

    echo ""
    echo "-------- LAST KMSG (PREVIOUS BOOT) --------"
    for f in "$src"/last_kmsg_*.txt; do
      [[ -f "$f" ]] && cat "$f"
    done

  } > "$dst"

  ok "Android/$scenario → $dst ($(wc -l < "$dst") lines)"
}

# ── Linux: merge QEMU serial logs per scenario ───────────────
normalize_linux() {
  local scenario="$1"
  local src="$LINUX_LOGS/$scenario"
  local dst="$OUTPUT_DIR/linux/${scenario}.log"

  [[ -d "$src" ]] || return

  log "Normalizing Linux/$scenario..."

  {
    echo "================================================================"
    echo "  Linux Boot Log — Scenario: $scenario"
    echo "  Generated: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "================================================================"
    echo ""

    for f in "$src"/*.log; do
      [[ -f "$f" ]] || continue
      echo "-------- $(basename "$f") --------"
      cat "$f"
      echo ""
    done

  } > "$dst"

  ok "Linux/$scenario → $dst ($(wc -l < "$dst") lines)"
}

# ── Combine into a single mega-log (for full analysis) ────────
combine_all() {
  local combined="$OUTPUT_DIR/combined/full_boot_log.log"

  log "Creating combined log..."

  {
    echo "================================================================"
    echo "  COMBINED BOOT LOG — Android + Linux"
    echo "  All scenarios: normal, slow, selinux/audit, panic"
    echo "  Generated: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "================================================================"
    echo ""

    for f in "$OUTPUT_DIR/android"/*.log "$OUTPUT_DIR/linux"/*.log; do
      [[ -f "$f" ]] || continue
      echo ""
      echo "######## $(basename "$f") ########"
      echo ""
      cat "$f"
    done
  } > "$combined"

  ok "Combined log → $combined ($(wc -l < "$combined") lines)"
}

# ── Generate index file ───────────────────────────────────────
generate_index() {
  local index="$OUTPUT_DIR/INDEX.md"
  {
    echo "# Boot Log Collection Index"
    echo ""
    echo "Generated: $(date '+%Y-%m-%d %H:%M:%S')"
    echo ""
    echo "## Files"
    echo ""
    find "$OUTPUT_DIR" -name "*.log" | sort | while read -r f; do
      local lines
      lines=$(wc -l < "$f")
      local rel="${f#$OUTPUT_DIR/}"
      echo "- \`$rel\` — $lines lines"
    done
    echo ""
    echo "## Usage with Orchestrator"
    echo ""
    echo '```bash'
    echo "# Analyze a specific scenario"
    echo "./orchestrator.sh $OUTPUT_DIR/android/normal.log"
    echo ""
    echo "# Analyze the full combined log"
    echo "./orchestrator.sh $OUTPUT_DIR/combined/full_boot_log.log"
    echo ""
    echo "# Feed directly to the BSP diagnostic agent"
    echo "python cli.py --dmesg $OUTPUT_DIR/linux/panic.log"
    echo '```'
  } > "$index"

  ok "Index → $index"
}

# ── Main ─────────────────────────────────────────────────────
main() {
  echo -e "\n${BOLD}╔══════════════════════════════════════════════╗${NC}"
  echo -e "${BOLD}║  Boot Log Collector & Normalizer            ║${NC}"
  echo -e "${BOLD}╚══════════════════════════════════════════════╝${NC}\n"

  # Android scenarios
  for scenario in normal selinux slow panic; do
    normalize_android "$scenario"
  done

  # Linux scenarios
  for scenario in normal slow panic audit; do
    normalize_linux "$scenario"
  done

  combine_all
  generate_index

  echo -e "\n${BOLD}╔══════════════════════════════════════════════╗${NC}"
  echo -e "${BOLD}║  Collection complete!                        ║${NC}"
  echo -e "${BOLD}╚══════════════════════════════════════════════╝${NC}\n"
  cat "$OUTPUT_DIR/INDEX.md"
}

main "$@"
