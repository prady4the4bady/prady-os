# Kryos BIOS AI (Phase 34)

This folder contains Stage 1 of the BIOS AI Layer: a lightweight UEFI app that runs before GRUB.

## Stage 1 behavior

- Reads pre-OS hardware state (memory map, coarse hardware profile, secure boot state)
- Runs Phase 34 inference stub (heuristic classifier)
- Writes boot decision to EFI variable `KryosBootDecision`
- Prints decision to the UEFI console
- Never writes to the filesystem

Boot decisions:

- `NORMAL`
- `REPAIR`
- `SAFE`
- `RECOVERY`

## Build prerequisites

- EDK2 workspace
- Clang or GCC cross-compile toolchain
- OVMF for local VM testing

## Build steps (EDK2)

```bash
# from your edk2 workspace root
source edksetup.sh
build -a X64 -t CLANGPDB -p /path/to/prady-os/firmware/uefi-ai/KryosBiosAI.inf
```

## Run in QEMU/OVMF

```bash
qemu-system-x86_64 \
  -drive if=pflash,format=raw,readonly=on,file=OVMF_CODE.fd \
  -drive if=pflash,format=raw,file=OVMF_VARS.fd \
  -drive format=raw,file=fat:rw:/path/to/esp
```

Place `KryosBiosAI.efi` under `EFI/BOOT/` in the ESP and chain to GRUB from your boot manager.

## Phase note

- Phase 34: inference is heuristic-based in `ModelRunner.c`
- Phase 38: replace heuristic with a tiny Q4 GGML runtime for real pre-OS classification
