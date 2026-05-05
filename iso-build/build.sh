#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
CONFIG_DIR="${SCRIPT_DIR}/config"
INCLUDES_DIR="${CONFIG_DIR}/includes.chroot"
PROJECT_DST="${INCLUDES_DIR}/opt/prady-os"
THEME_SRC="${SCRIPT_DIR}/plymouth"
THEME_DST="${INCLUDES_DIR}/usr/share/plymouth/themes/prady"
PRADY_RELEASE_FILE="${INCLUDES_DIR}/etc/prady/os-release"
CONFIG_ONLY=0

if [[ "${1:-}" == "--config-only" ]]; then
  CONFIG_ONLY=1
fi

if ! command -v lb >/dev/null 2>&1; then
  echo "Error: live-build (lb) is not installed on this host." >&2
  exit 1
fi

mkdir -p "${PROJECT_DST}"
mkdir -p "${THEME_DST}"
mkdir -p "$(dirname "${PRADY_RELEASE_FILE}")"

chmod +x "${CONFIG_DIR}"/hooks/live/*.hook.chroot
chmod +x "${INCLUDES_DIR}/etc/xdm/Xsession"

echo "[1/5] Syncing repository into live image payload at /opt/prady-os ..."
rsync -a --delete \
  --exclude '.git' \
  --exclude '.venv' \
  --exclude '**/node_modules' \
  --exclude '**/__pycache__' \
  --exclude '*.iso' \
  --exclude '.pytest_cache' \
  "${REPO_ROOT}/" "${PROJECT_DST}/"

echo "[2/5] Installing Plymouth theme payload ..."
rsync -a --delete "${THEME_SRC}/" "${THEME_DST}/"

echo "[3/5] Writing Prady build metadata ..."
cat > "${PRADY_RELEASE_FILE}" <<EOF
PRADY_VERSION=0.1.0
PRADY_CODENAME=caveman
BUILD_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF

echo "[4/5] Running lb clean ..."
lb clean --all

echo "[5/5] Running lb config + lb build ..."
# Use grub-pc for BIOS and grub-efi for EFI (avoids the syslinux asset issue)
export LB_BOOTLOADER_BIOS="grub-pc"
export LB_BOOTLOADER_EFI="grub-efi"
lb config \
  --mode debian \
  --distribution bookworm \
  --architectures amd64 \
  --binary-images iso-hybrid \
  --debian-installer false \
  --archive-areas "main contrib non-free non-free-firmware" \
  --mirror-bootstrap "http://deb.debian.org/debian" \
  --mirror-chroot "http://deb.debian.org/debian" \
  --mirror-chroot-security "http://deb.debian.org/debian-security" \
  --mirror-binary "http://deb.debian.org/debian" \
  --mirror-binary-security "http://deb.debian.org/debian-security" \
  --security false \
  --bootappend-live "boot=live components quiet splash" \
  --initramfs live-boot \
  --system normal \
  --linux-packages none

if [[ "${CONFIG_ONLY}" -eq 1 ]]; then
  echo "lb config completed. Skipping lb build (--config-only)."
  exit 0
fi

lb build

ISO_FILE="$(find . -maxdepth 1 -type f -name '*.iso' | head -n 1 || true)"
if [[ -z "${ISO_FILE}" ]]; then
  echo "Error: no ISO file was produced by lb build." >&2
  exit 1
fi

cp -f "${ISO_FILE}" "prady-os.iso"
echo "ISO build complete: ${SCRIPT_DIR}/prady-os.iso"
