#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$ROOT_DIR/build"
OUTPUT_DIR="$ROOT_DIR/dist"

echo "════════════════════════════════════════"
echo "  PradyOS ISO Build System"
echo "  $(date)"
echo "════════════════════════════════════════"

# Check we're on Linux
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
  echo "ERROR: ISO must be built on Linux (Debian/Ubuntu)"
  echo "Use WSL2 on Windows: wsl --install -d Ubuntu"
  exit 1
fi

# Install build dependencies
echo "[1/7] Installing build dependencies..."
sudo apt-get install -y live-build debootstrap squashfs-tools \
  xorriso isolinux syslinux-common grub-pc-bin grub-efi-amd64-bin

# Copy our files into the live-build config
echo "[2/7] Staging PradyOS files..."
cp -r "$ROOT_DIR/compositor/kryos-hyprland-config" \
  "$ROOT_DIR/installer/live-build-config/config/includes.chroot/etc/kryos/hyprland"
cp -r "$ROOT_DIR/shell/kryos-shell" \
  "$ROOT_DIR/installer/live-build-config/config/includes.chroot/opt/kryos/shell"
cp -r "$ROOT_DIR/prax-agent/src" \
  "$ROOT_DIR/installer/live-build-config/config/includes.chroot/opt/kryos/agent"
cp -r "$ROOT_DIR/vyrex/kryos-vyrex-config" \
  "$ROOT_DIR/installer/live-build-config/config/includes.chroot/etc/kryos/vyrex"
cp -r "$ROOT_DIR/installer/firstboot-wizard" \
  "$ROOT_DIR/installer/live-build-config/config/includes.chroot/opt/kryos/firstboot"
cp "$ROOT_DIR/packages/systemd/"*.service \
  "$ROOT_DIR/installer/live-build-config/config/includes.chroot/etc/systemd/system/"

# Build the ISO
echo "[3/7] Running live-build (this takes 20-40 minutes)..."
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"
cp -r "$ROOT_DIR/installer/live-build-config/." .
lb build 2>&1 | tee "$BUILD_DIR/build.log"

# Copy output ISO
echo "[4/7] Packaging ISO..."
mkdir -p "$OUTPUT_DIR"
cp "$BUILD_DIR/live-image-amd64.hybrid.iso" "$OUTPUT_DIR/kryos-os-1.0.iso"

echo "[5/7] Calculating checksums..."
sha256sum "$OUTPUT_DIR/kryos-os-1.0.iso" > "$OUTPUT_DIR/kryos-os-1.0.iso.sha256"

echo ""
echo "════════════════════════════════════════"
echo "  BUILD COMPLETE"
echo "  ISO: $OUTPUT_DIR/kryos-os-1.0.iso"
echo "  Size: $(du -h "$OUTPUT_DIR/kryos-os-1.0.iso" | cut -f1)"
echo "════════════════════════════════════════"
echo ""
echo "To test in QEMU:"
echo "  qemu-system-x86_64 -m 4G -enable-kvm \\"
echo "    -cdrom $OUTPUT_DIR/kryos-os-1.0.iso \\"
echo "    -vga virtio -display gtk"
