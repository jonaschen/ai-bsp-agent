#!/bin/bash
# ============================================================
#  run-android-emulator.sh
#  Boot Android AVD and capture logs across multiple scenarios
#  Scenarios: normal boot, slow boot, SELinux denials, panic
# ============================================================
set -euo pipefail

ANDROID_SDK="${ANDROID_SDK_ROOT:-$HOME/android-sdk}"
AVD_NAME="${AVD_NAME:-boot_log_avd}"
OUTPUT_DIR="${1:-./logs/android}"
CYCLES="${2:-3}"           # number of boot cycles per scenario

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

log()  { echo -e "${CYAN}[ANDROID]${NC} $*"; }
ok()   { echo -e "${GREEN}[OK]${NC}     $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}   $*"; }

EMULATOR="$ANDROID_SDK/emulator/emulator"
ADB="$ANDROID_SDK/platform-tools/adb"

mkdir -p "$OUTPUT_DIR"/{normal,selinux,slow,panic}

# ── Wait for boot complete ────────────────────────────────────
wait_for_boot() {
  local timeout="${1:-180}"
  local elapsed=0
  log "Waiting for boot complete (timeout: ${timeout}s)..."
  while [[ $elapsed -lt $timeout ]]; do
    local prop
    prop=$("$ADB" shell getprop sys.boot_completed 2>/dev/null || echo "0")
    [[ "$prop" == "1" ]] && { ok "Boot complete!"; return 0; }
    sleep 3
    elapsed=$((elapsed + 3))
    echo -n "."
  done
  echo ""
  warn "Boot timed out after ${timeout}s"
  return 1
}

# ── Kill running emulator ─────────────────────────────────────
kill_emulator() {
  "$ADB" emu kill 2>/dev/null || true
  sleep 3
  pkill -f "emulator.*$AVD_NAME" 2>/dev/null || true
  sleep 2
}

# ── Capture all logs from running device ─────────────────────
capture_logs() {
  local out_dir="$1"
  local label="$2"
  local ts
  ts=$(date '+%Y%m%d_%H%M%S')

  log "Capturing logs → $out_dir ($label)"

  # 1. Full logcat (all buffers)
  "$ADB" logcat -d -b all > "$out_dir/logcat_${label}_${ts}.txt" 2>/dev/null || true

  # 2. kernel dmesg
  "$ADB" shell dmesg > "$out_dir/dmesg_${label}_${ts}.txt" 2>/dev/null || true

  # 3. Last kmsg (previous boot, if available)
  "$ADB" shell cat /proc/last_kmsg > "$out_dir/last_kmsg_${label}_${ts}.txt" 2>/dev/null || true

  # 4. Boot events (timing)
  "$ADB" shell logcat -d -b events | grep -E "boot_|am_|wm_" \
    > "$out_dir/boot_events_${label}_${ts}.txt" 2>/dev/null || true

  # 5. System properties snapshot
  "$ADB" shell getprop > "$out_dir/getprop_${label}_${ts}.txt" 2>/dev/null || true

  # 6. SELinux audit log
  "$ADB" shell dmesg | grep -i "avc\|selinux\|denied" \
    > "$out_dir/selinux_${label}_${ts}.txt" 2>/dev/null || true

  ok "Logs saved to $out_dir"
}

# ── Inject artificial delay (simulate slow driver init) ───────
inject_slow_boot_simulation() {
  # After boot, we can't redo boot, but we can modify AVD config
  # to simulate slow boot on next cycle via low RAM settings
  local avd_config="$HOME/.android/avd/${AVD_NAME}.avd/config.ini"
  if [[ -f "$avd_config" ]]; then
    # Restrict RAM to force swapping and slow boot
    sed -i 's/hw.ramSize=.*/hw.ramSize=1024/' "$avd_config" 2>/dev/null || true
    warn "AVD RAM limited to 1024MB to simulate slow boot"
  fi
}

restore_avd_config() {
  local avd_config="$HOME/.android/avd/${AVD_NAME}.avd/config.ini"
  if [[ -f "$avd_config" ]]; then
    sed -i 's/hw.ramSize=.*/hw.ramSize=2048/' "$avd_config" 2>/dev/null || true
  fi
}

# ── Trigger SELinux denials ───────────────────────────────────
trigger_selinux_denials() {
  log "Triggering SELinux denial scenarios..."

  # Access protected paths from a shell context that lacks the required
  # SELinux domain — each attempt generates an AVC denial in dmesg.
  "$ADB" shell "su 0 cat /data/system/packages.xml"       2>/dev/null || true
  "$ADB" shell "su 0 ls /proc/1/fd"                        2>/dev/null || true
  "$ADB" shell "su 0 cat /sys/kernel/debug/tracing/trace"  2>/dev/null || true
  "$ADB" shell "su 0 cat /proc/kmsg"                       2>/dev/null || true
  "$ADB" shell "su 0 ls /data/data"                        2>/dev/null || true
  "$ADB" shell "su 0 cat /dev/kmem"                        2>/dev/null || true

  sleep 5
  ok "SELinux denial triggers sent"
}

# ── Trigger kernel panic (via sysrq) — captured in last_kmsg ──
trigger_kernel_panic() {
  warn "Triggering kernel panic (device will reboot)..."
  # Enable sysrq
  "$ADB" shell "su 0 echo 1 > /proc/sys/kernel/sysrq" 2>/dev/null || true
  # Trigger panic — device will crash and reboot
  "$ADB" shell "su 0 echo c > /proc/sysrq-trigger" 2>/dev/null || true

  log "Waiting for device to reboot after panic..."
  sleep 20
  "$ADB" wait-for-device
  wait_for_boot 180
  ok "Device recovered from panic"
}

# ════════════════════════════════════════════════════════════
#  SCENARIO 1: Normal Boot (multiple cycles)
# ════════════════════════════════════════════════════════════
run_normal_cycles() {
  echo -e "\n${BOLD}━━━ Scenario: Normal Boot Cycles ━━━━━━━━━━━━━━${NC}\n"

  for i in $(seq 1 "$CYCLES"); do
    log "Normal boot cycle $i / $CYCLES"
    kill_emulator

    "$EMULATOR" \
      -avd "$AVD_NAME" \
      -no-window \
      -no-audio \
      -no-snapshot \
      -wipe-data \
      -gpu swiftshader_indirect \
      -logcat-output "$OUTPUT_DIR/normal/emulator_log_cycle${i}.txt" \
      &

    sleep 10
    "$ADB" wait-for-device

    if wait_for_boot 180; then
      capture_logs "$OUTPUT_DIR/normal" "cycle${i}"
    else
      warn "Cycle $i boot timed out, capturing partial logs"
      capture_logs "$OUTPUT_DIR/normal" "cycle${i}_partial"
    fi

    kill_emulator
    log "Cycle $i done. Sleeping 5s..."
    sleep 5
  done
}

# ════════════════════════════════════════════════════════════
#  SCENARIO 2: Slow Boot (RAM limited)
# ════════════════════════════════════════════════════════════
run_slow_boot() {
  echo -e "\n${BOLD}━━━ Scenario: Slow Boot (Low RAM) ━━━━━━━━━━━━${NC}\n"

  inject_slow_boot_simulation
  kill_emulator

  "$EMULATOR" \
    -avd "$AVD_NAME" \
    -no-window \
    -no-audio \
    -no-snapshot \
    -wipe-data \
    -gpu swiftshader_indirect \
    -memory 1024 \
    -logcat-output "$OUTPUT_DIR/slow/emulator_log_slow.txt" \
    &

  sleep 10
  "$ADB" wait-for-device

  # Use longer timeout for slow boot
  if wait_for_boot 300; then
    capture_logs "$OUTPUT_DIR/slow" "slow_boot"
  else
    capture_logs "$OUTPUT_DIR/slow" "slow_boot_timeout"
  fi

  restore_avd_config
  kill_emulator
}

# ════════════════════════════════════════════════════════════
#  SCENARIO 3: SELinux Denial Scenario
# ════════════════════════════════════════════════════════════
run_selinux_scenario() {
  echo -e "\n${BOLD}━━━ Scenario: SELinux Denials ━━━━━━━━━━━━━━━━${NC}\n"

  kill_emulator

  "$EMULATOR" \
    -avd "$AVD_NAME" \
    -no-window \
    -no-audio \
    -no-snapshot \
    -wipe-data \
    -gpu swiftshader_indirect \
    -logcat-output "$OUTPUT_DIR/selinux/emulator_log_selinux.txt" \
    &

  sleep 10
  "$ADB" wait-for-device
  wait_for_boot 180

  # Trigger SELinux denials post-boot
  trigger_selinux_denials

  # Capture logs with denial events
  capture_logs "$OUTPUT_DIR/selinux" "selinux_scenario"
  kill_emulator
}

# ════════════════════════════════════════════════════════════
#  SCENARIO 4: Kernel Panic → Recovery
# ════════════════════════════════════════════════════════════
run_panic_scenario() {
  echo -e "\n${BOLD}━━━ Scenario: Kernel Panic + Recovery ━━━━━━━━${NC}\n"
  warn "This scenario triggers a real kernel panic. The AVD will reboot."

  kill_emulator

  "$EMULATOR" \
    -avd "$AVD_NAME" \
    -no-window \
    -no-audio \
    -no-snapshot \
    -wipe-data \
    -gpu swiftshader_indirect \
    -logcat-output "$OUTPUT_DIR/panic/emulator_log_panic.txt" \
    &

  sleep 10
  "$ADB" wait-for-device
  wait_for_boot 180

  # Capture pre-panic boot log
  capture_logs "$OUTPUT_DIR/panic" "pre_panic"

  # Trigger panic
  trigger_kernel_panic

  # Capture post-reboot (last_kmsg has panic trace)
  capture_logs "$OUTPUT_DIR/panic" "post_panic"

  kill_emulator
}

# ── Main ─────────────────────────────────────────────────────
main() {
  echo -e "\n${BOLD}╔══════════════════════════════════════════════╗${NC}"
  echo -e "${BOLD}║  Android Boot Log Generator                  ║${NC}"
  echo -e "${BOLD}╚══════════════════════════════════════════════╝${NC}\n"

  log "AVD: $AVD_NAME"
  log "Output: $OUTPUT_DIR"
  log "Boot cycles: $CYCLES"

  # Check emulator available
  [[ -f "$EMULATOR" ]] || { echo "emulator not found at $EMULATOR. Run setup.sh first."; exit 1; }
  [[ -f "$ADB" ]]      || { echo "adb not found at $ADB. Run setup.sh first."; exit 1; }

  run_normal_cycles
  run_slow_boot
  run_selinux_scenario
  run_panic_scenario

  echo -e "\n${BOLD}╔══════════════════════════════════════════════╗${NC}"
  echo -e "${BOLD}║  All Android scenarios complete!             ║${NC}"
  echo -e "${BOLD}╚══════════════════════════════════════════════╝${NC}\n"
  echo "  Logs saved to: $OUTPUT_DIR"
  echo "  Run collect-logs.sh to normalize for the orchestrator."
}

main "$@"
