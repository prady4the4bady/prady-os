SHELL := /bin/bash

BLUE := \033[1;34m
GREEN := \033[1;32m
YELLOW := \033[1;33m
RESET := \033[0m

ISO_DIR := $(CURDIR)/iso

.PHONY: all iso test clean

iso:
	@echo -e "$(BLUE)[build] Starting ISO pipeline...$(RESET)"
	@bash "$(ISO_DIR)/scripts/01-bootstrap.sh"
	@bash "$(ISO_DIR)/scripts/02-install-prady.sh"
	@bash "$(ISO_DIR)/scripts/03-build-iso.sh"
	@echo -e "$(GREEN)[build] ISO build complete.$(RESET)"

test:
	@echo -e "$(BLUE)[build] Launching QEMU test...$(RESET)"
	@bash "$(ISO_DIR)/scripts/04-test-qemu.sh"
	@echo -e "$(GREEN)[build] QEMU session finished.$(RESET)"

clean:
	@echo -e "$(YELLOW)[build] Cleaning generated ISO artifacts...$(RESET)"
	@rm -rf "$(ISO_DIR)/rootfs" "$(ISO_DIR)/iso" "$(ISO_DIR)/efiboot.img" "$(CURDIR)/prady-os-v2.iso"
	@echo -e "$(GREEN)[build] Clean complete.$(RESET)"

all: iso test
