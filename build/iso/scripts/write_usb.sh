#!/usr/bin/env bash
# write_usb.sh — Write Prady OS ISO to USB drive
# Phase 33: Production ISO Build
#
# Uses dd with a progress bar (pv if available) to write the ISO.
# Includes safety checks to avoid accidental system drive overwrites.
#
# Usage:
#   ./write_usb.sh <iso-path> <device>
#
# Examples:
#   ./write_usb.sh ./output/kryos-os-dev.iso /dev/sdb
#   ./write_usb.sh ./output/kryos-os-dev.iso /dev/sdX
#
# To list connected block devices:
#   lsblk

set -euo pipefail

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; NC='\033[0m'

log()  { echo -e "${BLUE}[USB]${NC} $*"; }
ok()   { echo -e "${GREEN}[ OK ]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()  { echo -e "${RED}[ERR ]${NC} $*" >&2; }

ISO_PATH="${1:-}"
DEVICE="${2:-}"

# ── Usage ─────────────────────────────────────────────────────────────────────
if [ -z "${ISO_PATH}" ] || [ -z "${DEVICE}" ]; then
    echo ""
    echo "Usage: $0 <iso-path> <device>"
    echo ""
    echo "Examples:"
    echo "  $0 ./output/kryos-os-dev.iso /dev/sdb"
    echo ""
    echo "List available block devices with: lsblk"
    echo ""
    exit 1
fi

# ── Verify ISO ────────────────────────────────────────────────────────────────
if [ ! -f "${ISO_PATH}" ]; then
    err "ISO file not found: ${ISO_PATH}"
    err "Run 'make iso' first to build the ISO."
    exit 1
fi

# ── Safety: refuse dangerous devices ─────────────────────────────────────────
UNSAFE_DEVICES="/dev/sda /dev/nvme0n1 /dev/nvme1n1 /dev/vda /dev/xvda /dev/hda"
for UNSAFE in ${UNSAFE_DEVICES}; do
    if [ "${DEVICE}" = "${UNSAFE}" ]; then
        err "Refusing to write to ${DEVICE} — this is likely your primary system drive!"
        err "Double-check your target device with: lsblk"
        exit 1
    fi
done

# ── Verify device is a block device ──────────────────────────────────────────
if [ ! -b "${DEVICE}" ]; then
    err "Not a block device: ${DEVICE}"
    err "Run 'lsblk' to find your USB drive device path."
    exit 1
fi

# ── Require root ──────────────────────────────────────────────────────────────
if [ "$(id -u)" -ne 0 ]; then
    err "This script must be run as root."
    err "Re-run with: sudo $0 ${ISO_PATH} ${DEVICE}"
    exit 1
fi

# ── Confirmation ──────────────────────────────────────────────────────────────
ISO_SIZE=$(du -sh "${ISO_PATH}" | cut -f1)
DEVICE_INFO=$(lsblk -no NAME,SIZE,MODEL "${DEVICE}" 2>/dev/null | head -1 || echo "${DEVICE}")

echo ""
echo -e "${RED}══════════════════════════════════════════════════════════${NC}"
echo -e "${RED}  ⚠  DATA DESTRUCTION WARNING ⚠${NC}"
echo -e "${RED}══════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "  ISO:    ${CYAN:-}${ISO_PATH}${NC} (${ISO_SIZE})"
echo -e "  Device: ${DEVICE_INFO}"
echo ""
echo -e "${RED}  ALL DATA on ${DEVICE} will be PERMANENTLY ERASED.${NC}"
echo -e "${RED}  There is NO undo.${NC}"
echo ""
echo -n "  Type YES (uppercase) to continue, anything else to cancel: "
read -r CONFIRM

if [ "${CONFIRM}" != "YES" ]; then
    warn "Cancelled."
    exit 0
fi

# ── Unmount all partitions ────────────────────────────────────────────────────
log "Unmounting partitions on ${DEVICE}..."
for PART in "${DEVICE}"?* "${DEVICE}p"?*; do
    if [ -b "${PART}" ] && mount | grep -q "^${PART} "; then
        log "  Unmounting ${PART}..."
        umount "${PART}" || warn "  Failed to unmount ${PART} (may be safe to ignore)"
    fi
done

# ── Write ─────────────────────────────────────────────────────────────────────
log "Writing ${ISO_PATH} → ${DEVICE}..."
log "(This may take several minutes depending on USB speed)"

if command -v pv >/dev/null 2>&1; then
    ISO_BYTES=$(stat -c%s "${ISO_PATH}")
    pv -s "${ISO_BYTES}" "${ISO_PATH}" | dd of="${DEVICE}" bs=4M oflag=sync status=none
else
    warn "pv not installed — no progress bar. Install with: sudo apt install pv"
    dd if="${ISO_PATH}" of="${DEVICE}" bs=4M conv=fsync status=progress
fi

# ── Sync ─────────────────────────────────────────────────────────────────────
log "Syncing write buffers..."
sync

# ── Spot-check: verify MBR ───────────────────────────────────────────────────
log "Verifying write (MBR checksum)..."
ISO_MBR=$(dd if="${ISO_PATH}" bs=512 count=1 2>/dev/null | sha256sum | awk '{print $1}')
DEV_MBR=$(dd if="${DEVICE}"   bs=512 count=1 2>/dev/null | sha256sum | awk '{print $1}')

if [ "${ISO_MBR}" = "${DEV_MBR}" ]; then
    ok "MBR verification passed ✓"
else
    warn "MBR checksum mismatch — the write may have failed. Try again."
fi

echo ""
ok "Prady OS ISO written to ${DEVICE}"
echo -e "  ${GREEN}You can now safely remove the USB drive.${NC}"
echo ""
echo "  UEFI boot: Enable USB boot in your BIOS/UEFI firmware settings."
echo "  Legacy boot: Press F12, F8, or DEL at startup to select USB."
echo ""
