/* prax_agent_seccomp.bpf.c — Syscall allowlist for prax-agent process
 *
 * This program uses BPF_PROG_TYPE_TRACEPOINT to enforce an allowlist of syscalls.
 * Attempts to invoke denied syscalls result in SIGKILL (fail-closed).
 * Ring buffer events logged for denials.
 */

#include "vmlinux.h"
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_core_read.h>

#define ALLOWED_SYSCALL 1
#define DENIED_SYSCALL 0

/* Ring buffer for denial events */
struct {
    __uint(type, BPF_MAP_TYPE_RINGBUF);
    __uint(max_entries, 256 * 1024);
} denial_events SEC(".maps");

/* Map to track target PIDs (set by userspace) */
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 10);
    __type(key, u32);
    __type(value, u8);
} target_pids SEC(".maps");

struct event_t {
    u32 pid;
    u32 uid;
    u64 ts_ns;
    u32 syscall_nr;
    char comm[16];
};

/* Allowlist: syscalls permitted for prax-agent */
static __always_inline int is_syscall_allowed(u32 nr) {
    switch (nr) {
        /* File I/O */
        case 0:   /* read */
        case 1:   /* write */
        case 257: /* openat */
        case 3:   /* close */
        case 8:   /* lseek */
        case 217: /* getdents64 */
        case 5:   /* stat (old) */
        case 6:   /* fstat (old) */
        case 21:  /* access */
        case 268: /* newfstatat */
        case 79:  /* getcwd */
        
        /* Memory management */
        case 9:   /* link */
        case 10:  /* unlink */
        case 11:  /* execve (controlled) */
        case 12:  /* chdir */
        case 33:  /* access */
        case 45:  /* brk */
        case 9:   /* mmap (old) */
        case 9:   /* mmap2 (old) */
        case 222: /* mmap */
        case 10:  /* mprotect */
        
        /* Process control */
        case 231: /* exit_group */
        case 60:  /* exit */
        case 39:  /* getpid */
        case 110: /* getppid */
        case 186: /* gettid */
        case 14:  /* getuid */
        case 16:  /* getgid */
        
        /* Signals & synchronization */
        case 13:  /* rt_sigaction */
        case 14:  /* rt_sigprocmask */
        case 202: /* futex */
        case 288: /* futex_waitv */
        
        /* Network (limited) */
        case 288: /* accept4 */
        case 42:  /* connect */
        case 44:  /* sendmsg */
        case 47:  /* recvmsg */
        
        /* Timers */
        case 228: /* clock_gettime */
        case 96:  /* gettimeofday */
        
        /* File descriptor operations */
        case 72:  /* fcntl */
        case 73:  /* ioctl */
        case 19:  /* lseek */
        
        /* epoll (async I/O) */
        case 19:  /* epoll_wait */
        case 233: /* epoll_ctl */
        case 256: /* epoll_create1 */
            return ALLOWED_SYSCALL;
        
        default:
            return DENIED_SYSCALL;
    }
}

/* Tracepoint: sys_enter for all syscalls */
SEC("tracepoint/raw_syscalls/sys_enter")
int trace_sys_enter(struct trace_event_raw_sys_enter *ctx) {
    u64 uid_gid = bpf_get_current_uid_gid();
    u32 uid = uid_gid & 0xFFFFFFFF;
    u32 pid = bpf_get_current_pid_tgid() & 0xFFFFFFFF;
    
    /* Check if this PID is in target set */
    u8 *is_target = bpf_map_lookup_elem(&target_pids, &pid);
    if (!is_target)
        return 0; /* Not a target; allow all */
    
    u32 syscall_nr = ctx->id;
    
    if (!is_syscall_allowed(syscall_nr)) {
        /* Log denial event */
        struct event_t *event = bpf_ringbuf_reserve(&denial_events, sizeof(*event), 0);
        if (event) {
            event->pid = pid;
            event->uid = uid;
            event->ts_ns = bpf_ktime_get_ns();
            event->syscall_nr = syscall_nr;
            bpf_get_current_comm(&event->comm, sizeof(event->comm));
            bpf_ringbuf_submit(event, 0);
        }
        
        /* Send SIGKILL to the process */
        bpf_send_signal(9); /* SIGKILL */
    }
    
    return 0;
}

char LICENSE[] SEC("license") = "GPL";
__u32 _version SEC("version") = 1;
