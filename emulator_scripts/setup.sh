#!/bin/bash
# ============================================================
#  setup.sh — Install all dependencies for boot log generation
#  Supports: Linux x86_64
# ============================================================
set -euo pipefail

ALPINE_VERSION="3.19.1"

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
      qemu-system-x86 qemu-system-arm qemu-system-aarch64 qemu-utils \
      adb android-tools-adb \
      wget curl unzip python3 \
      ovmf \
      expect socat
    ;;
  dnf)
    sudo dnf install -y \
      qemu qemu-kvm qemu-system-aarch64 \
      android-tools \
      wget curl unzip python3 \
      edk2-ovmf \
      expect socat
    ;;
  pacman)
    sudo pacman -Sy --noconfirm \
      qemu-full \
      android-tools \
      wget curl unzip python3 \
      edk2-ovmf \
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

# ── 7. Download Alpine Linux for QEMU ────────────────────────
ALPINE_DIR="$HOME/qemu-alpine"
ALPINE_ISO="$ALPINE_DIR/alpine.iso"
ALPINE_DISK="$ALPINE_DIR/alpine-disk.qcow2"

mkdir -p "$ALPINE_DIR"

if [[ -f "$ALPINE_DISK" ]]; then
  ok "Alpine QEMU disk already exists at $ALPINE_DISK"
else
  log "Downloading Alpine Linux ${ALPINE_VERSION} ISO..."
  ALPINE_MINOR="${ALPINE_VERSION%.*}"   # e.g. 3.19
  ALPINE_URL="https://dl-cdn.alpinelinux.org/alpine/v${ALPINE_MINOR}/releases/x86_64/alpine-virt-${ALPINE_VERSION}-x86_64.iso"
  wget -q --show-progress "$ALPINE_URL" -O "$ALPINE_ISO"

  log "Creating QEMU disk image (4GB)..."
  qemu-img create -f qcow2 "$ALPINE_DISK" 4G

  ok "Alpine ISO and disk ready"
fi

# ── Summary ──────────────────────────────────────────────────
echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║  Setup Complete!                             ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  Android SDK  : $ANDROID_SDK"
echo -e "  AVD Name     : $AVD_NAME"
echo -e "  Alpine disk  : $ALPINE_DISK"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "  source $SHELL_RC          # reload PATH"
echo "  ./run-android-emulator.sh  # capture Android boot logs"
echo "  ./run-linux-qemu.sh        # capture Linux boot logs"
