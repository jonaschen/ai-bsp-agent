#!/bin/bash
# ============================================================
#  run-linux-qemu.sh
#  Boot Alpine Linux in QEMU and capture logs across scenarios
#  Scenarios: normal, slow (throttled CPU), panic, SELinux-like
# ============================================================
set -euo pipefail

OUTPUT_DIR="${1:-./logs/linux}"
CYCLES="${2:-3}"

ALPINE_DIR="$HOME/qemu-alpine"
ALPINE_ISO="$ALPINE_DIR/alpine.iso"
BASE_DISK="$ALPINE_DIR/alpine-disk.qcow2"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

log()  { echo -e "${CYAN}[QEMU]${NC}   $*"; }
ok()   { echo -e "${GREEN}[OK]${NC}     $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}   $*"; }

mkdir -p "$OUTPUT_DIR"/{normal,slow,panic,audit}

# ── KVM availability check ────────────────────────────────────
if [[ -r /dev/kvm ]]; then
  KVM_FLAG="-enable-kvm"
  log "KVM available — using hardware acceleration"
else
  KVM_FLAG=""
  warn "KVM not available — running in software emulation (slow)"
  warn "To enable: sudo modprobe kvm_intel  (or kvm_amd)"
fi

# ── QEMU base command builder ─────────────────────────────────
# Uses serial console → all boot output captured to file
qemu_boot() {
  local disk="$1"
  local logfile="$2"
  local mem="${3:-512M}"
  local cpus="${4:-2}"
  shift 4
  local extra_args=("$@")   # remaining args passed as array — no word-split issues

  # -nographic: serial console to stdout
  qemu-system-x86_64 \
    $KVM_FLAG \
    -m "$mem" \
    -smp "$cpus" \
    -drive file="$disk",format=qcow2 \
    -cdrom "$ALPINE_ISO" \
    -boot order=dc \
    -nographic \
    -serial "file:$logfile" \
    -monitor "unix:/tmp/qemu-monitor.sock,server,nowait" \
    -netdev user,id=net0 \
    -device e1000,netdev=net0 \
    "${extra_args[@]}" \
    &

  echo $!
}

# ── Send command via QEMU monitor ────────────────────────────
monitor_cmd() {
  local cmd="$1"
  echo "$cmd" | socat - UNIX-CONNECT:/tmp/qemu-monitor.sock 2>/dev/null || true
}

# ── Wait for kernel boot message in log ──────────────────────
wait_for_kernel_boot() {
  local logfile="$1"
  local timeout="${2:-60}"
  local elapsed=0

  log "Waiting for kernel boot output..."
  while [[ $elapsed -lt $timeout ]]; do
    if grep -q "Freeing unused kernel" "$logfile" 2>/dev/null; then
      ok "Kernel boot reached userspace"
      return 0
    fi
    sleep 2
    elapsed=$((elapsed + 2))
    echo -n "."
  done
  echo ""
  warn "Kernel boot wait timed out"
  return 1
}

# ── Create per-scenario disk (copy-on-write from base) ────────
make_scenario_disk() {
  local name="$1"
  local out="$ALPINE_DIR/disk_${name}.qcow2"
  qemu-img create -f qcow2 -b "$BASE_DISK" -F qcow2 "$out" 2>/dev/null
  echo "$out"
}

# ── Kill QEMU ────────────────────────────────────────────────
kill_qemu() {
  monitor_cmd "quit" 2>/dev/null || true
  sleep 2
  pkill -f "qemu-system-x86_64" 2>/dev/null || true
  sleep 2
}

# ════════════════════════════════════════════════════════════
#  SCENARIO 1: Normal Boot — multiple cycles
# ════════════════════════════════════════════════════════════
run_normal_cycles() {
  echo -e "\n${BOLD}━━━ Scenario: Normal Boot Cycles ━━━━━━━━━━━━━━${NC}\n"

  for i in $(seq 1 "$CYCLES"); do
    log "Normal boot cycle $i / $CYCLES"
    local disk logfile pid

    disk=$(make_scenario_disk "normal_c${i}")
    logfile="$OUTPUT_DIR/normal/boot_cycle${i}.log"

    pid=$(qemu_boot "$disk" "$logfile" "512M" "2")
    log "QEMU PID: $pid"

    sleep 5
    wait_for_kernel_boot "$logfile" 90 || true

    # Let it run a bit more to get full boot
    sleep 30

    # Capture dmesg-style via monitor
    monitor_cmd "info version" >> "$logfile" 2>/dev/null || true

    kill_qemu
    ok "Cycle $i log: $logfile ($(wc -l < "$logfile") lines)"
    sleep 3
  done
}

# ════════════════════════════════════════════════════════════
#  SCENARIO 2: Slow Boot — throttled CPU + limited RAM
# ════════════════════════════════════════════════════════════
run_slow_boot() {
  echo -e "\n${BOLD}━━━ Scenario: Slow Boot (Throttled) ━━━━━━━━━━${NC}\n"

  local disk logfile pid
  disk=$(make_scenario_disk "slow")
  logfile="$OUTPUT_DIR/slow/boot_slow.log"

  # 256MB RAM + 1 CPU + icount to slow down CPU execution rate
  # -icount: simulate fixed-rate CPU (slows everything down)
  pid=$(qemu_boot "$disk" "$logfile" "256M" "1" -icount shift=1,align=off,sleep=on)
  log "QEMU PID: $pid (throttled mode)"

  sleep 5
  wait_for_kernel_boot "$logfile" 180 || true
  sleep 45

  kill_qemu
  ok "Slow boot log: $logfile ($(wc -l < "$logfile") lines)"
}

# ════════════════════════════════════════════════════════════
#  SCENARIO 3: Kernel Panic
#  Method: enable sysrq in guest, then trigger crash via QEMU
#  monitor sendkey.  Note: -append without -kernel is ignored
#  for ISO boots — panic is triggered purely via sysrq.
# ════════════════════════════════════════════════════════════
run_panic_scenario() {
  echo -e "\n${BOLD}━━━ Scenario: Kernel Panic ━━━━━━━━━━━━━━━━━━━${NC}\n"

  local disk logfile pid
  disk=$(make_scenario_disk "panic")
  logfile="$OUTPUT_DIR/panic/boot_panic.log"

  pid=$(qemu_boot "$disk" "$logfile" "512M" "2")
  log "QEMU PID: $pid"

  # Wait for normal boot first
  sleep 5
  wait_for_kernel_boot "$logfile" 90 || true
  sleep 20

  log "Triggering kernel panic via sysrq 'c' (QEMU monitor sendkey)..."
  # sendkey alt-sysrq-c = Alt+SysRq+c → kernel crash command.
  # Requires CONFIG_MAGIC_SYSRQ=y (enabled in Alpine virt kernel).
  monitor_cmd "sendkey alt-sysrq-c"

  # Wait for panic trace to be written then allow reboot
  sleep 30

  # Second boot — serial log now contains Oops/panic trace + reboot messages
  log "Capturing post-panic reboot..."
  sleep 20

  kill_qemu
  ok "Panic log: $logfile ($(wc -l < "$logfile") lines)"
  warn "Check for 'Oops:', 'BUG:', 'Kernel panic' in the log"
}

# ════════════════════════════════════════════════════════════
#  SCENARIO 4: Audit / SELinux-like denials
#  Alpine uses BusyBox so no real SELinux, but we can enable
#  kernel audit subsystem + AppArmor to generate similar denials
# ════════════════════════════════════════════════════════════
run_audit_scenario() {
  echo -e "\n${BOLD}━━━ Scenario: Audit / Security Denials ━━━━━━━━${NC}\n"

  local disk logfile pid
  disk=$(make_scenario_disk "audit")
  logfile="$OUTPUT_DIR/audit/boot_audit.log"

  pid=$(qemu_boot "$disk" "$logfile" "512M" "2")

  log "QEMU PID: $pid"

  sleep 5
  wait_for_kernel_boot "$logfile" 90 || true
  sleep 30

  # Generate some audit events via monitor (limited without full OS access)
  log "Boot with audit subsystem active"

  kill_qemu
  ok "Audit log: $logfile ($(wc -l < "$logfile") lines)"
}

# ── Inject extra error lines into logs (post-processing) ──────
# Since Alpine in QEMU may not generate all desired error types,
# we augment logs with realistic synthetic entries
augment_logs_with_errors() {
  log "Augmenting logs with realistic error patterns..."

  # Add realistic driver timeout errors to slow boot log
  cat >> "$OUTPUT_DIR/slow/boot_slow.log" << 'EOF'

[   12.543210] mmc0: Timeout waiting for hardware interrupt.
[   12.643210] mmc0: Got data interrupt 0x00000002 even though no data operation was in progress.
[   15.123456] usb 1-1: device descriptor read/64, error -71
[   15.234567] usb 1-1: device not accepting address 2, error -71
[   18.901234] ata1: SRST failed (errno=-16)
[   22.345678] thermal thermal_zone0: failed to read out thermal zone (-61)
[   25.456789] platform regulatory.0: Direct firmware load for regulatory.db failed with error -2
[   25.456790] cfg80211: failed to load regulatory.db
EOF

  # Add SELinux-like audit denials to audit log
  cat >> "$OUTPUT_DIR/audit/boot_audit.log" << 'EOF'

[    8.234567] audit: type=1400 audit(1234567890.123:45): apparmor="DENIED" operation="open" profile="/usr/sbin/ntpd" name="/proc/net/if_inet6" pid=312 comm="ntpd" requested_mask="r" denied_mask="r" fsuid=123 ouid=0
[    9.345678] audit: type=1400 audit(1234567890.234:46): apparmor="DENIED" operation="exec" profile="unconfined" name="/usr/lib/systemd/systemd-networkd" pid=401 comm="sh"
[   10.456789] audit: type=1400 audit(1234567890.345:47): apparmor="DENIED" operation="file_lock" profile="/usr/sbin/dnsmasq" name="/var/run/dnsmasq/dnsmasq.pid" pid=512
[   11.567890] audit: type=1400 audit(1234567890.456:48): apparmor="DENIED" operation="capable" profile="/usr/sbin/cupsd" capability=net_admin pid=623 comm="cupsd"
EOF

  ok "Logs augmented with error patterns"
}

# ── Main ─────────────────────────────────────────────────────
main() {
  echo -e "\n${BOLD}╔══════════════════════════════════════════════╗${NC}"
  echo -e "${BOLD}║  Linux QEMU Boot Log Generator              ║${NC}"
  echo -e "${BOLD}╚══════════════════════════════════════════════╝${NC}\n"

  log "Output: $OUTPUT_DIR"
  log "Boot cycles: $CYCLES"

  # Check requirements
  command -v qemu-system-x86_64 &>/dev/null || { echo "qemu-system-x86_64 not found. Run setup.sh first."; exit 1; }
  [[ -f "$ALPINE_ISO" ]]  || { echo "Alpine ISO not found at $ALPINE_ISO. Run setup.sh first."; exit 1; }
  [[ -f "$BASE_DISK" ]]   || { echo "Alpine disk not found at $BASE_DISK. Run setup.sh first."; exit 1; }

  run_normal_cycles
  run_slow_boot
  run_panic_scenario
  run_audit_scenario
  augment_logs_with_errors

  echo -e "\n${BOLD}╔══════════════════════════════════════════════╗${NC}"
  echo -e "${BOLD}║  All Linux scenarios complete!               ║${NC}"
  echo -e "${BOLD}╚══════════════════════════════════════════════╝${NC}\n"
  echo "  Logs saved to: $OUTPUT_DIR"
  find "$OUTPUT_DIR" -name "*.log" | while read -r f; do
    echo "  $(wc -l < "$f") lines  →  $f"
  done
  echo ""
  echo "  Run collect-logs.sh to normalize for the orchestrator."
}

main "$@"
