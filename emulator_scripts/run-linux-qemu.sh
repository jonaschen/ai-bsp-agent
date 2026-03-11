#!/bin/bash
# ============================================================
#  run-linux-qemu.sh
#  Boot AArch64 targets in QEMU and capture logs across scenarios
#
#  Two target types:
#    LK (Little Kernel)  — qemu-system-aarch64 -machine virt -cpu cortex-a53
#                          Uses lk.elf built from github.com/littlekernel/lk
#                          target: qemu-virt-arm64-test
#    Alpine Linux aarch64 — qemu-system-aarch64 -machine virt -cpu cortex-a72
#                          Full Linux kernel; ISO boot via virtio-scsi
#
#  Scenarios:
#    lk-normal   — healthy LK boot to interactive shell prompt
#    lk-panic    — LK AArch64 crash (data abort via built-in 'crash' command)
#    linux-panic — Alpine aarch64 kernel panic via sysrq-c
#    linux-audit — Alpine aarch64 boot with augmented audit/security denials
# ============================================================
set -euo pipefail

OUTPUT_DIR="${1:-./logs/linux}"
CYCLES="${2:-3}"

ALPINE_DIR="$HOME/qemu-alpine"
LK_ELF="$ALPINE_DIR/lk.elf"
ALPINE_ISO="$ALPINE_DIR/alpine-aarch64.iso"
BASE_DISK="$ALPINE_DIR/alpine-aarch64-disk.qcow2"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

log()  { echo -e "${CYAN}[QEMU]${NC}   $*"; }
ok()   { echo -e "${GREEN}[OK]${NC}     $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}   $*"; }

mkdir -p "$OUTPUT_DIR"/{lk-normal,lk-panic,linux-panic,linux-audit}

# ── No KVM for aarch64 guest on x86_64 host ──────────────────
# KVM requires host CPU == guest ISA.  For AArch64 on an x86_64 host
# we always run TCG (software emulation).  No -enable-kvm flag.
warn "Running AArch64 targets in TCG mode (no KVM on x86_64 host)."

# ── Kill QEMU ────────────────────────────────────────────────
kill_qemu() {
  pkill -f "qemu-system-aarch64" 2>/dev/null || true
  sleep 2
}

# ════════════════════════════════════════════════════════════
#  SCENARIO 1: LK Normal Boot — multiple cycles
#  Boots the LK ELF; waits for the '> ' or '] ' prompt;
#  captures full UART output then exits.
# ════════════════════════════════════════════════════════════
run_lk_normal_cycles() {
  echo -e "\n${BOLD}━━━ Scenario: LK Normal Boot Cycles ━━━━━━━━━━━${NC}\n"

  [[ -f "$LK_ELF" ]] || { warn "LK ELF not found at $LK_ELF — skipping LK scenarios.  Run setup.sh first."; return; }

  for i in $(seq 1 "$CYCLES"); do
    log "LK normal boot cycle $i / $CYCLES"
    local logfile="$OUTPUT_DIR/lk-normal/boot_cycle${i}.log"

    # Use 'expect' to interact with the LK UART console:
    #   - wait for the '> ' prompt (LK shell ready)
    #   - send 'help' to emit version/capability info
    #   - wait 2 s then exit cleanly
    expect -f - <<EOF > "$logfile" 2>&1
spawn qemu-system-aarch64 \
  -machine virt \
  -cpu cortex-a53 \
  -m 256M \
  -smp 1 \
  -bios none \
  -kernel $LK_ELF \
  -nographic \
  -serial stdio

set timeout 60
expect {
  -re {[>\]]\s} {
    send "help\r"
    sleep 2
    send "\x01x"
  }
  timeout { puts "\[TIMEOUT] LK did not reach shell prompt"; exit 1 }
}
EOF
    ok "LK cycle $i log: $logfile ($(wc -l < "$logfile") lines)"
    sleep 1
  done
}

# ════════════════════════════════════════════════════════════
#  SCENARIO 2: LK Panic — AArch64 data abort via 'crash' cmd
#  The LK 'crash' command writes to address 0 → data abort →
#  AArch64 register dump (x0–x29, elr, spsr) + stack trace
# ════════════════════════════════════════════════════════════
run_lk_panic() {
  echo -e "\n${BOLD}━━━ Scenario: LK AArch64 Crash ━━━━━━━━━━━━━━━${NC}\n"

  [[ -f "$LK_ELF" ]] || { warn "LK ELF not found — skipping."; return; }

  local logfile="$OUTPUT_DIR/lk-panic/boot_lk_panic.log"
  log "Triggering LK AArch64 crash via 'crash' command..."

  expect -f - <<EOF > "$logfile" 2>&1
spawn qemu-system-aarch64 \
  -machine virt \
  -cpu cortex-a53 \
  -m 256M \
  -smp 1 \
  -bios none \
  -kernel $LK_ELF \
  -nographic \
  -serial stdio

set timeout 60
expect {
  -re {[>\]]\s} {
    # 'crash' writes to address 0x0 — triggers a level-0 Data Abort
    # ESR_EL1 = 0x96000044 (DABT, write, level-0 translation fault)
    send "crash\r"
    sleep 5
    send "\x01x"
  }
  timeout { puts "\[TIMEOUT] LK did not reach shell before crash trigger"; exit 1 }
}
EOF

  ok "LK panic log: $logfile ($(wc -l < "$logfile") lines)"
  warn "Check for AArch64 register dump (x0..x29, elr, spsr) and PANIC in the log"
}

# ════════════════════════════════════════════════════════════
#  SCENARIO 3: Alpine Linux aarch64 — Kernel Panic
#  Boots Alpine ISO; triggers panic via sysrq-c after login
# ════════════════════════════════════════════════════════════

# Create a per-scenario qcow2 copy-on-write disk from the base
make_scenario_disk() {
  local name="$1"
  local out="$ALPINE_DIR/disk_aarch64_${name}.qcow2"
  qemu-img create -f qcow2 -b "$BASE_DISK" -F qcow2 "$out" 2>/dev/null
  echo "$out"
}

# Boot Alpine aarch64 with a UART log; returns PID
qemu_alpine_boot() {
  local disk="$1"
  local logfile="$2"
  local mem="${3:-512M}"
  shift 3
  local extra_args=("$@")

  qemu-system-aarch64 \
    -machine virt \
    -cpu cortex-a72 \
    -m "$mem" \
    -smp 2 \
    -drive "file=$disk,format=qcow2,if=virtio" \
    -drive "file=$ALPINE_ISO,format=raw,if=virtio,media=cdrom,readonly=on" \
    -boot order=dc \
    -nographic \
    -serial "file:$logfile" \
    -monitor "unix:/tmp/qemu-aarch64-monitor.sock,server,nowait" \
    -netdev user,id=net0 \
    -device virtio-net-device,netdev=net0 \
    "${extra_args[@]}" \
    &

  echo $!
}

monitor_cmd() {
  local cmd="$1"
  echo "$cmd" | socat - UNIX-CONNECT:/tmp/qemu-aarch64-monitor.sock 2>/dev/null || true
}

wait_for_kernel_boot() {
  local logfile="$1"
  local timeout="${2:-120}"
  local elapsed=0

  log "Waiting for Alpine aarch64 kernel boot output..."
  while [[ $elapsed -lt $timeout ]]; do
    if grep -q "Freeing unused kernel" "$logfile" 2>/dev/null; then
      ok "Kernel boot reached userspace"
      return 0
    fi
    sleep 3
    elapsed=$((elapsed + 3))
    echo -n "."
  done
  echo ""
  warn "Kernel boot wait timed out"
  return 1
}

run_linux_panic() {
  echo -e "\n${BOLD}━━━ Scenario: Alpine aarch64 Kernel Panic ━━━━━${NC}\n"

  [[ -f "$ALPINE_ISO" ]] || { warn "Alpine aarch64 ISO not found at $ALPINE_ISO — skipping.  Run setup.sh first."; return; }
  [[ -f "$BASE_DISK" ]]  || { warn "Alpine aarch64 disk not found at $BASE_DISK — skipping."; return; }

  local disk logfile
  disk=$(make_scenario_disk "panic")
  logfile="$OUTPUT_DIR/linux-panic/boot_panic.log"

  local pid
  pid=$(qemu_alpine_boot "$disk" "$logfile" "512M")
  log "QEMU PID: $pid"

  sleep 5
  wait_for_kernel_boot "$logfile" 120 || true
  sleep 20

  log "Triggering kernel panic via sysrq 'c' (QEMU monitor sendkey)..."
  monitor_cmd "sendkey alt-sysrq-c"

  sleep 30
  log "Capturing post-panic output..."
  sleep 10

  kill_qemu
  ok "Panic log: $logfile ($(wc -l < "$logfile") lines)"
  warn "Check for 'Oops:', 'BUG:', or 'Kernel panic' in the log"
}

# ════════════════════════════════════════════════════════════
#  SCENARIO 4: Alpine Linux aarch64 — Audit / Security denials
#  Augmented with realistic AppArmor denial lines
# ════════════════════════════════════════════════════════════
run_linux_audit() {
  echo -e "\n${BOLD}━━━ Scenario: Alpine aarch64 Audit / Denials ━━${NC}\n"

  [[ -f "$ALPINE_ISO" ]] || { warn "Alpine aarch64 ISO not found — skipping."; return; }
  [[ -f "$BASE_DISK" ]]  || { warn "Alpine aarch64 disk not found — skipping."; return; }

  local disk logfile
  disk=$(make_scenario_disk "audit")
  logfile="$OUTPUT_DIR/linux-audit/boot_audit.log"

  local pid
  pid=$(qemu_alpine_boot "$disk" "$logfile" "512M")
  log "QEMU PID: $pid"

  sleep 5
  wait_for_kernel_boot "$logfile" 120 || true
  sleep 30

  kill_qemu
  ok "Audit log: $logfile ($(wc -l < "$logfile") lines)"
}

# ── Inject extra error lines into logs (post-processing) ──────
augment_logs_with_errors() {
  log "Augmenting logs with realistic error patterns..."

  shopt -s nullglob

  # Add realistic driver timeout errors to LK normal log (cycle 1 only)
  local lk_log="$OUTPUT_DIR/lk-normal/boot_cycle1.log"
  if [[ -f "$lk_log" ]]; then
    cat >> "$lk_log" << 'EOF'

[   12.543210] mmc0: Timeout waiting for hardware interrupt.
[   15.123456] usb 1-1: device descriptor read/64, error -71
[   18.901234] ata1: SRST failed (errno=-16)
[   22.345678] thermal thermal_zone0: failed to read out thermal zone (-61)
EOF
  fi

  # Add AppArmor audit denials to linux-audit log
  local audit_log="$OUTPUT_DIR/linux-audit/boot_audit.log"
  if [[ -f "$audit_log" ]]; then
    cat >> "$audit_log" << 'EOF'

[    8.234567] audit: type=1400 audit(1234567890.123:45): apparmor="DENIED" operation="open" profile="/usr/sbin/ntpd" name="/proc/net/if_inet6" pid=312 comm="ntpd" requested_mask="r" denied_mask="r" fsuid=123 ouid=0
[    9.345678] audit: type=1400 audit(1234567890.234:46): apparmor="DENIED" operation="exec" profile="unconfined" name="/usr/lib/systemd/systemd-networkd" pid=401 comm="sh"
[   10.456789] audit: type=1400 audit(1234567890.345:47): apparmor="DENIED" operation="file_lock" profile="/usr/sbin/dnsmasq" name="/var/run/dnsmasq/dnsmasq.pid" pid=512
[   11.567890] audit: type=1400 audit(1234567890.456:48): apparmor="DENIED" operation="capable" profile="/usr/sbin/cupsd" capability=net_admin pid=623 comm="cupsd"
EOF
  fi

  ok "Logs augmented with error patterns"
}

# ── Main ─────────────────────────────────────────────────────
main() {
  echo -e "\n${BOLD}╔══════════════════════════════════════════════╗${NC}"
  echo -e "${BOLD}║  AArch64 QEMU Boot Log Generator            ║${NC}"
  echo -e "${BOLD}╚══════════════════════════════════════════════╝${NC}\n"

  log "Output: $OUTPUT_DIR"
  log "LK boot cycles: $CYCLES"
  log "LK ELF: $LK_ELF"
  log "Alpine ISO: $ALPINE_ISO"

  # Check requirements
  command -v qemu-system-aarch64 &>/dev/null || { echo "qemu-system-aarch64 not found. Run setup.sh first."; exit 1; }
  command -v expect            &>/dev/null || { echo "'expect' not found. Run setup.sh first."; exit 1; }

  run_lk_normal_cycles
  run_lk_panic
  run_linux_panic
  run_linux_audit
  augment_logs_with_errors

  echo -e "\n${BOLD}╔══════════════════════════════════════════════╗${NC}"
  echo -e "${BOLD}║  All AArch64 scenarios complete!             ║${NC}"
  echo -e "${BOLD}╚══════════════════════════════════════════════╝${NC}\n"
  echo "  Logs saved to: $OUTPUT_DIR"
  find "$OUTPUT_DIR" -name "*.log" | while read -r f; do
    echo "  $(wc -l < "$f") lines  →  $f"
  done
  echo ""
  echo "  Run collect-logs.sh to normalize for the orchestrator."
}

main "$@"
