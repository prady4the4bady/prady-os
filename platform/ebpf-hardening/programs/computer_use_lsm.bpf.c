/* computer_use_lsm.bpf.c — LSM hooks for computer-use service
 *
 * Uses BPF_LSM to enforce access control on file operations and socket operations.
 * Allows: /dev/input/*, /dev/uinput (keyboard/mouse)
 * Allows: X11 sockets, Wayland sockets
 * Denies: Raw packet sockets (AF_PACKET)
 * Denies: Netlink route manipulation
 * Denies: /proc/*/mem access (cross-process memory read)
 */

#include "vmlinux.h"
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_core_read.h>

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
    char operation[32];
    char path[256];
    u64 ts_ns;
};

static __always_inline int str_starts_with(const char *str, const char *prefix, size_t max_len) {
    #pragma unroll
    for (int i = 0; i < 16 && i < max_len; i++) {
        if (prefix[i] == '\0') return 1;
        if (str[i] != prefix[i]) return 0;
    }
    return 1;
}

static __always_inline int is_allowed_device_path(const char *path) {
    /* Allow /dev/input/* */
    if (str_starts_with(path, "/dev/input", 10)) return 1;
    
    /* Allow /dev/uinput */
    if (str_starts_with(path, "/dev/uinput", 11)) return 1;
    
    /* Allow /tmp/.X11-unix/* */
    if (str_starts_with(path, "/tmp/.X11-unix", 14)) return 1;
    
    /* Allow /run/user/*/wayland-* (Wayland sockets) */
    if (str_starts_with(path, "/run/user", 9)) return 1;
    
    return 0;
}

/* LSM hook: open file */
SEC("lsm/file_open")
int BPF_PROG(lsm_file_open, struct file *file) {
    u32 pid = bpf_get_current_pid_tgid() & 0xFFFFFFFF;
    
    u8 *is_target = bpf_map_lookup_elem(&target_pids, &pid);
    if (!is_target)
        return 0; /* Not a target; allow all */
    
    struct dentry *dentry = file->f_path.dentry;
    struct qstr d_name;
    
    BPF_CORE_READ_INTO(&d_name, dentry, d_name);
    
    /* Deny /proc/*/mem access */
    if (d_name.len == 3) {
        char name[4];
        bpf_probe_read_kernel_str(name, sizeof(name), d_name.name);
        if (name[0] == 'm' && name[1] == 'e' && name[2] == 'm') {
            struct event_t *event = bpf_ringbuf_reserve(&denial_events, sizeof(*event), 0);
            if (event) {
                event->pid = pid;
                event->ts_ns = bpf_ktime_get_ns();
                bpf_probe_read_kernel_str(event->operation, sizeof(event->operation), "/proc/mem");
                bpf_probe_read_kernel_str(event->path, sizeof(event->path), d_name.name);
                bpf_ringbuf_submit(event, 0);
            }
            return -12; /* -ENOMEM or similar; userspace turns this to -EPERM */
        }
    }
    
    return 0;
}

/* LSM hook: socket creation */
SEC("lsm/socket_create")
int BPF_PROG(lsm_socket_create, int family, int type, int protocol) {
    u32 pid = bpf_get_current_pid_tgid() & 0xFFFFFFFF;
    
    u8 *is_target = bpf_map_lookup_elem(&target_pids, &pid);
    if (!is_target)
        return 0;
    
    /* Deny AF_PACKET (raw sockets) */
    if (family == 17) { /* AF_PACKET */
        struct event_t *event = bpf_ringbuf_reserve(&denial_events, sizeof(*event), 0);
        if (event) {
            event->pid = pid;
            event->ts_ns = bpf_ktime_get_ns();
            bpf_probe_read_kernel_str(event->operation, sizeof(event->operation), "socket_create");
            bpf_probe_read_kernel_str(event->path, sizeof(event->path), "AF_PACKET");
            bpf_ringbuf_submit(event, 0);
        }
        return -1; /* -EPERM */
    }
    
    /* Deny AF_NETLINK with NETLINK_ROUTE */
    if (family == 16 && protocol == 0) { /* AF_NETLINK, NETLINK_ROUTE */
        struct event_t *event = bpf_ringbuf_reserve(&denial_events, sizeof(*event), 0);
        if (event) {
            event->pid = pid;
            event->ts_ns = bpf_ktime_get_ns();
            bpf_probe_read_kernel_str(event->operation, sizeof(event->operation), "socket_create");
            bpf_probe_read_kernel_str(event->path, sizeof(event->path), "NETLINK_ROUTE");
            bpf_ringbuf_submit(event, 0);
        }
        return -1; /* -EPERM */
    }
    
    return 0;
}

char LICENSE[] SEC("license") = "GPL";
__u32 _version SEC("version") = 1;
