# Building PradyOS from Source

## Prerequisites
- Ubuntu 22.04+ or Debian Bookworm (for live-build)
- 20GB free disk space
- 8GB RAM
- Internet connection (for package downloads)

## Quick Build
```bash
git clone https://github.com/pradyun/kryos-os
cd kryos-os
chmod +x scripts/build-iso.sh
./scripts/build-iso.sh
```

## Test in QEMU (no real hardware needed)
```bash
qemu-system-x86_64 -m 4G -enable-kvm \
  -cdrom dist/kryos-os-1.0.iso \
  -vga virtio -display gtk
```

## Architecture Overview
[diagram of all layers]
