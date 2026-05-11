"""sandboxing.py — Metadata-only sandbox profile generation for Kryos services.

This module generates seccomp and Landlock policy metadata. In development mode
these are metadata-only structures (no kernel enforcement). Phase 29+ will wire
these profiles to actual kernel interfaces (seccomp bpf, Landlock LSM).
"""
from __future__ import annotations

from typing import Any

# Default minimum syscall set for a Python FastAPI/uvicorn microservice.
_DEFAULT_ALLOWED_SYSCALLS: list[str] = [
    "read", "write", "open", "openat", "close", "fstat", "lstat", "stat",
    "mmap", "mprotect", "munmap", "brk", "rt_sigaction", "rt_sigprocmask",
    "ioctl", "access", "pipe", "select", "sched_yield", "mremap", "madvise",
    "shmget", "shmat", "shmctl", "dup", "dup2", "nanosleep", "getpid",
    "sendfile", "socket", "connect", "accept", "sendto", "recvfrom",
    "sendmsg", "recvmsg", "bind", "listen", "getsockname", "getpeername",
    "socketpair", "setsockopt", "getsockopt", "clone", "fork", "execve",
    "exit", "wait4", "kill", "uname", "fcntl", "flock", "fsync",
    "getdents", "getcwd", "chdir", "rename", "mkdir", "rmdir", "unlink",
    "readlink", "chmod", "fchmod", "chown", "fchown", "umask", "gettimeofday",
    "getrlimit", "getrusage", "sysinfo", "times", "ptrace", "getuid", "syslog",
    "getgid", "setuid", "setgid", "geteuid", "getegid", "setpgid", "getppid",
    "getpgrp", "setsid", "setreuid", "setregid", "getgroups", "setgroups",
    "setresuid", "getresuid", "setresgid", "getresgid", "getpgid", "setfsuid",
    "setfsgid", "getsid", "capget", "capset", "rt_sigsuspend", "sigaltstack",
    "utime", "mknod", "uselib", "personality", "ustat", "statfs", "fstatfs",
    "sysfs", "getpriority", "setpriority", "sched_setparam", "sched_getparam",
    "sched_setscheduler", "sched_getscheduler", "sched_get_priority_max",
    "sched_get_priority_min", "sched_rr_get_interval", "mlock", "munlock",
    "mlockall", "munlockall", "vhangup", "modify_ldt", "pivot_root",
    "prctl", "arch_prctl", "adjtimex", "setrlimit", "chroot", "sync",
    "acct", "settimeofday", "mount", "umount2", "swapon", "swapoff",
    "reboot", "sethostname", "setdomainname", "iopl", "ioperm",
    "init_module", "delete_module", "quotactl", "nfsservctl",
    "gettid", "readahead", "setxattr", "lsetxattr", "fsetxattr",
    "getxattr", "lgetxattr", "fgetxattr", "listxattr", "llistxattr",
    "flistxattr", "removexattr", "lremovexattr", "fremovexattr",
    "tkill", "time", "futex", "sched_setaffinity", "sched_getaffinity",
    "set_thread_area", "io_setup", "io_destroy", "io_getevents",
    "io_submit", "io_cancel", "get_thread_area", "lookup_dcookie",
    "epoll_create", "epoll_ctl", "epoll_wait", "remap_file_pages",
    "set_tid_address", "semtimedop", "fadvise64", "timer_create",
    "timer_settime", "timer_gettime", "timer_getoverrun", "timer_delete",
    "clock_settime", "clock_gettime", "clock_getres", "clock_nanosleep",
    "exit_group", "epoll_wait", "tgkill", "utimes", "vserver", "mbind",
    "set_mempolicy", "get_mempolicy", "mq_open", "mq_unlink",
    "mq_timedsend", "mq_timedreceive", "mq_notify", "mq_getsetattr",
    "kexec_load", "waitid", "add_key", "request_key", "keyctl",
    "ioprio_set", "ioprio_get", "inotify_init", "inotify_add_watch",
    "inotify_rm_watch", "migrate_pages", "openat", "mkdirat", "mknodat",
    "fchownat", "futimesat", "newfstatat", "unlinkat", "renameat",
    "linkat", "symlinkat", "readlinkat", "fchmodat", "faccessat",
    "pselect6", "ppoll", "unshare", "set_robust_list", "get_robust_list",
    "splice", "tee", "sync_file_range", "vmsplice", "move_pages",
    "utimensat", "epoll_pwait", "signalfd", "timerfd_create",
    "eventfd", "fallocate", "timerfd_settime", "timerfd_gettime",
    "accept4", "signalfd4", "eventfd2", "epoll_create1", "dup3",
    "pipe2", "inotify_init1", "preadv", "pwritev", "rt_tgsigqueueinfo",
    "perf_event_open", "recvmmsg", "fanotify_init", "fanotify_mark",
    "prlimit64", "name_to_handle_at", "open_by_handle_at", "clock_adjtime",
    "syncfs", "sendmmsg", "setns", "getcpu", "process_vm_readv",
    "process_vm_writev", "kcmp", "finit_module", "sched_setattr",
    "sched_getattr", "renameat2", "seccomp", "getrandom", "memfd_create",
    "kexec_file_load", "bpf", "execveat", "userfaultfd", "membarrier",
    "mlock2", "copy_file_range", "preadv2", "pwritev2", "pkey_mprotect",
    "pkey_alloc", "pkey_free", "statx", "io_pgetevents", "rseq",
]


def generate_seccomp_profile(
    service_name: str,
    allowed_syscalls: list[str] | None = None,
) -> dict[str, Any]:
    """Generate a seccomp profile metadata dict for a named service.

    The returned dict describes the intended seccomp BPF policy but does NOT
    attach it to any process. Phase 29+ will feed this into the kernel via
    prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, ...).

    Args:
        service_name: Logical name of the service (e.g. "package-manager").
        allowed_syscalls: Explicit allowlist. Defaults to _DEFAULT_ALLOWED_SYSCALLS.

    Returns:
        A dict with keys: service_name, defaultAction, syscalls, metadata_only.
    """
    syscalls = allowed_syscalls if allowed_syscalls is not None else _DEFAULT_ALLOWED_SYSCALLS
    return {
        "service_name": service_name,
        "defaultAction": "SCMP_ACT_ERRNO",
        "syscalls": [
            {
                "names": syscalls,
                "action": "SCMP_ACT_ALLOW",
            }
        ],
        "metadata_only": True,
        "note": "Phase 29+ will attach this profile via prctl(PR_SET_SECCOMP).",
    }


def generate_landlock_policy(
    service_name: str,
    read_paths: list[str],
    write_paths: list[str],
) -> dict[str, Any]:
    """Generate a Landlock filesystem policy metadata dict for a named service.

    The returned dict describes the intended Landlock ruleset but does NOT
    activate it. Phase 29+ will materialise this via landlock_create_ruleset(2)
    and landlock_add_rule(2).

    Args:
        service_name: Logical name of the service (e.g. "watchdog").
        read_paths: Filesystem paths the service needs read access to.
        write_paths: Filesystem paths the service needs write access to.

    Returns:
        A dict with keys: service_name, read_paths, write_paths, metadata_only.
    """
    return {
        "service_name": service_name,
        "read_paths": read_paths,
        "write_paths": write_paths,
        "deny": ["execute"],
        "metadata_only": True,
        "note": "Phase 29+ will activate this via landlock_create_ruleset(2).",
    }
