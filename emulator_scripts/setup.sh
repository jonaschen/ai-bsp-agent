#!/bin/bash
# ============================================================
#  setup.sh — Install all dependencies for boot log generation
#  Supports: Linux x86_64 host; AArch64 QEMU guests (TCG)
#
#  Installs:
#    - qemu-system-aarch64 (TCG; no KVM needed for AArch64 targets)
#    - gcc-aarch64-linux-gnu cross-compiler (for Little Kernel build)
#    - Little Kernel (github.com/littlekernel/lk) — target qemu-virt-arm64-test
#    - Alpine Linux 3.19 aarch64 ISO + qcow2 base disk
#    - Android SDK + AVD (for android-avd scenarios)
# ============================================================
set -euo pipefail

ALPINE_VERSION="3.19.1"
LK_REPO="https://github.com/littlekernel/lk.git"
LK_TARGET="qemu-virt-arm64-test"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

log()  { echo -e "${CYAN}[SETUP]${NC} $*"; }
ok()   { echo -e "${GREEN}[OK]${NC}   $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()  { echo -e "${RED}[ERR]${NC}  $*" >&2; exit 1; }

# ── Detect distro ────────────────────────────────────────────
if command -v apt-get &>/dev/null; then
  PKG_MGR="apt"
elif command -v dnf &>/dev/null; then
  PKG_MGR="dnf"
elif command -v pacman &>/dev/null; then
  PKG_MGR="pacman"
else
  err "Unsupported package manager. Please install packages manually."
fi

log "Detected package manager: $PKG_MGR"

# ── 1. System packages ───────────────────────────────────────
log "Installing system packages..."

case "$PKG_MGR" in
  apt)
    sudo apt-get update -qq
    sudo apt-get install -y \
      qemu-system-aarch64 qemu-utils \
      gcc-aarch64-linux-gnu make git \
      adb android-tools-adb \
      wget curl unzip python3 \
      expect socat
    ;;
  dnf)
    sudo dnf install -y \
      qemu-system-aarch64 qemu-img \
      gcc-aarch64-linux-gnu make git \
      android-tools \
      wget curl unzip python3 \
      expect socat
    ;;
  pacman)
    sudo pacman -Sy --noconfirm \
      qemu-system-aarch64 \
      aarch64-linux-gnu-gcc make git \
      android-tools \
      wget curl unzip python3 \
      expect socat
    ;;
esac
ok "System packages installed"

# ── 2. KVM check ─────────────────────────────────────────────
log "Checking KVM support..."
if [[ -r /dev/kvm ]]; then
  ok "KVM available — emulation will be fast"
else
  warn "KVM not available. Android emulator will be very slow without it."
  warn "To enable: sudo modprobe kvm_intel  (or kvm_amd on AMD hosts)"
  if ! groups | grep -qw kvm; then
    warn "Current user is not in the 'kvm' group. Run:"
    warn "  sudo usermod -aG kvm \$USER  && newgrp kvm"
  fi
fi

# ── 3. Android cmdline-tools ─────────────────────────────────
ANDROID_SDK="$HOME/android-sdk"
CMDLINE_TOOLS="$ANDROID_SDK/cmdline-tools/latest"

if [[ -f "$CMDLINE_TOOLS/bin/sdkmanager" ]]; then
  ok "Android cmdline-tools already installed at $CMDLINE_TOOLS"
else
  log "Downloading Android cmdline-tools..."
  mkdir -p "$ANDROID_SDK/cmdline-tools"

  CMDLINE_URL="https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip"
  TMP_ZIP="/tmp/cmdline-tools.zip"

  wget -q --show-progress "$CMDLINE_URL" -O "$TMP_ZIP"
  unzip -q "$TMP_ZIP" -d "$ANDROID_SDK/cmdline-tools/"

  # Google puts it in 'cmdline-tools/', rename to 'latest'
  if [[ -d "$ANDROID_SDK/cmdline-tools/cmdline-tools" ]]; then
    mv "$ANDROID_SDK/cmdline-tools/cmdline-tools" "$CMDLINE_TOOLS"
  fi

  rm -f "$TMP_ZIP"
  ok "Android cmdline-tools installed"
fi

# ── 4. Add to PATH ───────────────────────────────────────────
EXPORT_LINES=(
  "export ANDROID_SDK_ROOT=$ANDROID_SDK"
  "export ANDROID_HOME=$ANDROID_SDK"
  "export PATH=\$PATH:$CMDLINE_TOOLS/bin:$ANDROID_SDK/platform-tools:$ANDROID_SDK/emulator"
)

SHELL_RC="$HOME/.bashrc"
[[ "$SHELL" == *zsh* ]] && SHELL_RC="$HOME/.zshrc"

for line in "${EXPORT_LINES[@]}"; do
  grep -qF "$line" "$SHELL_RC" 2>/dev/null || echo "$line" >> "$SHELL_RC"
done

# Export for current session
export ANDROID_SDK_ROOT="$ANDROID_SDK"
export ANDROID_HOME="$ANDROID_SDK"
export PATH="$PATH:$CMDLINE_TOOLS/bin:$ANDROID_SDK/platform-tools:$ANDROID_SDK/emulator"

ok "PATH updated in $SHELL_RC"

# ── 5. Accept licenses & install AVD packages ────────────────
log "Installing Android SDK packages (this may take a few minutes)..."

yes | sdkmanager --licenses > /dev/null 2>&1 || true

sdkmanager \
  "platform-tools" \
  "emulator" \
  "system-images;android-34;google_apis;x86_64" \
  --sdk_root="$ANDROID_SDK"

ok "Android SDK packages installed"

# ── 6. Create AVD ────────────────────────────────────────────
AVD_NAME="boot_log_avd"
if avdmanager list avd | grep -q "$AVD_NAME"; then
  ok "AVD '$AVD_NAME' already exists"
else
  log "Creating AVD: $AVD_NAME"
  echo "no" | avdmanager create avd \
    --name "$AVD_NAME" \
    --package "system-images;android-34;google_apis;x86_64" \
    --device "pixel_6" \
    --force

  ok "AVD '$AVD_NAME' created"
fi

# ── 7. Download Alpine Linux aarch64 for QEMU ────────────────
ALPINE_DIR="$HOME/qemu-alpine"
ALPINE_ISO="$ALPINE_DIR/alpine-aarch64.iso"
ALPINE_DISK="$ALPINE_DIR/alpine-aarch64-disk.qcow2"

mkdir -p "$ALPINE_DIR"

if [[ -f "$ALPINE_DISK" ]]; then
  ok "Alpine aarch64 QEMU disk already exists at $ALPINE_DISK"
else
  log "Downloading Alpine Linux ${ALPINE_VERSION} aarch64 ISO..."
  ALPINE_MINOR="${ALPINE_VERSION%.*}"   # e.g. 3.19
  ALPINE_URL="https://dl-cdn.alpinelinux.org/alpine/v${ALPINE_MINOR}/releases/aarch64/alpine-virt-${ALPINE_VERSION}-aarch64.iso"
  wget -q --show-progress "$ALPINE_URL" -O "$ALPINE_ISO"

  log "Creating QEMU disk image (4GB)..."
  qemu-img create -f qcow2 "$ALPINE_DISK" 4G

  ok "Alpine aarch64 ISO and disk ready"
fi

# ── 8. Build Little Kernel (AArch64 QEMU target) ─────────────
LK_DIR="$ALPINE_DIR/lk"
LK_ELF="$ALPINE_DIR/lk.elf"

if [[ -f "$LK_ELF" ]]; then
  ok "Little Kernel ELF already exists at $LK_ELF"
else
  log "Cloning Little Kernel from $LK_REPO ..."
  if [[ -d "$LK_DIR" ]]; then
    git -C "$LK_DIR" pull --ff-only
  else
    git clone --depth=1 "$LK_REPO" "$LK_DIR"
  fi

  log "Building LK target: $LK_TARGET (cross-compiler: aarch64-linux-gnu-gcc)..."
  make -C "$LK_DIR" -j"$(nproc)" \
    ARCH=arm64 \
    TOOLCHAIN_PREFIX=aarch64-linux-gnu- \
    "$LK_TARGET"

  # Copy the ELF to a fixed path so run-linux-qemu.sh can find it
  cp "$LK_DIR/build-${LK_TARGET}/lk.elf" "$LK_ELF"
  ok "Little Kernel ELF built → $LK_ELF"
fi

# ── Summary ──────────────────────────────────────────────────
echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║  Setup Complete!                             ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  Android SDK    : $ANDROID_SDK"
echo -e "  AVD Name       : $AVD_NAME"
echo -e "  Alpine aarch64 : $ALPINE_DISK"
echo -e "  LK ELF         : $LK_ELF"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "  source $SHELL_RC           # reload PATH"
echo "  ./run-android-emulator.sh  # capture Android boot logs"
echo "  ./run-linux-qemu.sh        # capture AArch64 boot logs (LK + Alpine)"
