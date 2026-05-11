#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
ISO_PATH="${REPO_ROOT}/build/prady-os.iso"

if [[ ! -f "${ISO_PATH}" ]]; then
  echo "[04-test-qemu] ISO not found: ${ISO_PATH}"
  echo "Build first with: make -C build iso"
  exit 1
fi

KVM_FLAG=""
if [[ -e /dev/kvm ]]; then
  KVM_FLAG="-enable-kvm"
fi

echo "[04-test-qemu] Launching QEMU"
echo "Press Ctrl+Alt+G to release mouse from QEMU"

qemu-system-x86_64 \
  -m 4096 \
  -smp 4 \
  -cdrom "${ISO_PATH}" \
  -boot d \
  -vga virtio \
  -display sdl \
  -net nic -net user \
  ${KVM_FLAG}
