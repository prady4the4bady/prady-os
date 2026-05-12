#!/usr/bin/env bash
# build_iso.sh — Prady OS Production ISO Build Script
# Phase 38: Final Release Build
#
# Builds a bootable Prady OS ISO using Buildroot + GRUB.
#
# Usage:
#   ./build_iso.sh [--no-qemu] [--output=DIR]
#
# Options:
#   --no-qemu       Skip the optional QEMU boot test at the end
#   --output=DIR    Output directory (default: <repo_root>/output)
#   --help          Show this message
#
# Prerequisites (Ubuntu/Debian):
#   sudo apt install build-essential libncurses-dev bison flex \
#     libssl-dev libelf-dev wget rsync bc cpio unzip python3 \
#     grub-pc-bin grub-efi-amd64-bin xorriso squashfs-tools mtools

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_ISO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${BUILD_ISO_DIR}/../.." && pwd)"

# ── Configuration ────────────────────────────────────────────────────────────
BUILDROOT_VERSION="${BUILDROOT_VERSION:-2024.02}"
BUILDROOT_BASE="${REPO_ROOT}/.buildroot"
BUILDROOT_DIR="${BUILDROOT_BASE}/buildroot-${BUILDROOT_VERSION}"
BUILDROOT_OUTPUT="${BUILDROOT_BASE}/output"
DEFCONFIG="${BUILD_ISO_DIR}/buildroot-config/kryos_defconfig"
OVERLAY_DIR="${BUILD_ISO_DIR}/buildroot-config/overlay"
GRUB_CFG="${BUILD_ISO_DIR}/grub/grub.cfg"
GRUB_THEME_DIR="${BUILD_ISO_DIR}/grub/grub-theme"
UI_DIST="${REPO_ROOT}/ui/desktop-shell/dist"
PROD_COMPOSE="${BUILD_ISO_DIR}/docker-compose.prod.yml"
OUTPUT_DIR="${REPO_ROOT}/output"
ISO_NAME="prady-os.iso"
SKIP_QEMU="${SKIP_QEMU:-0}"
SIGN_ISO="${SIGN_ISO:-0}"

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'

log()  { echo -e "${BLUE}[BUILD]${NC} $*"; }
ok()   { echo -e "${GREEN}[ OK ]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()  { echo -e "${RED}[ERR ]${NC} $*" >&2; }

# ── Argument parsing ─────────────────────────────────────────────────────────
for arg in "$@"; do
    case "${arg}" in
        --no-qemu)   SKIP_QEMU=1 ;;
        --output=*)  OUTPUT_DIR="${arg#*=}" ;;
        --help|-h)
            sed -n '3,16p' "$0" | sed 's/^# //'
            exit 0
            ;;
    esac
done

log "═══════════════════════════════════════════════════════"
log "  Prady OS Production ISO Build — Phase 38"
log "═══════════════════════════════════════════════════════"
log "Repo root:         ${REPO_ROOT}"
log "Buildroot version: ${BUILDROOT_VERSION}"
log "Output dir:        ${OUTPUT_DIR}"
log ""

# ── Step 1: Preflight ────────────────────────────────────────────────────────
log "Step 1/6 — Preflight checks"
MISSING_TOOLS=""
for cmd in make wget xz rsync grub-mkrescue mksquashfs xorriso bc; do
    if ! command -v "${cmd}" >/dev/null 2>&1; then
        MISSING_TOOLS="${MISSING_TOOLS} ${cmd}"
    fi
done

if [ -n "${MISSING_TOOLS}" ]; then
    warn "Missing build tools:${MISSING_TOOLS}"
    warn "Install: sudo apt install build-essential grub-pc-bin grub-efi-amd64-bin xorriso squashfs-tools wget bc rsync"
    warn "Proceeding — build will fail if tools are absent when needed"
fi
mkdir -p "${OUTPUT_DIR}"
ok "Preflight done"

# ── Step 2: Buildroot download ───────────────────────────────────────────────
log "Step 2/6 — Buildroot ${BUILDROOT_VERSION}"
if [ ! -d "${BUILDROOT_DIR}" ]; then
    log "Downloading Buildroot ${BUILDROOT_VERSION}..."
    mkdir -p "${BUILDROOT_BASE}"
    BUILDROOT_URL="https://buildroot.org/downloads/buildroot-${BUILDROOT_VERSION}.tar.xz"
    wget -q --show-progress -O "/tmp/buildroot-${BUILDROOT_VERSION}.tar.xz" "${BUILDROOT_URL}"
    tar -xf "/tmp/buildroot-${BUILDROOT_VERSION}.tar.xz" -C "${BUILDROOT_BASE}"
    rm -f "/tmp/buildroot-${BUILDROOT_VERSION}.tar.xz"
    ok "Buildroot ${BUILDROOT_VERSION} extracted to ${BUILDROOT_DIR}"
else
    ok "Buildroot ${BUILDROOT_VERSION} already present"
fi

# ── Step 3: Stage overlay files ─────────────────────────────────────────────
log "Step 3/6 — Staging overlay files"

# Desktop shell dist
if [ -d "${UI_DIST}" ]; then
    log "Copying ui/desktop-shell/dist/ → overlay/usr/share/kryos/"
    mkdir -p "${OVERLAY_DIR}/usr/share/kryos"
    rsync -a --delete "${UI_DIST}/" "${OVERLAY_DIR}/usr/share/kryos/"
    ok "Desktop shell staged ($(du -sh "${UI_DIST}" | cut -f1))"
else
    warn "ui/desktop-shell/dist/ not found — run: cd ui/desktop-shell && npm run build"
    mkdir -p "${OVERLAY_DIR}/usr/share/kryos"
fi

# Production compose file
log "Staging docker-compose.prod.yml → overlay/etc/kryos/"
mkdir -p "${OVERLAY_DIR}/etc/kryos"
cp "${PROD_COMPOSE}" "${OVERLAY_DIR}/etc/kryos/docker-compose.prod.yml"

# GRUB config + theme into overlay boot area
log "Staging GRUB config + theme → overlay/boot/grub/"
mkdir -p "${OVERLAY_DIR}/boot/grub/theme"
cp "${GRUB_CFG}" "${OVERLAY_DIR}/boot/grub/grub.cfg"
cp -r "${GRUB_THEME_DIR}/." "${OVERLAY_DIR}/boot/grub/theme/"

# Generate background.png if generator is available and bg missing
if [ ! -f "${GRUB_THEME_DIR}/background.png" ]; then
    if command -v python3 >/dev/null 2>&1; then
        log "Generating GRUB background.png..."
        python3 "${GRUB_THEME_DIR}/generate_background.py" \
            --output "${GRUB_THEME_DIR}/background.png" 2>/dev/null \
            && cp "${GRUB_THEME_DIR}/background.png" "${OVERLAY_DIR}/boot/grub/theme/background.png" \
            || warn "Pillow not installed — background.png will be missing from theme"
    else
        warn "python3 not found — skipping background.png generation"
    fi
fi

# Ensure init script is executable
chmod +x "${OVERLAY_DIR}/etc/init.d/S99kryos"
ok "Overlay staging complete"

# ── Step 4: Buildroot build ──────────────────────────────────────────────────
log "Step 4/6 — Buildroot build (this takes 1–4 hours on first run)"
log "           Subsequent builds use ccache and are much faster."

mkdir -p "${BUILDROOT_OUTPUT}"
cp "${DEFCONFIG}" "${BUILDROOT_DIR}/configs/kryos_defconfig"

make -C "${BUILDROOT_DIR}" \
    O="${BUILDROOT_OUTPUT}" \
    kryos_defconfig

make -C "${BUILDROOT_DIR}" \
    O="${BUILDROOT_OUTPUT}" \
    BR2_ROOTFS_OVERLAY="${OVERLAY_DIR}" \
    -j"$(nproc)"

ok "Buildroot build complete"

# ── Step 5: Create ISO with grub-mkrescue ───────────────────────────────────
log "Step 5/6 — Creating bootable ISO with grub-mkrescue"

ISO_STAGING="${BUILDROOT_OUTPUT}/iso-staging"
mkdir -p "${ISO_STAGING}/boot/grub/theme"
mkdir -p "${ISO_STAGING}/EFI/BOOT"

# Kernel and initrd
cp "${BUILDROOT_OUTPUT}/images/bzImage"          "${ISO_STAGING}/boot/vmlinuz"
cp "${BUILDROOT_OUTPUT}/images/rootfs.squashfs"  "${ISO_STAGING}/boot/rootfs.squashfs"

if [ -f "${BUILDROOT_OUTPUT}/images/rootfs.cpio.gz" ]; then
    cp "${BUILDROOT_OUTPUT}/images/rootfs.cpio.gz" "${ISO_STAGING}/boot/initrd.img"
fi

# Copy Memtest86+ if built
find "${BUILDROOT_OUTPUT}/build" -name "memtest" -maxdepth 3 2>/dev/null \
    | head -1 \
    | xargs -I{} cp {} "${ISO_STAGING}/boot/memtest86+.bin" 2>/dev/null || true

# GRUB config + theme
cp "${GRUB_CFG}"                    "${ISO_STAGING}/boot/grub/grub.cfg"
cp -r "${GRUB_THEME_DIR}/."         "${ISO_STAGING}/boot/grub/theme/"

# Build ISO
ISO_OUTPUT="${OUTPUT_DIR}/${ISO_NAME}"
grub-mkrescue \
    --output="${ISO_OUTPUT}" \
    --modules="normal linux ext2 fat squash4 part_msdos part_gpt efi_gop gfxterm png all_video" \
    "${ISO_STAGING}"

ok "ISO created: ${ISO_OUTPUT}"

# ── Step 6: Verify, sign, and report ────────────────────────────────────────
log "Step 6/6 — Verification"

ISO_SIZE=$(du -sh "${ISO_OUTPUT}" | cut -f1)
SHA256=$(sha256sum "${ISO_OUTPUT}" | awk '{print $1}')

# Write sidecar file
echo "${SHA256}  ${ISO_NAME}" > "${OUTPUT_DIR}/${ISO_NAME%.iso}.sha256"

if [ "${SIGN_ISO}" = "1" ]; then
    log "Signing enabled (SIGN_ISO=1), generating release signatures"
    "${SCRIPT_DIR}/sign_iso.sh" "${ISO_OUTPUT}"
else
    log "Signing skipped (set SIGN_ISO=1 to generate release signatures)"
fi

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  ✓ Prady OS Release ISO Build Complete${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
printf "  %-10s %s\n" "ISO:" "${ISO_OUTPUT}"
printf "  %-10s %s\n" "Size:" "${ISO_SIZE}"
printf "  %-10s %s\n" "SHA256:" "${SHA256}"
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo ""
ok "SHA256 saved to ${OUTPUT_DIR}/${ISO_NAME%.iso}.sha256"

# ── Optional: QEMU boot test ─────────────────────────────────────────────────
if [ "${SKIP_QEMU}" = "0" ] && command -v qemu-system-x86_64 >/dev/null 2>&1; then
    log "Launching QEMU boot test (press Ctrl+Alt+G to release cursor, close window to quit)"
    qemu-system-x86_64 \
        -cdrom "${ISO_OUTPUT}" \
        -m 4G \
        -smp 4 \
        -enable-kvm \
        -vga virtio \
        -display gtk \
        -boot d
elif [ "${SKIP_QEMU}" = "1" ]; then
    log "QEMU test skipped (--no-qemu)"
else
    warn "qemu-system-x86_64 not found — skipping boot test (install: sudo apt install qemu-system-x86)"
fi

