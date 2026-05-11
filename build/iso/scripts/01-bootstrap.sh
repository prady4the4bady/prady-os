#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ISO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${ISO_DIR}/../.." && pwd)"
ROOTFS="${ISO_DIR}/rootfs"

if [[ "${EUID}" -ne 0 ]]; then
  echo "[01-bootstrap] Please run as root (sudo)."
  exit 1
fi

if ! command -v debootstrap >/dev/null 2>&1; then
  apt-get update
  apt-get install -y debootstrap squashfs-tools xorriso grub-pc-bin grub-efi-amd64-bin mtools dosfstools
fi

mkdir -p "${ROOTFS}"

if [[ ! -f "${ROOTFS}/etc/debian_version" ]]; then
  echo "[01-bootstrap] Bootstrapping Debian Bookworm into ${ROOTFS}"
  debootstrap --arch=amd64 bookworm "${ROOTFS}" http://deb.debian.org/debian
else
  echo "[01-bootstrap] Existing rootfs detected, reusing ${ROOTFS}"
fi

cp /etc/resolv.conf "${ROOTFS}/etc/resolv.conf"

cat > "${ROOTFS}/tmp/bootstrap-install.sh" <<'CHROOT'
#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y --no-install-recommends \
  linux-image-amd64 grub-efi-amd64 systemd systemd-sysv \
  network-manager curl wget git python3 python3-pip python3-venv \
  xorg openbox lightdm lightdm-gtk-greeter chromium \
  pulseaudio alsa-utils \
  docker.io docker-compose nodejs npm \
  locales tzdata ca-certificates rsync live-boot initramfs-tools

sed -i 's/^# *en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen
locale-gen en_US.UTF-8
update-locale LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8
ln -sf /usr/share/zoneinfo/UTC /etc/localtime
echo UTC > /etc/timezone

echo kryos-os > /etc/hostname

cat > /etc/fstab <<'FSTAB'
tmpfs / tmpfs defaults 0 0
tmpfs /tmp tmpfs nosuid,nodev 0 0
FSTAB

systemctl enable NetworkManager.service
CHROOT

chmod +x "${ROOTFS}/tmp/bootstrap-install.sh"
chroot "${ROOTFS}" /bin/bash /tmp/bootstrap-install.sh
rm -f "${ROOTFS}/tmp/bootstrap-install.sh"

echo "[01-bootstrap] Done."