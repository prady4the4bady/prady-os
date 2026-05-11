#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ISO_WORK_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${ISO_WORK_DIR}/../.." && pwd)"
ROOTFS="${ISO_WORK_DIR}/rootfs"
ISO_ROOT="${ISO_WORK_DIR}/iso"
LIVE_DIR="${ISO_ROOT}/live"
OUTPUT_ISO="${REPO_ROOT}/build/prady-os.iso"
EFI_IMG="${ISO_WORK_DIR}/efiboot.img"

if [[ "${EUID}" -ne 0 ]]; then
  echo "[03-build-iso] Please run as root (sudo)."
  exit 1
fi

mkdir -p "${REPO_ROOT}/build"

"${SCRIPT_DIR}/01-bootstrap.sh"
"${SCRIPT_DIR}/02-install-kryos.sh"

echo "[03-build-iso] Building initramfs in chroot"
chroot "${ROOTFS}" /bin/bash -lc 'set -e; update-initramfs -c -k all'

rm -rf "${ISO_ROOT}"
mkdir -p "${LIVE_DIR}" "${ISO_ROOT}/boot/grub" "${ISO_ROOT}/EFI/BOOT"

KERNEL_PATH="$(ls -1 "${ROOTFS}"/boot/vmlinuz-* | tail -n1)"
INITRD_PATH="$(ls -1 "${ROOTFS}"/boot/initrd.img-* | tail -n1)"
cp "${KERNEL_PATH}" "${ISO_ROOT}/vmlinuz"
cp "${INITRD_PATH}" "${ISO_ROOT}/initrd.img"

if [[ -f "${ISO_WORK_DIR}/grub/wallpaper.png" ]]; then
  cp "${ISO_WORK_DIR}/grub/wallpaper.png" "${ISO_ROOT}/boot/grub/wallpaper.png"
elif [[ -f "${REPO_ROOT}/compositor/hyprland-base/assets/install/wall0.png" ]]; then
  cp "${REPO_ROOT}/compositor/hyprland-base/assets/install/wall0.png" "${ISO_ROOT}/boot/grub/wallpaper.png"
fi

cp "${ISO_WORK_DIR}/grub/grub.cfg" "${ISO_ROOT}/boot/grub/grub.cfg"

echo "[03-build-iso] Packing squashfs"
mksquashfs "${ROOTFS}" "${LIVE_DIR}/filesystem.squashfs" -comp xz -b 1M -Xdict-size 100% -noappend
(
  cd "${LIVE_DIR}"
  md5sum filesystem.squashfs > filesystem.md5
)

echo "[03-build-iso] Preparing BIOS/UEFI boot images"
BIOS_IMG_SRC="/usr/lib/grub/i386-pc/eltorito.img"
if [[ ! -f "${BIOS_IMG_SRC}" ]]; then
  echo "[03-build-iso] Missing ${BIOS_IMG_SRC}. Install grub-pc-bin."
  exit 1
fi
cp "${BIOS_IMG_SRC}" "${ISO_ROOT}/boot/grub/bios.img"

if [[ ! -f "${EFI_IMG}" ]]; then
  dd if=/dev/zero of="${EFI_IMG}" bs=1M count=20
  mkfs.vfat "${EFI_IMG}"
fi

mkdir -p /tmp/kryos-efi/EFI/BOOT
if command -v grub-mkstandalone >/dev/null 2>&1; then
  grub-mkstandalone -O x86_64-efi -o /tmp/kryos-efi/EFI/BOOT/BOOTX64.EFI \
    "boot/grub/grub.cfg=${ISO_WORK_DIR}/grub/grub.cfg"
else
  echo "[03-build-iso] grub-mkstandalone not found"
  exit 1
fi

mmd -i "${EFI_IMG}" ::/EFI ::/EFI/BOOT || true
mcopy -o -i "${EFI_IMG}" /tmp/kryos-efi/EFI/BOOT/BOOTX64.EFI ::/EFI/BOOT/
cp "${EFI_IMG}" "${ISO_ROOT}/EFI/efiboot.img"

echo "[03-build-iso] Assembling ISO via xorriso"
xorriso -as mkisofs \
  -iso-level 3 \
  -full-iso9660-filenames \
  -volid "PradyOS" \
  -eltorito-boot boot/grub/bios.img \
  -no-emul-boot -boot-load-size 4 -boot-info-table \
  --eltorito-catalog boot/grub/boot.cat \
  --grub2-boot-info \
  --grub2-mbr /usr/lib/grub/i386-pc/boot_hybrid.img \
  -eltorito-alt-boot \
  -e EFI/efiboot.img \
  -no-emul-boot \
  -append_partition 2 0xef "${EFI_IMG}" \
  -output "${OUTPUT_ISO}" \
  "${ISO_ROOT}"

SIZE_MB="$(du -m "${OUTPUT_ISO}" | awk '{print $1}')"
echo "[03-build-iso] Done: ${OUTPUT_ISO} (${SIZE_MB} MB)"
