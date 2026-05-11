# Makefile for eBPF programs
# Compile with clang targeting BPF ISA, use CO-RE (Compile Once - Run Everywhere)

LLVM_CONFIG ?= llvm-config
ARCH ?= x86
KERNELDIR ?= /usr/src/linux

CLANG ?= clang
STRIP ?= llvm-strip
BPFTOOL ?= bpftool

VMLINUX_BTF ?= /sys/kernel/btf/vmlinux
VMLINUX_H ?= vmlinux.h

INCLUDES ?= -I$(shell $(LLVM_CONFIG) --includedir) -I/usr/include/bpf
CFLAGS ?= -O2 -target bpf -D__TARGET_ARCH_$(ARCH) -D__KERNEL__ -D__BPF_CORE__
LDFLAGS ?= -lelf -lz

TARGETS := prady_agent_seccomp.bpf.o computer_use_lsm.bpf.o audit_syscalls.bpf.o

all: $(TARGETS)

%.bpf.o: %.bpf.c
	$(CLANG) $(INCLUDES) $(CFLAGS) -c $< -o $@

clean:
	rm -f *.o *.ll

.PHONY: all clean
