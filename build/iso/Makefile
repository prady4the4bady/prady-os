# Prady OS — ISO Build Makefile
# Phase 38: Production ISO Build
#
# Usage:
#   make iso           Build the full Prady OS ISO (takes hours on first run)
#   make iso-fast      Build ISO, skip QEMU test
#   make clean         Remove output artifacts
#   make clean-all     Remove output + buildroot download cache
#   make test          Run ISO Python test suite (no build required)
#   make test-qemu     Boot the built ISO in QEMU (KVM)
#   make test-qemu-efi Boot the built ISO in QEMU with UEFI (needs ovmf)
#   make sha256        Print SHA256 of the built ISO
#   make write-usb     Write ISO to USB drive (USB=/dev/sdX)
#   make sign          Sign the ISO (SHA256 + optional GPG)
#   make deps-check    Verify all build tools are installed
#   make help          Show this help

.PHONY: iso iso-fast clean clean-all test test-qemu test-qemu-efi \
        sha256 write-usb sign deps-check help

SHELL      := /bin/bash
REPO_ROOT  := $(shell git rev-parse --show-toplevel 2>/dev/null || realpath ../..)
OUTPUT_DIR := $(REPO_ROOT)/output
ISO_PATH   := $(OUTPUT_DIR)/prady-os.iso
SCRIPTS    := $(CURDIR)/scripts
TESTS      := $(CURDIR)/tests
QEMU_MEM   := 4G
QEMU_SMP   := 4

##@ Build targets

iso: deps-check ## Build the complete Prady OS bootable ISO
	@echo "Starting Prady OS ISO build..."
	bash "$(SCRIPTS)/build_iso.sh"

iso-fast: deps-check ## Build ISO, skipping the QEMU boot test
	@echo "Starting Prady OS ISO build (no QEMU)..."
	bash "$(SCRIPTS)/build_iso.sh" --no-qemu

##@ Test targets

test: ## Run ISO Python test suite (no ISO build required — fast)
	@echo "Running ISO test suite..."
	python -m pytest "$(TESTS)/" -W error::DeprecationWarning -q

test-qemu: ## Boot the built ISO in QEMU with KVM (requires built ISO)
	@test -f "$(ISO_PATH)" || { echo "ERROR: ISO not found. Run 'make iso' first."; exit 1; }
	@echo "Launching Prady OS in QEMU (KVM)..."
	qemu-system-x86_64 \
		-cdrom "$(ISO_PATH)" \
		-m $(QEMU_MEM) \
		-smp $(QEMU_SMP) \
		-enable-kvm \
		-vga virtio \
		-display gtk \
		-boot d

test-qemu-efi: ## Boot in QEMU with UEFI firmware (requires ovmf package)
	@test -f "$(ISO_PATH)" || { echo "ERROR: ISO not found. Run 'make iso' first."; exit 1; }
	@test -f /usr/share/ovmf/OVMF.fd || { echo "Install OVMF: sudo apt install ovmf"; exit 1; }
	qemu-system-x86_64 \
		-cdrom "$(ISO_PATH)" \
		-bios /usr/share/ovmf/OVMF.fd \
		-m $(QEMU_MEM) \
		-smp $(QEMU_SMP) \
		-enable-kvm \
		-vga virtio \
		-display gtk \
		-boot d

##@ Utility targets

sha256: ## Print SHA256 checksum of the built ISO
	@test -f "$(ISO_PATH)" || { echo "ERROR: ISO not built. Run 'make iso'."; exit 1; }
	@sha256sum "$(ISO_PATH)"

sign: ## Sign the ISO with SHA256 and optional GPG signature
	bash "$(SCRIPTS)/sign_iso.sh" "$(ISO_PATH)"

write-usb: ## Write ISO to USB drive. Usage: make write-usb USB=/dev/sdX
	@test -n "$(USB)" || { \
		echo "Usage: make write-usb USB=/dev/sdX"; \
		echo "Run 'lsblk' to find your USB drive"; \
		exit 1; \
	}
	bash "$(SCRIPTS)/write_usb.sh" "$(ISO_PATH)" "$(USB)"

##@ Maintenance

clean: ## Remove build output artifacts
	@echo "Cleaning output directory..."
	rm -rf "$(OUTPUT_DIR)"
	@echo "Clean complete"

clean-all: clean ## Remove output AND buildroot download cache
	rm -rf "$(REPO_ROOT)/.buildroot"
	@echo "Full clean complete"

deps-check: ## Verify all required build tools are installed
	@echo "Checking build dependencies..."
	@MISSING=""; \
	for cmd in make wget tar xz rsync bc grub-mkrescue mksquashfs xorriso; do \
		command -v "$$cmd" >/dev/null 2>&1 || MISSING="$$MISSING $$cmd"; \
	done; \
	if [ -n "$$MISSING" ]; then \
		echo "Missing tools:$$MISSING"; \
		echo "Install: sudo apt install build-essential grub-pc-bin grub-efi-amd64-bin xorriso squashfs-tools wget bc rsync"; \
		echo "(Build will proceed — missing tools will cause a failure at the relevant step)"; \
	else \
		echo "All required build tools present"; \
	fi

##@ Help

help: ## Show this help message
	@awk 'BEGIN {FS = ":.*##"; printf "\n\033[1mPrady OS ISO Build\033[0m\n\nUsage: make \033[36m<target>\033[0m\n"} \
	/^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } \
	/^[a-zA-Z_-]+:.*##/ { printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)
	@echo ""
