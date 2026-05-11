/* audit_syscalls.bpf.c — Comprehensive syscall audit logger
 *
 * Attaches to sys_enter_* tracepoints for processes in kryos cgroup.
 * Logs all syscalls (allowed and denied) to ring buffer.
 * Userspace daemon reads and sends batches to audit-log service.
 */

#include "vmlinux.h"
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_core_read.h>

/* Ring buffer for syscall events */
struct {
    __uint(type, BPF_MAP_TYPE_RINGBUF);
    __uint(max_entries, 512 * 1024);
} syscall_events SEC(".maps");

/* Map to track monitored cgroups */
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 16);
    __type(key, u64);
    __type(value, u8);
} monitored_cgroups SEC(".maps");

struct syscall_event_t {
    u32 pid;
    u32 tgid;
    u64 uid_gid;
    u32 syscall_nr;
    u64 arg1;
    u64 arg2;
    u64 arg3;
    u64 arg4;
    u64 ts_ns;
    char comm[16];
    u8 denied;
};

/* Tracepoint: sys_enter for all syscalls */
SEC("tracepoint/raw_syscalls/sys_enter")
int trace_sys_enter(struct trace_event_raw_sys_enter *ctx) {
    u64 uid_gid = bpf_get_current_uid_gid();
    u32 pid = bpf_get_current_pid_tgid() & 0xFFFFFFFF;
    u32 tgid = bpf_get_current_pid_tgid() >> 32;
    
    /* Check if this cgroup is monitored (optional) */
    u64 cgroup_id = bpf_get_current_cgroup_id();
    u8 *is_monitored = bpf_map_lookup_elem(&monitored_cgroups, &cgroup_id);
    if (!is_monitored && cgroup_id != 0)
        return 0; /* Not in monitored cgroup; skip */
    
    struct syscall_event_t *event = bpf_ringbuf_reserve(&syscall_events, sizeof(*event), 0);
    if (!event)
        return 0;
    
    event->pid = pid;
    event->tgid = tgid;
    event->uid_gid = uid_gid;
    event->syscall_nr = ctx->id;
    event->arg1 = ctx->args[0];
    event->arg2 = ctx->args[1];
    event->arg3 = ctx->args[2];
    event->arg4 = ctx->args[3];
    event->ts_ns = bpf_ktime_get_ns();
    event->denied = 0;
    bpf_get_current_comm(&event->comm, sizeof(event->comm));
    
    bpf_ringbuf_submit(event, 0);
    
    return 0;
}

char LICENSE[] SEC("license") = "GPL";
__u32 _version SEC("version") = 1;
